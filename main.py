#!/usr/bin/env python3
"""
Telegram Bot Builder - Main Entry Point
A bot that helps users create and manage their own contest bots.
"""

import os
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from config import Config
from admin_panel import AdminPanel
from bot_factory import BotFactory
from database import Database
from rate_limiter import get_rate_limiter
from input_validator import InputValidator
from error_handler import ErrorHandler
from backup_manager import get_backup_manager
from ui_helpers import KeyboardBuilder, MessageFormatter

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class TelegramBotBuilder:
    """Main bot builder class"""
    
    def __init__(self):
        self.config = Config()
        self.database = Database()
        self.admin_panel = AdminPanel(self.database)
        self.bot_factory = BotFactory(self.database)
        self.rate_limiter = get_rate_limiter()
        self.validator = InputValidator()
        self.error_handler = ErrorHandler()
        self.backup_manager = get_backup_manager()
        self.default_referral_share_text = (
            "🎉 {bot_name} konkursida qatnashing!\n\n"
            "Men seni {count} do'stim bilan taklif qildim.\n"
            "Ishtirok etish uchun shu havolaga o't: {link}\n\n"
            "Siz ham do'stlaringizni taklif qiling va sovrinlarni yuting! 🔥"
        )
        
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.config.ADMIN_USER_IDS
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with reply keyboard menu"""
        user = update.effective_user
        user_id = user.id
        
        # Register user in database
        self.database.get_or_create_user(
            telegram_id=user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            username=user.username
        )
        
        is_admin = self.is_admin(user_id)
        
        if is_admin:
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men sizga konkurs botlari yaratib beradigan botman.\n"
                "Kerakli bo'limni tanlang:"
            )
        else:
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men konkurs botlari yaratish xizmati botiman.\n\n"
                "❗️ Bot yaratish faqat adminlar uchun ruxsat etilgan.\n"
                "Agar sizga bot kerak bo'lsa, admin bilan bog'laning."
            )
        
        reply_markup = KeyboardBuilder.create_main_menu_keyboard(is_admin)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = update.effective_user.id
        
        if self.is_admin(user_id):
            help_text = (
                "📋 Bot Builder yordami (Admin):\n\n"
                "1️⃣ Yangi bot yaratish uchun /create_bot buyrug'ini bosing\n"
                "2️⃣ Bot tokeningizni yuboring\n"
                "3️⃣ Konkurs sozlamalarini kiriting\n"
                "4️⃣ Botingiz tayyor!\n\n"
                "🔧 /my_bots - Botlarni boshqarish\n"
                "⚙️ /admin - Admin panel\n\n"
                "❓ Savollar bo'lsa telegram: @admin"
            )
        else:
            help_text = (
                "📋 Bot Builder yordami:\n\n"
                "❗️ Bot yaratish xizmati faqat adminlar uchun.\n\n"
                "Agar sizga konkurs boti kerak bo'lsa:\n"
                "1️⃣ Admin bilan bog'laning\n"
                "2️⃣ Bot yaratish so'rovini yuboring\n"
                "3️⃣ Admin sizga bot yaratib beradi\n\n"
                "📞 Admin bilan bog'lanish: @menejer_1w"
            )
        
        await update.message.reply_text(help_text)

    async def create_bot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle bot creation - Only for admins"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(
                "❌ Kechirasiz, bot yaratish faqat adminlar uchun ruxsat etilgan.\n\n"
                "Admin bilan bog'laning yoki mavjud botlardan foydalaning."
            )
            return
            
        await self.bot_factory.start_bot_creation(update, context)

    async def my_bots_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's bots with management options - Only for admins"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(
                "❌ Kechirasiz, bot boshqaruvi faqat adminlar uchun ruxsat etilgan.\n\n"
                "Admin bilan bog'laning."
            )
            return
        
        bots = self.database.get_user_bots(user_id)
        
        if not bots:
            keyboard = [[InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🤖 Sizda hali botlar yo'q.\n\n"
                "Birinchi botingizni yaratish uchun tugmani bosing!",
                reply_markup=reply_markup
            )
            return
            
        # Create inline keyboard for bot management
        keyboard = []
        for bot in bots:
            status_emoji = "✅" if bot['active'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_emoji} {bot['name']}", 
                    callback_data=f"manage_bot_{bot['id']}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")])
        keyboard.append([InlineKeyboardButton("📊 Umumiy statistika", callback_data="overall_stats")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bots_text = f"🤖 **Sizning botlaringiz ({len(bots)}/5):**\n\n"
        
        total_contests = sum(bot['contests_count'] for bot in bots)
        total_participants = sum(bot.get('total_participants', 0) for bot in bots)
        
        bots_text += (
            f"📊 **Umumiy statistika:**\n"
            f"🏆 Jami konkurslar: {total_contests}\n"
            f"👥 Jami ishtirokchilar: {total_participants}\n\n"
            f"Bot tanlang yoki yangi bot yarating:"
        )
        
        await update.message.reply_text(bots_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel bot creation process"""
        user_id = update.effective_user.id
        
        # Check if user is creating a bot
        if self.bot_factory.is_user_creating_bot(user_id):
            # Clear bot creation state
            self.bot_factory.bot_creation_states.pop(user_id, None)
            
            # Show main menu keyboard
            keyboard = [
                [KeyboardButton("🤖 Botlarni boshqarish"), KeyboardButton("🏆 Konkurslar")],
                [KeyboardButton("⚙️ Admin panel")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
            
            await update.message.reply_text(
                "❌ Bot yaratish bekor qilindi.\n\n"
                "📋 Bosh menyuga qaytdingiz.",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "ℹ️ Siz hozir bot yaratmayapsiz.\n\n"
                "📋 Yangi bot yaratish uchun /create_bot buyrug'ini ishlating."
            )

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        
        user_id = query.from_user.id
        data = query.data
        
        # Rate limiting check for button clicks
        is_allowed, cooldown = self.rate_limiter.check_rate_limit(user_id, 'button_click')
        if not is_allowed:
            await query.answer(
                f"⏳ Juda ko'p tugma bosdingiz! {cooldown} soniya kuting.",
                show_alert=True
            )
            return
        
        await query.answer()
        
        # Log callback data for debugging
        logger.info(f"Callback query from user {user_id}: {data}")
        
        if data == "create_new_bot":
            if not self.is_admin(user_id):
                await query.edit_message_text(
                    "❌ Kechirasiz, bot yaratish faqat adminlar uchun ruxsat etilgan.\n\n"
                    "Admin bilan bog'laning."
                )
                return
            await self.bot_factory.start_bot_creation(update, context)
        elif data.startswith("manage_bot_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            bot_id = int(data.split("_")[2])
            await self._show_bot_management(query, bot_id)
        elif data == "overall_stats":
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            await self._show_overall_stats(query, user_id)
        elif data.startswith("bot_stats_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            bot_id = int(data.split("_")[2])
            await self._show_bot_statistics(query, bot_id)
        elif data.startswith("bot_action_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            await self._handle_bot_action(query, context)
        elif data.startswith("referral_share_edit_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            parts = data.split("_")
            if len(parts) >= 4:
                bot_id = int(parts[3])
                await self._start_referral_share_edit(query, context, bot_id)
        elif data.startswith("referral_share_cancel_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            parts = data.split("_")
            if len(parts) >= 4:
                bot_id = int(parts[3])
                await self._cancel_referral_share_edit(query, context, bot_id)
        elif data.startswith("admin_"):
            await self.admin_panel.handle_admin_callback(update, context)
        elif data.startswith("broadcast_") or data.startswith("confirm_broadcast_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            await self.admin_panel.handle_admin_callback(update, context)
        elif data.startswith("edit_welcome_"):
            await self._handle_edit_welcome(query, context)
        elif data.startswith("edit_name_"):
            await self._handle_edit_name(query, context)
        elif data.startswith("edit_description_"):
            await self._handle_edit_description(query, context)
        elif data.startswith("contest_bot_"):
            await self._handle_contest_bot_callback(query, context)
        elif data == "refresh_contests":
            await self._handle_refresh_contests(query)
        elif data == "my_bots":
            await self._handle_my_bots_callback(query, context)
        elif data == "admin_panel":
            await self._handle_admin_panel_callback(query, context)
        elif data == "help_info":
            await self._handle_help_callback(query)
        elif data == "back_to_menu":
            await self._handle_back_to_menu(query)
        elif data == "show_bots_list":
            await self._handle_show_bots_list(query, context)
        elif data == "delete_bot_menu":
            await self._handle_delete_bot_menu(query)
        elif data == "back_to_main_menu":
            await self._handle_back_to_main_menu_keyboard(query)
        elif data.startswith("delete_selected_bot_"):
            bot_id = int(data.split("_")[3])
            await self._handle_actual_bot_deletion(query, bot_id)
        elif data.startswith("confirm_delete_"):
            bot_id = int(data.split("_")[2])
            await self._handle_actual_bot_deletion(query, bot_id)
        elif data == "delete_bot_menu":
            await self._handle_delete_bot_menu(query)
        elif data == "back_to_bot_menu":
            await self._handle_back_to_bot_menu(query)
        elif data == "back_to_bots":
            await self._handle_back_to_bots(query)
        elif data == "show_bots_list":
            await self._handle_show_bots_list_callback(query)
        elif data.startswith("export_users_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            bot_id = int(data.split("_")[2])
            await self._export_users_data(query, bot_id)
        elif data.startswith("export_referrals_"):
            if not self.is_admin(user_id):
                await query.edit_message_text("❌ Ruxsat yo'q!")
                return
            bot_id = int(data.split("_")[2])
            await self._export_referrals_data(query, bot_id)
            
    async def _show_bot_management(self, query, bot_id: int):
        """Show bot management options"""
        bot = self.database.get_bot_by_id(bot_id)
        if not bot:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        keyboard = [
            [InlineKeyboardButton("📊 Statistika", callback_data=f"bot_action_stats_{bot_id}")],
            [InlineKeyboardButton("🏆 Konkurslar", callback_data=f"bot_action_contests_{bot_id}")],
            [InlineKeyboardButton("⚙️ Bot sozlamalari", callback_data=f"bot_action_settings_{bot_id}")],
            [InlineKeyboardButton("📢 Broadcast", callback_data=f"bot_action_broadcast_{bot_id}")],
            [InlineKeyboardButton("📥 Excel yuklash", callback_data=f"bot_action_export_{bot_id}")],
            [InlineKeyboardButton("📱 Obuna sozlamalari", callback_data=f"bot_action_subscription_{bot_id}")],
            [InlineKeyboardButton("🔗 Referral sozlamalari", callback_data=f"bot_action_referral_settings_{bot_id}")],
            [InlineKeyboardButton("🔄 Qayta ishga tushirish", callback_data=f"bot_action_restart_{bot_id}")],
            [InlineKeyboardButton("🗑 O'chirish", callback_data=f"bot_action_delete_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_bots")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        status = "✅ Faol" if bot['active'] else "❌ Nofaol"
        
        bot_text = (
            f"🤖 **{bot['name']}**\n\n"
            f"🔗 Username: @{bot['username']}\n"
            f"📊 Status: {status}\n"
            f"🏆 Konkurslar: {bot.get('contests_count', 0)}\n"
            f"📅 Yaratilgan: {bot['created_at']}\n\n"
            f"📝 {bot['description']}\n\n"
            f"Quyidagi amallardan birini tanlang:"
        )
        
        await query.edit_message_text(bot_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _show_bot_contests(self, query, bot_id: int):
        """Show and manage bot contests"""
        contests = self.database.get_bot_contests(bot_id)
        bot = self.database.get_bot_by_id(bot_id)
        
        text = f"🏆 **{bot['name']} - Konkurslar boshqaruvi**\n\n"
        
        if contests:
            text += "📋 **Mavjud konkurslar:**\n"
            for contest in contests[:5]:  # Ko'rsatish uchun 5 ta
                status = "🟢 Faol" if contest['active'] else "🔴 To'xtatilgan"
                participants = self.database.get_contest_participants_count(contest['id'])
                text += f"• **{contest['title']}**\n"
                text += f"   Status: {status}\n"
                text += f"   Ishtirokchilar: {participants} ta\n"
                text += f"   Yaratilgan: {contest['created_at']}\n\n"
        else:
            text += "❌ Hozircha konkurslar yo'q\n\n"
            
        keyboard = [
            [InlineKeyboardButton("➕ Yangi konkurs yaratish", callback_data=f"create_contest_{bot_id}")],
            [InlineKeyboardButton("📋 Barcha konkurslar", callback_data=f"all_contests_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _show_bot_settings(self, query, bot_id: int):
        """Show bot configuration settings"""
        bot = self.database.get_bot_by_id(bot_id)
        settings = self.database.get_bot_settings(bot_id)
        
        text = f"⚙️ **{bot['name']} - Bot sozlamalari**\n\n"
        text += f"📛 **Nom:** {bot['name']}\n"
        text += f"🤖 **Username:** @{bot['username']}\n"
        text += f"📝 **Tavsif:** {bot['description']}\n"
        text += f"📊 **Status:** {'✅ Faol' if bot['active'] else '❌ Nofaol'}\n\n"
        
        text += "⚙️ **Sozlamalar:**\n"
        phone_required = settings.get('phone_required', settings.get('require_phone', True))
        text += f"📱 Telefon raqami majburiy: {'✅' if phone_required else '❌'}\n"
        text += f"🔗 Referral tizimi: {'✅' if settings.get('referral_enabled', True) else '❌'}\n"
        text += f"📢 Avtomatik e'lonlar: {'✅' if settings.get('auto_announcements', True) else '❌'}\n"
        text += f"🏆 Avtomatik g'olib tanlash: {'✅' if settings.get('auto_winner_selection', False) else '❌'}\n"
        
        keyboard = [
            [InlineKeyboardButton("📝 Nom/Tavsif o'zgartirish", callback_data=f"edit_bot_info_{bot_id}")],
            [InlineKeyboardButton("📱 Telefon sozlamalari", callback_data=f"phone_settings_{bot_id}")],
            [InlineKeyboardButton("🔗 Referral sozlamalari", callback_data=f"referral_settings_{bot_id}")],
            [InlineKeyboardButton("🏆 G'olib tanlash sozlamalari", callback_data=f"winner_settings_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _show_subscription_settings(self, query, bot_id: int):
        """Show subscription requirements settings"""
        bot = self.database.get_bot_by_id(bot_id)
        channels = self.database.get_required_channels(bot_id)
        
        text = f"📱 **{bot['name']} - Majburiy obuna sozlamalari**\n\n"
        
        if channels:
            text += "📋 **Majburiy kanallar:**\n"
            for channel in channels:
                text += f"• {channel['name']} (@{channel['username']})\n"
            text += "\n"
        else:
            text += "❌ Majburiy kanallar belgilanmagan\n\n"
            
        text += "⚙️ **Sozlamalar:**\n"
        text += "Foydalanuvchilar botga kirishdan oldin ushbu kanallarga obuna bo'lishi shart\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Kanal qo'shish", callback_data=f"add_channel_{bot_id}")],
            [InlineKeyboardButton("🗑 Kanal o'chirish", callback_data=f"remove_channel_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _show_referral_settings(self, query, bot_id: int):
        """Show referral system settings"""
        bot = self.database.get_bot_by_id(bot_id)
        settings = self.database.get_bot_settings(bot_id)
        referral_stats = self.database.get_bot_referral_stats(bot_id)
        
        text = f"🔗 **{bot['name']} - Referral tizimi sozlamalari**\n\n"
        
        text += "📊 **Statistika:**\n"
        text += f"👥 Jami referrallar: {referral_stats.get('total_referrals', 0)}\n"
        text += f"🏆 Eng faol referrer: {referral_stats.get('top_referrer', 'Mavjud emas')}\n\n"
        
        text += "⚙️ **Sozlamalar:**\n"
        referral_status = "✅ Faol" if settings.get('referral_enabled', True) else "❌ O'chiq"
        rewards_status = "✅ Faol" if settings.get('referral_rewards', False) else "❌ O'chiq"
        text += f"🔗 Referral tizimi: {referral_status}\n"
        text += f"🎁 Referral mukofoti: {rewards_status}\n"
        
        keyboard = [
            [InlineKeyboardButton("🔛 Referral yoqish/o'chirish", callback_data=f"toggle_referral_{bot_id}")],
            [InlineKeyboardButton("🎁 Mukofot sozlamalari", callback_data=f"referral_rewards_{bot_id}")],
            [InlineKeyboardButton("✏️ Referral xabarini tahrirlash", callback_data=f"referral_share_edit_{bot_id}")],
            [InlineKeyboardButton("📊 Batafsil statistika", callback_data=f"referral_stats_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _start_referral_share_edit(self, query, context: ContextTypes.DEFAULT_TYPE, bot_id: int):
        """Start referral share message editing from main admin panel."""
        user_id = query.from_user.id

        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return

        bot_info = self.database.get_bot_by_id(bot_id)
        if not bot_info:
            await query.edit_message_text("❌ Bot topilmadi!")
            return

        bot_settings = self.database.get_bot_settings(bot_id) or {}
        current_text = bot_settings.get('referral_share_text') or self.default_referral_share_text
        safe_current = current_text.replace('```', "'''")

        media_id = bot_settings.get('referral_share_media')
        media_type = bot_settings.get('referral_share_media_type') or 'photo'
        media_status = "🖼 Media ulanmagan."
        if media_id:
            media_status = f"🖼 Joriy media: {media_type.upper()}"

        placeholders = (
            "• {link} — foydalanuvchining referral havolasi\n"
            "• {count} — foydalanuvchi taklif qilganlar soni\n"
            "• {first_name} — foydalanuvchi ismi\n"
            "• {bot_name} — bot nomi"
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"referral_share_cancel_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"bot_action_referral_settings_{bot_id}")]
        ])

        instructions = (
            f"✏️ **{bot_info['name']} - Referral xabarini tahrirlash**\n\n"
            "Matn yuboring yoki rasm/video bilan caption yuboring.\n"
            "Faqat matn yuborsangiz, mavjud media o'chiriladi.\n\n"
            "🔁 **O'zgaruvchilar:**\n"
            f"{placeholders}\n\n"
            f"{media_status}\n\n"
            "**Joriy matn:**\n"
            f"```\n{safe_current}\n```\n\n"
            "Yangi kontentni yuboring."
        )

        if not hasattr(context, 'user_data'):
            context.user_data = {}

        context.user_data[user_id] = {
            'editing_mode': 'referral_share',
            'bot_id': bot_id,
            'referral_edit_message': {
                'chat_id': query.message.chat_id,
                'message_id': query.message.message_id
            }
        }

        await query.edit_message_text(instructions, parse_mode='Markdown', reply_markup=keyboard)

    async def _cancel_referral_share_edit(self, query, context: ContextTypes.DEFAULT_TYPE, bot_id: int):
        """Cancel referral share editing and return to referral settings."""
        user_id = query.from_user.id

        if hasattr(context, 'user_data') and user_id in context.user_data:
            context.user_data[user_id] = {}

        await self._show_referral_settings(query, bot_id)

    async def _handle_referral_share_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Persist referral share message content provided by admin."""
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        user_state = context.user_data.get(user_id, {})
        if user_state.get('editing_mode') != 'referral_share':
            return

        bot_id = user_state.get('bot_id')
        if not bot_id:
            return

        message = update.message
        if not message:
            return

        text_content = message.text or message.caption
        photo = message.photo[-1] if message.photo else None
        video = message.video if message.video else None

        if not text_content:
            await message.reply_text("❗ Matn bo'sh bo'lmasligi kerak. Caption yozing yoki oddiy matn yuboring.")
            return

        updates = {
            'referral_share_text': text_content,
            'referral_share_media': None,
            'referral_share_media_type': None
        }

        if photo:
            updates['referral_share_media'] = photo.file_id
            updates['referral_share_media_type'] = 'photo'
        elif video:
            updates['referral_share_media'] = video.file_id
            updates['referral_share_media_type'] = 'video'

        success = False
        try:
            success = self.database.update_bot_settings(bot_id, updates)
        except Exception as exc:
            logger.error(f"Failed to update referral share message for bot {bot_id}: {exc}")

        if not success:
            await message.reply_text("❌ Xabarni saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring.")
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Referral sozlamalariga qaytish", callback_data=f"bot_action_referral_settings_{bot_id}")]
        ])

        success_text = (
            "✅ Referral ulashish xabari yangilandi!\n\n"
            "Natijani tekshirish uchun yaratilgan botdagi \"🔗 Mening referral havolam\" tugmasini bosing."
        )

        edited = False
        message_meta = user_state.get('referral_edit_message')
        if message_meta:
            try:
                await context.bot.edit_message_text(
                    success_text,
                    chat_id=message_meta['chat_id'],
                    message_id=message_meta['message_id'],
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                edited = True
            except Exception as exc:
                logger.warning(
                    "Could not edit referral instructions message for bot %s: %s",
                    bot_id,
                    exc
                )

        if not edited:
            await message.reply_text(success_text, reply_markup=keyboard, parse_mode='Markdown')

        context.user_data[user_id] = {}
        
    async def _show_broadcast_panel(self, query, bot_id: int):
        """Show broadcast message panel"""
        bot = self.database.get_bot_by_id(bot_id)
        participants = self.database.get_bot_participants_count(bot_id)
        
        text = f"📢 **{bot['name']} - Broadcast panel**\n\n"
        text += f"👥 **Jami foydalanuvchilar:** {participants} ta\n\n"
        text += "📝 **Xabar turlari:**\n"
        text += "• 📝 Oddiy matn\n"
        text += "• 🖼 Rasm bilan\n"
        text += "• 📹 Video bilan\n"
        text += "• 🔗 Tugma bilan\n\n"
        text += "Xabar yuborish uchun turdini tanlang:"
        
        keyboard = [
            [InlineKeyboardButton("📝 Matn xabar", callback_data=f"broadcast_text_{bot_id}")],
            [InlineKeyboardButton("🖼 Rasm bilan xabar", callback_data=f"broadcast_photo_{bot_id}")],
            [InlineKeyboardButton("📹 Video bilan xabar", callback_data=f"broadcast_video_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _show_bot_stats(self, query, bot_id: int):
        """Show detailed bot statistics"""
        bot = self.database.get_bot_by_id(bot_id)
        stats = self.database.get_bot_detailed_stats(bot_id)
        
        text = f"📊 **{bot['name']} - Batafsil statistika**\n\n"
        text += f"👥 **Foydalanuvchilar:**\n"
        text += f"• Jami: {stats.get('total_users', 0)}\n"
        text += f"• Faol: {stats.get('active_users', 0)}\n"
        text += f"• Oxirgi hafta qo'shilgan: {stats.get('new_users_week', 0)}\n\n"
        
        text += f"🔗 **Referrallar:**\n"
        text += f"• Jami: {stats.get('total_referrals', 0)}\n"
        text += f"• Eng faol referrer: {stats.get('top_referrer', 'Mavjud emas')}\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _export_bot_data(self, query, bot_id: int):
        """Show export options menu"""
        bot = self.database.get_bot_by_id(bot_id)
        
        text = f"📥 **{bot['name']} - Excel eksport**\n\n"
        text += "📊 Qaysi ma'lumotlarni eksport qilmoqchisiz?"
        
        keyboard = [
            [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data=f"export_users_{bot_id}")],
            [InlineKeyboardButton("🔗 Referral qo'shganlar", callback_data=f"export_referrals_{bot_id}")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _export_users_data(self, query, bot_id: int):
        """Export users data to Excel"""
        bot = self.database.get_bot_by_id(bot_id)
        
        try:
            from excel_exporter import ExcelExporter
            exporter = ExcelExporter(self.database)
            file_path = exporter.export_bot_data(bot_id)
            
            await query.message.reply_document(
                document=open(file_path, 'rb'),
                filename=f"{bot['name']}_foydalanuvchilar.xlsx",
                caption=f"📊 **{bot['name']}** - Barcha foydalanuvchilar"
            )
            
            await query.answer("✅ Foydalanuvchilar eksport qilindi!", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error in export users data: {e}")
            await query.answer("❌ Ma'lumotlarni yuklashda xatolik yuz berdi!", show_alert=True)
    
    async def _export_referrals_data(self, query, bot_id: int):
        """Export referrals data to Excel"""
        bot = self.database.get_bot_by_id(bot_id)
        
        try:
            from excel_exporter import ExcelExporter
            exporter = ExcelExporter(self.database)
            file_path = await exporter.export_referrals_only(bot_id)
            
            await query.message.reply_document(
                document=open(file_path, 'rb'),
                filename=f"{bot['name']}_referrallar.xlsx",
                caption=f"� **{bot['name']}** - Referral qo'shganlar"
            )
            
            await query.answer("✅ Referrallar eksport qilindi!", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error in export referrals data: {e}")
            await query.answer("❌ Ma'lumotlarni yuklashda xatolik yuz berdi!", show_alert=True)
        
    async def _show_overall_stats(self, query, user_id: int):
        """Show overall statistics for user's bots"""
        stats = self.database.get_user_overall_stats(user_id)
        
        stats_text = (
            f"📊 **Umumiy statistika**\n\n"
            f"🤖 Botlar soni: {stats['total_bots']}\n"
            f"✅ Faol botlar: {stats['active_bots']}\n"
            f"🏆 Jami konkurslar: {stats['total_contests']}\n"
            f"👥 Jami ishtirokchilar: {stats['total_participants']}\n"
            f"📝 Jami yuborilgan: {stats['total_submissions']}\n\n"
            f"📈 **Oxirgi hafta:**\n"
            f"🆕 Yangi konkurslar: {stats['new_contests_week']}\n"
            f"👤 Yangi ishtirokchilar: {stats['new_participants_week']}\n\n"
            f"🏆 **Eng faol bot:** {stats['most_active_bot']}"
        )
        
        keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_bots")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _handle_bot_action(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle bot management actions"""
        data = query.data
        action_parts = data.split("_")
        action = action_parts[2]
        bot_id = int(action_parts[3])
        
        if action == "restart":
            try:
                await self.bot_factory.restart_bot(bot_id)
                await query.answer("✅ Bot qayta ishga tushirildi!", show_alert=True)
            except Exception as e:
                await query.answer(f"❌ Xatolik: {str(e)}", show_alert=True)
                
        elif action == "contests":
            await self._show_bot_contests(query, bot_id)
        elif action == "settings":
            await self._show_bot_settings(query, bot_id)
        elif action == "subscription":
            await self._show_subscription_settings(query, bot_id)
        elif action == "referral" and len(action_parts) > 3:
            if hasattr(context, 'user_data'):
                user_state = context.user_data.get(query.from_user.id)
                if user_state and user_state.get('editing_mode') == 'referral_share':
                    context.user_data[query.from_user.id] = {}
            await self._show_referral_settings(query, bot_id)
        elif action == "broadcast":
            await self._show_broadcast_panel(query, bot_id)
        elif action == "export":
            await self._export_bot_data(query, bot_id)
        elif action == "stats":
            await self._show_bot_stats(query, bot_id)
        elif action == "delete":
            keyboard = [
                [InlineKeyboardButton("❌ Ha, o'chirish", callback_data=f"confirm_delete_{bot_id}")],
                [InlineKeyboardButton("⬅️ Orqaga", callback_data=f"manage_bot_{bot_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ **OGOHLANTIRISH!**\n\n"
                "Bot o'chirilsa, barcha ma'lumotlar (konkurslar, ishtirokchilar) ham o'chadi!\n\n"
                "Rostdan ham o'chirmoqchimisiz?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin panel access"""
        await self.admin_panel.show_admin_panel(update, context)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages and keyboard buttons"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Rate limiting check
        is_allowed, cooldown = self.rate_limiter.check_rate_limit(user_id, 'message')
        if not is_allowed:
            await update.message.reply_text(
                f"⏳ Juda ko'p xabar yuboryapsiz!\n\n"
                f"Iltimos {cooldown} soniya kuting."
            )
            return
        
        # Debug: log received message
        logger.info(f"User {user_id} sent message: '{message_text}'")
        
        # Check if user pressed cancel during bot creation
        if message_text == "❌ Bekor qilish" and self.bot_factory.is_user_creating_bot(user_id):
            # Clear bot creation state
            self.bot_factory.bot_creation_states.pop(user_id, None)
            
            # Show main menu
            reply_markup = KeyboardBuilder.create_main_menu_keyboard(self.is_admin(user_id))
            
            await update.message.reply_text(
                "❌ Bot yaratish bekor qilindi.\n\n"
                "📋 Bosh menyuga qaytdingiz.",
                reply_markup=reply_markup
            )
            return
        
        # Check if user is in bot creation process
        if self.bot_factory.is_user_creating_bot(user_id):
            await self.bot_factory.handle_bot_creation_step(update, context)
            return
            
        # Check if admin panel is handling welcome message editing
        if hasattr(self.admin_panel, 'handle_welcome_message_input'):
            handled = await self.admin_panel.handle_welcome_message_input(update, context)
            if handled:
                return
                
        # Check if admin is sending broadcast message
        if hasattr(self.admin_panel, 'handle_broadcast_message'):
            handled = await self.admin_panel.handle_broadcast_message(update, context)
            if handled:
                return
        
        # Check if admin is editing bot info (name, description)
        if hasattr(self.admin_panel, 'handle_admin_text_input'):
            handled = await self.admin_panel.handle_admin_text_input(update, context)
            if handled:
                return
        
        # Check if admin is adding channel
        if hasattr(self.admin_panel, 'handle_channel_input'):
            handled = await self.admin_panel.handle_channel_input(update, context)
            if handled:
                return
        
        # Check if user is editing bot settings
        user_data = getattr(context, 'user_data', {}).get(user_id, {})
        if user_data.get('editing_mode'):
            await self._handle_editing_input(update, context)
            return
            
        # Handle keyboard button presses
        if message_text == "🤖 Botlarni boshqarish":
            await self._show_bot_management_menu(update)
        elif message_text == "🏆 Konkurslar":
            await self._show_all_contests(update)
        elif message_text == "⚙️ Admin panel":
            await self.admin_command(update, context)
        elif message_text == "🇺🇿 Qo'llanma":
            await self._handle_qollanma(update)
        elif message_text == "📞 Admin bilan bog'lanish":
            await update.message.reply_text(
                "📞 Admin bilan bog'lanish:\n\n"
                "Telegram: @admin\n"
                "Bot yaratish so'rovingizni yuboring."
            )
        elif message_text == "➕ Yangi bot yaratish":
            await self.create_bot_command(update, context)
        elif message_text == "🗑 Botni o'chirish":
            await self._handle_botni_ochirish(update, context)
        elif message_text == "🔙 Orqaga":
            await self._handle_orqaga_button(update)
        elif message_text == "🔙 Bot menyusiga":
            await self._show_bot_management_menu(update)
        else:
            # Check if message is a bot name from the list
            await self._handle_bot_name_selection(update, context, message_text)

    async def handle_media_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo and video messages for admin welcome editing"""
        # Check if admin panel is handling welcome message editing
        if hasattr(self.admin_panel, 'handle_welcome_message_input'):
            handled = await self.admin_panel.handle_welcome_message_input(update, context)
            if handled:
                return

        user_id = update.effective_user.id
        user_state = getattr(context, 'user_data', {}).get(user_id, {})
        if user_state.get('editing_mode') == 'referral_share':
            await self._handle_referral_share_submission(update, context)
            return
                
        # If not handled by admin panel, send default response
        await update.message.reply_text("❓ Bu media xabar nimaga tegishli ekanligi aniq emas.")

    async def _show_bot_management_menu(self, update):
        """Show bot management menu with keyboard buttons"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(
                "❌ Kechirasiz, bot boshqaruvi faqat adminlar uchun ruxsat etilgan.\n\n"
                "Admin bilan bog'laning."
            )
            return
            
        text = (
            "🤖 **Bot boshqaruvi menyusi**\n\n"
            "Kerakli bo'limni tanlang:"
        )
        
        keyboard = [
            [KeyboardButton("➕ Yangi bot yaratish")],
            [KeyboardButton("🗑 Botni o'chirish")],
            [KeyboardButton("🔙 Orqaga")]
        ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_qollanma(self, update):
        """Handle Qo'llanma button"""
        user_id = update.effective_user.id
        
        if self.is_admin(user_id):
            text = (
                "🇺🇿 **Qo'llanma (Admin)**\n\n"
                "**📱 Bot yaratish:**\n"
                "1️⃣ 🤖 Botlarni boshqarish tugmasini bosing\n"
                "2️⃣ Bot tokenini kiriting (BotFather'dan)\n"
                "3️⃣ Bot sozlamalarini to'ldiring\n"
                "4️⃣ Botingiz tayyor!\n\n"
                "**🏆 Konkurs yaratish:**\n"
                "• Yaratilgan botga kiring\n"
                "• Admin panel → Yangi konkurs\n"
                "• Konkurs ma'lumotlarini kiriting\n"
                "• Konkurs faollashtiriladi\n\n"
                "**📊 Excel Export (YANGI!):**\n"
                "Bot → Admin Panel → Ma'lumotlar → Excel eksport\n\n"
                "**Excel faylda:**\n"
                "📄 Sheet 1: Barcha foydalanuvchilar\n"
                "📄 Sheet 2: Referral orqali kelganlar\n"
                "📄 Sheet 3: Konkurslar ro'yxati\n"
                "📄 Sheet 4: **Referral statistika**\n"
                "   • Har bir foydalanuvchi qancha odam qo'shgan\n"
                "   • Qo'shgan odamlarning to'liq ma'lumotlari\n"
                "   • Telefon raqamlari, username, sana\n\n"
                "**🎯 Bot boshqaruvi:**\n"
                "• Statistika ko'rish\n"
                "• Ishtirokchilar ro'yxati\n"
                "• G'oliblarni tanlash\n"
                "• Xabar yuborish (broadcast)\n"
                "• Admin qo'shish/o'chirish"
            )
        else:
            text = (
                "🇺🇿 **Qo'llanma**\n\n"
                "**🤖 Bot yaratish xizmati haqida:**\n\n"
                "Bu bot orqali professional konkurs botlari yaratiladi.\n"
                "Bot yaratish faqat adminlar uchun ruxsat etilgan.\n\n"
                "**✨ Bot imkoniyatlari:**\n"
                "• 🏆 Konkurs o'tkazish\n"
                "• 👥 Ishtirokchilarni boshqarish\n"
                "• 📊 To'liq statistika\n"
                "• 📋 Excel eksport (4 ta sheet)\n"
                "• 🎁 G'oliblarni tanlash\n"
                "• 📢 Xabar yuborish\n"
                "• 👤 Referral tizimi\n"
                "• 📱 Telefon tasdiqdan o'tkazish\n\n"
                "**📊 Excel eksportda:**\n"
                "1️⃣ Barcha foydalanuvchilar\n"
                "2️⃣ Referral statistikasi\n"
                "3️⃣ Har kim qancha odam qo'shgan\n"
                "4️⃣ To'liq telefon raqamlar\n\n"
                "**🆕 Agar sizga bot kerak bo'lsa:**\n"
                "1️⃣ Admin bilan bog'laning\n"
                "2️⃣ Konkurs turingizni ayting\n"
                "3️⃣ Kerakli sozlamalarni bering\n"
                "4️⃣ Admin sizga tayyor bot beradi\n\n"
                "📞 **Admin:** @admin"
            )
            
        await update.message.reply_text(text, parse_mode='Markdown')

    async def _handle_my_bots_callback(self, query, context):
        """Handle my_bots callback"""
        user_id = query.from_user.id
        
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return
        
        bots = self.database.get_user_bots(user_id)
        
        if not bots:
            keyboard = [[InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🤖 Sizda hali botlar yo'q.\n\n"
                "Birinchi botingizni yaratish uchun tugmani bosing!",
                reply_markup=reply_markup
            )
            return
            
        # Create inline keyboard for bot management
        keyboard = []
        for bot in bots:
            status_emoji = "🟢" if bot.get('active', True) else "🔴"
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {bot['name']}", 
                callback_data=f"manage_bot_{bot['id']}"
            )])
            
        keyboard.append([InlineKeyboardButton("➕ Yangi bot qo'shish", callback_data="create_new_bot")])
        keyboard.append([InlineKeyboardButton("📊 Umumiy statistika", callback_data="overall_stats")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        total_bots = len(bots)
        active_bots = len([b for b in bots if b.get('active', True)])
        
        text = (
            f"🤖 **Sizning botlaringiz**\n\n"
            f"📊 **Statistika:**\n"
            f"• Jami botlar: {total_bots}\n"
            f"• Faol botlar: {active_bots}\n\n"
            f"Boshqarish uchun botni tanlang:"
        )
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_admin_panel_callback(self, query, context):
        """Handle admin_panel callback"""
        user_id = query.from_user.id
        
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return
            
        await self.admin_panel.show_admin_panel(query, context)
    
    async def _handle_help_callback(self, query):
        """Handle help_info callback"""
        user_id = query.from_user.id
        
        if self.is_admin(user_id):
            help_text = (
                "📋 **Bot Builder yordami (Admin)**\n\n"
                "🔹 **Yangi bot yaratish** - Konkurs boti yaratish\n"
                "🔹 **Mening botlarim** - Botlarni boshqarish\n"
                "🔹 **Admin panel** - Tizim boshqaruvi\n\n"
                "**Bot yaratish bosqichlari:**\n"
                "1️⃣ Yangi bot yaratish tugmasini bosing\n"
                "2️⃣ Bot tokeningizni yuboring\n"
                "3️⃣ Bot nomini va tavsifini kiriting\n"
                "4️⃣ Botingiz tayyor!\n\n"
                "❓ Savollar bo'lsa: @admin"
            )
        else:
            help_text = (
                "📋 **Bot Builder yordami**\n\n"
                "❗️ Bot yaratish xizmati faqat adminlar uchun.\n\n"
                "**Agar sizga konkurs boti kerak bo'lsa:**\n"
                "1️⃣ Admin bilan bog'laning\n"
                "2️⃣ Bot yaratish so'rovini yuboring\n"
                "3️⃣ Admin sizga bot yaratib beradi\n\n"
                "📞 Admin bilan bog'lanish: @admin"
            )
        
        keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_back_to_menu(self, query):
        """Handle back to main menu"""
        user = query.from_user
        user_id = user.id
        
        if self.is_admin(user_id):
            # Admin uchun to'liq funksiyalar
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men sizga konkurs botlari yaratib beradigan botman.\n"
                "Kerakli bo'limni tanlang:"
            )
            
            keyboard = [
                [InlineKeyboardButton("🆕 Yangi bot yaratish", callback_data="create_new_bot")],
                [InlineKeyboardButton("🤖 Mening botlarim", callback_data="my_bots")],
                [InlineKeyboardButton("⚙️ Admin panel", callback_data="admin_panel")],
                [InlineKeyboardButton("ℹ️ Yordam", callback_data="help_info")]
            ]
            
        else:
            # Oddiy foydalanuvchi uchun cheklangan
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men konkurs botlari yaratish xizmati botiman.\n\n"
                "❗️ Bot yaratish faqat adminlar uchun ruxsat etilgan.\n"
                "Agar sizga bot kerak bo'lsa, admin bilan bog'laning."
            )
            
            keyboard = [
                [InlineKeyboardButton("ℹ️ Yordam", callback_data="help_info")],
                [InlineKeyboardButton("📞 Admin bilan bog'lanish", url="https://t.me/admin")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)

    async def _handle_show_bots_list(self, query, context):
        """Handle show bots list callback - same as my_bots_command but as callback"""
        user_id = query.from_user.id
        
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return
            
        bots = self.database.get_user_bots(user_id)
        
        if not bots:
            keyboard = [
                [InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_bot_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "🤖 Sizda hale botlar yo'q.\n\n"
                "Birinchi botingizni yaratish uchun tugmani bosing!",
                reply_markup=reply_markup
            )
            return
            
        # Create inline keyboard for bot management
        keyboard = []
        for bot in bots:
            status_emoji = "✅" if bot['active'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_emoji} {bot['name']}", 
                    callback_data=f"manage_bot_{bot['id']}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")])
        keyboard.append([InlineKeyboardButton("📊 Umumiy statistika", callback_data="overall_stats")])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_bot_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bots_text = f"🤖 **Sizning botlaringiz ({len(bots)}/5):**\n\n"
        
        total_contests = sum(bot['contests_count'] for bot in bots)
        total_participants = sum(bot.get('total_participants', 0) for bot in bots)
        
        bots_text += (
            f"📊 **Umumiy statistika:**\n"
            f"🏆 Jami konkurslar: {total_contests}\n"
            f"👥 Jami ishtirokchilar: {total_participants}\n\n"
            f"Bot tanlang yoki yangi bot yarating:"
        )
        
        await query.edit_message_text(bots_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_delete_bot_menu(self, query):
        """Handle delete bot menu"""
        user_id = query.from_user.id

        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return

        # Super admin sees ALL bots, regular admin sees only their bots
        is_super_admin = self.config.is_super_admin(user_id)

        logger.info(f"Delete bot menu - User {user_id}, is_super_admin: {is_super_admin}")

        if is_super_admin:
            # Get all bots with owner info
            bots = self.database.get_all_bots_with_owners()
            logger.info(f"Super admin - Found {len(bots)} total bots in database")
        else:
            bots = self.database.get_user_bots(user_id)
            logger.info(f"Regular admin - Found {len(bots)} bots for user {user_id}")

        if not bots:
            keyboard = [
                [InlineKeyboardButton("🔙 Bot menyusiga", callback_data="back_to_bot_menu")],
                [InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                "🤖 O'chirishga bot yo'q.\n\n"
                "Avval bot yarating!",
                reply_markup=reply_markup
            )
            return

        delete_notice = (
            "⚠️ **Ogohlantirish:** Tugmani bosishingiz bilanoq bot, konkurslar va foydalanuvchi ma'lumotlari darhol o'chiriladi."
        )

        if is_super_admin:
            text = (
                "🗑 **Bot o'chirish** (SUPER ADMIN)\n\n"
                f"{delete_notice}\n\n"
                "🔓 Siz barcha botlarni ko'rishingiz va o'chirishingiz mumkin:\n\n"
                "O'chirish uchun botni tanlang:"
            )
        else:
            text = (
                "🗑 **Bot o'chirish**\n\n"
                f"{delete_notice}\n\n"
                "O'chirish uchun botni tanlang:"
            )

        keyboard = []
        for bot in bots:
            status_emoji = "✅" if bot['active'] else "❌"

            # For super admin, show owner info
            if is_super_admin and bot.get('owner_id') != user_id:
                owner_tag = f" [ID: {bot.get('owner_id', 'N/A')}]"
                button_text = f"🗑 {status_emoji} {bot['name']}{owner_tag}"
            else:
                button_text = f"🗑 {status_emoji} {bot['name']}"

            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"delete_selected_bot_{bot['id']}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("🔙 Bot menyusiga", callback_data="back_to_bot_menu"),
            InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_menu")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_actual_bot_deletion(self, query, bot_id: int):
        """Actually delete the bot"""
        user_id = query.from_user.id
        logger.info(f"Starting bot deletion process for bot_id: {bot_id} by user: {user_id}")
        
        bot = self.database.get_bot_by_id(bot_id)
        if not bot:
            logger.error(f"Bot {bot_id} not found in database")
            keyboard = [[InlineKeyboardButton("🔙 Bot menyusiga", callback_data="back_to_bot_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Bot topilmadi!", reply_markup=reply_markup)
            return
        
        # Check if user is the bot owner OR super admin
        is_super_admin = self.config.is_super_admin(user_id)
        if bot['owner_id'] != user_id and not is_super_admin:
            logger.warning(f"User {user_id} attempted to delete bot {bot_id} owned by {bot['owner_id']}")
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="delete_bot_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ Xatolik!\n\n"
                "Siz faqat o'zingiz yaratgan botlarni o'chira olasiz!\n\n"
                f"Bu bot boshqa admin tomonidan yaratilgan.",
                reply_markup=reply_markup
            )
            return
        
        if is_super_admin and bot['owner_id'] != user_id:
            logger.info(f"SUPER ADMIN {user_id} deleting bot {bot_id} owned by {bot['owner_id']}")
        else:
            logger.info(f"Found bot: {bot['name']} (@{bot['username']}), owner verified")
        
        try:
            # Stop bot if running
            logger.info(f"Stopping bot {bot_id}")
            await self.bot_factory.stop_bot(bot_id)
            
            # Delete from database
            logger.info(f"Deleting bot {bot_id} from database")
            success = self.database.delete_bot(bot_id)
            
            if success:
                logger.info(f"Bot {bot_id} successfully deleted by user {user_id}")
                text = (
                    "✅ Bot muvaffaqiyatli o'chirildi!\n\n"
                    f"🤖 Bot: {bot['name']}\n"
                    f"🔗 Username: @{bot['username']}\n\n"
                    "Barcha ma'lumotlar butunlay o'chirildi."
                )
                reply_markup = None
            else:
                logger.error(f"Failed to delete bot {bot_id} from database")
                text = "❌ Bot ma'lumotlarini o'chirishda xatolik yuz berdi!"
                keyboard = [
                    [InlineKeyboardButton("🗑 Yana o'chirish", callback_data="delete_bot_menu")],
                    [InlineKeyboardButton("🔙 Bot menyusiga", callback_data="back_to_bot_menu"),
                     InlineKeyboardButton("🏠 Asosiy menyu", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error during bot deletion: {e}")
            await query.edit_message_text(
                f"❌ Bot o'chirishda xatolik:\n{str(e)}\n\n"
                "Admin bilan bog'laning."
            )

    async def _handle_back_to_main_menu_keyboard(self, query):
        """Handle back to main menu from bot management"""
        user = query.from_user
        user_id = user.id
        
        if self.is_admin(user_id):
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men sizga konkurs botlari yaratib beradigan botman.\n"
                "Kerakli bo'limni tanlang:"
            )
        else:
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men konkurs botlari yaratish xizmati botiman.\n\n"
                "❗️ Bot yaratish faqat adminlar uchun ruxsat etilgan.\n"
                "Agar sizga bot kerak bo'lsa, admin bilan bog'laning."
            )
        
        # Delete the inline message and send new keyboard message
        await query.message.delete()
        
        if self.is_admin(user_id):
            keyboard = [
                [KeyboardButton("🤖 Botlarni boshqarish")],
                [KeyboardButton("⚙️ Admin panel")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
        else:
            keyboard = [
                [KeyboardButton("📞 Admin bilan bog'lanish")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await query.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def _handle_back_to_bot_menu(self, query):
        """Handle back to bot management menu"""
        text = (
            "🤖 **Bot boshqaruvi menyusi**\n\n"
            "Quyidagi amallardan birini tanlang:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Botlar ro'yxati", callback_data="show_bots_list")],
            [InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")],
            [InlineKeyboardButton("🗑 Botni o'chirish", callback_data="delete_bot_menu")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_botlar_royxati(self, update, context):
        """Handle Botlar ro'yxati keyboard button - now with inline keyboard and statistics"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(
                "❌ Kechirasiz, bot boshqaruvi faqat adminlar uchun ruxsat etilgan.\n\n"
                "Admin bilan bog'laning."
            )
            return
            
        bots = self.database.get_user_bots(user_id)
        
        if not bots:
            text = (
                "🤖 **Botlar ro'yxati**\n\n"
                "❌ Sizda hali botlar yo'q.\n\n"
                "Avval bot yarating!"
            )
            
            keyboard = [
                [InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
            
        # Create inline keyboard buttons for each bot  
        keyboard = []
        for bot in bots:
            status_emoji = "🟢" if bot['active'] else "🔴"
            keyboard.append([InlineKeyboardButton(f"🤖 {status_emoji} {bot['name']}", callback_data=f"bot_stats_{bot['id']}")])
            
        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bots_text = f"🤖 **Botlar ro'yxati ({len(bots)}/5)**\n\n"
        bots_text += "📊 Bot statistikasini ko'rish uchun botni tanlang:"
        
        await update.message.reply_text(bots_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_botni_ochirish(self, update, context):
        """Handle Botni o'chirish keyboard button"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(
                "❌ Kechirasiz, bot boshqaruvi faqat adminlar uchun ruxsat etilgan.\n\n"
                "Admin bilan bog'laning."
            )
            return
            
        bots = self.database.get_user_bots(user_id)
        
        if not bots:
            await update.message.reply_text(
                "🤖 O'chirishga bot yo'q.\n\n"
                "Avval bot yarating!"
            )
            return
            
        text = "🗑 **Bot o'chirish**\n\n" \
               "⚠️ **Ogohlantirish:** Bot o'chirilsa, barcha ma'lumotlar ham o'chadi!\n\n" \
               "O'chirish uchun botni tanlang:"
        
        keyboard = []
        for bot in bots:
            status_emoji = "✅" if bot['active'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"🗑 {status_emoji} {bot['name']}",
                    callback_data=f"delete_selected_bot_{bot['id']}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_orqaga_button(self, update):
        """Handle Orqaga keyboard button - context aware"""
        user = update.effective_user
        user_id = user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(
                "Tugmalardan foydalaning yoki /help buyrug'ini yuboring."
            )
            return
            
        # Always go back to main menu from bot management screens
        await self._go_to_main_menu(update)
            
    async def _go_to_main_menu(self, update):
        """Go back to main menu"""
        user = update.effective_user
        user_id = user.id
        
        if self.is_admin(user_id):
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men sizga konkurs botlari yaratib beradigan botman.\n"
                "Kerakli bo'limni tanlang:"
            )
            
            keyboard = [
                [KeyboardButton("🤖 Botlarni boshqarish"), KeyboardButton("🏆 Konkurslar")],
                [KeyboardButton("⚙️ Admin panel")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
            
        else:
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men konkurs botlari yaratish xizmati botiman.\n\n"
                "❗️ Bot yaratish faqat adminlar uchun ruxsat etilgan.\n"
                "Agar sizga bot kerak bo'lsa, admin bilan bog'laning."
            )
            
            keyboard = [
                [KeyboardButton("📞 Admin bilan bog'lanish")]
            ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def _handle_bot_name_selection(self, update, context, message_text):
        """Handle bot name selection from keyboard"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            return  # Just ignore non-admin messages instead of replying
            
        # Get user's bots
        bots = self.database.get_user_bots(user_id)
        
        # Find matching bot by name (removing status emoji)
        selected_bot = None
        for bot in bots:
            bot_display_name = f"✅ {bot['name']}" if bot['active'] else f"❌ {bot['name']}"
            if message_text == bot_display_name:
                selected_bot = bot
                break
                
        if selected_bot:
            await self._show_individual_bot_management(update, selected_bot['id'])
        # Remove the else block that was causing the problem message

    async def _show_individual_bot_management(self, update, bot_id: int):
        """Show individual bot management options"""
        bot = self.database.get_bot_by_id(bot_id)
        if not bot:
            await update.message.reply_text("❌ Bot topilmadi!")
            return
            
        text = (
            f"🤖 **{bot['name']} - Bot boshqaruvi**\n\n"
            f"🔗 Username: @{bot['username']}\n"
            f"📊 Status: {'✅ Faol' if bot['active'] else '❌ Nofaol'}\n"
            f"📅 Yaratilgan: {bot['created_at']}\n\n"
            f"Kerakli amalni tanlang:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Statistika", callback_data=f"bot_action_stats_{bot_id}")],
            [InlineKeyboardButton("🏆 Konkurslar", callback_data=f"bot_action_contests_{bot_id}")],
            [InlineKeyboardButton("⚙️ Bot sozlamalari", callback_data=f"bot_action_settings_{bot_id}")],
            [InlineKeyboardButton("📢 Broadcast", callback_data=f"bot_action_broadcast_{bot_id}")],
            [InlineKeyboardButton("📥 Excel yuklash", callback_data=f"bot_action_export_{bot_id}")],
            [InlineKeyboardButton("📱 Obuna sozlamalari", callback_data=f"bot_action_subscription_{bot_id}")],
            [InlineKeyboardButton("🔗 Referral sozlamalari", callback_data=f"bot_action_referral_settings_{bot_id}")],
            [InlineKeyboardButton("🔄 Qayta ishga tushirish", callback_data=f"bot_action_restart_{bot_id}")],
            [InlineKeyboardButton("🗑 O'chirish", callback_data=f"bot_action_delete_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_back_to_bots(self, query):
        """Handle back to bots list"""
        user_id = query.from_user.id
        await self._handle_my_bots_callback(query, None)
        
    async def _handle_back_to_menu(self, query):
        """Handle back to main menu"""
        user = query.from_user
        user_id = user.id
        
        if self.is_admin(user_id):
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men sizga konkurs botlari yaratib beradigan botman.\n"
                "Kerakli bo'limni tanlang:"
            )
            
            keyboard = [
                [InlineKeyboardButton("🤖 Botlarni boshqarish", callback_data="my_bots")],
                [InlineKeyboardButton("⚙️ Admin panel", callback_data="admin_panel")],
                [InlineKeyboardButton("🇺🇿 Qo'llanma", callback_data="help_info")]
            ]
            
        else:
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men konkurs botlari yaratish xizmati botiman.\n\n"
                "❗️ Bot yaratish faqat adminlar uchun ruxsat etilgan.\n"
                "Agar sizga bot kerak bo'lsa, admin bilan bog'laning."
            )
            
            keyboard = [
                [InlineKeyboardButton("📞 Admin bilan bog'lanish", callback_data="contact_admin")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)
        
    async def _handle_back_to_main_menu_keyboard(self, query):
        """Handle back to main menu from keyboard"""
        user = query.from_user
        user_id = user.id
        
        if self.is_admin(user_id):
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men sizga konkurs botlari yaratib beradigan botman.\n"
                "Kerakli bo'limni tanlang:"
            )
            
            keyboard = [
                [KeyboardButton("🤖 Botlarni boshqarish"), KeyboardButton("🏆 Konkurslar")],
                [KeyboardButton("⚙️ Admin panel")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
            
        else:
            welcome_text = (
                f"Salom {user.first_name}! 🤖\n\n"
                "Men konkurs botlari yaratish xizmati botiman.\n\n"
                "❗️ Bot yaratish faqat adminlar uchun ruxsat etilgan.\n"
                "Agar sizga bot kerak bo'lsa, admin bilan bog'laning."
            )
            
            keyboard = [
                [KeyboardButton("📞 Admin bilan bog'lanish")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)
        
    async def _handle_back_to_bot_menu(self, query):
        """Handle back to bot menu"""
        user_id = query.from_user.id
        await self._show_bot_management_menu_inline(query)
        
    async def _show_bot_management_menu_inline(self, query):
        """Show bot management menu with inline keyboard"""
        user_id = query.from_user.id
        
        if not self.is_admin(user_id):
            await query.edit_message_text(
                "❌ Kechirasiz, bot boshqaruvi faqat adminlar uchun ruxsat etilgan.\n\n"
                "Admin bilan bog'laning."
            )
            return
            
        text = (
            "🤖 **Bot boshqaruvi menyusi**\n\n"
            "Kerakli bo'limni tanlang:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Botlar ro'yxati", callback_data="show_bots_list")],
            [InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")],
            [InlineKeyboardButton("🗑 Botni o'chirish", callback_data="delete_bot_menu")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _show_bot_statistics(self, query, bot_id: int):
        """Show bot statistics when bot is selected from list"""
        bot = self.database.get_bot_by_id(bot_id)
        if not bot:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        # Get bot statistics
        contests_count = len(self.database.get_bot_contests(bot_id)) if hasattr(self.database, 'get_bot_contests') else 0
        total_participants = 0
        active_contests = 0
        
        # Calculate total participants across all contests
        if hasattr(self.database, 'get_bot_contests'):
            contests = self.database.get_bot_contests(bot_id)
            for contest in contests:
                if hasattr(self.database, 'get_contest_participants_count'):
                    total_participants += self.database.get_contest_participants_count(contest.get('id', 0))
                if contest.get('active', False):
                    active_contests += 1
        
        status = "🟢 Faol" if bot['active'] else "🔴 Nofaol"
        
        stats_text = (
            f"🤖 **{bot['name']} - Statistika**\n\n"
            f"🔗 Username: @{bot['username']}\n"
            f"📊 Status: {status}\n"
            f"📅 Yaratilgan: {bot['created_at']}\n\n"
            f"📈 **Statistika:**\n"
            f"🏆 Jami konkurslar: {contests_count}\n"
            f"🟢 Faol konkurslar: {active_contests}\n"
            f"👥 Jami ishtirokchilar: {total_participants}\n\n"
            f"📝 {bot['description']}"
        )
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Bot sozlamalari", callback_data=f"manage_bot_{bot_id}")],
            [InlineKeyboardButton("🔙 Botlar ro'yxatiga", callback_data="show_bots_list")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_show_bots_list_callback(self, query):
        """Handle show bots list callback"""
        user_id = query.from_user.id
        
        bots = self.database.get_user_bots(user_id)
        
        if not bots:
            text = (
                "🤖 **Botlar ro'yxati**\n\n"
                "❌ Sizda hali botlar yo'q.\n\n"
                "Avval bot yarating!"
            )
            
            keyboard = [
                [InlineKeyboardButton("➕ Yangi bot yaratish", callback_data="create_new_bot")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
            
        # Create inline keyboard buttons for each bot with icons
        keyboard = []
        for bot in bots:
            status_emoji = "🟢" if bot['active'] else "🔴"
            bot_icon = "🤖"
            button_text = f"{bot_icon} {status_emoji} {bot['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"bot_stats_{bot['id']}")])
        
        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        bots_text = f"🤖 **Botlar ro'yxati ({len(bots)}/5)**\n\n"
        bots_text += "📊 Bot statistikasini ko'rish uchun botni tanlang:"
        
        await query.edit_message_text(bots_text, reply_markup=reply_markup, parse_mode='Markdown')

    def run(self):
        """Start the bot"""
        logger.info("Starting Telegram Bot Builder...")
        
        # Create application
        application = Application.builder().token(self.config.MAIN_BOT_TOKEN).build()
        
        # Set config and bot_factory in bot_data for access in handlers
        application.bot_data['config'] = self.config
        application.bot_data['bot_factory'] = self.bot_factory

        # Add error handler
        application.add_error_handler(self.error_handler.handle_error)

        # Add handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("create_bot", self.create_bot_command))
        application.add_handler(CommandHandler("my_bots", self.my_bots_command))
        application.add_handler(CommandHandler("cancel", self.cancel_command))
        application.add_handler(CommandHandler("admin", self.admin_command))
        application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        # Message handlers for different types of content
        application.add_handler(MessageHandler(filters.PHOTO, self.handle_media_message))
        application.add_handler(MessageHandler(filters.VIDEO, self.handle_media_message))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Start existing contest bots
        async def post_init(app):
            # Clear pending updates first to avoid conflicts
            try:
                logger.info("Clearing pending updates...")
                await app.bot.get_updates(offset=-1, limit=1)
                logger.info("✅ Cleared pending updates")
            except Exception as e:
                logger.warning(f"Could not clear updates: {e}")
            
            # Create initial backup
            try:
                logger.info("Creating initial backup...")
                self.backup_manager.auto_backup(compress=True, cleanup=True)
            except Exception as e:
                logger.error(f"Could not create initial backup: {e}")
            
            await self.bot_factory.start_all_existing_bots()
             
        application.post_init = post_init

        # Start bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def _show_all_contests(self, update):
        """Show all created contest bots as contests"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(
                "❌ Kechirasiz, konkurslar bo'limi faqat adminlar uchun ruxsat etilgan.\n\n"
                "Admin bilan bog'laning."
            )
            return
        
        # Get all bots (each bot is a contest)
        bots = self.database.get_all_bots_admin()
        
        if not bots:
            await update.message.reply_text(
                "🚫 Hozircha konkurs botlari yo'q!\n\n"
                "Konkurs yaratish uchun avval bot yaratishingiz kerak."
            )
            return
        
        text = "🏆 <b>Barcha konkurs botlari:</b>\n\n"
        
        for i, bot in enumerate(bots, 1):
            status = "✅ Faol" if bot['active'] else "❌ Faol emas"
            
            # Escape HTML characters for safety
            bot_name = str(bot['name']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            bot_username = str(bot['username']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;') if bot['username'] else 'N/A'
            owner_name = str(bot['owner_name']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            
            text += (
                f"<b>{i}. {bot_name}</b>\n"
                f"   🤖 Bot: @{bot_username}\n"
                f"   👤 Egasi: {owner_name}\n"
                f"   📅 Yaratilgan: {bot['created_at']}\n"
                f"   📊 Holat: {status}\n"
                f"   🏆 Ishtirokchilar: {bot['contests_count']}\n\n"
            )
            
        # Send message without inline keyboard buttons
        await update.message.reply_text(text, parse_mode='HTML')

    async def _handle_contest_bot_callback(self, query, context):
        """Handle contest bot selection"""
        bot_id = int(query.data.split("_")[2])
        
        # Get bot details
        bot = self.database.get_bot_by_id(bot_id)
        if not bot:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        # Show bot details as contest details
        status = "✅ Faol" if bot['active'] else "❌ Faol emas"
        
        # Escape HTML characters
        bot_name = str(bot['name']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
        bot_username = str(bot['username']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;') if bot['username'] else 'N/A'
        
        text = f"🏆 <b>Konkurs: {bot_name}</b>\n\n"
        text += f"🤖 <b>Bot:</b> @{bot_username}\n"
        text += f"📊 <b>Holat:</b> {status}\n"
        text += f"📅 <b>Yaratilgan:</b> {bot['created_at']}\n"
        text += f"🏆 <b>Ishtirokchilar soni:</b> {bot.get('contests_count', 0)}\n\n"
        
        if bot['active']:
            text += "✅ Bu konkurs hozir faol va ishtirokchilar qabul qilinmoqda."
        else:
            text += "❌ Bu konkurs hozir faol emas."
            
        keyboard = [
            [InlineKeyboardButton("📊 Batafsil statistika", callback_data=f"bot_action_stats_{bot_id}")],
            [InlineKeyboardButton("⚙️ Sozlamalar", callback_data=f"bot_action_settings_{bot_id}")],
            [InlineKeyboardButton("🔙 Konkurslarga qaytish", callback_data="refresh_contests")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _handle_refresh_contests(self, query):
        """Refresh contests list"""
        # Get all bots (each bot is a contest)
        bots = self.database.get_all_bots_admin()
        
        if not bots:
            await query.edit_message_text(
                "🚫 Hozircha konkurs botlari yo'q!\n\n"
                "Konkurs yaratish uchun avval bot yaratishingiz kerak."
            )
            return
        
        text = "🏆 <b>Barcha konkurs botlari:</b>\n\n"
        
        for i, bot in enumerate(bots, 1):
            status = "✅ Faol" if bot['active'] else "❌ Faol emas"
            
            # Escape HTML characters for safety
            bot_name = str(bot['name']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            bot_username = str(bot['username']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;') if bot['username'] else 'N/A'
            owner_name = str(bot['owner_name']).replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
            
            text += (
                f"<b>{i}. {bot_name}</b>\n"
                f"   🤖 Bot: @{bot_username}\n"
                f"   👤 Egasi: {owner_name}\n"
                f"   📅 Yaratilgan: {bot['created_at']}\n"
                f"   📊 Holat: {status}\n"
                f"   🏆 Ishtirokchilar: {bot['contests_count']}\n\n"
            )
            
        # Create inline keyboard for bot management
        keyboard = []
        for bot in bots[:10]:  # Show first 10 bots as buttons
            bot_name_short = bot['name'][:20] + "..." if len(bot['name']) > 20 else bot['name']
            keyboard.append([InlineKeyboardButton(
                f"🤖 {bot_name_short}", 
                callback_data=f"contest_bot_{bot['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔄 Yangilash", callback_data="refresh_contests")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    
    async def _handle_edit_welcome(self, query, context):
        """Handle start message editing"""
        bot_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return
            
        bot_info = self.database.get_bot_by_id(bot_id)
        if not bot_info:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        # Get current welcome message
        settings = self.database.get_bot_settings(bot_id)
        current_welcome = settings.get('welcome_message', 'Hozirda standart xabar ishlatilmoqda')
        
        text = (
            f"📨 **{bot_info['name']} - Start xabarini tahrirlash**\n\n"
            f"**Joriy xabar:**\n{current_welcome}\n\n"
            f"Yangi start xabarini yozing. Bu xabar foydalanuvchilar /start "
            f"bosganda ko'rinadi.\n\n"
            f"💡 **Maslahat:** Qisqa va tushunarli bo'lsin!"
        )
        
        # Set editing mode
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        context.user_data[user_id] = {
            'editing_mode': 'welcome_message',
            'bot_id': bot_id
        }
        
        await query.edit_message_text(text, parse_mode='Markdown')
        
    async def _handle_edit_name(self, query, context):
        """Handle bot name editing"""
        bot_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return
            
        bot_info = self.database.get_bot_by_id(bot_id)
        if not bot_info:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        text = (
            f"📛 **{bot_info['name']} - Bot nomini tahrirlash**\n\n"
            f"**Joriy nom:** {bot_info['name']}\n\n"
            f"Yangi bot nomini kiriting:"
        )
        
        # Set editing mode
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        context.user_data[user_id] = {
            'editing_mode': 'bot_name',
            'bot_id': bot_id
        }
        
        await query.edit_message_text(text, parse_mode='Markdown')
        
    async def _handle_edit_description(self, query, context):
        """Handle bot description editing"""
        bot_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        
        if not self.is_admin(user_id):
            await query.edit_message_text("❌ Ruxsat yo'q!")
            return
            
        bot_info = self.database.get_bot_by_id(bot_id)
        if not bot_info:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        description_text = bot_info.get('description', "Tavsif yo'q")
        text = (
            f"📝 **{bot_info['name']} - Tavsifni tahrirlash**\n\n"
            f"**Joriy tavsif:** {description_text}\n\n"
            f"Yangi bot tavsifini kiriting:"
        )
        
        # Set editing mode
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        context.user_data[user_id] = {
            'editing_mode': 'bot_description',
            'bot_id': bot_id
        }
        
        await query.edit_message_text(text, parse_mode='Markdown')
        
    async def _handle_editing_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle editing input for bot settings"""
        user_id = update.effective_user.id
        user_data = context.user_data.get(user_id, {})
        editing_mode = user_data.get('editing_mode')
        bot_id = user_data.get('bot_id')
        
        if not editing_mode or not bot_id:
            return
        
        # Rate limit check for edit actions
        is_allowed, cooldown = self.rate_limiter.check_rate_limit(user_id, 'edit_action')
        if not is_allowed:
            await update.message.reply_text(
                f"⏳ Juda ko'p tahrirlash qilyapsiz!\n\n"
                f"Iltimos {cooldown} soniya kuting."
            )
            return
            
        if editing_mode == 'referral_share':
            await self._handle_referral_share_submission(update, context)
            return

        text = (update.message.text or "").strip()

        bot_info = self.database.get_bot_by_id(bot_id)
        if not bot_info:
            await update.message.reply_text("❌ Bot topilmadi!")
            context.user_data[user_id] = {}
            return
            
        try:
            if editing_mode == 'welcome_message':
                # Validate message text
                is_valid, error_msg = self.validator.validate_message_text(text)
                if not is_valid:
                    await update.message.reply_text(error_msg)
                    return
                
                # Sanitize input
                text = self.validator.sanitize_text(text)
                
                success = self.database.update_welcome_message(bot_id, text)
                if success:
                    await update.message.reply_text(
                        f"✅ **Start xabari yangilandi!**\n\n"
                        f"🤖 Bot: {bot_info['name']}\n"
                        f"📨 **Yangi xabar:**\n{text}\n\n"
                        f"Endi foydalanuvchilar /start bosganda bu xabar ko'rinadi.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("❌ Start xabarini yangilashda xatolik!")
                    
            elif editing_mode == 'bot_name':
                # Validate bot name
                is_valid, error_msg = self.validator.validate_bot_name(text)
                if not is_valid:
                    await update.message.reply_text(error_msg)
                    return
                
                # Sanitize input
                text = self.validator.sanitize_text(text)
                
                success = self.database.update_bot_info(bot_id, name=text)
                if success:
                    await update.message.reply_text(
                        f"✅ **Bot nomi yangilandi!**\n\n"
                        f"📛 Yangi nom: {text}\n"
                        f"🆔 Bot ID: {bot_id}",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("❌ Bot nomini yangilashda xatolik!")
                    
            elif editing_mode == 'bot_description':
                # Validate description
                is_valid, error_msg = self.validator.validate_description(text)
                if not is_valid:
                    await update.message.reply_text(error_msg)
                    return
                
                # Sanitize input
                text = self.validator.sanitize_text(text)
                
                success = self.database.update_bot_info(bot_id, description=text)
                if success:
                    await update.message.reply_text(
                        f"✅ **Bot tavsifi yangilandi!**\n\n"
                        f"📝 Yangi tavsif: {text}\n"
                        f"🆔 Bot ID: {bot_id}",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text("❌ Bot tavsifini yangilashda xatolik!")
                    
        except Exception as e:
            logger.error(f"Error updating bot info: {e}")
            await update.message.reply_text("❌ Tahrirlashda xatolik yuz berdi!")
        
        # Clear editing state
        context.user_data[user_id] = {}


if __name__ == '__main__':
    bot_builder = TelegramBotBuilder()
    bot_builder.run()
