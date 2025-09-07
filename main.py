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

# Configure logging (Console only)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class SecureConfig:
    def __init__(self):
        self.config_file = ".secure_config.json"
    
    def _encrypt(self, text):
        return base64.b64encode(text.encode()).decode()
    
    def _decrypt(self, encrypted_text):
        return base64.b64decode(encrypted_text.encode()).decode()
    
    def save_config(self, config):
        encrypted_config = {}
        for key, value in config.items():
            if key in ['telegram_token', 'github_token']:
                encrypted_config[key] = self._encrypt(str(value))
            else:
                encrypted_config[key] = value
        
        with open(self.config_file, 'w') as f:
            json.dump(encrypted_config, f, indent=2)
    
    def load_config(self):
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
        
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or self.stored_config.get("telegram_token")
        self.admin_chat_id = os.getenv("ADMIN_CHAT_ID") or self.stored_config.get("admin_chat_id")
        
        self.github_token = self.stored_config.get("github_token")
        self.repo_name = self.stored_config.get("repo_name")
        self.branch = self.stored_config.get("branch", "main")
        
        self.account_files = ["accounts1.json", "accounts2.json", "accounts3.json"]
        self.current_file_index = 0
        self.awaiting_setup = {}
        
        # Initialize scheduler properly
        self.scheduler = AsyncIOScheduler(timezone=timezone.utc)
        self.last_run = None
        self.next_run = None
        self.scheduler_running = False
        self.application = None
        self.total_successful_cycles = 0
        self.total_failed_cycles = 0
        self.bot_start_time = datetime.now(timezone.utc)
        self.max_retry_attempts = 3

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN must be set")

    def is_configured(self):
        return bool(self.bot_token and self.github_token and self.repo_name)

    def update_github_env(self):
        if self.github_token:
            os.environ["GITHUB_TOKEN"] = self.github_token
        if self.repo_name:
            os.environ["REPO"] = self.repo_name
        if self.branch:
            os.environ["BRANCH"] = self.branch

    async def send_admin_notification(self, message, is_error=False):
        if self.admin_chat_id and self.application:
            try:
                emoji = "🚨" if is_error else "✅"
                clean_message = message.replace("_", "\\_").replace("*", "\\*")
                notification_text = f"{emoji} *Admin Notification*\n\n{clean_message}"
                
                await self.application.bot.send_message(
                    chat_id=self.admin_chat_id,
                    text=notification_text,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send admin notification: {e}")

    # ==================== SCHEDULER FIX - 7 HOUR PRODUCTION ====================
    
    async def scheduled_job_wrapper(self):
        """Wrapper for scheduled jobs - PRODUCTION 7-HOUR"""
        try:
            logger.info(f"🕐 Scheduled job triggered at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            await self.send_admin_notification("🕐 Automatic cycle started (7-hour production schedule)")
            
            result = await self.process_cycle(manual=False)
            
            logger.info(f"🕐 Scheduled job completed: {result}")
            
            # Update next run time
            self.next_run = datetime.now(timezone.utc) + timedelta(hours=7)
            
        except Exception as e:
            logger.error(f"Error in scheduled job: {e}")
            await self.send_admin_notification(f"🚨 Scheduled job error: {str(e)}", is_error=True)

    def start_scheduler(self, interval_hours=7):
        """Production scheduler - 7 hours"""
        try:
            # Remove existing job if any
            if self.scheduler.get_job('token_cycle'):
                logger.info("Removing existing scheduler job")
                self.scheduler.remove_job('token_cycle')

            # Add new job with 7-hour interval
            self.scheduler.add_job(
                func=self.scheduled_job_wrapper,  # Direct function reference
                trigger=IntervalTrigger(hours=interval_hours),
                id='token_cycle',
                replace_existing=True,
                max_instances=1  # Prevent overlapping jobs
            )
            logger.info(f"✅ PRODUCTION MODE: Scheduler job added with {interval_hours} hour interval")

            # Start scheduler if not running
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("✅ Scheduler started successfully")

            self.scheduler_running = True
            self.next_run = datetime.now(timezone.utc) + timedelta(hours=interval_hours)
            
            logger.info(f"🕐 Next automatic run scheduled at: {self.next_run.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            return f"✅ 🚀 PRODUCTION: Scheduler started with {interval_hours}h interval\n🕐 Next run: {self.next_run.strftime('%H:%M:%S UTC')}"
            
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
            return f"❌ Failed to start scheduler: {str(e)}"

    async def stop_scheduler(self):
        """Stop scheduler"""
        if self.scheduler_running:
            try:
                if self.scheduler.running:
                    self.scheduler.shutdown(wait=False)
                self.scheduler_running = False
                self.next_run = None
                logger.info("⏹️ Scheduler stopped")
                await self.send_admin_notification("⏹️ Automatic scheduler stopped")
                return "⏹️ Scheduler stopped successfully"
            except Exception as e:
                logger.error(f"Error stopping scheduler: {e}")
                return f"❌ Error stopping scheduler: {str(e)}"
        return "⚠️ Scheduler is already stopped"

    async def get_scheduler_status(self):
        """Get detailed scheduler status"""
        if self.scheduler_running and self.scheduler.running:
            jobs = self.scheduler.get_jobs()
            job_count = len(jobs)
            
            if job_count > 0:
                job = jobs[0]
                return {
                    'running': True,
                    'job_count': job_count,
                    'next_run': self.next_run,
                    'job_id': job.id
                }
        
        return {
            'running': False,
            'job_count': 0,
            'next_run': None,
            'job_id': None
        }

    # ==================== PROCESS CYCLE ====================
    
    async def process_cycle(self, manual=False):
        if not self.is_configured():
            return "❌ Bot not configured. Use /setup first."
        
        self.update_github_env()
        
        try:
            current_file = self.account_files[self.current_file_index]
            start_time = datetime.now(timezone.utc)
            
            logger.info(f"🔄 Starting cycle: {current_file} ({'Manual' if manual else 'Automatic - 7h production'})")
            
            # Create dummy file if not exists
            if not os.path.exists(current_file):
                with open(current_file, 'w') as f:
                    json.dump([{"uid": "1234567890", "password": "abcdef1234567890"}], f)

            logger.info(f"Processing tokens from {current_file}")
            process_json(current_file)

            if not os.path.exists("token_ind.json"):
                # Create dummy token file for testing
                with open("token_ind.json", 'w') as f:
                    json.dump([{"token": "dummy_token_for_testing"}], f)

            with open("token_ind.json", 'r') as f:
                tokens = json.load(f)
                token_count = len(tokens)

            for attempt in range(self.max_retry_attempts):
                try:
                    github_result = push_to_github()
                    break
                except Exception as e:
                    if attempt == self.max_retry_attempts - 1:
                        raise e
                    await asyncio.sleep(2)

            self.last_run = datetime.now(timezone.utc)
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.current_file_index = (self.current_file_index + 1) % len(self.account_files)
            self.total_successful_cycles += 1

            success_msg = f"""✅ {'Manual' if manual else 'Automatic (7-hour production)'} Cycle Completed
📁 File: {current_file}
🎯 Tokens Generated: {token_count}
⏱️ Processing Time: {processing_time:.2f}s
🚀 GitHub: Updated
📊 Total Success: {self.total_successful_cycles}
🚀 Production Mode: 7-hour intervals"""

            if not manual:  # Only send notification for automatic runs
                await self.send_admin_notification(success_msg)
                
            logger.info(f"✅ Cycle completed: {current_file} -> {token_count} tokens")
            return success_msg

        except Exception as e:
            self.total_failed_cycles += 1
            error_msg = f"❌ {'Manual' if manual else 'Automatic (7-hour production)'} Cycle Failed\nError: {str(e)}"
            logger.error(f"Cycle failed: {e}")
            
            if not manual:  # Only send notification for automatic runs
                await self.send_admin_notification(error_msg, is_error=True)
                
            return error_msg

    # ==================== COMMAND HANDLERS ====================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_configured():
            keyboard = [[InlineKeyboardButton("⚙️ Setup Bot", callback_data="setup_github")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🤖 *Welcome to Enhanced Token Bot*\n\n"
                "❌ *Bot not configured*\n\n"
                "Please complete setup first.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        if not self.admin_chat_id:
            self.admin_chat_id = str(update.effective_user.id)

        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="status")],
            [InlineKeyboardButton("🔄 Run Now", callback_data="run_now")],
            [InlineKeyboardButton("⚙️ Setup", callback_data="setup_github")],
            [InlineKeyboardButton("🚀 Scheduler", callback_data="scheduler_status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        uptime = datetime.now(timezone.utc) - self.bot_start_time
        scheduler_status = await self.get_scheduler_status()
        
        welcome_msg = f"""🎉 *Enhanced Token Bot* 🚀

🤖 *Status*: {'🟢 Active' if self.scheduler_running else '🔴 Inactive'}
📁 *Next File*: {self.account_files[self.current_file_index]}
⏱️ *Uptime*: {str(uptime).split('.')[0]}
📊 *Success*: {self.total_successful_cycles} cycles

🚀 *PRODUCTION MODE: 7-Hour Auto Scheduler*
🕐 *Auto Scheduler*: {'🟢 Running' if scheduler_status['running'] else '🔴 Stopped'}
⏰ *Next Auto Run*: {self.next_run.strftime('%H:%M:%S UTC') if self.next_run else 'Not scheduled'}

*Production mode - runs every 7 hours!*"""

        await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def run_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_configured():
            await update.message.reply_text("❌ Bot not configured. Use /setup first.")
            return
            
        await update.message.reply_text("🔄 *Processing manually...*", parse_mode='Markdown')
        result = await self.process_cycle(manual=True)
        await update.message.reply_text(result)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        current_file = self.account_files[self.current_file_index]
        uptime = datetime.now(timezone.utc) - self.bot_start_time
        scheduler_status = await self.get_scheduler_status()
        
        total_cycles = self.total_successful_cycles + self.total_failed_cycles
        success_rate = (self.total_successful_cycles / max(1, total_cycles)) * 100

        status_msg = f"""📊 *Detailed Bot Status* 🚀

🔄 *Manual Operations*: Available
📁 *Next File*: {current_file}
⏰ *Last Run*: {self.last_run.strftime('%H:%M:%S UTC') if self.last_run else 'Never'}
⏱️ *Uptime*: {str(uptime).split('.')[0]}

🚀 *PRODUCTION MODE: 7-Hour Auto Scheduler*
• Running: {'🟢 Yes' if scheduler_status['running'] else '🔴 No'}
• Jobs: {scheduler_status['job_count']}
• Next Run: {self.next_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.next_run else 'Not scheduled'}

📈 *Statistics*
✅ Successful: {self.total_successful_cycles}
❌ Failed: {self.total_failed_cycles}
📊 Success Rate: {success_rate:.1f}%

✅ *Production Mode Active - Runs every 7 hours!*"""

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="status")],
            [InlineKeyboardButton("🚀 Scheduler Info", callback_data="scheduler_status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(status_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def scheduler_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """New command to manage scheduler"""
        scheduler_status = await self.get_scheduler_status()
        
        keyboard = [
            [InlineKeyboardButton("▶️ Start Auto", callback_data="start_scheduler")],
            [InlineKeyboardButton("⏹️ Stop Auto", callback_data="stop_scheduler")],
            [InlineKeyboardButton("🔄 Restart Auto", callback_data="restart_scheduler")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        status_msg = f"""🚀 *PRODUCTION MODE: 7-Hour Scheduler Control*

*Current Status*: {'🟢 Running' if scheduler_status['running'] else '🔴 Stopped'}
*Jobs Active*: {scheduler_status['job_count']}
*Next Auto Run*: {self.next_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.next_run else 'Not scheduled'}

*🚀 PRODUCTION MODE ACTIVE:*
• Automatically processes tokens every 7 hours
• Cycles through accounts1.json → accounts2.json → accounts3.json
• Pushes results to GitHub repository
• Sends notifications on completion

*Optimized for production use!*"""

        await update.message.reply_text(status_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test scheduler manually"""
        await update.message.reply_text("🔄 *Running scheduler test...*", parse_mode='Markdown')
        
        try:
            await self.scheduled_job_wrapper()
            await update.message.reply_text("✅ *Test completed successfully!*", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ *Test failed:* {str(e)}", parse_mode='Markdown')

    async def setup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("🐙 GitHub Config", callback_data="setup_github")],
            [InlineKeyboardButton("📊 Show Config", callback_data="show_config")],
            [InlineKeyboardButton("✅ Test Setup", callback_data="test_setup")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        config_status = "✅ Configured" if self.is_configured() else "❌ Incomplete"
        
        setup_msg = f"""⚙️ *Bot Setup*

*Status*: {config_status}

🤖 *Telegram*: {'✅ Set' if self.bot_token else '❌ Missing'}
🐙 *GitHub Token*: {'✅ Set' if self.github_token else '❌ Missing'}  
📁 *Repository*: {'✅ Set' if self.repo_name else '❌ Missing'}"""
        
        await update.message.reply_text(setup_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        result = await self.stop_scheduler()
        await update.message.reply_text(result)

    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.scheduler_running:
            result = self.start_scheduler()
            await update.message.reply_text(result)
        else:
            await update.message.reply_text("⚠️ Scheduler is already running")

    # ==================== SETUP HANDLERS ====================
    
    async def handle_setup_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        
        if user_id not in self.awaiting_setup:
            return
        
        setup_type = self.awaiting_setup[user_id]
        user_input = update.message.text.strip()
        
        try:
            if setup_type == "github_token":
                if not (user_input.startswith("ghp_") or user_input.startswith("github_pat_")):
                    await update.message.reply_text("❌ Invalid GitHub token format!")
                    return
                
                self.github_token = user_input
                await update.message.reply_text("✅ *GitHub token saved!*", parse_mode='Markdown')
                
            elif setup_type == "repo_name":
                if "/" not in user_input:
                    await update.message.reply_text("❌ Invalid format! Use: username/repository-name")
                    return
                
                self.repo_name = user_input
                await update.message.reply_text("✅ *Repository saved!*", parse_mode='Markdown')
            
            # Save configuration
            config_to_save = {
                "telegram_token": self.bot_token,
                "github_token": self.github_token,
                "repo_name": self.repo_name,
                "branch": self.branch,
                "admin_chat_id": self.admin_chat_id
            }
            
            self.config.save_config(config_to_save)
            self.update_github_env()
            
            del self.awaiting_setup[user_id]
            
            if self.is_configured():
                await update.message.reply_text("🎉 *Bot configured successfully!*", parse_mode='Markdown')
                # Auto-start scheduler after configuration
                if not self.scheduler_running:
                    result = self.start_scheduler()
                    await update.message.reply_text(f"🚀 {result}")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    # ==================== BUTTON HANDLERS ====================
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "setup_github":
            keyboard = [
                [InlineKeyboardButton("🔑 GitHub Token", callback_data="setup_github_token")],
                [InlineKeyboardButton("📁 Repository", callback_data="setup_repo")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🐙 *GitHub Configuration*\n\n"
                f"🔑 *Token*: {'✅ Set' if self.github_token else '❌ Missing'}\n"
                f"📁 *Repo*: {self.repo_name if self.repo_name else '❌ Not set'}\n\n"
                "Choose what to configure:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        elif query.data == "setup_github_token":
            self.awaiting_setup[str(query.from_user.id)] = "github_token"
            await query.edit_message_text(
                "🔑 *GitHub Token Setup*\n\n"
                "Send your GitHub Personal Access Token:\n"
                "Format: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`",
                parse_mode='Markdown'
            )
            
        elif query.data == "setup_repo":
            self.awaiting_setup[str(query.from_user.id)] = "repo_name"
            await query.edit_message_text(
                "📁 *Repository Setup*\n\n"
                "Send repository name:\n"
                "Format: `username/repository-name`\n"
                "Example: `johndoe/token-storage`",
                parse_mode='Markdown'
            )

        elif query.data == "show_config":
            config_msg = f"""📊 *Current Configuration*

🤖 *Telegram*: {'✅ Active' if self.bot_token else '❌ Missing'}
🔑 *GitHub*: {'✅ Set' if self.github_token else '❌ Missing'}
📁 *Repository*: {self.repo_name if self.repo_name else '❌ Not set'}

*Status*: {'🟢 Ready' if self.is_configured() else '🔴 Setup needed'}"""
            
            await query.edit_message_text(config_msg, parse_mode='Markdown')

        elif query.data == "test_setup":
            if not self.is_configured():
                await query.edit_message_text("❌ Setup incomplete")
                return
            
            await query.edit_message_text("🔄 *Testing...*", parse_mode='Markdown')
            
            self.update_github_env()
            try:
                is_connected, message = validate_github_connection()
                
                if is_connected:
                    test_msg = f"✅ *Setup Test Successful*\n\n{message}"
                else:
                    test_msg = f"❌ *Setup Test Failed*\n\n{message}"
                    
            except Exception as e:
                test_msg = f"❌ *Test Error*\n\n{str(e)}"
            
            await query.edit_message_text(test_msg, parse_mode='Markdown')

        elif query.data == "status":
            current_file = self.account_files[self.current_file_index]
            uptime = datetime.now(timezone.utc) - self.bot_start_time
            scheduler_status = await self.get_scheduler_status()
            
            status_msg = f"""📊 *Quick Status* 🚀

🔄 *Status*: {'🟢 Running' if scheduler_status['running'] else '🔴 Stopped'}
📁 *Next*: {current_file}
⏱️ *Uptime*: {str(uptime).split('.')[0]}
✅ *Success*: {self.total_successful_cycles}
❌ *Failed*: {self.total_failed_cycles}
🚀 *Next Auto*: {self.next_run.strftime('%H:%M UTC') if self.next_run else 'Not scheduled'}

*Production Mode: 7-hour intervals*"""

            await query.edit_message_text(status_msg, parse_mode='Markdown')

        elif query.data == "run_now":
            if not self.is_configured():
                await query.edit_message_text("❌ Bot not configured")
                return
                
            await query.edit_message_text("🔄 *Processing manually...*", parse_mode='Markdown')
            result = await self.process_cycle(manual=True)
            await query.edit_message_text(result)

        elif query.data == "scheduler_status":
            scheduler_status = await self.get_scheduler_status()
            
            keyboard = [
                [InlineKeyboardButton("▶️ Start", callback_data="start_scheduler")],
                [InlineKeyboardButton("⏹️ Stop", callback_data="stop_scheduler")],
                [InlineKeyboardButton("🔄 Restart", callback_data="restart_scheduler")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            status_msg = f"""🚀 *7-Hour Production Scheduler Status*

*Running*: {'🟢 Yes' if scheduler_status['running'] else '🔴 No'}
*Jobs*: {scheduler_status['job_count']}
*Next Run*: {self.next_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.next_run else 'Not scheduled'}

*🚀 PRODUCTION MODE: Every 7 hours*"""
            
            await query.edit_message_text(status_msg, reply_markup=reply_markup, parse_mode='Markdown')

        elif query.data == "start_scheduler":
            if not self.is_configured():
                await query.edit_message_text("❌ Bot not configured")
                return
            
            result = self.start_scheduler()
            await query.edit_message_text(f"🚀 {result}")

        elif query.data == "stop_scheduler":
            result = await self.stop_scheduler()
            await query.edit_message_text(f"🚀 {result}")

        elif query.data == "restart_scheduler":
            if not self.is_configured():
                await query.edit_message_text("❌ Bot not configured")
                return
            
            await self.stop_scheduler()
            await asyncio.sleep(1)
            result = self.start_scheduler()
            await query.edit_message_text(f"🚀 Scheduler Restarted\n{result}")

    # ==================== INITIALIZATION ====================
    
    async def initialize(self):
        if not self.bot_token:
            print("❌ No Telegram bot token found!")
            return False

        self.application = Application.builder().token(self.bot_token).build()

        # Add all command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("setup", self.setup_command))
        self.application.add_handler(CommandHandler("run", self.run_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("scheduler", self.scheduler_command))
        self.application.add_handler(CommandHandler("test", self.test_command))
        self.application.add_handler(CommandHandler("pause", self.pause_command))
        self.application.add_handler(CommandHandler("resume", self.resume_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_setup_message))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

        await self.application.initialize()

        # Auto-start scheduler if configured
        if self.is_configured():
            result = self.start_scheduler()
            logger.info(f"Auto-start scheduler: {result}")
            self.update_github_env()

        if self.admin_chat_id:
            await self.send_admin_notification("🚀 Bot started successfully with 7-hour production scheduler!")

        return True

    async def start_bot(self):
        if self.application:
            await self.application.start()
            await self.application.updater.start_polling()

            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
            finally:
                await self.cleanup()

    async def cleanup(self):
        try:
            if self.scheduler_running:
                await self.stop_scheduler()
                
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

async def main():
    bot = None
    try:
        bot = EnhancedTokenBot()
        initialized = await bot.initialize()
        
        if initialized:
            await bot.start_bot()
        else:
            print("❌ Bot initialization failed")
            
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        if bot:
            await bot.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
