import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import logging
import psutil
import subprocess

# Import your existing modules
from gwt import process_json
from github_update import push_to_github, set_github_credentials, is_github_configured, validate_github_connection

# Load environment variables
load_dotenv()

# Configure logging with more detailed format
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Conversation states for setup
GITHUB_TOKEN, GITHUB_REPO = range(2)

class EnhancedTokenBot:
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID")  # Admin ke liye notification
        self.account_files = ["accounts1.json", "accounts2.json", "accounts3.json"]
        self.current_file_index = 0
        
        # Enhanced tracking
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self.last_run = None
        self.next_run = None
        self.last_github_update = None
        self.scheduler_running = False
        self.application = None
        self.total_successful_cycles = 0
        self.total_failed_cycles = 0
        self.bot_start_time = datetime.now(timezone.utc)
        
        # Auto-restart settings
        self.auto_restart_enabled = True
        self.max_retry_attempts = 3
        
        # GitHub setup flag
        self.github_setup_complete = False
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must be set in .env file")
    
    async def send_admin_notification(self, message, is_error=False):
        """Send notification to admin"""
        if self.admin_chat_id and self.application:
            try:
                emoji = "🚨" if is_error else "✅"
                await self.application.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=f"{emoji} **Admin Notification**\n\n{message}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")
    
    async def process_cycle(self, manual=False):
        """Enhanced process cycle with better error handling"""
        try:
            # Check if GitHub is configured
            if not is_github_configured():
                error_msg = "❌ GitHub not configured. Use /setup command first."
                logger.error(error_msg)
                await self.send_admin_notification(error_msg, is_error=True)
                return error_msg
            
            current_file = self.account_files[self.current_file_index]
            start_time = datetime.now(timezone.utc)
            
            logger.info(f"Starting cycle: {current_file} ({'Manual' if manual else 'Auto'})")
            
            # Check if file exists
            if not os.path.exists(current_file):
                error_msg = f"❌ File {current_file} not found"
                logger.error(error_msg)
                await self.send_admin_notification(f"File Error: {current_file} missing", is_error=True)
                self.total_failed_cycles += 1
                return error_msg
            
            # Check file size and validity
            with open(current_file, 'r') as f:
                try:
                    data = json.load(f)
                    if not data:
                        raise ValueError("Empty file")
                except json.JSONDecodeError:
                    error_msg = f"❌ Invalid JSON format in {current_file}"
                    logger.error(error_msg)
                    await self.send_admin_notification(f"JSON Error: {current_file} has invalid format", is_error=True)
                    self.total_failed_cycles += 1
                    return error_msg
            
            # Process JSON using gwt.py
            logger.info(f"Processing tokens from {current_file}")
            process_json(current_file)
            
            # Verify token_ind.json was created
            if not os.path.exists("token_ind.json"):
                error_msg = "❌ token_ind.json was not created"
                logger.error(error_msg)
                await self.send_admin_notification("Token Generation Failed: token_ind.json not created", is_error=True)
                self.total_failed_cycles += 1
                return error_msg
            
            # Check token count
            with open("token_ind.json", 'r') as f:
                tokens = json.load(f)
                token_count = len(tokens)
            
            # Push to GitHub with retry mechanism
            github_result = None
            for attempt in range(self.max_retry_attempts):
                try:
                    github_result = push_to_github()
                    break
                except Exception as e:
                    if attempt == self.max_retry_attempts - 1:
                        raise e
                    logger.warning(f"GitHub push attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(2)
            
            # Update tracking variables
            self.last_run = datetime.now(timezone.utc)
            self.last_github_update = datetime.now(timezone.utc)
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            # Move to next file for next cycle
            self.current_file_index = (self.current_file_index + 1) % len(self.account_files)
            self.total_successful_cycles += 1
            
            success_msg = f"""✅ **Cycle Completed Successfully**
📁 File: {current_file}
🎯 Tokens Generated: {token_count}
⏱️ Processing Time: {processing_time:.2f}s
🚀 GitHub: Updated
📊 Total Success: {self.total_successful_cycles}"""
            
            logger.info(f"Cycle completed: {current_file} -> {token_count} tokens")
            
            # Send admin notification for successful cycle
            await self.send_admin_notification(success_msg)
            
            return success_msg
            
        except Exception as e:
            self.total_failed_cycles += 1
            error_msg = f"❌ **Cycle Failed**\nFile: {current_file}\nError: {str(e)}\nTotal Failures: {self.total_failed_cycles}"
            logger.error(f"Cycle failed: {e}")
            await self.send_admin_notification(error_msg, is_error=True)
            
            # Auto-restart on failure if enabled
            if self.auto_restart_enabled and not manual:
                await self.auto_recovery()
            
            return error_msg
    
    async def auto_recovery(self):
        """Automatic recovery mechanism"""
        try:
            logger.info("Attempting auto-recovery...")
            await self.send_admin_notification("🔧 Auto-recovery initiated", is_error=True)
            
            # Wait before retry
            await asyncio.sleep(30)
            
            # Try next file in sequence
            self.current_file_index = (self.current_file_index + 1) % len(self.account_files)
            result = await self.process_cycle()
            
            if "✅" in result:
                await self.send_admin_notification("🎉 Auto-recovery successful!")
            
        except Exception as e:
            logger.error(f"Auto-recovery failed: {e}")
            await self.send_admin_notification(f"❌ Auto-recovery failed: {str(e)}", is_error=True)
    
    def start_scheduler(self, interval_hours=8):
        """Enhanced scheduler with custom intervals"""
        if not is_github_configured():
            return "❌ GitHub not configured. Use /setup command first."
        
        if not self.scheduler_running:
            # Remove existing job if any
            if self.scheduler.get_job('token_cycle'):
                self.scheduler.remove_job('token_cycle')
            
            self.scheduler.add_job(
                lambda: asyncio.create_task(self.process_cycle()),
                trigger=IntervalTrigger(hours=interval_hours),
                id='token_cycle',
                replace_existing=True
            )
            
            if not self.scheduler.running:
                self.scheduler.start()
            
            self.scheduler_running = True
            self.next_run = datetime.now(timezone.utc) + timedelta(hours=interval_hours)
            
            logger.info(f"Scheduler started - {interval_hours}-hour cycle activated")
            return f"✅ Scheduler started with {interval_hours}h interval"
    
    async def stop_scheduler(self):
        """Enhanced stop with confirmation"""
        if self.scheduler_running:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            self.scheduler_running = False
            self.next_run = None
            logger.info("Scheduler stopped")
            await self.send_admin_notification("ℹ️ Scheduler stopped by user")
            return "ℹ️ Scheduler stopped successfully"
        return "⚠️ Scheduler is already stopped"
    
    async def get_system_stats(self):
        """Get system statistics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            uptime = datetime.now(timezone.utc) - self.bot_start_time
            
            return {
                'cpu': cpu_percent,
                'memory_used': memory.percent,
                'disk_used': disk.percent,
                'uptime': str(uptime).split('.')[0]  # Remove microseconds
            }
        except:
            return None
    
    # ==================== SETUP COMMANDS ====================
    
    async def setup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start GitHub setup conversation"""
        if is_github_configured():
            keyboard = [
                [InlineKeyboardButton("🔄 Reconfigure", callback_data="reconfigure_github")],
                [InlineKeyboardButton("✅ Test Connection", callback_data="test_github")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_msg = f"""🎉 **Welcome to Enhanced Token Bot**

🤖 **Bot Status**: {'🟢 Active' if self.scheduler_running else '🔴 Inactive'}
🔧 **GitHub**: {github_status}
📁 **Next File**: {self.account_files[self.current_file_index]}
📄 **Auto Cycle**: Every 8 hours
📊 **Success Rate**: {self.total_successful_cycles}/{self.total_successful_cycles + self.total_failed_cycles} cycles

{'⚠️ Please setup GitHub first using the button below.' if not is_github_configured() else 'Use buttons below or type /help for commands.'}"""

        await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def run_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced run command with progress indicator"""
        if not is_github_configured():
            await update.message.reply_text(
                "❌ **GitHub not configured**\n\nUse /setup command first to configure GitHub credentials.",
                parse_mode='Markdown'
            )
            return
        
        await update.message.reply_text("🔄 **Processing next file...**\n⏳ Please wait...", parse_mode='Markdown')
        
        result = await self.process_cycle(manual=True)
        
        # Create inline keyboard for post-run actions
        keyboard = [
            [InlineKeyboardButton("📊 View Status", callback_data="status")],
            [InlineKeyboardButton("📈 Statistics", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(result, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced status with system info"""
        current_file = self.account_files[self.current_file_index]
        uptime = datetime.now(timezone.utc) - self.bot_start_time
        success_rate = (self.total_successful_cycles / max(1, self.total_successful_cycles + self.total_failed_cycles)) * 100
        
        # Get system stats
        sys_stats = await self.get_system_stats()
        
        github_status = "✅ Configured" if is_github_configured() else "❌ Not Configured"
        
        status_msg = f"""📊 **Enhanced Bot Status**

🔧 **GitHub**: {github_status}
🔄 **Scheduler**: {'🟢 Running' if self.scheduler_running else '🔴 Stopped'}
📁 **Next File**: `{current_file}`
⏰ **Last Run**: {self.last_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.last_run else 'Never'}
⏰ **Next Run**: {self.next_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.next_run else 'Not scheduled'}
🚀 **Last GitHub**: {self.last_github_update.strftime('%Y-%m-%d %H:%M:%S UTC') if self.last_github_update else 'Never'}

📈 **Statistics**
✅ Successful: {self.total_successful_cycles}
❌ Failed: {self.total_failed_cycles}
📊 Success Rate: {success_rate:.1f}%
⏱️ Uptime: {str(uptime).split('.')[0]}

📋 **Files Cycle**: {' → '.join(self.account_files)}"""

        if sys_stats:
            status_msg += f"""

💻 **System Stats**
🖥️ CPU: {sys_stats['cpu']:.1f}%
💾 RAM: {sys_stats['memory_used']:.1f}%
💿 Disk: {sys_stats['disk_used']:.1f}%"""

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="status")],
            [InlineKeyboardButton("📈 Detailed Stats", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(status_msg, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Settings command for configuration"""
        github_status = "✅ Configured" if is_github_configured() else "❌ Not Configured"
        
        keyboard = [
            [InlineKeyboardButton("🔧 GitHub Setup" if not is_github_configured() else "🔧 Reconfigure GitHub", callback_data="start_setup")],
            [InlineKeyboardButton("⏰ Change Interval", callback_data="change_interval")],
            [InlineKeyboardButton("🔄 Toggle Auto-Restart", callback_data="toggle_restart")],
            [InlineKeyboardButton("📁 Switch File", callback_data="switch_file")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        settings_msg = f"""⚙️ **Bot Settings**

🔧 **GitHub**: {github_status}
🔄 **Auto-Restart**: {'✅ Enabled' if self.auto_restart_enabled else '❌ Disabled'}
⏰ **Current Interval**: 8 hours
🔄 **Max Retries**: {self.max_retry_attempts}
📁 **Current File Index**: {self.current_file_index + 1}/3

Choose an option below:"""
        
        await update.message.reply_text(settings_msg, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def logs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent logs"""
        try:
            with open('bot.log', 'r') as f:
                lines = f.readlines()
                recent_logs = ''.join(lines[-20:])  # Last 20 lines
            
            if not recent_logs.strip():
                await update.message.reply_text("📄 No recent logs found.")
                return
            
            # Truncate if too long
            if len(recent_logs) > 3000:
                recent_logs = recent_logs[-3000:]
            
            await update.message.reply_text(f"📄 **Recent Logs:**\n```\n{recent_logs}\n```", parse_mode='Markdown')
            
        except FileNotFoundError:
            await update.message.reply_text("📄 Log file not found.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error reading logs: {str(e)}")
    
    async def restart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Restart the bot"""
        await update.message.reply_text("🔄 **Restarting bot...**\nPlease wait 10-15 seconds.", parse_mode='Markdown')
        await self.send_admin_notification("🔄 Bot restart initiated by user")
        
        # Stop scheduler
        await self.stop_scheduler()
        
        # Restart the application
        os.execv(os.sys.executable, ['python'] + os.sys.argv)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced help with categorized commands"""
        help_text = """🤖 **Enhanced Token Bot - Command Reference**

**🔧 Setup Commands**
/setup - Configure GitHub credentials
/status - Show detailed bot status

**🔄 Core Operations**
/run - Immediately process next JSON file
/logs - View recent bot logs

**⚙️ Control Commands**
/pause - Pause/stop scheduler
/resume - Resume scheduler
/restart - Restart entire bot
/settings - Bot configuration menu

**📊 Information**
/stats - Detailed statistics
/health - System health check
/files - List account files status

**🛠️ Admin Commands**
/emergency - Emergency stop all operations
/backup - Create backup of current tokens
/cleanup - Clean temporary files

**🎛️ Quick Actions (Inline Buttons)**
Use /start to access quick action buttons for common operations.

**⏰ How It Works:**
• 8-hour cycle: accounts1.json → accounts2.json → accounts3.json
• Each cycle: Extract tokens → Update GitHub repo
• Auto-recovery on failures
• Real-time admin notifications

**🔧 First Time Setup:**
1. Use /setup command
2. Provide GitHub token (with repo permissions)
3. Provide repository name (username/repo-name)
4. Start the scheduler with /resume or inline buttons"""
        
        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    # Pause/Resume commands
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        result = await self.stop_scheduler()
        await update.message.reply_text(result)
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_github_configured():
            await update.message.reply_text(
                "❌ **GitHub not configured**\n\nUse /setup command first to configure GitHub credentials.",
                parse_mode='Markdown'
            )
            return
        
        if not self.scheduler_running:
            result = self.start_scheduler()
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("⚠️ Scheduler is already running")
    
    # ==================== CALLBACK QUERY HANDLERS ====================
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button callbacks"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "status":
            await self.handle_status_callback(query)
        elif query.data == "run_now":
            await self.handle_run_callback(query)
        elif query.data == "settings":
            await self.handle_settings_callback(query)
        elif query.data == "help":
            await self.handle_help_callback(query)
        elif query.data == "stats":
            await self.handle_stats_callback(query)
        elif query.data == "toggle_restart":
            await self.handle_toggle_restart_callback(query)
        elif query.data == "main_menu":
            await self.handle_main_menu_callback(query)
        elif query.data == "start_setup":
            await self.handle_setup_callback(query)
        elif query.data == "start_scheduler":
            await self.handle_start_scheduler_callback(query)
        elif query.data == "test_cycle":
            await self.handle_test_cycle_callback(query)
        elif query.data == "test_github":
            await self.handle_test_github_callback(query)
        elif query.data == "reconfigure_github":
            await self.handle_reconfigure_callback(query)
    
    async def handle_setup_callback(self, query):
        """Handle setup button callback"""
        await query.edit_message_text(
            "🚀 **GitHub Setup**\n\n"
            "To configure GitHub, please use the /setup command.\n\n"
            "This will start a secure conversation to collect your GitHub credentials.",
            parse_mode='Markdown'
        )
    
    async def handle_start_scheduler_callback(self, query):
        """Handle start scheduler callback"""
        if is_github_configured():
            result = self.start_scheduler()
            await query.edit_message_text(f"✅ **Scheduler Started**\n\n{result}", parse_mode='Markdown')
        else:
            await query.edit_message_text("❌ **GitHub not configured**\n\nUse /setup first.", parse_mode='Markdown')
    
    async def handle_test_cycle_callback(self, query):
        """Handle test cycle callback"""
        await query.edit_message_text("🔄 **Running test cycle...**\n⏳ Please wait...", parse_mode='Markdown')
        result = await self.process_cycle(manual=True)
        await query.edit_message_text(f"🧪 **Test Cycle Complete**\n\n{result}", parse_mode='Markdown')
    
    async def handle_test_github_callback(self, query):
        """Handle test GitHub callback"""
        is_connected, message = validate_github_connection()
        status = "✅" if is_connected else "❌"
        await query.edit_message_text(f"{status} **GitHub Connection Test**\n\n{message}", parse_mode='Markdown')
    
    async def handle_reconfigure_callback(self, query):
        """Handle reconfigure GitHub callback"""
        await query.edit_message_text(
            "🔧 **Reconfigure GitHub**\n\n"
            "To reconfigure GitHub credentials, use the /setup command.\n\n"
            "This will overwrite your current settings.",
            parse_mode='Markdown'
        )
    
    async def handle_status_callback(self, query):
        """Handle status button callback"""
        current_file = self.account_files[self.current_file_index]
        github_status = "✅" if is_github_configured() else "❌"
        
        status_msg = f"""📊 **Quick Status**

🔧 **GitHub**: {github_status}
🔄 **Status**: {'🟢 Running' if self.scheduler_running else '🔴 Stopped'}
📁 **Next**: {current_file}
✅ **Success**: {self.total_successful_cycles}
❌ **Failed**: {self.total_failed_cycles}

Use /status for detailed info."""
        
        await query.edit_message_text(status_msg, parse_mode='Markdown')
    
    async def handle_run_callback(self, query):
        """Handle run now button callback"""
        if not is_github_configured():
            await query.edit_message_text(
                "❌ **GitHub not configured**\n\nUse /setup command first.",
                parse_mode='Markdown'
            )
            return
        
        await query.edit_message_text("🔄 **Processing...**\n⏳ Please wait...", parse_mode='Markdown')
        result = await self.process_cycle(manual=True)
        await query.edit_message_text(result, parse_mode='Markdown')
    
    async def handle_settings_callback(self, query):
        """Handle settings callback"""
        github_status = "✅ On" if is_github_configured() else "❌ Off"
        
        keyboard = [
            [InlineKeyboardButton("🔧 GitHub Setup" if not is_github_configured() else "🔧 Reconfigure", callback_data="start_setup")],
            [InlineKeyboardButton("🔄 Toggle Auto-Restart", callback_data="toggle_restart")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        settings_msg = f"""⚙️ **Quick Settings**

🔧 **GitHub**: {github_status}
🔄 **Auto-Restart**: {'✅ On' if self.auto_restart_enabled else '❌ Off'}

Use /settings for full options."""
        
        await query.edit_message_text(settings_msg, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_stats_callback(self, query):
        """Handle statistics callback"""
        uptime = datetime.now(timezone.utc) - self.bot_start_time
        total_cycles = self.total_successful_cycles + self.total_failed_cycles
        success_rate = (self.total_successful_cycles / max(1, total_cycles)) * 100
        
        stats_msg = f"""📈 **Detailed Statistics**

⏱️ **Uptime**: {str(uptime).split('.')[0]}
🔄 **Total Cycles**: {total_cycles}
✅ **Successful**: {self.total_successful_cycles}
❌ **Failed**: {self.total_failed_cycles}
📊 **Success Rate**: {success_rate:.1f}%
🎯 **Current File**: {self.current_file_index + 1}/3"""
        
        await query.edit_message_text(stats_msg, parse_mode='Markdown')
    
    async def handle_toggle_restart_callback(self, query):
        """Handle toggle auto-restart callback"""
        self.auto_restart_enabled = not self.auto_restart_enabled
        status = "enabled" if self.auto_restart_enabled else "disabled"
        
        await query.edit_message_text(
            f"🔄 Auto-restart has been **{status}**",
            parse_mode='Markdown'
        )
        
        await self.send_admin_notification(f"🔄 Auto-restart {status} by user")
    
    async def handle_main_menu_callback(self, query):
        """Return to main menu"""
        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("🔄 Run Now", callback_data="run_now")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
            [InlineKeyboardButton("📋 Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🏠 **Main Menu**\nChoose an option:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def handle_help_callback(self, query):
        """Handle help callback"""
        help_msg = """📋 **Quick Help**

🔧 `/setup` - Configure GitHub
🔄 `/run` - Process next file
📊 `/status` - Detailed status
⚙️ `/settings` - Configuration
🔄 `/pause` - Stop scheduler
▶️ `/resume` - Start scheduler

Type /help for full command list."""
        
        await query.edit_message_text(help_msg, parse_mode='Markdown')
    
    # ==================== INITIALIZATION AND STARTUP ====================
    
    async def initialize(self):
        """Initialize the enhanced bot"""
        # Create application
        self.application = Application.builder().token(self.bot_token).build()
        
        # Setup conversation handler for GitHub setup
        setup_handler = ConversationHandler(
            entry_points=[CommandHandler("setup", self.setup_command)],
            states={
                GITHUB_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_github_token)],
                GITHUB_REPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_github_repo)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_setup)],
        )
        
        # Add handlers
        self.application.add_handler(setup_handler)
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("run", self.run_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("logs", self.logs_command))
        self.application.add_handler(CommandHandler("restart", self.restart_command))
        self.application.add_handler(CommandHandler("pause", self.pause_command))
        self.application.add_handler(CommandHandler("resume", self.resume_command))
        
        # Add callback query handler
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Initialize application
        await self.application.initialize()
        
        # Check if GitHub is configured and start scheduler if it is
        if is_github_configured():
            self.start_scheduler()
            self.github_setup_complete = True
        
        # Send startup notification to admin
        github_status = "✅ Configured" if is_github_configured() else "❌ Needs Setup"
        await self.send_admin_notification(f"🚀 Enhanced Token Bot started!\n\n🔧 GitHub: {github_status}")
        
        logger.info("Enhanced bot initialized successfully!")
    
    async def start_bot(self):
        """Start the bot polling"""
        if self.application:
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("Enhanced bot started and polling...")
            
            # Keep running
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received interrupt signal, shutting down...")
            finally:
                await self.cleanup()
    
    async def cleanup(self):
        """Enhanced cleanup with admin notification"""
        try:
            await self.send_admin_notification("🛑 Bot is shutting down...")
            
            if self.scheduler_running:
                await self.stop_scheduler()
            
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            
            logger.info("Cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

async def main():
    """Main function with enhanced error handling"""
    bot = None
    try:
        bot = EnhancedTokenBot()
        await bot.initialize()
        await bot.start_bot()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        if bot and bot.admin_chat_id:
            try:
                await bot.send_admin_notification(f"🚨 Bot startup failed: {str(e)}", is_error=True)
            except:
                pass
    finally:
        if bot:
            await bot.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted")
    except Exception as e:
        logger.error(f"Program error: {e}")
            
            await update.message.reply_text(
                "🔧 **GitHub is already configured!**\n\nWhat would you like to do?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🚀 **GitHub Setup**\n\n"
            "📋 Please follow these steps:\n\n"
            "1️⃣ Go to GitHub.com → Settings → Developer settings → Personal access tokens\n"
            "2️⃣ Create a new token with 'repo' permissions\n"
            "3️⃣ Copy the token and send it here\n\n"
            "⚠️ **Your token will be stored securely and never logged**\n\n"
            "Send your GitHub token now:",
            parse_mode='Markdown'
        )
        return GITHUB_TOKEN
    
    async def receive_github_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive and validate GitHub token"""
        token = update.message.text.strip()
        
        # Delete user's message immediately for security
        try:
            await update.message.delete()
        except:
            pass
        
        # Basic token validation
        if not token.startswith(('ghp_', 'github_pat_')):
            await update.message.reply_text(
                "❌ **Invalid token format**\n\n"
                "GitHub tokens should start with 'ghp_' or 'github_pat_'\n\n"
                "Please try again or use /cancel to stop setup.",
                parse_mode='Markdown'
            )
            return GITHUB_TOKEN
        
        # Store token temporarily
        context.user_data['github_token'] = token
        
        await update.message.reply_text(
            "✅ **Token received!**\n\n"
            "Now please send your repository name in this format:\n"
            "`username/repository_name`\n\n"
            "Example: `john123/my-tokens`",
            parse_mode='Markdown'
        )
        return GITHUB_REPO
    
    async def receive_github_repo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receive and validate GitHub repository"""
        repo = update.message.text.strip()
        token = context.user_data.get('github_token')
        
        # Basic repo validation
        if '/' not in repo or len(repo.split('/')) != 2:
            await update.message.reply_text(
                "❌ **Invalid repository format**\n\n"
                "Please use the format: `username/repository_name`\n"
                "Example: `john123/my-tokens`",
                parse_mode='Markdown'
            )
            return GITHUB_REPO
        
        # Test GitHub connection
        await update.message.reply_text("🔍 **Testing GitHub connection...**", parse_mode='Markdown')
        
        # Set credentials temporarily for testing
        set_github_credentials(token, repo)
        
        # Validate connection
        is_connected, message = validate_github_connection()
        
        if is_connected:
            # Save credentials permanently
            self.github_setup_complete = True
            
            # Clear temporary data
            context.user_data.clear()
            
            keyboard = [
                [InlineKeyboardButton("▶️ Start Scheduler", callback_data="start_scheduler")],
                [InlineKeyboardButton("🔄 Run Test Cycle", callback_data="test_cycle")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            success_msg = f"""✅ **GitHub Setup Complete!**

📊 {message}
🎯 Repository: `{repo}`

Your bot is now ready to use! What would you like to do next?"""
            
            await update.message.reply_text(success_msg, reply_markup=reply_markup, parse_mode='Markdown')
            await self.send_admin_notification(f"🔧 GitHub configured: {repo}")
            
            return ConversationHandler.END
        
        else:
            await update.message.reply_text(
                f"❌ **Connection failed**\n\n{message}\n\n"
                "Please check your token and repository name, then try again.\n\n"
                "Use /setup to start over or /cancel to stop.",
                parse_mode='Markdown'
            )
            return GITHUB_REPO
    
    async def cancel_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel setup conversation"""
        context.user_data.clear()
        await update.message.reply_text(
            "❌ **Setup cancelled**\n\nUse /setup when you're ready to configure GitHub.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # ==================== TELEGRAM COMMAND HANDLERS ====================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced start command with welcome message"""
        github_status = "✅ Configured" if is_github_configured() else "❌ Not Configured"
        
        if not is_github_configured():
            keyboard = [
                [InlineKeyboardButton("🔧 Setup GitHub", callback_data="start_setup")],
                [InlineKeyboardButton("📋 Help", callback_data="help")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("📊 Status", callback_data="status")],
                [InlineKeyboardButton("🔄 Run Now", callback_data="run_now")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
                [InlineKeyboardButton("📋 Help", callback_data="help")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)