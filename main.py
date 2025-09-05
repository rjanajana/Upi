import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import base64

# Import your existing modules
from gwt import process_json
from github_update import push_to_github, validate_github_connection

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SecureConfig:
    """Handle encrypted configuration storage"""
    
    def __init__(self):
        self.config_file = ".secure_config.json"
    
    def _encrypt(self, text):
        """Simple encryption"""
        return base64.b64encode(text.encode()).decode()
    
    def _decrypt(self, encrypted_text):
        """Simple decryption"""
        return base64.b64decode(encrypted_text.encode()).decode()
    
    def save_config(self, config):
        """Save encrypted configuration"""
        encrypted_config = {}
        for key, value in config.items():
            if key in ['telegram_token', 'github_token']:
                encrypted_config[key] = self._encrypt(str(value))
            else:
                encrypted_config[key] = value
        
        with open(self.config_file, 'w') as f:
            json.dump(encrypted_config, f, indent=2)
    
    def load_config(self):
        """Load and decrypt configuration"""
        if not os.path.exists(self.config_file):
            return {}
        
        try:
            with open(self.config_file, 'r') as f:
                encrypted_config = json.load(f)
            
            decrypted_config = {}
            for key, value in encrypted_config.items():
                if key in ['telegram_token', 'github_token']:
                    decrypted_config[key] = self._decrypt(value)
                else:
                    decrypted_config[key] = value
            
            return decrypted_config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

