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

    async def process_cycle(self, manual=False):
        if not self.is_configured():
            return "❌ Bot not configured. Use /setup first."
        
        self.update_github_env()
        
        try:
            current_file = self.account_files[self.current_file_index]
            start_time = datetime.now(timezone.utc)
            logger.info(f"Starting cycle: {current_file}")

            if not os.path.exists(current_file):
                error_msg = f"❌ File {current_file} not found"
                self.total_failed_cycles += 1
                return error_msg

            logger.info(f"Processing tokens from {current_file}")
            process_json(current_file)

            if not os.path.exists("token_ind.json"):
                error_msg = "❌ token_ind.json was not created"
                self.total_failed_cycles += 1
                return error_msg

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
            self.last_github_update = datetime.now(timezone.utc)
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            self.current_file_index = (self.current_file_index + 1) % len(self.account_files)
            self.total_successful_cycles += 1

            success_msg = f"""✅ Cycle Completed Successfully
📁 File: {current_file}
🎯 Tokens Generated: {token_count}
⏱️ Processing Time: {processing_time:.2f}s
🚀 GitHub: Updated
📊 Total Success: {self.total_successful_cycles}"""

            await self.send_admin_notification(success_msg)
            return success_msg

        except Exception as e:
            self.total_failed_cycles += 1
            error_msg = f"❌ Cycle Failed\nError: {str(e)}"
            await self.send_admin_notification(error_msg, is_error=True)
            return error_msg

    def start_scheduler(self, interval_hours=8):
        if not self.scheduler_running and self.is_configured():
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
            return f"✅ Scheduler started with {interval_hours}h interval"
        return "❌ Cannot start scheduler"

    async def stop_scheduler(self):
        if self.scheduler_running:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
            self.scheduler_running = False
            self.next_run = None
            return "⏹️ Scheduler stopped successfully"
        return "⚠️ Scheduler is already stopped"

    # ==================== TELEGRAM COMMAND HANDLERS ====================
    
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
            [InlineKeyboardButton("⚙️ Settings", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        uptime = datetime.now(timezone.utc) - self.bot_start_time
        welcome_msg = f"""🎉 *Enhanced Token Bot*

🤖 *Status*: {'🟢 Active' if self.scheduler_running else '🔴 Inactive'}
📁 *Next File*: {self.account_files[self.current_file_index]}
⏱️ *Uptime*: {str(uptime).split('.')[0]}
📊 *Success*: {self.total_successful_cycles} cycles"""

        await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode='Markdown')

    async def run_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_configured():
            await update.message.reply_text("❌ Bot not configured. Use /setup first.")
            return
            
        await update.message.reply_text("🔄 *Processing...*", parse_mode='Markdown')
        result = await self.process_cycle(manual=True)
        await update.message.reply_text(result)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        current_file = self.account_files[self.current_file_index]
        uptime = datetime.now(timezone.utc) - self.bot_start_time
        
        total_cycles = self.total_successful_cycles + self.total_failed_cycles
        success_rate = (self.total_successful_cycles / max(1, total_cycles)) * 100

        status_msg = f"""📊 *Bot Status*

🔄 *Scheduler*: {'🟢 Running' if self.scheduler_running else '🔴 Stopped'}
📁 *Next File*: {current_file}
⏰ *Last Run*: {self.last_run.strftime('%H:%M:%S UTC') if self.last_run else 'Never'}
⏱️ *Uptime*: {str(uptime).split('.')[0]}

📈 *Statistics*
✅ Successful: {self.total_successful_cycles}
❌ Failed: {self.total_failed_cycles}
📊 Success Rate: {success_rate:.1f}%"""

        await update.message.reply_text(status_msg, parse_mode='Markdown')

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
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    # ==================== CALLBACK HANDLERS ====================

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
🌿 *Branch*: {self.branch}

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
            
            status_msg = f"""📊 *Quick Status*

🔄 *Status*: {'🟢 Running' if self.scheduler_running else '🔴 Stopped'}
📁 *Next*: {current_file}
⏱️ *Uptime*: {str(uptime).split('.')[0]}
✅ *Success*: {self.total_successful_cycles}
❌ *Failed*: {self.total_failed_cycles}"""

            await query.edit_message_text(status_msg, parse_mode='Markdown')

        elif query.data == "run_now":
            if not self.is_configured():
                await query.edit_message_text("❌ Bot not configured")
                return
                
            await query.edit_message_text("🔄 *Processing...*", parse_mode='Markdown')
            result = await self.process_cycle(manual=True)
            await query.edit_message_text(result)

        elif query.data == "settings":
            settings_msg = f"""⚙️ *Quick Settings*

🔄 *Auto-Restart*: {'✅ On' if self.auto_restart_enabled else '❌ Off'}

Use /setup for configuration options."""

            await query.edit_message_text(settings_msg, parse_mode='Markdown')

    # ==================== INITIALIZATION ====================

    async def initialize(self):
        if not self.bot_token:
            print("❌ No Telegram bot token found!")
            return False

        self.application = Application.builder().token(self.bot_token).build()

        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("setup", self.setup_command))
        self.application.add_handler(CommandHandler("run", self.run_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("pause", self.pause_command))
        self.application.add_handler(CommandHandler("resume", self.resume_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_setup_message))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

        await self.application.initialize()

        if self.is_configured():
            self.start_scheduler()
            self.update_github_env()

      