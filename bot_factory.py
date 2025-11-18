"""
Bot Factory - Creates and manages contest bots
"""
import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import Update, Bot, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import InvalidToken

from contest_manager import ContestManager
from rate_limiter import get_rate_limiter
from input_validator import InputValidator
from ui_helpers import KeyboardBuilder, MessageFormatter

logger = logging.getLogger(__name__)

class BotFactory:
    """Factory for creating and managing contest bots"""
    
    def __init__(self, database):
        self.database = database
        self.active_bots = {}  # Store running bot instances
        self.bot_creation_states = {}  # Track bot creation process
        self.contest_managers = {}  # Store contest managers for each bot
        self.rate_limiter = get_rate_limiter()
        self.validator = InputValidator()
        
    def is_user_creating_bot(self, user_id: int) -> bool:
        """Check if user is currently creating a bot"""
        return user_id in self.bot_creation_states
        
    async def start_bot_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start bot creation process"""
        user_id = update.effective_user.id
        
        # Check if user has reached bot limit
        user_bots = self.database.get_user_bots(user_id)
        from config import Config
        config = Config()
        if len(user_bots) >= config.MAX_BOTS_PER_USER:
            await update.message.reply_text(
                f"❌ Siz maksimal bot soni ({config.MAX_BOTS_PER_USER}) ga yetdingiz!"
            )
            return
            
        # Initialize bot creation state
        self.bot_creation_states[user_id] = {
            'step': 'waiting_for_token',
            'bot_data': {}
        }
        
        # Create cancel keyboard
        reply_markup = KeyboardBuilder.create_cancel_keyboard()
        
        await update.message.reply_text(
            "🤖 **Yangi konkurs boti yaratish!**\n\n"
            "📋 **Qadamlar:**\n"
            "1️⃣ @BotFather ga boring\n"
            "2️⃣ /newbot buyrug'ini yuboring\n"
            "3️⃣ Bot uchun nom va username kiriting\n"
            "4️⃣ Olingan tokenni shu yerga yuboring\n\n"
            "💡 **Token formati:**\n"
            "`1234567890:ABCdefGHIjklMNOpqrSTUvwxyz1234567890A`",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    async def handle_bot_creation_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle each step of bot creation"""
        user_id = update.effective_user.id
        state = self.bot_creation_states.get(user_id)
        
        if not state:
            return
            
        if state['step'] == 'waiting_for_token':
            await self._handle_token_input(update, context, state)
        elif state['step'] == 'waiting_for_bot_name':
            await self._handle_bot_name_input(update, context, state)
            
    async def _handle_token_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
        """Handle bot token input"""
        token = update.message.text.strip()
        
        # Validate token format
        from config import Config
        config = Config()
        if not config.validate_bot_token(token):
            await update.message.reply_text(
                "❌ Noto'g'ri token format!\n\n"
                "📝 To'g'ri token format:\n"
                "• Bot ID: 8-10 raqam\n"
                "• Ikki nuqta (:)\n"
                "• Hash: 35 ta belgi (harflar, raqamlar, _, -)\n\n"
                "💡 Misol: 1234567890:ABCdefGHIjklMNOpqrSTUvwxyz1234567890A\n\n"
                "🤖 @BotFather dan yangi token oling!"
            )
            return
            
        # Test token by creating bot instance
        try:
            test_bot = Bot(token)
            bot_info = await test_bot.get_me()
            
            # Check if bot already exists in our database
            if self.database.bot_exists_by_token(token):
                await update.message.reply_text("❌ Bu bot allaqachon ro'yxatdan o'tgan!")
                return
                
            # Save bot info
            state['bot_data']['token'] = token
            state['bot_data']['username'] = bot_info.username
            state['bot_data']['bot_id'] = bot_info.id
            state['step'] = 'waiting_for_bot_name'
            
            # Keep cancel button
            keyboard = [[KeyboardButton("❌ Bekor qilish")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
            
            await update.message.reply_text(
                f"✅ Bot muvaffaqiyatli tekshirildi!\n"
                f"Bot username: @{bot_info.username}\n\n"
                f"2️⃣ Bot uchun nom kiriting (masalan: 'Mening Konkurs Botim'):",
                reply_markup=reply_markup
            )
            
        except InvalidToken:
            await update.message.reply_text(
                "❌ Noto'g'ri token! Botfather dan to'g'ri token oling."
            )
        except Exception as e:
            logger.error(f"Error testing bot token: {e}")
            await update.message.reply_text(
                "❌ Bot tokenini tekshirishda xatolik yuz berdi. Qayta urinib ko'ring."
            )
            
    async def _handle_bot_name_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
        """Handle bot name input and create bot immediately"""
        bot_name = update.message.text.strip()
        user_id = update.effective_user.id
        
        # Rate limit check for bot creation
        is_allowed, cooldown = self.rate_limiter.check_rate_limit(user_id, 'bot_creation')
        if not is_allowed:
            await update.message.reply_text(
                f"⏳ Juda ko'p bot yaratyapsiz!\n\n"
                f"Iltimos {cooldown} soniya ({cooldown // 60} daqiqa) kuting."
            )
            return
        
        # Input validation using InputValidator
        is_valid, error_msg = self.validator.validate_bot_name(bot_name)
        if not is_valid:
            await update.message.reply_text(error_msg)
            return
        
        # Sanitize input
        bot_name = self.validator.sanitize_text(bot_name)
            
        state['bot_data']['name'] = bot_name
        
        # Set default description
        description = f"Konkurs boti - {bot_name}"
        
        # Create bot in database immediately
        try:
            # Ensure user exists in database before creating bot
            self.database.get_or_create_user(
                telegram_id=user_id,
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name,
                username=update.effective_user.username
            )
            
            bot_id = self.database.create_bot(
                user_id=user_id,
                token=state['bot_data']['token'],
                name=bot_name,
                username=state['bot_data']['username'],
                description=description,
                telegram_bot_id=state['bot_data']['bot_id']
            )
            
            # Set default bot settings
            default_settings = {
                'phone_required': True,
                'welcome_message': f"🎉 **{bot_name}ga xush kelibsiz!**\n\nKonkurslarda ishtirok eting va sovrinlar yutib oling!"
            }
            self.database.update_bot_settings(bot_id, default_settings)
            
            # Start the bot
            await self._start_contest_bot(bot_id, state['bot_data']['token'])
            
            # Clean up creation state
            del self.bot_creation_states[user_id]
            
            # Send success message with main menu keyboard (same as start command)
            from telegram import ReplyKeyboardMarkup, KeyboardButton
            keyboard = [
                [KeyboardButton("🤖 Botlarni boshqarish"), KeyboardButton("🏆 Konkurslar")],
                [KeyboardButton("⚙️ Admin panel")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            # Generate referral link for the bot
            bot_username = state['bot_data']['username']
            referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
            
            await update.message.reply_text(
                f"🎉 Bot muvaffaqiyatli yaratildi!\n\n"
                f"📛 Nom: {bot_name}\n"
                f"🤖 Username: @{bot_username}\n\n"
                f"🔗 Sizning referal havolangiz:\n"
                f"`{referral_link}`\n\n"
                f"✅ Bot ishga tushirildi va foydalanishga tayyor!",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error creating bot: {e}")
            await update.message.reply_text(
                "❌ Bot yaratishda xatolik yuz berdi. Qayta urinib ko'ring."
            )
        
    async def _start_contest_bot(self, bot_id: int, token: str):
        """Start a contest bot instance"""
        try:
            # Create contest manager for this bot
            contest_manager = ContestManager(self.database, bot_id)
            self.contest_managers[bot_id] = contest_manager
            
            # Create bot application
            application = Application.builder().token(token).build()
            
            # Add handlers for contest bot
            application.add_handler(CommandHandler("start", contest_manager.start_command))
            application.add_handler(CommandHandler("help", contest_manager.help_command))
            application.add_handler(CommandHandler("admin", contest_manager.admin_command))
            application.add_handler(CommandHandler("join", contest_manager.join_contest_command))
            application.add_handler(CommandHandler("contests", contest_manager.list_contests_command))
            application.add_handler(CommandHandler("referrals", contest_manager.referrals_command))
            application.add_handler(CallbackQueryHandler(contest_manager.handle_callback_query))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, contest_manager.handle_message))
            application.add_handler(MessageHandler(filters.PHOTO, contest_manager.handle_photo))
            application.add_handler(MessageHandler(filters.VIDEO, contest_manager.handle_video))
            application.add_handler(MessageHandler(filters.CONTACT, contest_manager.handle_contact))
            
            # Store bot instance
            self.active_bots[bot_id] = application
            
            # Initialize and start polling in background
            await application.initialize()
            await application.start()
            await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            
            logger.info(f"Contest bot {bot_id} started successfully")
            
        except Exception as e:
            logger.error(f"Error starting contest bot {bot_id}: {e}")
            raise
            
    async def stop_bot(self, bot_id: int):
        """Stop a contest bot"""
        if bot_id in self.active_bots:
            try:
                application = self.active_bots[bot_id]
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
                del self.active_bots[bot_id]
                if bot_id in self.contest_managers:
                    del self.contest_managers[bot_id]
                logger.info(f"Contest bot {bot_id} stopped")
            except Exception as e:
                logger.error(f"Error stopping bot {bot_id}: {e}")
                
    async def restart_bot(self, bot_id: int):
        """Restart a contest bot"""
        bot_data = self.database.get_bot_by_id(bot_id)
        if bot_data:
            await self.stop_bot(bot_id)
            await self._start_contest_bot(bot_id, bot_data['token'])
            
    async def start_all_existing_bots(self):
        """Start all existing active bots from database"""
        try:
            active_bots = self.database.get_active_bots()
            logger.info(f"Starting {len(active_bots)} existing bots...")
            
            for bot_data in active_bots:
                bot_id = bot_data['id']
                token = bot_data['token']
                
                try:
                    await self._start_contest_bot(bot_id, token)
                    logger.info(f"Successfully started bot {bot_id} ({bot_data['name']})")
                except Exception as e:
                    logger.error(f"Failed to start bot {bot_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error starting existing bots: {e}")
            
    def get_bot_status(self, bot_id: int) -> str:
        """Get bot status"""
        return "active" if bot_id in self.active_bots else "inactive"