class EnhancedTokenBot:
    def __init__(self):
        self.config = SecureConfig()
        self.stored_config = self.config.load_config()
        
        # Try to get bot token from environment or stored config
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or self.stored_config.get("telegram_token")
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID") or self.stored_config.get("admin_chat_id")
        
        # GitHub settings from stored config
        self.github_token = self.stored_config.get("github_token")
        self.repo_name = self.stored_config.get("repo_name")
        self.branch = self.stored_config.get("branch", "main")
        
        self.account_files = ["accounts1.json", "accounts2.json", "accounts3.json"]
        self.current_file_index = 0
        
        # Setup state management
        self.awaiting_setup = {}
        
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

        if not self.bot_token:
            print("❌ No Telegram bot token found!")
            print("🔧 Please set TELEGRAM_BOT_TOKEN in .env file")
            raise ValueError("TELEGRAM_BOT_TOKEN must be set")

    def is_configured(self):
        """Check if bot is fully configured"""
        return bool(self.bot_token and self.github_token and self.repo_name)

    def update_github_env(self):
        """Update environment variables for github_update.py"""
        if self.github_token:
            os.environ["GITHUB_TOKEN"] = self.github_token
        if self.repo_name:
            os.environ["REPO"] = self.repo_name
        if self.branch:
            os.environ["BRANCH"] = self.branch

    async def send_admin_notification(self, message, is_error=False):
        """Send notification to admin with better error handling"""
        if self.admin_chat_id and self.application:
            try:
                emoji = "🚨" if is_error else "✅"
                # Escape special characters for Markdown
                clean_message = message.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("]", "\\]")
                notification_text = f"{emoji} *Admin Notification*\n\n{clean_message}"
                
                await self.application.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")
                # Fallback: send without markdown
                try:
                    await self.application.bot.send_message(
                        chat_id=self.admin_chat_id,
                        text=f"{'🚨' if is_error else '✅'} {message}"
                    )
                except Exception as e2:
                    logger.error(f"Failed to send plain notification: {e2}")

    async def get_system_stats(self):
        """Basic system statistics without psutil"""
        uptime = datetime.now(timezone.utc) - self.bot_start_time
        return {
            'uptime': str(uptime).split('.')[0],
            'note': 'Lightweight mode - detailed system monitoring disabled'
        }

    # ==================== CORE PROCESS METHODS ====================
    
    async def process_cycle(self, manual=False):
        """Enhanced process cycle with configuration check"""
        if not self.is_configured():
            error_msg = "❌ Bot not configured. Use /setup to configure GitHub and Telegram settings."
            return error_msg
        
        # Update environment for github operations
        self.update_github_env()
        
        try:
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

            # Process JSON using gwt.py
            logger.info(f"Processing tokens from {current_file}")
            process_json(current_file)

            # Verify token_ind.json was created
            if not os.path.exists("token_ind.json"):
                error_msg = "❌ token_ind.json was not created"
                logger.error(error_msg)
                await self.send_admin_notification("Token Generation Failed", is_error=True)
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

            success_msg = f"""✅ Cycle Completed Successfully
📁 File: {current_file}
🎯 Tokens Generated: {token_count}
⏱️ Processing Time: {processing_time:.2f}s
🚀 GitHub: Updated
📊 Total Success: {self.total_successful_cycles}"""

            logger.info(f"Cycle completed: {current_file} -> {token_count} tokens")
            await self.send_admin_notification(success_msg)
            return success_msg

        except Exception as e:
            self.total_failed_cycles += 1
            error_msg = f"❌ Cycle Failed\nFile: {current_file}\nError: {str(e)}\nTotal Failures: {self.total_failed_cycles}"
            logger.error(f"Cycle failed: {e}")
            await self.send_admin_notification(error_msg, is_error=True)
            return error_msg

    def start_scheduler(self, interval_hours=8):
        """Enhanced scheduler with custom intervals"""
        if not self.scheduler_running and self.is_configured():
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
        elif not self.is_configured():
            return "❌ Cannot start scheduler: Bot not configured"
        else:
            return "⚠️ Scheduler already running"

    async def stop_scheduler(self):
        """Enhanced stop with confirmation"""
        if self.scheduler_running:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            self.scheduler_running = False
            self.next_run = None
            logger.info("Scheduler stopped")
            await self.send_admin_notification("⏹️ Scheduler stopped by user")
            return "⏹️ Scheduler stopped successfully"
        return "⚠️ Scheduler is already stopped"

    # ==================== TELEGRAM COMMAND HANDLERS ====================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced start command with configuration check"""
        if not self.is_configured():
            keyboard = [
                [InlineKeyboardButton("⚙️ Setup Bot", callback_data="setup_github")],
                [InlineKeyboardButton("📋 Help", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🤖 *Welcome to Enhanced Token Bot*\n\n"
                "❌ *Bot not configured*\n\n"
                "Please complete setup first to use the bot.\n"
                "Use the button below or type /setup",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        # Store admin chat ID if not set
        if not self.admin_chat_id:
            self.admin_chat_id = str(update.effective_user.id)
            config_to_save = self.stored_config.copy()
            config_to_save["admin_chat_id"] = self.admin_chat_id
            self.config.save_config(config_to_save)

        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("🔄 Run Now", callback_data="run_now")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
            [InlineKeyboardButton("📋 Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        welcome_msg = f"""🎉 *Welcome to Enhanced Token Bot*

🤖 *Current Status*: {'🟢 Active' if self.scheduler_running else '🔴 Inactive'}
📁 *Next File*: {self.account_files[self.current_file_index]}
🔄 *Auto Cycle*: Every 8 hours
📊 *Success Rate*: {self.total_successful_cycles}/{self.total_successful_cycles + self.total_failed_cycles} cycles

Use buttons below or type /help for commands."""

        await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def run_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced run command with progress indicator"""
        if not self.is_configured():
            await update.message.reply_text("❌ Bot not configured. Use /setup first.")
            return
            
        await update.message.reply_text("🔄 *Processing next file...*\n⏳ Please wait...", parse_mode='Markdown')
        result = await self.process_cycle(manual=True)

        keyboard = [
            [InlineKeyboardButton("📊 View Status", callback_data="status")],
            [InlineKeyboardButton("📈 Statistics", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(result, reply_markup=reply_markup)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced status with system info"""
        current_file = self.account_files[self.current_file_index]
        uptime = datetime.now(timezone.utc) - self.bot_start_time
        
        total_cycles = self.total_successful_cycles + self.total_failed_cycles
        success_rate = (self.total_successful_cycles / max(1, total_cycles)) * 100

        sys_stats = await self.get_system_stats()

        status_msg = f"""📊 *Enhanced Bot Status*

🔄 *Scheduler*: {'🟢 Running' if self.scheduler_running else '🔴 Stopped'}
📁 *Next File*: `{current_file}`
⏰ *Last Run*: {self.last_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.last_run else 'Never'}
⏰ *Next Run*: {self.next_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.next_run else 'Not scheduled'}

📈 *Statistics*
✅ Successful: {self.total_successful_cycles}
❌ Failed: {self.total_failed_cycles}
📊 Success Rate: {success_rate:.1f}%
⏱️ Uptime: {sys_stats['uptime']}"""

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="status")],
            [InlineKeyboardButton("📈 Detailed Stats", callback_data="stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(status_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def setup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Setup bot configuration through Telegram"""
        keyboard = [
            [InlineKeyboardButton("🐙 GitHub Config", callback_data="setup_github")],
            [InlineKeyboardButton("📊 Show Config", callback_data="show_config")],
            [InlineKeyboardButton("✅ Test Setup", callback_data="test_setup")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        config_status = "✅ Configured" if self.is_configured() else "❌ Incomplete"
        
        setup_msg = f"""⚙️ *Bot Setup & Configuration*

*Current Status*: {config_status}

🤖 *Telegram Token*: {'✅ Set' if self.bot_token else '❌ Missing'}
🐙 *GitHub Token*: {'✅ Set' if self.github_token else '❌ Missing'}  
📁 *Repository*: {'✅ Set' if self.repo_name else '❌ Missing'}

Choose what to configure:"""
        
        await update.message.reply_text(setup_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced help with categorized commands"""
        help_text = """🤖 *Enhanced Token Bot - Command Reference*

*🔄 Core Operations*
/run - Process next JSON file immediately
/status - Show detailed bot status
/setup - Configure bot settings

*⚙️ Control Commands*
/pause - Pause/stop scheduler
/resume - Resume scheduler

*📊 Information*
/config - Show current configuration
/help - Show this help message

*⏰ How It Works:*
• 8-hour cycle: accounts1.json → accounts2.json → accounts3.json
• Each cycle: Extract tokens → Update GitHub repo
• Auto-recovery on failures
• Real-time admin notifications"""

        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("⚙️ Setup", callback_data="setup_github")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        result = await self.stop_scheduler()
        await update.message.reply_text(result)

    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.scheduler_running:
            result = self.start_scheduler()
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("⚠️ Scheduler is already running")

    async def config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current configuration status"""
        config_msg = f"""📋 *Current Configuration*

🤖 *Telegram Bot*: {'✅ Connected' if self.bot_token else '❌ Not configured'}
🐙 *GitHub Token*: {'✅ Set' if self.github_token else '❌ Missing'}
📁 *Repository*: {self.repo_name if self.repo_name else '❌ Not set'}
🌿 *Branch*: {self.branch}

*Account Files*:
• accounts1.json: {'✅' if os.path.exists('accounts1.json') else '❌'}
• accounts2.json: {'✅' if os.path.exists('accounts2.json') else '❌'} 
• accounts3.json: {'✅' if os.path.exists('accounts3.json') else '❌'}

*Status*: {'🟢 Ready to run' if self.is_configured() else '🔴 Setup required'}

Use /setup to configure missing items."""
        
        await update.message.reply_text(config_msg, parse_mode='Markdown')

    # ==================== SETUP HANDLERS ====================

    async def handle_setup_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle setup input messages"""
        user_id = str(update.effective_user.id)
        
        if user_id not in self.awaiting_setup:
            return
        
        setup_type = self.awaiting_setup[user_id]
        user_input = update.message.text.strip()
        
        try:
            if setup_type == "github_token":
                if not (user_input.startswith("ghp_") or user_input.startswith("github_pat_")):
                    await update.message.reply_text("❌ Invalid GitHub token format!\nShould start with 'ghp_' or 'github_pat_'")
                    return
                
                self.github_token = user_input
                await update.message.reply_text("✅ *GitHub token saved!*", parse_mode='Markdown')
                
            elif setup_type == "repo_name":
                if "/" not in user_input or len(user_input.split("/")) != 2:
                    await update.message.re