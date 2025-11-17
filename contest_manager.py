"""
Contest Manager - Handles contest operations for individual bots
"""
import asyncio
import logging
import sqlite3
import os
import openpyxl
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Bot
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from excel_exporter import ExcelExporter
from subscription_manager import SubscriptionManager
from broadcast_manager import BroadcastManager

logger = logging.getLogger(__name__)

class ContestManager:
    """Manages contests for individual bots"""
    
    def __init__(self, database, bot_id: int):
        self.database = database
        self.bot_id = bot_id
        self.excel_exporter = ExcelExporter(database)
        self.subscription_manager = SubscriptionManager(database)
        self.broadcast_manager = BroadcastManager(database)
        self._last_message_content = {}  # Track last message content to avoid duplicate edits
        self.default_phone_request_message = (
            "🎉 **Juda yaxshi!**\n\n"
            "Sizga bog'lana olishimiz uchun pastdagi \"📲 Raqamni ulashish\" tugmasini bosib telefon "
            "raqamingizni yuboring yoki raqamingizni 90 123 45 67 kabi yozib yuboring."
        )
        self.default_phone_post_message = (
            "🎉 **Xush kelibsiz!**\n\n"
            "✅ Barcha tekshiruvlar muvaffaqiyatli o'tdi!\n\n"
            "🏆 Endi konkursda ishtirok eta olasiz!\n"
            "👇 Quyidagi tugmalardan birini tanlang:"
        )
        self.default_manual_text = (
            "🇺🇿 **{bot_name} botidan foydalanish bo'yicha qo'llanma**\n\n"
            "1️⃣ /start buyrug'ini yuboring va ko'rsatmalarga amal qiling.\n"
            "2️⃣ \"🏆 Konkurslar\" bo'limidan faol musobaqani tanlab ishtirok eting.\n"
            "3️⃣ Talab qilingan media (foto/video) va tavsifni yuboring.\n"
            "4️⃣ 📊 \"Mening hisobim\" orqali statistika va mukofotlaringizni kuzating.\n"
            "5️⃣ 🔗 \"Mening referral havolam\" tugmasi orqali do'stlaringizni taklif qilib bonus oling.\n\n"
            "❓ Savollar tug'ilsa, bot egasi bilan bog'laning. Omad!"
        )
        self.default_referral_share_text = (
            "🎁 Do'stlaringizni taklif qiling va bonus ballar oling!\n\n"
            "👥 Har bir do'stingiz uchun +1 ball\n"
            "🔗 Sizning referral havolangiz:\n{link}\n\n"
            "📊 Hozircha {count} ta do'stingiz ro'yxatdan o'tdi"
        )
        self.default_referral_followup_text = (
            "☝️ Yuqoridagi havolani do'stlaringizga yuboring\n"
            "✅ Har kim sizning havolangiz orqali botga kirsa, siz +1 ball olasiz!"
        )
        self.default_referral_button_text = "Qo'shilish"
        
    def _is_admin_user(self, user_id: int) -> bool:
        """Return True if user is bot owner or delegated admin."""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        if bot_info and user_id == bot_info.get('owner_id'):
            return True
        bot_admins = self.database.get_bot_admins(self.bot_id)
        return user_id in bot_admins

    def _get_user_state(self, context, user_id: int) -> Dict:
        """Ensure and return mutable state dict for the given user."""
        if not hasattr(context, 'user_data') or context.user_data is None:
            context.user_data = {}
        return context.user_data.setdefault(user_id, {})

    def _clear_phone_state(self, context, user_id: int) -> Dict:
        """Reset phone verification tracking for the user."""
        state = self._get_user_state(context, user_id)
        state.pop('phone_verified', None)
        state.pop('awaiting_phone', None)
        return state

    def _mark_phone_pending(self, context, user_id: int) -> Dict:
        """Mark that the user must re-share their phone number."""
        state = self._get_user_state(context, user_id)
        state['phone_verified'] = False
        state['awaiting_phone'] = True
        return state

    def _mark_phone_verified(self, context, user_id: int) -> Dict:
        """Mark that the user has satisfied the current phone request."""
        state = self._get_user_state(context, user_id)
        state['phone_verified'] = True
        state.pop('awaiting_phone', None)
        return state

    async def _remove_reply_keyboard_for_admin(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        """Hide the regular reply keyboard when entering admin flows."""
        if not hasattr(context, 'chat_data'):
            context.chat_data = {}
        chat_state = context.chat_data.setdefault(chat_id, {})

        if chat_state.get('admin_keyboard_removed'):
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text="🔐 Admin rejimi: foydalanuvchi menyusi yopildi.",
            reply_markup=ReplyKeyboardRemove()
        )
        chat_state['admin_keyboard_removed'] = True

    def _restore_reply_keyboard_flag(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
        """Allow future admin sessions to hide the keyboard again."""
        if not hasattr(context, 'chat_data'):
            context.chat_data = {}
        chat_state = context.chat_data.setdefault(chat_id, {})
        chat_state.pop('admin_keyboard_removed', None)

    async def _safe_edit_message(self, query, text, **kwargs):
        """Safely edit message to avoid duplicate content error"""
        message_id = query.message.message_id
        chat_id = query.message.chat_id
        key = f"{chat_id}_{message_id}"
        
        # Check if content is the same as last edit
        if key in self._last_message_content and self._last_message_content[key] == text:
            await query.answer()  # Just answer the callback to remove loading
            return

        try:
            # Clean text for safe parsing
            clean_text = text.replace('**', '*').replace('__', '_')
            await query.edit_message_text(clean_text, **kwargs)
            self._last_message_content[key] = text
        except Exception as e:
            if "Message is not modified" in str(e):
                await query.answer()  # Just answer the callback
            elif "can't parse entities" in str(e).lower():
                logger.error(f"Parse error, trying without markdown: {e}")
                try:
                    # Try without parse_mode if markdown fails
                    kwargs_no_parse = kwargs.copy()
                    kwargs_no_parse.pop('parse_mode', None)
                    await query.edit_message_text(text, **kwargs_no_parse)
                    self._last_message_content[key] = text
                except Exception as e2:
                    logger.error(f"Failed even without parse_mode: {e2}")
                    await query.answer("❌ Xatolik yuz berdi")
            else:
                logger.error(f"Error editing message: {e}")
                await query.answer("❌ Xatolik yuz berdi")

    def _get_phone_request_message(self, bot_settings: Dict = None) -> str:
        """Return phone request message from settings or default"""
        if bot_settings is None:
            bot_settings = self.database.get_bot_settings(self.bot_id)
        return bot_settings.get('phone_request_message') or self.default_phone_request_message

    def _get_phone_post_message(self, bot_settings: Dict = None) -> str:
        """Return post-phone verification message from settings or default"""
        if bot_settings is None:
            bot_settings = self.database.get_bot_settings(self.bot_id)
        return bot_settings.get('phone_post_message') or self.default_phone_post_message

    def _get_phone_menu_hint(self) -> str:
        """Return menu hint shown during phone verification."""
        return (
            "ℹ️ *Eslatma:*\n"
            "Menyu tugmalari qulaylik uchun ochiq. Telefon raqamini yubormaguningizcha asosiy funksiyalar bloklangan."
        )

    def _build_main_menu_buttons(self) -> List[List[KeyboardButton]]:
        """Return main menu buttons as rows for reply keyboards."""
        return [
            [KeyboardButton("🔗 Mening referral havolam")],
            [KeyboardButton("📊 Mening hisobim")],
            [KeyboardButton("📂 Qo'llanma")]
        ]

    def _build_main_menu_keyboard(self) -> ReplyKeyboardMarkup:
        """Construct the main menu reply keyboard."""
        return ReplyKeyboardMarkup(
            self._build_main_menu_buttons(),
            resize_keyboard=True,
            one_time_keyboard=False
        )

    def _build_phone_request_keyboard(self) -> ReplyKeyboardMarkup:
        """Construct phone request keyboard that still shows the main menu buttons."""
        main_buttons = self._build_main_menu_buttons()

        # Always keep the three main menu buttons visible even during phone request
        keyboard_layout = [[KeyboardButton("📲 Raqamni ulashish", request_contact=True)]]
        keyboard_layout.extend(main_buttons)

        return ReplyKeyboardMarkup(
            keyboard_layout,
            resize_keyboard=True,
            one_time_keyboard=False
        )

    def _get_referral_share_settings(self, bot_settings: Dict = None) -> Dict:
        """Return referral share configuration with defaults."""
        if bot_settings is None:
            bot_settings = self.database.get_bot_settings(self.bot_id)
        bot_info = self.database.get_bot_by_id(self.bot_id)
        return {
            'text': self._resolve_placeholders(
                bot_settings.get('referral_share_text') or self.default_referral_share_text,
                bot_info
            ),
            'followup_text': self._resolve_placeholders(
                bot_settings.get('referral_followup_text') or self.default_referral_followup_text,
                bot_info
            ),
            'button_text': bot_settings.get('referral_button_text') or self.default_referral_button_text,
            'media': bot_settings.get('referral_share_media'),
            'media_type': bot_settings.get('referral_share_media_type'),
        }

    def _get_manual_settings(self, bot_settings: Dict = None, bot_info: Dict = None) -> Dict:
        """Return manual/guide configuration with defaults applied."""
        if bot_settings is None:
            bot_settings = self.database.get_bot_settings(self.bot_id)
        if bot_info is None:
            bot_info = self.database.get_bot_by_id(self.bot_id)

        raw_text = bot_settings.get('guide_text') or self.default_manual_text
        resolved_text = self._resolve_placeholders(raw_text, bot_info)
        is_custom = bool(bot_settings.get('guide_text'))

        return {
            'text': resolved_text,
            'raw_text': raw_text,
            'media': bot_settings.get('guide_media'),
            'media_type': bot_settings.get('guide_media_type'),
            'is_custom': is_custom,
        }

    @staticmethod
    def _resolve_placeholders(template: str, bot_info: Dict = None) -> str:
        """Safely replace supported placeholders in text templates."""
        if not template:
            return ''

        replacements = {
            '{bot_name}': bot_info.get('name', '') if bot_info else '',
        }

        resolved = template
        for placeholder, value in replacements.items():
            resolved = resolved.replace(placeholder, value)

        return resolved

    def _format_referral_share_text(
        self,
        template: str,
        referral_link: str,
        user,
        referral_count: int,
        bot_info: Dict,
        append_link: bool = True,
    ) -> str:
        """Inject dynamic placeholders into the referral share/follow-up text."""
        replacements = {
            'link': referral_link,
            'count': str(referral_count),
            'first_name': (user.first_name or '') if user else '',
            'last_name': (user.last_name or '') if user else '',
            'username': f"@{user.username}" if user and user.username else '',
            'bot_name': bot_info.get('name', '') if bot_info else '',
            'bot_username': bot_info.get('username', '') if bot_info else '',
        }

        formatted = template or ''
        for key, value in replacements.items():
            formatted = formatted.replace(f"{{{key}}}", value)

        # Don't append link if already in template
        if append_link and '{link}' not in (template or ''):
            formatted = formatted.rstrip() + f"\n\n🔗 {referral_link}"

        return formatted

    async def _send_referral_share_message(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        referral_link: str,
        user,
        referral_count: int,
    ) -> None:
        """Send the configured referral share message with optional media and button."""
        bot_settings = self.database.get_bot_settings(self.bot_id)
        share_settings = self._get_referral_share_settings(bot_settings)
        bot_info = self.database.get_bot_by_id(self.bot_id)
        text = self._format_referral_share_text(
            share_settings['text'], referral_link, user, referral_count, bot_info
        )
        followup_template = share_settings.get('followup_text') or ''

        button_text = share_settings['button_text'] or self.default_referral_button_text
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(button_text, url=referral_link)]
        ])

        async def _send_without_parse_mode():
            if share_settings['media'] and share_settings['media_type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=share_settings['media'],
                    caption=text,
                    reply_markup=reply_markup,
                )
            elif share_settings['media'] and share_settings['media_type'] == 'video':
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=share_settings['media'],
                    caption=text,
                    reply_markup=reply_markup,
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                )

        try:
            if share_settings['media'] and share_settings['media_type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=share_settings['media'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                )
            elif share_settings['media'] and share_settings['media_type'] == 'video':
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=share_settings['media'],
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown',
                )
        except BadRequest as send_error:
            if "can't parse entities" in str(send_error).lower():
                await _send_without_parse_mode()
            else:
                logger.error(f"Error sending referral share message: {send_error}")
                fallback_text = (
                    f"🔗 Sizning referral havolangiz:\n{referral_link}\n\n"
                    "Matnni yuborishda xatolik yuz berdi. Sozlamalarni tekshiring."
                )
                await context.bot.send_message(chat_id=chat_id, text=fallback_text)

        if followup_template.strip():
            followup_text = self._format_referral_share_text(
                followup_template,
                referral_link,
                user,
                referral_count,
                bot_info,
                append_link=False,
            )
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=followup_text,
                    parse_mode='Markdown',
                )
            except BadRequest as followup_error:
                if "can't parse entities" in str(followup_error).lower():
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=followup_text,
                    )
                else:
                    logger.error(f"Error sending referral follow-up message: {followup_error}")

    async def _send_manual_message(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        manual_settings: Dict,
    ) -> None:
        """Send the configured manual/guide content with optional media."""
        text = manual_settings['text']
        media = manual_settings['media']
        media_type = manual_settings['media_type']

        async def _send_without_parse_mode():
            if media and media_type == 'photo':
                await context.bot.send_photo(chat_id=chat_id, photo=media, caption=text)
            elif media and media_type == 'video':
                await context.bot.send_video(chat_id=chat_id, video=media, caption=text)
            else:
                await context.bot.send_message(chat_id=chat_id, text=text)

        try:
            if media and media_type == 'photo':
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=media,
                    caption=text,
                    parse_mode='Markdown'
                )
            elif media and media_type == 'video':
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=media,
                    caption=text,
                    parse_mode='Markdown'
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='Markdown'
                )
        except BadRequest as send_error:
            if "can't parse entities" in str(send_error).lower():
                await _send_without_parse_mode()
            else:
                logger.error(f"Error sending manual message: {send_error}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="📂 Qo'llanmani ko'rsatishda xatolik yuz berdi. Sozlamalarni tekshiring."
                )
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command with standardized bot builder flow"""
        user = update.effective_user
        user_id = user.id
        
        logger.info(f"Bot {self.bot_id} - Start command from user {user_id}")
        
        # Register user
        self.database.get_or_create_user(
            user.id, user.first_name, user.last_name, user.username
        )
        
        # Add user to bot_users table for broadcast tracking
        self.database.add_bot_user(self.bot_id, user_id)
        
        # Handle referral if present
        await self._handle_referral_start(update, context)
        
        # Get bot info and settings
        bot_info = self.database.get_bot_by_id(self.bot_id)
        bot_settings = self.database.get_bot_settings(self.bot_id)
        
        # Check if admin - they bypass all checks
        if self._is_admin_user(user_id):
            logger.info(f"Bot {self.bot_id} - Admin {user_id} bypassing all checks")
            await update.message.reply_text(
                "👑 **Admin panel**\n\n"
                "🔧 /admin - Boshqaruv paneli\n"
                "📋 /help - Yordam",
                parse_mode='Markdown'
            )
            return
        
        # Reset phone verification state so every /start requires fresh confirmation
        self._clear_phone_state(context, user_id)

        # STEP 1: Check mandatory channel subscriptions first
        subscription_enabled = bot_settings.get('subscription_enabled', False)
        if subscription_enabled:
            if not await self._check_required_subscriptions_with_custom_message(update, context, bot_info, bot_settings):
                return  # User needs to subscribe first
        
        # STEP 3: Check phone verification (faqat yoqilgan bo'lsa)
        phone_required = bot_settings.get('phone_required', False)
        if phone_required:
            if not await self._check_phone_verification(update, context):
                return  # User needs to verify phone first
        
        # STEP 4: Show main menu with referral and account buttons (2ta knopka faqat telefon tasdiqlagandan keyin)
        await self._show_main_menu(update, context)
        
        logger.info(f"Bot {self.bot_id} - Successfully completed start flow for user {user_id}")
        
    async def _show_welcome_message_with_subscription_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show welcome message, then enforce subscription and phone requirements."""
        if not update.message:
            return

        user = update.effective_user
        if not user:
            return

        bot_info = self.database.get_bot_by_id(self.bot_id)
        bot_settings = self.database.get_bot_settings(self.bot_id)

        custom_welcome = bot_settings.get('welcome_message', '')
        welcome_media = bot_settings.get('welcome_media', '')
        media_type = bot_settings.get('welcome_media_type', '')

        if custom_welcome:
            try:
                if welcome_media and media_type:
                    if media_type == 'photo':
                        await update.message.reply_photo(
                            photo=welcome_media,
                            caption=custom_welcome,
                            parse_mode='Markdown'
                        )
                    elif media_type == 'video':
                        await update.message.reply_video(
                            video=welcome_media,
                            caption=custom_welcome,
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_text(custom_welcome, parse_mode='Markdown')
                else:
                    await update.message.reply_text(custom_welcome, parse_mode='Markdown')
            except Exception as send_error:
                logger.error(f"Error sending welcome message: {send_error}")
                await update.message.reply_text(custom_welcome, parse_mode='Markdown')

        if not await self._check_required_subscriptions(update, context):
            return

        bot_settings = self.database.get_bot_settings(self.bot_id)
        phone_required = bot_settings.get('phone_required', False)
        is_admin = self._is_admin_user(user.id)

        if phone_required and not is_admin:
            self._mark_phone_pending(context, user.id)
            logger.info(f"Bot {self.bot_id} - Requesting phone during welcome for user {user.id}")
            await self._request_phone_number_after_start(update, context)
            return

        if is_admin:
            await update.message.reply_text(
                "👑 **Admin sifatida kirgansiz!**\n\n"
                "🔧 /admin - Admin panelga kirish\n"
                "📋 /help - Yordam\n\n"
                "🎉 Botdan bemalol foydalanishingiz mumkin!",
                parse_mode='Markdown'
            )
            return

        await self._show_final_welcome_with_buttons(update, context)

    async def _show_final_welcome_with_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show final welcome message with keyboard buttons"""
        keyboard = [
            [KeyboardButton("🔗 Mening referral havolam")],
            [KeyboardButton("📊 Mening hisobim")],
            [KeyboardButton("📂 Qo'llanma")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

        if update.effective_chat:
            self._restore_reply_keyboard_flag(context, update.effective_chat.id)
        
        await update.message.reply_text(
            "🎉 **Xush kelibsiz!**\n\n"
            "📋 /help - Yordam\n",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def _show_welcome_message(self, update: Update):
        """Show welcome message - only if custom message is set"""
        if not update.message:
            return

        bot_settings = self.database.get_bot_settings(self.bot_id)
        custom_welcome = bot_settings.get('welcome_message', '')
        welcome_media = bot_settings.get('welcome_media', '')
        media_type = bot_settings.get('welcome_media_type', '')
        
        if not custom_welcome:
            return
        
        try:
            if welcome_media and media_type:
                if media_type == 'photo':
                    await update.message.reply_photo(
                        photo=welcome_media,
                        caption=custom_welcome,
                        parse_mode='Markdown'
                    )
                elif media_type == 'video':
                    await update.message.reply_video(
                        video=welcome_media,
                        caption=custom_welcome,
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(custom_welcome, parse_mode='Markdown')
            else:
                await update.message.reply_text(custom_welcome, parse_mode='Markdown')
        except Exception as send_error:
            logger.error(f"Error sending welcome message with media: {send_error}")
            await update.message.reply_text(custom_welcome, parse_mode='Markdown')

    async def _show_welcome_message_for_callback(self, query):
        """Show welcome message for callback query - intentionally empty to avoid duplicates"""
        return

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries for admin panel and user actions"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        data = query.data

        if data == "check_subscription":
            await self._check_subscription_callback(query, context)
            return
        if data.startswith("channel_info"):
            channel_id = None
            if ':' in data:
                channel_id = data.split(':', 1)[1] or None
            await self._handle_channel_info_callback(query, channel_id)
            return
        if data == "request_phone":
            await self._request_phone_number_from_callback(query, context)
            return
        if data == "my_referral_link":
            await self._show_my_referral_link(query, context)
            return
        if data == "my_account":
            await self._show_my_account(query)
            return
        if data == "close_message":
            try:
                await query.message.delete()
            except Exception:
                await query.answer("✅", show_alert=False)
            return

        bot_info = self.database.get_bot_by_id(self.bot_id)
        if user_id != bot_info['owner_id']:
            await query.edit_message_text("❌ Faqat bot egasi admin paneliga kira oladi!")
            return

        await self._remove_reply_keyboard_for_admin(context, query.message.chat_id)

        if data == "admin":
            await self._handle_back(query, context)
        elif data == "admin_broadcast":
            await self._handle_broadcast(query, context)
        elif data == "admin_channels":
            await self._handle_channels(query, context)
        elif data == "admin_phone_settings":
            await self._handle_phone_settings(query, context)
        elif data == "admin_manual_settings":
            await self._handle_manual_settings(query, context)
        elif data == "admin_referral_settings":
            await self._handle_referral_settings(query, context)
        elif data == "admin_back":
            await self._handle_back(query, context)
        elif data.startswith("channel_") or data.startswith("remove_channel_") or data.startswith("edit_subscription_") or data.startswith("reset_subscription_"):
            await self._handle_channel_action(query, context)
        elif data.startswith("referral_"):
            if data == "referral_export":
                await self._export_referrals_excel(query, context)
            else:
                await self._handle_referral_action(query, context)
        elif data == "manual_edit":
            await self._start_manual_edit(query, context)
        elif data == "manual_cancel_edit":
            await self._cancel_manual_edit(query, context)
        elif data == "manual_preview":
            await self._handle_manual_preview(query, context)
        elif data == "manual_reset_default":
            await self._reset_manual_to_default(query, context)
        elif data == "admin_statistics":
            await self._handle_statistics(query, context)
        elif data == "admin_restart_bot":
            await self._handle_restart_bot(query, context)
        elif data == "admin_edit_welcome":
            await self._handle_edit_welcome_direct(query, context)
        elif data == "admin_export_excel":
            await self._handle_export_excel(query, context)
        elif data == "admin_export_users":
            await self._export_users_excel(query, context)
        elif data == "admin_export_referrals":
            await self._export_referrals_only_excel(query, context)
        elif data.startswith("contest_"):
            await self._handle_contest_action(query, context)
        elif data.startswith("phone_"):
            await self._handle_phone_action(query, context)
        elif data.startswith("settings_"):
            await self._handle_settings_action(query, context)
        elif data.startswith("winner_"):
            await self._handle_winner_action(query, context)
        elif data == "detailed_stats":
            await self._handle_detailed_stats(query, context)
        elif data == "add_new_channel":
            await self._handle_add_new_channel(query, context)
    async def _handle_participants(self, query, context):
        """Show participants list"""
        participants = self.database.get_all_participants(self.bot_id)
        
        text = f"👥 **Ishtirokchilar ({len(participants)} ta)**\n\n"
        
        if participants:
            for i, participant in enumerate(participants[:10], 1):  # Faqat 10 ta ko'rsatish
                text += f"{i}. {participant['first_name']}"
                if participant.get('last_name'):
                    text += f" {participant['last_name']}"
                if participant.get('username'):
                    text += f" (@{participant['username']})"
                text += f" - {participant['joined_at'][:10]}\n"
            
            if len(participants) > 10:
                text += f"\n... va yana {len(participants) - 10} ta ishtirokchi"
        else:
            text += "❌ Hozircha ishtirokchilar yo'q"
            
        keyboard = [
            [InlineKeyboardButton("📥 Xabar yuborish", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _handle_select_winners(self, query, context):
        """Handle winner selection"""
        text = (
            "🏆 **G'oliblarni aniqlash**\n\n"
            "G'olib tanlash usulini tanlang:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎲 Tasodifiy tanlash", callback_data="winner_random")],
            [InlineKeyboardButton("👑 Qo'lda tanlash", callback_data="winner_manual")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        

        
    async def _handle_export_excel(self, query, context):
        """Show Excel export options menu"""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        
        text = f"📥 **{bot_info.get('name', 'Bot')} - Excel eksport**\n\n"
        text += "📊 Qaysi ma'lumotlarni eksport qilmoqchisiz?"
        
        keyboard = [
            [InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_export_users")],
            [InlineKeyboardButton("🔗 Referral qo'shganlar", callback_data="admin_export_referrals")],
            [InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _export_users_excel(self, query, context):
        """Export all users data to Excel"""
        try:
            await query.answer("📊 Excel fayl tayyorlanmoqda...", show_alert=True)
            
            import os
            from excel_exporter import ExcelExporter
            
            exporter = ExcelExporter(self.database)
            bot_info = self.database.get_bot_by_id(self.bot_id)
            
            file_path = exporter.export_users_only(self.bot_id)
            
            if not os.path.exists(file_path):
                await query.answer("❌ Excel fayl yaratishda xatolik!", show_alert=True)
                return
            
            with open(file_path, 'rb') as file:
                await context.bot.send_document(
                    chat_id=query.from_user.id,
                    document=file,
                    filename=f"{bot_info.get('name', 'bot')}_foydalanuvchilar.xlsx",
                    caption=f"� **{bot_info.get('name', 'Bot')}** - Barcha foydalanuvchilar",
                    parse_mode='Markdown'
                )
            
            await query.edit_message_text("✅ Excel fayl muvaffaqiyatli yuborildi!")
            
        except Exception as e:
            logger.error(f"Error exporting users data: {e}")
            await query.answer("❌ Xatolik yuz berdi!", show_alert=True)
    
    async def _export_referrals_only_excel(self, query, context):
        """Export only referrals data to Excel"""
        try:
            await query.answer("📊 Excel fayl tayyorlanmoqda...", show_alert=True)
            
            import os
            from excel_exporter import ExcelExporter
            
            exporter = ExcelExporter(self.database)
            bot_info = self.database.get_bot_by_id(self.bot_id)
            
            file_path = exporter.export_referrals_only(self.bot_id)
            
            if not os.path.exists(file_path):
                await query.answer("❌ Excel fayl yaratishda xatolik!", show_alert=True)
                return
            
            with open(file_path, 'rb') as file:
                await context.bot.send_document(
                    chat_id=query.from_user.id,
                    document=file,
                    filename=f"{bot_info.get('name', 'bot')}_referrallar.xlsx",
                    caption=f"🔗 **{bot_info.get('name', 'Bot')}** - Referral qo'shganlar",
                    parse_mode='Markdown'
                )
            
            # Clean up - delete the file after sending
            try:
                os.remove(file_path)
            except Exception as cleanup_error:
                logger.error(f"File cleanup error: {cleanup_error}")
            
            # Update the message to show success
            await query.edit_message_text(
                "✅ **Excel fayl muvaffaqiyatli yuborildi!**\n\n"
                "📁 Fayl sizning shaxsiy chatga yuborildi.",
                parse_mode='Markdown'
            )
            
        except ImportError as e:
            logger.error(f"Excel exporter import error: {e}")
            await query.answer("❌ Excel eksport moduli topilmadi!", show_alert=True)
            await query.edit_message_text(
                "❌ **Xatolik yuz berdi!**\n\n"
                "Excel eksport funksiyasi ishlamayapti.\n"
                "Iltimos, admin bilan bog'laning.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Excel export error: {e}")
            await query.answer("❌ Excel eksportda xatolik!", show_alert=True)
            await query.edit_message_text(
                "❌ **Excel eksportda xatolik!**\n\n"
                f"Xatolik: {str(e)}\n\n"
                "Iltimos, qayta urinib ko'ring.",
                parse_mode='Markdown'
            )
            
    async def _handle_broadcast(self, query, context):
        """Handle broadcast message selection"""
        user_id = query.from_user.id
        
        text = (
            "📢 **Xabar yuborish**\n\n"
            "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing:\n"
            "(Matn, rasm yoki video yuborishingiz mumkin)"
        )
        
        # Set broadcast state directly
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        context.user_data[user_id] = {'broadcast_mode': True, 'broadcast_type': 'all_users'}
        
        await query.edit_message_text(text, parse_mode='Markdown')
        

        
    async def _handle_referral_settings(self, query, context):
        """Handle referral settings"""
        settings = self.database.get_bot_settings(self.bot_id)
        referral_enabled = settings.get('referral_enabled', True)
        share_custom = bool(settings.get('referral_share_text') or settings.get('referral_share_media'))
        followup_custom = bool(settings.get('referral_followup_text'))
        
        status = "✅ Faol" if referral_enabled else "❌ O'chiq"
        referral_count = self.database.get_bot_referral_count(self.bot_id)
        
        # Toggle button text based on current status
        toggle_text = "❌ O'chirish" if referral_enabled else "✅ Yoqish"
        toggle_callback = "referral_disable" if referral_enabled else "referral_enable"
        
        text = (
            f"🎁 **Referral tizimi**\n\n"
            f"Status: {status}\n"
            f"Jami referrallar: {referral_count}\n\n"
            f"Referral tizimi foydalanuvchilarga do'stlarini taklif qilish imkonini beradi.\n\n"
            f"📝 Ulashish xabari: {'✏️ Maxsus' if share_custom else '📘 Standart'}\n"
            f"📨 Follow-up matni: {'✏️ Maxsus' if followup_custom else '📘 Standart'}"
        )
        
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data=toggle_callback)],
            [InlineKeyboardButton("✏️ Referral xabarini tahrirlash", callback_data="referral_edit_share")],
            [InlineKeyboardButton("✏️ Follow-up matnini tahrirlash", callback_data="referral_edit_followup")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_manual_settings(self, query, context):
        """Show manual/guide configuration options."""
        try:
            bot_info = self.database.get_bot_by_id(self.bot_id)
            bot_settings = self.database.get_bot_settings(self.bot_id)
            manual = self._get_manual_settings(bot_settings, bot_info)

            raw_text = manual['raw_text'] or ''
            preview = raw_text[:400]
            if len(raw_text) > 400:
                preview += "…"
            safe_preview = preview.replace('```', "'''") or "Matn o'rnatilmagan."

            media_status = "🖼 Media ulanmagan."
            if manual['media']:
                media_label = manual['media_type'].upper() if manual['media_type'] else "MEDIA"
                media_status = f"🖼 Media turi: {media_label}"

            status_label = "✏️ Maxsus" if manual['is_custom'] else "📘 Standart"

            text = (
                "📂 **Qo'llanma sozlamalari**\n\n"
                f"Holat: {status_label}\n"
                f"{media_status}\n\n"
                "**Joriy matn namunasi:**\n"
                f"```\n{safe_preview}\n```\n\n"
                "Matn va rasm/video ni o'zgartirish uchun variantni tanlang."
            )

            keyboard = [
                [InlineKeyboardButton("👀 Qo'llanmani ko'rish", callback_data="manual_preview")],
                [InlineKeyboardButton("✏️ Qo'llanmani tahrirlash", callback_data="manual_edit")],
                [InlineKeyboardButton("♻️ Standart holatga qaytarish", callback_data="manual_reset_default")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
            ]

            await self._safe_edit_message(
                query,
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error in _handle_manual_settings: {e}")
            try:
                await query.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.", show_alert=True)
            except Exception:
                pass

    async def _start_manual_edit(self, query, context):
        """Initiate manual editing flow from admin panel."""
        try:
            user_id = query.from_user.id
            if not hasattr(context, 'user_data'):
                context.user_data = {}

            user_state = context.user_data.get(user_id, {})
            user_state['editing'] = 'manual_message'
            user_state['manual_edit'] = True
            user_state['manual_edit_message'] = {
                'chat_id': query.message.chat_id,
                'message_id': query.message.message_id,
            }
            context.user_data[user_id] = user_state

            bot_settings = self.database.get_bot_settings(self.bot_id)
            bot_info = self.database.get_bot_by_id(self.bot_id)
            manual = self._get_manual_settings(bot_settings, bot_info)

            current_text = manual['raw_text'] or "Matn o'rnatilmagan."
            safe_current = current_text.replace('```', "'''")
            media_status = "🖼 Hozircha media ulanmagan."
            if manual['media']:
                media_label = manual['media_type'].upper() if manual['media_type'] else "MEDIA"
                media_status = f"🖼 Joriy media: {media_label}"

            placeholders = "• {bot_name} — bot nomi"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Bekor qilish", callback_data="manual_cancel_edit")],
                [InlineKeyboardButton("⬅️ Qo'llanma sozlamalari", callback_data="admin_manual_settings")]
            ])

            instructions = (
                "✏️ **Qo'llanmani tahrirlash**\n\n"
                "Matn yuboring yoki rasm/video bilan caption yuboring.\n"
                "Faqat matn yuborsangiz, mavjud media o'chiriladi.\n\n"
                "🔁 **O'zgaruvchilar:**\n"
                f"{placeholders}\n\n"
                f"{media_status}\n\n"
                "**Joriy matn:**\n"
                f"```\n{safe_current}\n```\n\n"
                "Yangi kontentni yuboring."
            )

            await self._safe_edit_message(
                query,
                instructions,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error in _start_manual_edit: {e}")
            try:
                await query.answer("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.", show_alert=True)
            except Exception:
                pass

    async def _cancel_manual_edit(self, query, context):
        """Cancel manual editing and return to settings."""
        await query.answer("Bekor qilindi.")

        user_id = query.from_user.id
        if hasattr(context, 'user_data') and user_id in context.user_data:
            context.user_data[user_id].pop('editing', None)
            context.user_data[user_id].pop('manual_edit', None)
            context.user_data[user_id].pop('manual_edit_message', None)

        await self._handle_manual_settings(query, context)

    async def _handle_manual_edit_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Persist manual text/media provided by admin."""
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        user_state = getattr(context, 'user_data', {}).get(user_id, {})
        if user_state.get('editing') != 'manual_message':
            return

        message = update.message
        if not message:
            return

        text_content = message.text or message.caption
        photo = message.photo[-1] if message.photo else None
        video = message.video if message.video else None

        if not text_content:
            await message.reply_text(
                "❗ Matn bo'sh bo'lmasligi kerak. Caption yozing yoki oddiy matn yuboring."
            )
            return

        updates = {
            'guide_text': text_content,
            'guide_media': None,
            'guide_media_type': None,
        }

        if photo:
            updates['guide_media'] = photo.file_id
            updates['guide_media_type'] = 'photo'
        elif video:
            updates['guide_media'] = video.file_id
            updates['guide_media_type'] = 'video'

        success = self.database.update_bot_settings(self.bot_id, updates)

        if not success:
            await message.reply_text("❌ Qo'llanmani saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring.")
            return

        confirmation_text = (
            "✅ Qo'llanma yangilandi!\n"
            "👀 Natijani ko'rish uchun '👀 Qo'llanmani ko'rish' tugmasini bosing."
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👀 Qo'llanmani ko'rish", callback_data="manual_preview")],
            [InlineKeyboardButton("⬅️ Qo'llanma sozlamalari", callback_data="admin_manual_settings")]
        ])

        message_meta = user_state.get('manual_edit_message')
        if message_meta:
            try:
                await context.bot.edit_message_text(
                    confirmation_text,
                    chat_id=message_meta['chat_id'],
                    message_id=message_meta['message_id'],
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
            except Exception as exc:
                logger.warning(f"Could not edit manual instructions message: {exc}")
                await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=keyboard)
        else:
            await message.reply_text(confirmation_text, parse_mode='Markdown', reply_markup=keyboard)

        user_state.pop('editing', None)
        user_state.pop('manual_edit', None)
        user_state.pop('manual_edit_message', None)
        context.user_data[user_id] = user_state

    async def _handle_manual_preview(self, query, context):
        """Send manual content to the admin for preview."""
        try:
            await query.answer("Ko'rsatilmoqda...", show_alert=False)
            
            bot_settings = self.database.get_bot_settings(self.bot_id)
            bot_info = self.database.get_bot_by_id(self.bot_id)
            manual = self._get_manual_settings(bot_settings, bot_info)

            await self._send_manual_message(context, query.message.chat_id, manual)
        except Exception as e:
            logger.error(f"Error in _handle_manual_preview: {e}")
            try:
                await query.answer("❌ Qo'llanmani ko'rsatishda xatolik!", show_alert=True)
            except Exception:
                pass

    async def _reset_manual_to_default(self, query, context):
        """Reset manual content to defaults."""
        try:
            success = self.database.update_bot_settings(self.bot_id, {
                'guide_text': None,
                'guide_media': None,
                'guide_media_type': None,
            })

            if success:
                try:
                    await query.answer("✅ Standart qo'llanma tiklandi!", show_alert=False)
                except Exception:
                    pass
            else:
                try:
                    await query.answer("❌ Qo'llanmani tiklashda xatolik!", show_alert=True)
                except Exception:
                    pass

            await self._handle_manual_settings(query, context)
        except Exception as e:
            logger.error(f"Error in _reset_manual_to_default: {e}")
            try:
                await query.answer("❌ Xatolik yuz berdi!", show_alert=True)
            except Exception:
                pass
        
    async def _handle_bot_settings(self, query, context):
        """Handle general bot settings"""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        bot_settings = self.database.get_bot_settings(self.bot_id)
        
        # Get current welcome message
        current_welcome = bot_settings.get('welcome_message', 'Standart xabar ishlatilmoqda')
        if current_welcome is None:
            current_welcome = 'Standart xabar ishlatilmoqda'
        welcome_preview = current_welcome[:50] + "..." if len(current_welcome) > 50 else current_welcome
        
        text = (
            f"⚙️ **Bot sozlamalari**\n\n"
            f"📛 Nom: {bot_info['name']}\n"
            f"🤖 Username: @{bot_info['username']}\n"
            f"📝 Tavsif: {bot_info['description']}\n\n"
            f"🏠 **Joriy start xabari:**\n{welcome_preview}\n\n"
            f"Quyidagi sozlamalarni o'zgartirishingiz mumkin:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📝 Start xabarini o'zgartirish", callback_data="settings_welcome")],
            [InlineKeyboardButton("📛 Bot nomi/tavsifi", callback_data="settings_info")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _handle_contest_action(self, query, context):
        """Handle contest-specific actions"""
        # Bu yerda konkurs bilan bog'liq amallar
        pass
        
    async def _handle_back(self, query, context):
        """Handle back to main admin panel"""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        reply_markup = self._build_admin_main_keyboard()
        
        await self._remove_reply_keyboard_for_admin(context, query.message.chat_id)

        await query.edit_message_text(
            f"🔧 Admin Panel - {bot_info['name']}\n\n"
            f"Quyidagi amallardan birini tanlang:",
            reply_markup=reply_markup
        )
        
    async def _handle_phone_action(self, query, context):
        """Handle phone-related actions"""
        data = query.data
        
        if data == "phone_toggle_requirement":
            await self._toggle_phone_requirement(query, context)
        elif data == "phone_required":
            self.database.update_bot_settings(self.bot_id, {'require_phone': True})
            await query.answer("✅ Telefon raqami majburiy qilindi!")
            await self._handle_phone_settings(query, context)
        elif data == "phone_optional":
            self.database.update_bot_settings(self.bot_id, {'require_phone': False})
            await query.answer("✅ Telefon raqami ixtiyoriy qilindi!")
            await self._handle_phone_settings(query, context)
        elif data == "phone_edit_request":
            await self._start_phone_message_edit(query, context, 'phone_request_message')
        elif data == "phone_edit_post":
            await self._start_phone_message_edit(query, context, 'phone_post_message')
        elif data == "phone_cancel_edit":
            await self._cancel_phone_edit(query, context)
            
    async def _start_phone_message_edit(self, query, context, message_type: str):
        """Start editing phone related messages from admin panel"""
        await query.answer()

        user_id = query.from_user.id
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        user_state = context.user_data.get(user_id, {})
        user_state['editing'] = message_type
        context.user_data[user_id] = user_state

        bot_settings = self.database.get_bot_settings(self.bot_id)

        if message_type == 'phone_request_message':
            title = "Telefon so'rov matni"
            description = "Bu xabar foydalanuvchidan telefon raqamini so'raydi. Markdown ishlatishingiz mumkin."
            current_text = self._get_phone_request_message(bot_settings)
        else:
            title = "Xush kelibsiz matni"
            description = "Bu xabar telefon raqami tasdiqlangandan keyin foydalanuvchiga ko'rsatiladi. Markdown ishlatishingiz mumkin."
            current_text = self._get_phone_post_message(bot_settings)

        safe_current = current_text.replace('```', "'''")

        cancel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="phone_cancel_edit")]
        ])

        text = (
            f"✏️ **{title}ni tahrirlash**\n\n"
            f"{description}\n\n"
            f"**Joriy matn:**\n"
            f"```\n{safe_current}\n```\n\n"
            "Yangi matnni yuboring. Bekor qilish uchun pastdagi \"❌ Bekor qilish\" tugmasini bosing."
        )

        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=cancel_markup)

    async def _cancel_phone_edit(self, query, context):
        """Cancel phone message editing and return to phone settings"""
        await query.answer("Bekor qilindi.")

        user_id = query.from_user.id
        if hasattr(context, 'user_data') and user_id in context.user_data:
            context.user_data[user_id].pop('editing', None)

        text, reply_markup = self._build_phone_settings_message()
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    async def _start_referral_share_edit(self, query, context):
        """Start editing the referral share message from the admin panel."""
        await query.answer()

        user_id = query.from_user.id
        if not hasattr(context, 'user_data'):
            context.user_data = {}

        user_state = context.user_data.get(user_id, {})
        user_state['editing'] = 'referral_share_message'
        user_state['referral_share_edit'] = True
        context.user_data[user_id] = user_state

        bot_settings = self.database.get_bot_settings(self.bot_id)
        share_settings = self._get_referral_share_settings(bot_settings)

        current_text = share_settings['text'] or "Matn o'rnatilmagan."
        safe_current = current_text.replace('```', "'''")
        media_status = "🖼 Hozircha media ulanmagan."
        if share_settings['media']:
            media_type = share_settings['media_type'] or 'photo'
            media_status = f"🖼 Joriy media: {media_type.upper()}"

        placeholders = (
            "• {link} — foydalanuvchining referral havolasi\n"
            "• {count} — hozirgacha taklif qilganlar soni\n"
            "• {first_name} — foydalanuvchi ismi\n"
            "• {bot_name} — bot nomi"
        )

        cancel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="referral_cancel_edit")]
        ])

        instructions = (
            "✏️ **Referral xabarini tahrirlash**\n\n"
            "Matn yuboring yoki rasm/video bilan birga caption yuboring.\n"
            "Faqat matn yuborsangiz, mavjud media o'chiriladi.\n\n"
            "🔁 **O'zgaruvchilar:**\n"
            f"{placeholders}\n\n"
            f"{media_status}\n\n"
            "**Joriy matn:**\n"
            f"```\n{safe_current}\n```\n\n"
            "Yangi kontentni yuboring. Bekor qilish uchun pastdagi tugmadan foydalaning."
        )

        await query.edit_message_text(instructions, parse_mode='Markdown', reply_markup=cancel_markup)

    async def _start_referral_followup_edit(self, query, context):
        """Start editing the referral follow-up message from the admin panel."""
        await query.answer()

        user_id = query.from_user.id
        if not hasattr(context, 'user_data'):
            context.user_data = {}

        user_state = context.user_data.get(user_id, {})
        user_state['editing'] = 'referral_followup_message'
        user_state['referral_followup_edit'] = True
        context.user_data[user_id] = user_state

        bot_settings = self.database.get_bot_settings(self.bot_id)
        bot_info = self.database.get_bot_by_id(self.bot_id)
        current_template = bot_settings.get('referral_followup_text') or self.default_referral_followup_text
        current_text = self._resolve_placeholders(current_template, bot_info) or "Matn o'rnatilmagan."
        safe_current = current_text.replace('```', "'''")

        placeholders = (
            "• {link} — foydalanuvchining referral havolasi\n"
            "• {count} — hozirgacha taklif qilganlar soni\n"
            "• {first_name} — foydalanuvchi ismi\n"
            "• {bot_name} — bot nomi"
        )

        instructions = (
            "✏️ **Referral follow-up xabarini tahrirlash**\n\n"
            "Faqat matn yuboring. Markdown formatlash ishlaydi.\n\n"
            "🔁 **O'zgaruvchilar:**\n"
            f"{placeholders}\n\n"
            "ℹ️ Standart matnga qaytish uchun `default` yoki `standart` deb yuboring.\n\n"
            "**Joriy matn:**\n"
            f"```\n{safe_current}\n```\n\n"
            "Yangi matnni yuboring. Bekor qilish uchun pastdagi tugmadan foydalaning."
        )

        cancel_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Bekor qilish", callback_data="referral_cancel_edit")]
        ])

        await query.edit_message_text(instructions, parse_mode='Markdown', reply_markup=cancel_markup)

    async def _cancel_referral_edit(self, query, context):
        """Cancel referral share editing and return to referral settings."""
        await query.answer("Bekor qilindi.")

        user_id = query.from_user.id
        if hasattr(context, 'user_data') and user_id in context.user_data:
            context.user_data[user_id].pop('editing', None)
            context.user_data[user_id].pop('referral_share_edit', None)
            context.user_data[user_id].pop('referral_followup_edit', None)

        await self._handle_referral_settings(query, context)

    async def _handle_referral_share_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Persist referral share text/media sent by the admin."""
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        user_state = getattr(context, 'user_data', {}).get(user_id, {})

        message = update.message
        text = message.text or message.caption
        photo = message.photo[-1] if message.photo else None
        video = message.video if message.video else None

        if not text:
            await message.reply_text(
                "❗ Matn bo'sh bo'lmasligi kerak. Caption yozing yoki oddiy matn yuboring."
            )
            return

        updates = {
            'referral_share_text': text,
            'referral_share_media': None,
            'referral_share_media_type': None,
        }

        if photo:
            updates['referral_share_media'] = photo.file_id
            updates['referral_share_media_type'] = 'photo'
        elif video:
            updates['referral_share_media'] = video.file_id
            updates['referral_share_media_type'] = 'video'

        success = self.database.update_bot_settings(self.bot_id, updates)

        if not success:
            await message.reply_text("❌ Xabarni saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring.")
            return

        if hasattr(context, 'user_data') and user_id in context.user_data:
            context.user_data[user_id].pop('editing', None)
            context.user_data[user_id].pop('referral_share_edit', None)

        await message.reply_text(
            "✅ Referral ulashish xabari yangilandi!\n"
            "Natijani tekshirish uchun '🔗 Mening referral havolam' tugmasini bosing."
        )

        referral_link = self._generate_referral_link(user_id)
        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)
        await self._send_referral_share_message(
            context,
            message.chat_id,
            referral_link,
            user,
            referral_count,
        )

    async def _handle_referral_followup_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Persist referral follow-up text sent by the admin."""
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        user_state = getattr(context, 'user_data', {}).get(user_id, {})
        if user_state.get('editing') != 'referral_followup_message':
            return

        message = update.message
        if not message:
            return

        if message.photo or message.video:
            await message.reply_text("❗ Bu xabar faqat matn ko'rinishida tahrirlanadi. Iltimos, matn yuboring.")
            return

        text = (message.text or message.caption or '').strip()
        if not text:
            await message.reply_text("❗ Matn bo'sh bo'lmasligi kerak.")
            return

        if text.lower() in {'default', 'standart'}:
            updates = {'referral_followup_text': None}
        else:
            updates = {'referral_followup_text': text}

        success = self.database.update_bot_settings(self.bot_id, updates)
        if not success:
            await message.reply_text("❌ Xabarni saqlashda xatolik yuz berdi. Qaytadan urinib ko'ring.")
            return

        if hasattr(context, 'user_data') and user_id in context.user_data:
            context.user_data[user_id].pop('editing', None)
            context.user_data[user_id].pop('referral_followup_edit', None)

        await message.reply_text(
            "✅ Follow-up xabari yangilandi!\n"
            "Natijani tekshirish uchun '🔗 Mening referral havolam' tugmasini bosing."
        )

        referral_link = self._generate_referral_link(user_id)
        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)
        await self._send_referral_share_message(
            context,
            message.chat_id,
            referral_link,
            user,
            referral_count,
        )

    async def _handle_referral_action(self, query, context):
        """Handle referral-related actions"""
        data = query.data
        
        if data == "referral_enable":
            self.database.update_bot_settings(self.bot_id, {'referral_enabled': True})
            await query.answer("✅ Referral tizimi yoqildi!")
            await self._handle_referral_settings(query, context)
        elif data == "referral_disable":
            self.database.update_bot_settings(self.bot_id, {'referral_enabled': False})
            await query.answer("✅ Referral tizimi o'chirildi!")
            await self._handle_referral_settings(query, context)
        elif data == "referral_edit_share":
            await self._start_referral_share_edit(query, context)
        elif data == "referral_edit_followup":
            await self._start_referral_followup_edit(query, context)
        elif data == "referral_cancel_edit":
            await self._cancel_referral_edit(query, context)
            
    async def _handle_settings_action(self, query, context):
        """Handle settings-related actions"""
        data = query.data
        
        if data == "settings_welcome":
            user_id = query.from_user.id
            if not hasattr(context, 'user_data'):
                context.user_data = {}
            context.user_data[user_id] = {'editing_welcome': True}
            
            # Get current welcome message
            bot_settings = self.database.get_bot_settings(self.bot_id)
            current_welcome = bot_settings.get('welcome_message', 'Hozirda maxsus xabar ornatilmagan')
            
            text = (
                "📝 **Start xabarini tahrirlash**\n\n"
                f"**Joriy xabar:**\n{current_welcome}\n\n"
                "Yangi start xabarini yozing. Bu xabar foydalanuvchilar /start "
                "bosganda ko'rinadi.\n\n"
                "💡 Maslahat: Qisqa va tushunarli bo'lsin!"
            )
            await query.edit_message_text(text, parse_mode='Markdown')
            
        elif data == "settings_info":
            user_id = query.from_user.id
            if not hasattr(context, 'user_data'):
                context.user_data = {}
            context.user_data[user_id] = {'editing_info': True, 'step': 'name'}
            
            text = (
                "📛 **Bot ma'lumotlarini tahrirlash**\n\n"
                "Yangi bot nomini kiriting:"
            )
            await query.edit_message_text(text, parse_mode='Markdown')
            
    async def _handle_winner_action(self, query, context):
        """Handle winner selection actions"""
        data = query.data
        
        if data == "winner_random":
            await self._select_random_winners(query, context)
        elif data == "winner_manual":
            await self._show_manual_winner_selection(query, context)
            
    async def _select_random_winners(self, query, context):
        """Select random winners from participants"""
        participants = self.database.get_all_participants(self.bot_id)
        
        if not participants:
            await query.answer("❌ Ishtirokchilar yo'q!", show_alert=True)
            return
            
        text = (
            f"🎲 **Tasodifiy g'olib tanlash**\n\n"
            f"Jami ishtirokchilar: {len(participants)}\n\n"
            f"Nechta g'olib tanlashni xohlaysiz? (1-10)"
        )
        
        user_id = query.from_user.id
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        context.user_data[user_id] = {'selecting_winners': True, 'method': 'random'}
        
        await query.edit_message_text(text, parse_mode='Markdown')
        
    async def _show_manual_winner_selection(self, query, context):
        """Show manual winner selection interface"""
        participants = self.database.get_all_participants(self.bot_id)
        
        if not participants:
            await query.answer("❌ Ishtirokchilar yo'q!", show_alert=True)
            return
            
        text = f"👑 **Qo'lda g'olib tanlash**\n\n"
        text += f"Jami {len(participants)} ta ishtirokchi\n\n"
        
        # Show first 5 participants
        for i, p in enumerate(participants[:5], 1):
            text += f"{i}. {p['first_name']}"
            if p.get('username'):
                text += f" (@{p['username']})"
            text += "\n"
        
        if len(participants) > 5:
            text += f"\n... va yana {len(participants) - 5} ta"
            
        keyboard = [
            [InlineKeyboardButton("📋 To'liq ro'yxat", callback_data="winners_full_list")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_select_winners")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "📚 Yordam bo'limi:\n\n"
            "🏆 Konkurslar haqida:\n\n"
            "❓ Savollar bo'lsa admin bilan bog'laning"
        )
        await update.message.reply_text(help_text)
        
    def _build_admin_main_keyboard(self) -> InlineKeyboardMarkup:
        """Build the standard admin panel keyboard layout."""
        keyboard = [
            [InlineKeyboardButton("📝 Start xabarini tahrirlash", callback_data="admin_edit_welcome"),
             InlineKeyboardButton("📥 Ommaviy xabar", callback_data="admin_broadcast")],
            [InlineKeyboardButton("📊 Statistika", callback_data="admin_statistics"),
             InlineKeyboardButton("📺 Kanal boshqaruvi", callback_data="admin_channels")],
            [InlineKeyboardButton("📱 Telefon sozlamalari", callback_data="admin_phone_settings"),
             InlineKeyboardButton("🔗 Referral sozlamalari", callback_data="admin_referral_settings")],
            [InlineKeyboardButton("✏️ Qo'llanma xabarini tahrirlash", callback_data="admin_manual_settings"),
             InlineKeyboardButton("📋 Excel eksport", callback_data="admin_export_excel")],
            [InlineKeyboardButton("🔄 Botni qayta ishga tushirish", callback_data="admin_restart_bot")],
        ]
        return InlineKeyboardMarkup(keyboard)

    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle comprehensive admin panel for bot owner and admins"""
        user_id = update.effective_user.id
        bot_info = self.database.get_bot_by_id(self.bot_id)
        
        # Check if user is bot owner or admin
        bot_admins = self.database.get_bot_admins(self.bot_id)
        is_owner = user_id == bot_info['owner_id']
        is_admin = user_id in bot_admins
        
        if not is_owner and not is_admin:
            await update.message.reply_text(
                "❌ Faqat bot egasi va adminlar admin paneliga kira oladi!\n\n"
                "🔐 Admin huquqlari olish uchun bot egasiga murojaat qiling."
            )
            return
        
        # Determine access level
        access_badge = "👑 Ega" if is_owner else "👨‍💻 Admin"
            
        # Get current statistics for display
        stats = self.database.get_bot_detailed_stats(self.bot_id)
        
        reply_markup = self._build_admin_main_keyboard()

        admin_text = (
            f"🔧 **Professional Admin Panel**\n"
            f"🤖 Bot: {bot_info['name']}\n"
            f"👤 Sizning rolingiz: {access_badge}\n\n"
            f"🎯 **Boshqaruv markazini tanlang:**"
        )

        await self._remove_reply_keyboard_for_admin(context, update.effective_chat.id)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=admin_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    async def list_contests_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List active contests"""
        contests = self.database.get_active_contests(self.bot_id)
        
    async def join_contest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle contest joining"""
        # Get active contests for this bot
        contests = self.database.get_active_contests(self.bot_id)
        
        # Create inline keyboard for contest selection
        keyboard = []
        for contest in contests:
            keyboard.append([
                InlineKeyboardButton(
                    f"🏆 {contest['title']}", 
                    callback_data=f"join_contest_{contest['id']}"
                )
            ])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Quyidagi konkursga ishtirok etmoqchisiz?",
            reply_markup=reply_markup
        )
        
    async def referrals_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's referral statistics"""
        user_id = update.effective_user.id
        
        # Check if referrals are enabled
        referral_settings = self.database.get_bot_referral_settings(self.bot_id)
        if not referral_settings['enabled']:
            await update.message.reply_text("🚫 Referal tizimi yoqilmagan!")
            return
            
        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)
        referral_link = self._generate_referral_link(user_id)
        
        # Check if user was referred by someone
        referred_by = self.database.get_user_referred_by(self.bot_id, user_id)
        referred_text = ""
        if referred_by:
            # Get referrer info
            with self.database.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT first_name, last_name FROM users WHERE telegram_id = ?",
                    (referred_by,)
                )
                referrer = cursor.fetchone()
                if referrer:
                    referrer_name = f"{referrer['first_name']} {referrer['last_name'] or ''}".strip()
                    referred_text = f"👤 Sizni taklif qilgan: {referrer_name}\n\n"
        
        referral_text = (
            f"🎁 **Referal tizimi**\n\n"
            f"{referred_text}"
            f"👥 Sizning referallaringiz: **{referral_count}** ta\n\n"
            f"🔗 **Sizning referal havola:**\n"
            f"`{referral_link}`\n\n"
            f"📋 **Qanday ishlaydi:**\n"
            f"• Havolangizni do'stlaringizga yuboring\n"
            f"• Ular bot orqali ro'yxatdan o'tganda sizga +1 referal\n"
            f"• Referallar soni doimo ko'rsatiladi\n\n"
            f"💡 **Maslahat:** Havolani nusxalash uchun ustiga bosing!"
        )
        
        await update.message.reply_text(referral_text, parse_mode='Markdown')
        
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages and keyboard buttons"""
        user_id = update.effective_user.id
        text = update.message.text
        user_state = self._get_user_state(context, user_id)
        is_admin_user = self._is_admin_user(user_id)

        # Check if user is sending phone number as text
        if await self._handle_phone_number_text(update, context):
            return

        # Block other interactions until phone number is provided when required
        bot_settings = self.database.get_bot_settings(self.bot_id)
        phone_required = bot_settings.get('phone_required', False)
        if not is_admin_user and phone_required and not user_state.get('phone_verified'):
            self._mark_phone_pending(context, user_id)
            if update.effective_chat:
                self._restore_reply_keyboard_flag(context, update.effective_chat.id)
            await update.message.reply_text(
                self._get_phone_request_message(bot_settings),
                reply_markup=self._build_phone_request_keyboard(),
                parse_mode='Markdown'
            )
            await update.message.reply_text(
                self._get_phone_menu_hint(),
                parse_mode='Markdown'
            )
            return
        
        # Check if user is adding a channel
        user_data = getattr(context, 'user_data', {}).get(user_id, {})
        if user_data.get('adding_channel'):
            await self._handle_channel_input(update, context)
            return

        # Handle manual editing flow
        if user_data.get('editing') == 'manual_message':
            await self._handle_manual_edit_submission(update, context)
            return

        if user_data.get('editing') == 'referral_followup_message':
            await self._handle_referral_followup_submission(update, context)
            return

        # Handle referral share editing
        if user_data.get('editing') == 'referral_share_message':
            await self._handle_referral_share_submission(update, context)
            return
        
        # Handle specific keyboard buttons
        if text == "🔗 Mening referral havolam":
            await self.handle_referral_link(update, context)
            return
        elif text == "📊 Mening hisobim":
            await self.handle_my_account(update, context)
            return
        elif text == "📂 Qo'llanma":
            await self._handle_manual_view(update, context)
            return

        # Check if user is creating broadcast
        if self.broadcast_manager.is_user_creating_broadcast(user_id):
            await self.broadcast_manager.handle_broadcast_creation(update, context)
            return
        
        # Handle new editing states
        if user_data.get('editing'):
            await self._handle_editing_input(update, context)
            return
        elif user_data.get('editing_welcome_direct'):
            await self._handle_welcome_edit_direct(update, context)
            return
        
        # Handle keyboard buttons
        text = update.message.text
        logger.info(f"Received message from user {user_id}: '{text}'")
        
        # Handle keyboard button clicks
        if text == "🔗 Mening referral havolam":
            logger.info(f"User {user_id} pressed referral link button")
            await self._show_my_referral_link_keyboard(update, context)
            return
        elif text == "📊 Mening hisobim":
            logger.info(f"User {user_id} pressed account button")
            await self._show_my_account_keyboard(update)
            return
        elif text == "📂 Qo'llanma":
            await self._handle_manual_view(update, context)
            return

        if user_data.get('creating_contest'):
            await self._handle_contest_creation(update, context)
        elif user_data.get('broadcast_mode'):
            await self._handle_broadcast_message(update, context)
        elif user_data.get('editing_welcome'):
            await self._handle_welcome_edit(update, context)
        elif user_data.get('editing_info'):
            await self._handle_info_edit(update, context)
        elif user_data.get('selecting_winners'):
            await self._handle_winner_count(update, context)
        else:
            # Don't show help commands, just let user use inline keyboard from start command
            pass
            
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle photo submissions"""
        user_id = update.effective_user.id
        
        # Check if user is in broadcast mode
        user_data = getattr(context, 'user_data', {}).get(user_id, {})
        if user_data.get('broadcast_mode'):
            await self._handle_broadcast_message(update, context)
            return

        if user_data.get('editing') == 'manual_message':
            await self._handle_manual_edit_submission(update, context)
            return

        if user_data.get('editing') == 'referral_followup_message':
            await self._handle_referral_followup_submission(update, context)
            return

        if user_data.get('editing') == 'referral_share_message':
            await self._handle_referral_share_submission(update, context)
            return
    async def _handle_winner_selection_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
        """Handle winner selection process"""
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        if state['step'] == 'waiting_for_contest_selection':
            # User selected contest ID
            try:
                contest_id = int(text)
                contests = self.database.get_active_contests(self.bot_id)
                
                if not any(c['id'] == contest_id for c in contests):
                    await update.message.reply_text("❌ Noto'g'ri konkurs ID!")
                    return
                    
                # Get submissions for this contest
                submissions = self.database.get_contest_submissions_for_voting(contest_id)
                
                if not submissions:
                    await update.message.reply_text("❌ Bu konkursda hech qanday ishtirok yo'q!")
                    return
                    
                state['contest_id'] = contest_id
                state['submissions'] = submissions
                state['step'] = 'waiting_for_winners_count'
                
                await update.message.reply_text(
                    f"📊 Konkursda {len(submissions)} ta ishtirok bor.\n\n"
                    f"Nechta g'olib aniqlaysiz? (1-10)"
                )
                
            except ValueError:
                await update.message.reply_text("❌ Raqam kiriting!")
                
        elif state['step'] == 'waiting_for_winners_count':
            try:
                winners_count = int(text)
                if winners_count < 1 or winners_count > 10:
                    await update.message.reply_text("❌ G'oliblar soni 1 dan 10 gacha bo'lishi kerak!")
                    return
                    
                state['winners_count'] = winners_count
                state['selected_winners'] = []
                state['current_position'] = 1
                state['step'] = 'selecting_winners'
                
                # Show submissions for selection
                await self._show_submissions_for_selection(update, state)
                
            except ValueError:
                await update.message.reply_text("❌ Raqam kiriting!")
                
        elif state['step'] == 'selecting_winners':
            try:
                submission_id = int(text)
                submissions = state['submissions']
                
                submission = next((s for s in submissions if s['id'] == submission_id), None)
                if not submission:
                    await update.message.reply_text("❌ Noto'g'ri submission ID!")
                    return
                    
                # Add to winners
                state['selected_winners'].append({
                    'user_id': submission['user_id'],
                    'submission_id': submission_id,
                    'position': state['current_position'],
                    'participant_name': submission['participant_name']
                })
                
                state['current_position'] += 1
                
                if len(state['selected_winners']) >= state['winners_count']:
                    # All winners selected, confirm
                    await self._confirm_winners_selection(update, state)
                else:
                    # Select next winner
                    await self._show_submissions_for_selection(update, state)
                    
            except ValueError:
                await update.message.reply_text("❌ Raqam kiriting!")
        
    async def _announce_winners(self, contest_id: int, winners: List[Dict]):
        """Announce contest winners to all bot users"""
        contest = self.database.get_contest_by_id(contest_id)
        bot_info = self.database.get_bot_by_id(self.bot_id)
        
    async def _request_phone_number_after_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Request phone number when no mandatory channels but phone required"""
        keyboard = [
            [KeyboardButton("📱 Telefon raqamini yuborish", request_contact=True)]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        if update.effective_chat:
            self._restore_reply_keyboard_flag(context, update.effective_chat.id)
        
        await update.message.reply_text(
            "📱 **Telefon raqamingiz kerak!**\n\n"
            "Bu botdan foydalanish uchun telefon raqamingizni yuborishingiz kerak.\n\n"
            "🏆 Telefon raqami konkursda ishtirok etish uchun majburiy hisoblanadi.\n\n"
            "🔒 Ma'lumotlaringiz xavfsiz saqlanadi va faqat konkurs maqsadlarida ishlatiladi.\n\n"
            "👇 Quyidagi tugmani bosib telefon raqamingizni yuboring:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    async def _check_subscription_callback(self, query, context):
        """Check if user subscribed to mandatory channels"""
        user = query.from_user
        logger.info(f"Bot {self.bot_id} - Checking subscription for user {user.id}")

        if self._is_admin_user(user.id):
            await query.answer("✅ Admin uchun tekshiruv shart emas", show_alert=False)
            try:
                await query.message.delete()
            except Exception as delete_error:
                logger.debug(f"Admin subscription promptni o'chirishning iloji bo'lmadi: {delete_error}")
            return
        
        # Check required channels
        required_channels = self.database.get_required_channels(self.bot_id)
        
        if not required_channels:
            # No channels required, check phone requirement
            await query.answer("✅ Obuna tasdiqlandi!", show_alert=True)
            
            bot_settings = self.database.get_bot_settings(self.bot_id)
            phone_required = bot_settings.get('phone_required', False)
            
            logger.info(f"Bot {self.bot_id} - No channels required. phone_required={phone_required}, bot_settings={bot_settings}")
            
            if phone_required:
                self._mark_phone_pending(context, user.id)
                logger.info(f"Bot {self.bot_id} - Requesting phone number from user {query.from_user.id}")
                await self._request_phone_number_from_callback(query, context)
            else:
                logger.info(f"Bot {self.bot_id} - Showing final buttons without phone request")
                await self._show_final_buttons_after_subscription(query, context)
            return
        
        not_subscribed = []
        
        for channel in required_channels:
            try:
                # Handle both dict and tuple formats properly
                if isinstance(channel, dict):
                    channel_id = channel.get('channel_id') or channel.get('channel_username')
                    channel_name = channel.get('name') or channel.get('channel_name', 'Kanal')
                else:
                    # Tuple format: (id, channel_id, name, username, ...)
                    channel_id = channel[1] if len(channel) > 1 else None
                    channel_name = channel[2] if len(channel) > 2 else 'Kanal'
                
                if not channel_id:
                    logger.error(f"No channel_id found for channel: {channel}")
                    not_subscribed.append(channel)
                    continue
                
                # Clean channel_id if it has @ prefix
                if isinstance(channel_id, str) and channel_id.startswith('@'):
                    channel_id = channel_id[1:]
                
                # If it's a username, convert to @username for API call
                if isinstance(channel_id, str) and not channel_id.startswith('-'):
                    chat_id = f"@{channel_id}"
                else:
                    chat_id = channel_id
                
                member = await context.bot.get_chat_member(chat_id, user.id)
                logger.info(f"Callback check - User {user.id} status for {chat_id}: {member.status}")
                
                if member.status in ['left', 'kicked']:
                    not_subscribed.append(channel)
                    logger.info(f"User {user.id} is NOT subscribed to {chat_id}")
                else:
                    logger.info(f"User {user.id} IS subscribed to {chat_id}")
                    
            except Exception as e:
                logger.error(f"Error checking subscription for channel {channel}: {e}")
                not_subscribed.append(channel)
        
        if not_subscribed:
            # User is NOT subscribed - show message and update
            logger.info(f"User {user.id} not subscribed to {len(not_subscribed)} channels")
            
            # Answer callback without popup
            try:
                await query.answer()
                logger.info(f"Callback answered for user {user.id}")
            except Exception as e:
                logger.error(f"Failed to answer callback: {e}")
            
            # Update message with warning text
            try:
                warning_text = (
                    "⚠️ *Kanallarga obuna bo'lmadingiz!*\n\n"
                    "Iltimos, barcha majburiy kanallarga obuna bo'lib, "
                    "qaytadan *\"✅ Bajarildi\"* tugmasini bosing."
                )
                reply_markup = self._build_subscription_keyboard(not_subscribed)
                await query.edit_message_text(
                    text=warning_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as edit_error:
                logger.warning(f"Could not update subscription keyboard: {edit_error}")
        else:
            # All subscriptions verified
            logger.info(f"User {user.id} subscribed to all channels - proceeding")
            await query.answer("✅ Obuna tasdiqlandi!", show_alert=True)
            
            # Check phone requirement
            bot_settings = self.database.get_bot_settings(self.bot_id)
            phone_required = bot_settings.get('phone_required', False)
            
            logger.info(f"Bot {self.bot_id} - All channels verified. phone_required={phone_required}, bot_settings={bot_settings}")
            
            if phone_required:
                # Phone required - show phone request
                self._mark_phone_pending(context, user.id)
                logger.info(f"Bot {self.bot_id} - Requesting phone number from user {user.id}")
                await self._request_phone_number_from_callback(query, context)
            else:
                # No phone required - show final buttons
                logger.info(f"Bot {self.bot_id} - Showing final buttons without phone request")
                await self._show_final_buttons_after_subscription(query, context)
    
    async def _request_phone_number_from_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Request phone number from callback"""
        bot_settings = self.database.get_bot_settings(self.bot_id)
        instruction_text = self._get_phone_request_message(bot_settings)

        await query.answer()

        await query.message.reply_text(
            instruction_text,
            reply_markup=self._build_phone_request_keyboard(),
            parse_mode='Markdown'
        )

        self._restore_reply_keyboard_flag(context, query.message.chat_id)

        await query.message.reply_text(
            self._get_phone_menu_hint(),
            parse_mode='Markdown'
        )

        # Remove the previous inline message if possible
        try:
            await query.message.delete()
        except Exception as delete_error:
            logger.debug(f"Could not delete subscription message: {delete_error}")
        
    async def _show_final_welcome_message(self, query, user):
        """Show final welcome message with main menu after all checks passed"""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        bot_settings = self.database.get_bot_settings(self.bot_id)
        
        # Check if phone is required and user has phone
        phone_required = self.database.get_bot_phone_requirement(self.bot_id)
        
        if phone_required and not self.database.user_has_phone(user.id):
            # Phone is required but not provided - don't show final welcome yet
            return
        
        # Get custom welcome message - only show if set
        custom_welcome = bot_settings.get('welcome_message')
        
        reply_markup = self._build_main_menu_keyboard()
        
        # Show welcome message or default success message
        if custom_welcome:
            await self._safe_edit_message(query, custom_welcome, parse_mode='HTML')
            # Send keyboard as separate message
            await query.message.reply_text(
                "🎉 Botdan foydalanishni boshlashingiz mumkin:",
                reply_markup=reply_markup
            )
        else:
            # Show default success message with keyboard
            await self._safe_edit_message(query,
                "✅ **Obuna muvaffaqiyatli tasdiqlandi!**\n\n"
                "🎉 Endi botdan to'liq foydalanishingiz mumkin!\n"
                "👇 Quyidagi tugmalardan birini tanlang:",
                parse_mode='Markdown'
            )
            # Send keyboard as separate message
            await query.message.reply_text(
                "Menyu:",
                reply_markup=reply_markup
            )
        
    async def _handle_phone_contact(self, update: Update):
        """Handle phone contact submission"""
        contact = update.message.contact
        user_id = update.effective_user.id
        
        # Check if contact belongs to the user
        if contact.user_id != user_id:
            await update.message.reply_text(
                "❌ Faqat o'zingizning telefon raqamingizni yuborishingiz mumkin!"
            )
            return
            
        # Save phone number
        phone_number = contact.phone_number
        success = self.database.save_user_phone(user_id, phone_number)
        
        if success:
            # Update user info with phone
            user = update.effective_user
            self.database.get_or_create_user(
                user.id, user.first_name, user.last_name, user.username, phone_number
            )
            
            await update.message.reply_text(
                "✅ **Telefon raqam tasdiqlandi!**\n\n"
                "🎉 Endi botdan foydalanishingiz mumkin!\n\n"
                "📋 /help - Yordam\n",
                reply_markup=self._build_main_menu_keyboard(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Telefon raqamni saqlashda xatolik yuz berdi. Qayta urinib ko'ring.",
                reply_markup=ReplyKeyboardRemove()
            )
    
    async def _show_welcome_with_referral_button(self, update: Update):
        """Show welcome message with referral and account buttons after phone verification"""
        user = update.effective_user
        bot_info = self.database.get_bot_by_id(self.bot_id)
        bot_settings = self.database.get_bot_settings(self.bot_id)
        
        await update.message.reply_text(
            "✅ **Telefon raqam tasdiqlandi!**\n\n"
            "🎉 Endi siz konkursda ishtirok eta olasiz!\n"
            "👇 Quyidagi tugmalardan birini tanlang:",
            reply_markup=self._build_main_menu_keyboard(),
            parse_mode='Markdown'
        )
    
    async def _show_my_referral_link_keyboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send the configured referral share message when keyboard button is pressed."""
        user = update.effective_user
        if not user:
            return

        referral_settings = self.database.get_bot_referral_settings(self.bot_id)
        if not referral_settings.get('enabled', True):
            await update.message.reply_text("❌ Referral tizimi yoqilmagan!")
            return

        referral_link = self._generate_referral_link(user.id)
        referral_count = self.database.get_user_referral_count(self.bot_id, user.id)

        await self._send_referral_share_message(
            context,
            update.effective_chat.id,
            referral_link,
            user,
            referral_count,
        )
        
    async def _show_my_account_keyboard(self, update: Update):
        """Show user's account information via keyboard"""
        user_id = update.effective_user.id
        user = update.effective_user
        logger.info(f"_show_my_account_keyboard called for user {user_id}")
        
        # Get user referral statistics
        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)
        logger.info(f"Referral count for user {user_id}: {referral_count}")
        
        # Get referral list
        referral_list = self.database.get_user_referrals(self.bot_id, user_id)
        
        # Check who referred this user
        referred_by_id = self.database.get_user_referred_by(self.bot_id, user_id)
        referred_by_text = ""
        if referred_by_id:
            try:
                # Get referrer's info
                referrer_info = self.database.get_user_by_telegram_id(referred_by_id)
                if referrer_info:
                    referrer_name = escape_markdown(referrer_info.get('first_name') or "Nomalum", version=1)
                    referred_by_text = f"👆 **Sizni taklif qilgan:** {referrer_name}\n\n"
            except Exception as e:
                logger.error(f"Error getting referrer info: {e}")
        
        def _md(value: Optional[str], fallback: str) -> str:
            return escape_markdown(value if value not in (None, "") else fallback, version=1)

        referral_count_display = _md(str(referral_count), "0")

        text_lines = [
            "📊 **Referral statistikasi**",
            f"👥 Jami referrallar: **{referral_count_display}** ta",
        ]

        if referred_by_text:
            text_lines.append(referred_by_text.rstrip())
            text_lines.append("")

        text_lines.extend([
            "🔗 Siz ham do'stlaringizni taklif qila olasiz!",
            "",
        ])

        if referral_list:
            text_lines.append("📋 **Sizning referrallaringiz:**")
            for i, ref in enumerate(referral_list[:5], 1):
                ref_name = _md(ref.get('first_name'), "Nomalum")
                text_lines.append(f"{i}. {ref_name}")
            if len(referral_list) > 5:
                text_lines.append(_md(f"... va yana {len(referral_list) - 5} ta", f"... va yana {len(referral_list) - 5} ta"))
        else:
            text_lines.append("📋 **Referrallar:** Hali yo'q")

        text = "\n".join(text_lines)

        logger.info(f"Sending account info to user {user_id}: {text}")
        try:
            await update.message.reply_text(text, parse_mode='Markdown')
        except BadRequest as send_error:
            if "can't parse entities" in str(send_error).lower():
                await update.message.reply_text(text)
            else:
                logger.error(f"Error sending account info via keyboard: {send_error}")
                await update.message.reply_text(
                    "❌ Hisob ma'lumotlarini ko'rsatishda xatolik yuz berdi. Keyinroq yana urinib ko'ring."
                )
        logger.info(f"Account info message sent successfully to user {user_id}")
    
    def _generate_referral_link(self, user_id: int) -> str:
        """Generate referral link for user"""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        bot_username = bot_info['username']
        return f"https://t.me/{bot_username}?start=ref_{user_id}"
        
    async def _show_my_referral_link(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Send referral share message when inline button is pressed."""
        user = query.from_user
        if not user:
            return

        referral_settings = self.database.get_bot_referral_settings(self.bot_id)
        if not referral_settings.get('enabled', True):
            await query.answer("❌ Referral tizimi yoqilmagan!", show_alert=True)
            return

        referral_link = self._generate_referral_link(user.id)
        referral_count = self.database.get_user_referral_count(self.bot_id, user.id)

        chat_id = query.message.chat_id if query.message else user.id
        await self._send_referral_share_message(
            context,
            chat_id,
            referral_link,
            user,
            referral_count,
        )
        
    async def _show_my_account(self, query):
        """Show user's account information"""
        user_id = query.from_user.id
        user = query.from_user
        
        # Get user referral statistics
        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)
        user_phone = self.database.get_user_phone(user_id)
        
        # Get referral list
        referral_list = self.database.get_user_referrals(self.bot_id, user_id)
        
        text = (
            f"👤 **Mening hisobim**\n\n"
            f"📛 **Ism:** {user.first_name}\n"
            f"📱 **Telefon:** {user_phone if user_phone else 'Berilmagan'}\n"
            f"🆔 **Username:** @{user.username if user.username else 'Yoq'}\n\n"
            f"📊 **Referral statistikasi:**\n"
            f"👥 Jami referrallar: **{referral_count}** ta\n\n"
        )
        
        if referral_list and len(referral_list) > 0:
            text += f"📋 **Sizning referrallaringiz:**\n"
            for i, ref in enumerate(referral_list[:5], 1):  # Show first 5
                ref_name = ref.get('first_name', 'Nomalum')
                text += f"{i}. {ref_name}\n"
            
            if len(referral_list) > 5:
                text += f"... va yana {len(referral_list) - 5} ta\n"
        else:
            text += f"📋 **Referrallar:** Hali yo'q\n"
        
        keyboard = [
            [InlineKeyboardButton("🔗 Mening referral havolam", callback_data="my_referral_link")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="close_message")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _show_referral_info(self, update: Update):
        """Show referral information to user"""
        user_id = update.effective_user.id
        referral_settings = self.database.get_bot_referral_settings(self.bot_id)
        
        if not referral_settings['enabled']:
            await update.message.reply_text("❌ Referral tizimi yoqilmagan.")
            return
            
        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)
        referral_link = self._generate_referral_link(user_id)
        
        text = (
            f"🎁 **{referral_settings['message']}**\n\n"
            f"👥 Sizning referallaringiz: {referral_count}\n"
            f"🔗 Sizning havolangiz:\n{referral_link}\n\n"
            f"Bu havolani do'stlaringizga yuboring va ular bot orqali ro'yxatdan o'tganda "
            f"referral hisobingizga qo'shiladi!"
        )
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    async def _handle_referral_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle referral when user starts bot"""
        user_id = update.effective_user.id
        
        # Check if there are start parameters
        if context.args and len(context.args) > 0:
            start_param = context.args[0]
            
            # Check if it's a referral link
            if start_param.startswith('ref_'):
                try:
                    referrer_id = int(start_param[4:])  # Remove 'ref_' prefix
                    
                    # Don't allow self-referral
                    if referrer_id != user_id:
                        # Check if referrals are enabled
                        referral_settings = self.database.get_bot_referral_settings(self.bot_id)
                        if referral_settings['enabled']:
                            # Check if this user is already referred by someone else
                            existing_referrer = self.database.get_user_referred_by(self.bot_id, user_id)
                            
                            if not existing_referrer:
                                # Add referral - this user hasn't been referred before
                                success = self.database.add_referral(self.bot_id, referrer_id, user_id)
                                
                                if success:
                                    logger.info(f"User {user_id} was referred by {referrer_id} in bot {self.bot_id}")
                                    
                                    # Notify referrer about new referral
                                    try:
                                        bot_info = self.database.get_bot_by_id(self.bot_id)
                                        user = update.effective_user
                                        
                                        # Get bot instance
                                        bot = Bot(token=bot_info['token'])
                                        
                                        referral_count = self.database.get_user_referral_count(self.bot_id, referrer_id)
                                        
                                        await bot.send_message(
                                            chat_id=referrer_id,
                                            text=(
                                                f"🎉 **Yangi referal!**\n\n"
                                                f"👤 {user.first_name} {user.last_name or ''} sizning havolangiz orqali botga qo'shildi!\n\n"
                                                f"👥 Jami referallaringiz: **{referral_count}** ta\n\n"
                                                f"💡 Ular ham o'z referrallarini yig'a olishadi!"
                                            ),
                                            parse_mode='Markdown'
                                        )
                                    except Exception as e:
                                        logger.error(f"Error notifying referrer: {e}")
                            else:
                                logger.info(f"User {user_id} already referred by {existing_referrer}, ignoring new referral from {referrer_id}")
                                    
                except ValueError:
                    # Invalid referrer ID
                    logger.error(f"Invalid referrer ID in start param: {start_param}")
                    pass
    
    async def _handle_contest_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle contest creation process"""
        user_id = update.effective_user.id
        text = update.message.text
        user_data = context.user_data.get(user_id, {})
        
        if user_data.get('step') == 'title':
            # Store title and ask for description
            context.user_data[user_id]['title'] = text
            context.user_data[user_id]['step'] = 'description'
            
            await update.message.reply_text(
                "✍️ **Konkurs tavsifini kiriting:**\n"
                "(Masalan: 'Eng chiroyli rasm konkursida qatnashing va sovrinlar yuting!')",
                parse_mode='Markdown'
            )
        elif user_data.get('step') == 'description':
            # Create contest
            title = user_data['title']
            description = text
            
            contest_id = self.database.create_contest(
                bot_id=self.bot_id, 
                title=title, 
                description=description,
                active=True
            )
            
            # Clear user state
            del context.user_data[user_id]
            
            await update.message.reply_text(
                f"✅ **Konkurs yaratildi!**\n\n"
                f"📝 Nom: {title}\n"
                f"📋 Tavsif: {description}\n\n"
                f"Konkurs faol holatda. Ishtirokchilar /join orqali qo'shilishlari mumkin.",
                parse_mode='Markdown'
            )
            
    async def _handle_broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle broadcast message creation"""
        user_id = update.effective_user.id

        if update.message.text:
            message_text = update.message.text
            message_type = 'text'
            media_file_id = None
        elif update.message.photo:
            message_text = update.message.caption or ""
            message_type = 'photo'
            media_file_id = update.message.photo[-1].file_id
        elif update.message.video:
            message_text = update.message.caption or ""
            message_type = 'video'
            media_file_id = update.message.video.file_id
        else:
            await update.message.reply_text("❌ Faqat matn, rasm yoki video yuborishingiz mumkin!")
            return

        participants = self.database.get_bot_all_users(self.bot_id)
        if not participants:
            await update.message.reply_text("❌ Xabar yuborish uchun ishtirokchilar yo'q!")
            if getattr(context, 'user_data', None) is not None:
                context.user_data.pop(user_id, None)
            return

        sent_count = 0
        failed_count = 0
        progress_msg = await update.message.reply_text("📤 Xabar yuborilmoqda...")

        for participant in participants:
            chat_id = participant.get('telegram_id') if isinstance(participant, dict) else participant
            try:
                if message_type == 'text':
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode='Markdown'
                    )
                elif message_type == 'photo':
                    send_kwargs = {'photo': media_file_id}
                    if message_text:
                        send_kwargs['caption'] = message_text
                        send_kwargs['parse_mode'] = 'Markdown'
                    await context.bot.send_photo(chat_id=chat_id, **send_kwargs)
                elif message_type == 'video':
                    send_kwargs = {'video': media_file_id}
                    if message_text:
                        send_kwargs['caption'] = message_text
                        send_kwargs['parse_mode'] = 'Markdown'
                    await context.bot.send_video(chat_id=chat_id, **send_kwargs)
                sent_count += 1
            except Exception as send_error:
                failed_count += 1
                logger.error(f"Broadcast send error for user {chat_id}: {send_error}")
            await asyncio.sleep(0.05)

        summary_text = (
            "✅ Xabar yuborildi!\n\n"
            f"📬 Yuborilganlar: {sent_count}\n"
            f"⚠️ Yuborilmaganlar: {failed_count}"
        )

        try:
            await progress_msg.edit_text(summary_text)
        except Exception:
            await update.message.reply_text(summary_text)

        self.database.log_broadcast(self.bot_id, message_type, sent_count, failed_count)

        if getattr(context, 'user_data', None) is not None:
            context.user_data.pop(user_id, None)
        
    async def _handle_info_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle bot info editing"""
        user_id = update.effective_user.id
        text = update.message.text
        user_data = context.user_data.get(user_id, {})
        
        if user_data.get('step') == 'name':
            # Store name and ask for description
            context.user_data[user_id]['new_name'] = text
            context.user_data[user_id]['step'] = 'description'
            
            await update.message.reply_text(
                "📝 **Bot tavsifini kiriting:**\n"
                "(Masalan: 'Turli konkurslar uchun mo\\'ljallangan bot')"
            )
        elif user_data.get('step') == 'description':
            # Update bot info
            new_name = user_data['new_name']
            new_description = text
            
            self.database.update_bot_info(self.bot_id, {
                'name': new_name,
                'description': new_description
            })
            
            # Clear state
            del context.user_data[user_id]
            
            await update.message.reply_text(
                f"✅ **Bot ma'lumotlari yangilandi!**\n\n"
                f"📛 Yangi nom: {new_name}\n"
                f"📝 Yangi tavsif: {new_description}",
                parse_mode='Markdown'
            )
            
    async def _handle_winner_count(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle winner count selection"""
        user_id = update.effective_user.id
        text = update.message.text
        
        try:
            count = int(text)
            if count < 1 or count > 10:
                await update.message.reply_text("❌ 1 dan 10 gacha son kiriting!")
                return
                
            # Select random winners
            participants = self.database.get_all_participants(self.bot_id)
            import random
            selected_winners = random.sample(participants, min(count, len(participants)))
            
            # Save winners to database
            for winner in selected_winners:
                self.database.add_winner(self.bot_id, winner['user_id'])
                
            # Clear state
            del context.user_data[user_id]
            
            # Show results
            winner_text = f"🏆 **{count} ta g'olib tanlandi!**\n\n"
            for i, winner in enumerate(selected_winners, 1):
                winner_text += f"{i}. {winner['first_name']}"
                if winner.get('username'):
                    winner_text += f" (@{winner['username']})"
                winner_text += "\n"
                
            await update.message.reply_text(winner_text, parse_mode='Markdown')
            
        except ValueError:
            await update.message.reply_text("❌ Iltimos, son kiriting!")
        except Exception as e:
            await update.message.reply_text(f"❌ Xatolik: {str(e)}")
    
    # Enhanced Admin Panel Functions
    async def _handle_restart_bot(self, query, context):
        """Handle bot restart"""
        try:
            # Update restart info in database
            self.database.update_bot_restart_info(self.bot_id)
            
            # Get bot factory and restart the bot
            bot_factory = context.bot_data.get('bot_factory')
            if bot_factory:
                await bot_factory.restart_bot(self.bot_id)
                await query.answer("✅ Bot muvaffaqiyatli qayta ishga tushirildi!")
                
                text = f"""
🔄 **Bot qayta ishga tushirildi!**

✅ Bot muvaffaqiyatli qayta ishga tushdi
⏰ Vaqt: {datetime.now().strftime('%H:%M:%S')}
📅 Sana: {datetime.now().strftime('%d.%m.%Y')}

Bot endi yangi sozlamalar bilan ishlaydi.
"""
                await self._safe_edit_message(query, text, parse_mode='Markdown')
            else:
                logger.error("Bot factory not found in context")
                await query.answer("❌ Bot factory topilmadi!")
                
        except Exception as e:
            logger.error(f"Error restarting bot: {e}")
            await query.answer("❌ Botni qayta ishga tushirishda xatolik!")
            

    
    async def _handle_editing_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle editing input for bot settings"""
        user_id = update.effective_user.id
        user_data = context.user_data.get(user_id, {})
        editing_type = user_data.get('editing')
        text = update.message.text.strip()
        
        if editing_type == 'bot_name':
            if self.database.update_bot_info(self.bot_id, name=text):
                await update.message.reply_text(f"✅ Bot nomi '{text}' ga o'zgartirildi!")
            else:
                await update.message.reply_text("❌ Bot nomini o'zgartirishda xatolik!")
                
        elif editing_type == 'bot_description':
            if self.database.update_bot_info(self.bot_id, description=text):
                await update.message.reply_text(f"✅ Bot tavsifi o'zgartirildi!")
            else:
                await update.message.reply_text("❌ Bot tavsifini o'zgartirishda xatolik!")
                
        elif editing_type == 'welcome_message':
            if self.database.update_welcome_message(self.bot_id, text):
                await update.message.reply_text(f"✅ Start xabari o'zgartirildi!")
            else:
                await update.message.reply_text("❌ Start xabarini o'zgartirishda xatolik!")
                
        elif editing_type == 'add_admin':
            try:
                admin_id = int(text)
                if self.database.add_bot_admin(self.bot_id, admin_id):
                    await update.message.reply_text(f"✅ Admin (ID: {admin_id}) qo'shildi!")
                else:
                    await update.message.reply_text("❌ Admin qo'shishda xatolik!")
            except ValueError:
                await update.message.reply_text("🔢 Iltimos, Telegram ID raqamini kiriting.")
                return
                
        elif editing_type == 'remove_admin':
            try:
                admin_id = int(text)
                if self.database.remove_bot_admin(self.bot_id, admin_id):
                    await update.message.reply_text(f"✅ Admin (ID: {admin_id}) olib tashlandi!")
                else:
                    await update.message.reply_text("❌ Admin olib tashlashda xatolik!")
            except ValueError:
                await update.message.reply_text("🔢 Iltimos, Telegram ID raqamini kiriting.")
                return
                
        elif editing_type == 'subscription_message':
            if self.database.update_subscription_message(self.bot_id, text):
                await update.message.reply_text("✅ Obuna xabari muvaffaqiyatli o'zgartirildi!")
            else:
                await update.message.reply_text("❌ Obuna xabarini o'zgartirishda xatolik!")
        elif editing_type == 'phone_request_message':
            lower_text = text.lower()
            cancel_inputs = ('/cancel', 'cancel', 'bekor')
            if lower_text in cancel_inputs:
                await update.message.reply_text("❌ Telefon so'rov matni tahrirlash bekor qilindi.")
                panel_text, panel_markup = self._build_phone_settings_message()
                await update.message.reply_text(panel_text, reply_markup=panel_markup, parse_mode='HTML')
            elif not text:
                await update.message.reply_text("❗ Matn bo'sh bo'lmasligi kerak.")
                return
            elif self.database.update_bot_settings(self.bot_id, {'phone_request_message': text}):
                await update.message.reply_text("✅ Telefon so'rov matni yangilandi!")
                panel_text, panel_markup = self._build_phone_settings_message()
                await update.message.reply_text(panel_text, reply_markup=panel_markup, parse_mode='HTML')
            else:
                await update.message.reply_text("❌ Telefon so'rov matnini o'zgartirishda xatolik yuz berdi!")
        elif editing_type == 'phone_post_message':
            lower_text = text.lower()
            cancel_inputs = ('/cancel', 'cancel', 'bekor')
            if lower_text in cancel_inputs:
                await update.message.reply_text("❌ Xush kelibsiz matnini tahrirlash bekor qilindi.")
                panel_text, panel_markup = self._build_phone_settings_message()
                await update.message.reply_text(panel_text, reply_markup=panel_markup, parse_mode='HTML')
            elif not text:
                await update.message.reply_text("❗ Matn bo'sh bo'lmasligi kerak.")
                return
            elif self.database.update_bot_settings(self.bot_id, {'phone_post_message': text}):
                await update.message.reply_text("✅ Xush kelibsiz matni yangilandi!")
                panel_text, panel_markup = self._build_phone_settings_message()
                await update.message.reply_text(panel_text, reply_markup=panel_markup, parse_mode='HTML')
            else:
                await update.message.reply_text("❌ Xush kelibsiz matnini o'zgartirishda xatolik yuz berdi!")
        
        # Clear editing state
        if user_id in context.user_data and 'editing' in context.user_data[user_id]:
            del context.user_data[user_id]['editing']
    
    async def _handle_edit_welcome_direct(self, query, context):
        """Handle direct start message editing from admin panel"""
        user_id = query.from_user.id
        bot_info = self.database.get_bot_by_id(self.bot_id)
        
        # Check if user is bot owner
        if user_id != bot_info['owner_id']:
            await query.edit_message_text("❌ Faqat bot egasi start xabarini o'zgartira oladi!")
            return
            
        # Get current welcome message
        bot_settings = self.database.get_bot_settings(self.bot_id)
        current_welcome = bot_settings.get('welcome_message', 'Hozirda standart xabar ishlatilmoqda')
        
        text = (
            f"📝 **{bot_info['name']} - Start xabarini tahrirlash**\n\n"
            f"**Joriy start xabar:**\n{current_welcome}\n\n"
            f"🔄 Yangi start xabarini yozing. Bu xabar foydalanuvchilar /start "
            f"bosganda ko'rinadi.\n\n"
            f"💡 **Maslahat:** \n"
            f"• Qisqa va tushunarli bo'lsin\n"
            f"• Bot nomi va maqsadini aytib bering\n"
            f"• Foydalanuvchini xush ko'ring\n\n"
            f"✍️ Yangi xabaringizni yozing:"
        )
        
        # Set editing mode for welcome message
        if not hasattr(context, 'user_data'):
            context.user_data = {}
        context.user_data[user_id] = {'editing_welcome_direct': True}
        
        try:
            await query.edit_message_text(text, parse_mode='Markdown')
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error editing welcome message: {e}")
                await query.answer("Xatolik yuz berdi!")
    
    async def _handle_welcome_edit_direct(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle welcome message editing directly from admin panel"""
        user_id = update.effective_user.id
        new_welcome = update.message.text.strip()
        
        bot_info = self.database.get_bot_by_id(self.bot_id)
        
        # Check if user is bot owner
        if user_id != bot_info['owner_id']:
            await update.message.reply_text("❌ Faqat bot egasi start xabarini o'zgartira oladi!")
            context.user_data[user_id] = {}
            return
        
        try:
            # Update welcome message in database
            success = self.database.update_welcome_message(self.bot_id, new_welcome)
            
            if success:
                # Create keyboard to return to admin panel
                keyboard = [
                    [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="admin_back")],
                    [InlineKeyboardButton("🔄 Yana tahrirlash", callback_data="admin_edit_welcome")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ **Start xabari muvaffaqiyatli yangilandi!**\n\n"
                    f"🤖 **Bot:** {bot_info['name']}\n\n"
                    f"📨 **Yangi start xabar:**\n{new_welcome}\n\n"
                    f"🎯 Endi foydalanuvchilar /start bosganda bu xabar ko'rinadi.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "❌ Start xabarini yangilashda xatolik yuz berdi!\n\n"
                    "Iltimos qayta urinib ko'ring."
                )
                
        except Exception as e:
            logger.error(f"Error updating welcome message: {e}")
            await update.message.reply_text(
                "❌ Xatolik yuz berdi!\n\n"
                "Iltimos qayta urinib ko'ring."
            )
        
        # Clear editing state
        context.user_data[user_id] = {}

    async def _handle_channels(self, query, context):
        """Handle channel management"""
        try:
            bot_info = self.database.get_bot_by_id(self.bot_id)
            if not bot_info:
                await query.edit_message_text("❌ Bot ma'lumotlari topilmadi.")
                return
                
            channels = self.database.get_required_channels(self.bot_id)
            
            # Check subscription status
            bot_settings = self.database.get_bot_settings(self.bot_id)
            subscription_enabled = bot_settings.get('subscription_enabled', False)
            
            # Channel limit constants
            MAX_CHANNELS = 10
            current_count = len(channels) if channels else 0
            
            text = f"📺 <b>Kanal boshqaruvi - {bot_info['name']}</b>\n\n"
            
            # Show subscription status
            status_icon = "✅" if subscription_enabled else "❌"
            status_text = "Yoqilgan" if subscription_enabled else "O'chirilgan"
            text += f"🔘 <b>Majburiy obuna:</b> {status_icon} {status_text}\n"
            text += f"📊 <b>Kanallar hisobi:</b> {current_count}/{MAX_CHANNELS}\n\n"
            
            if channels and len(channels) > 0:
                text += "<b>Majburiy obuna kanallari:</b>\n"
                for i, channel in enumerate(channels, 1):
                    try:
                        # Handle both dict and tuple formats safely
                        if isinstance(channel, dict):
                            channel_name = channel.get('name') or channel.get('channel_name') or f"Kanal {i}"
                            channel_username = channel.get('username') or channel.get('channel_username') or channel.get('channel_id', 'Unknown')
                        else:
                            # Tuple format: (id, channel_id, name, username, ...)
                            channel_name = channel[2] if len(channel) > 2 and channel[2] else f"Kanal {i}"
                            channel_username = channel[3] if len(channel) > 3 and channel[3] else (channel[1] if len(channel) > 1 else 'Unknown')
                        
                        # Clean username
                        if channel_username and channel_username.startswith('@'):
                            channel_username = channel_username[1:]
                        
                        # Format channel display
                        text += f"{i}. <b>{channel_name}</b> (@{channel_username})\n"
                        
                    except Exception as e:
                        logger.error(f"Error formatting channel {i}: {e}")
                        text += f"{i}. Kanal {i}\n"
                        
                text += "\n💡 <i>Kanallarni boshqarish uchun \"Kanallar ro'yxati\" tugmasini bosing</i>\n\n"
            else:
                text += "❌ Hozircha majburiy obuna kanallari yo'q.\n\n"
            
            # Create toggle button text
            toggle_text = "❌ Obunani o'chirish" if subscription_enabled else "✅ Obunani yoqish"
            
            # Create add channel button text based on limit
            if current_count >= MAX_CHANNELS:
                add_text = "🚫 Limit tugagan (10/10)"
                add_callback = "channel_limit_reached"
            else:
                add_text = "➕ Kanal qo'shish"
                add_callback = "channel_add"
            
            keyboard = [
                [InlineKeyboardButton(toggle_text, callback_data="channel_toggle_subscription")],
                [InlineKeyboardButton(add_text, callback_data=add_callback)],
                [InlineKeyboardButton("📋 Kanallar ro'yxati", callback_data="channel_list")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in _handle_channels: {e}")
            await query.edit_message_text(
                "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")
                ]])
            )

    async def _handle_referral_list(self, query, context):
        """Handle referral list display"""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        referrals = self.database.get_referrals_list(self.bot_id)
        
        text = f"👥 **Referral ro'yxati - {bot_info['name']}**\n\n"
        text += f"**Jami referral orqali kelganlar:** {len(referrals)}\n\n"
        
        if referrals:
            text += "**So'nggi 10 ta referral:**\n"
            for i, referral in enumerate(referrals[:10], 1):
                first_name = referral[0] or "Noma'lum"
                last_name = referral[1] or ""
                phone = referral[2] or "Telefon yo'q"
                full_name = f"{first_name} {last_name}".strip()
                text += f"{i}. {full_name}\n   📞 {phone}\n"
            if len(referrals) > 10:
                text += f"\n... va yana {len(referrals) - 10} ta\n"
        else:
            text += "❌ Hozircha referral orqali kelgan foydalanuvchilar yo'q.\n"
        
        keyboard = [
            [InlineKeyboardButton("📥 Excel yuklash", callback_data="referral_export")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def _handle_channel_action(self, query, context):
        """Handle channel actions"""
        try:
            data = query.data
            user_id = query.from_user.id
            
            if data == "channel_toggle_subscription":
                await self._toggle_subscription(query, context)
            elif data == "channel_add":
                # Check channel limit before allowing addition
                channels = self.database.get_required_channels(self.bot_id)
                MAX_CHANNELS = 10
                
                if len(channels) >= MAX_CHANNELS:
                    keyboard = [
                        [InlineKeyboardButton("📋 Kanallar ro'yxati", callback_data="channel_list")],
                        [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_channels")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"⚠️ **Kanal limiti tugadi!**\n\n"
                        f"📊 **Joriy holat:** {len(channels)}/{MAX_CHANNELS}\n\n"
                        f"🚫 Bitta bot uchun maksimal {MAX_CHANNELS} ta kanal qo'shish mumkin.\n\n"
                        f"💡 **Yechim:**\n"
                        f"• Avval keraksiz kanallarni olib tashlang\n"
                        f"• Keyin yangi kanal qo'shing\n\n"
                        f"📋 Kanallar ro'yxatiga o'ting va keraksiz kanallarni o'chiring.",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                    return
                
                context.user_data[user_id] = {'adding_channel': True}
                await query.edit_message_text(
                    "📺 **Kanal qo'shish**\n\n"
                    "Majburiy obuna qilmoqchi bo'lgan kanalingizni username yoki ID sini yuboring.\n\n"
                    "**Misol:**\n"
                    "• @kanalim\n"
                    "• -1001234567890\n\n"
                    "❗ Kanal ochiq bo'lishi kerak yoki botni kanalga admin qilib qo'ying.",
                    parse_mode='Markdown'
                )
            elif data == "channel_limit_reached":
                # Handle when limit button is clicked
                channels = self.database.get_required_channels(self.bot_id)
                keyboard = [
                    [InlineKeyboardButton("📋 Kanallar ro'yxati", callback_data="channel_list")],
                    [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_channels")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"⚠️ **Kanal limiti tugagan!**\n\n"
                    f"📊 **Joriy holat:** {len(channels)}/10\n\n"
                    f"🚫 Bitta bot uchun maksimal 10 ta kanal qo'shish mumkin.\n\n"
                    f"💡 **Yangi kanal qo'shish uchun:**\n"
                    f"• Avval keraksiz kanallarni o'chiring\n"
                    f"• Keyin qaytadan kanal qo'shing\n\n"
                    f"📋 Kanallar ro'yxatiga o'ting va keraksiz kanallarni boshqaring.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif data == "channel_list":
                await self._show_channels_list(query, context)
            elif data.startswith("view_channel_"):
                channel_id = data.replace("view_channel_", "")
                await self._handle_view_channel(query, context, channel_id)
            elif data.startswith("remove_channel_"):
                channel_identifier = data.replace("remove_channel_", "")
                removed = False
                try:
                    # Prefer removing via required_channels primary key (int)
                    record_id = int(channel_identifier)
                    removed = self.database.remove_required_channel(record_id)
                except ValueError:
                    # Fallback to legacy removal by channel_id in channels table
                    try:
                        removed = self.database.remove_channel(self.bot_id, channel_identifier)
                    except Exception as e:
                        logger.error(f"Error removing channel by identifier {channel_identifier}: {e}")
                        removed = False

                if removed:
                    await query.answer("✅ Kanal muvaffaqiyatli o'chirildi!")
                    await self._show_channels_list(query, context)
                else:
                    await query.answer("❌ Kanal o'chirishda xatolik yuz berdi!")
            elif data == "edit_subscription_message":
                user_id = query.from_user.id
                context.user_data[user_id] = {'editing': 'subscription_message'}
                await query.edit_message_text(
                    "💬 **Obuna xabarini tahrirlash**\n\n"
                    "Yangi obuna xabarini kiriting:\n\n"
                    "**Eslatma:** `{channels}` belgisini ishlatib, kanallar ro'yxati o'rnini ko'rsating.\n\n"
                    "**Misol:**\n"
                    "📺 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:\n\n"
                    "{channels}\n\n"
                    "🔄 Obuna bo'lgach tugmani bosing.",
                    parse_mode='Markdown'
                )
            elif data == "reset_subscription_message":
                default_message = (
                    "📺 **Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:**\n\n"
                    "{channels}\n\n"
                    "1️⃣ Avvalo kanallarga qo'shiling.\n"
                    "2️⃣ So'ng \"✅ Bajarildi\" tugmasini bosing."
                )
                if self.database.update_subscription_message(self.bot_id, default_message):
                    await query.answer("✅ Obuna xabari standart holatga qaytarildi!")
                    await self._handle_subscription_message(query, context)
                else:
                    await query.answer("❌ Xatolik yuz berdi!")
            else:
                # Unknown channel action
                await query.answer("❌ Noma'lum amal!")
                
        except Exception as e:
            logger.error(f"Error in _handle_channel_action: {e}")
            await query.edit_message_text(
                "❌ Kanal amalini bajarishda xatolik yuz berdi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")
                ]])
            )

    async def _show_channels_list(self, query, context):
        """Show channels list with management options"""
        try:
            bot_info = self.database.get_bot_by_id(self.bot_id)
            if not bot_info:
                await query.edit_message_text("❌ Bot ma'lumotlari topilmadi.")
                return
                
            channels = self.database.get_required_channels(self.bot_id)
            
            text = f"📋 <b>Kanallar ro'yxati - {bot_info['name']}</b>\n\n"
            
            keyboard = []  # Initialize keyboard list
            
            if channels and len(channels) > 0:
                text += "<b>Majburiy obuna kanallari:</b>\n\n"
                for i, channel in enumerate(channels, 1):
                    try:
                        # Debug log
                        logger.info(f"Processing channel {i}: {channel}")
                        
                        # Handle dict format (expected from get_required_channels)
                        if isinstance(channel, dict):
                            channel_name = channel.get('name', f"Kanal {i}")
                            channel_identifier = channel.get('channel_id') or ''
                            channel_record_id = str(channel.get('id', ''))
                            channel_username = channel.get('username') or channel.get('channel_username', '')

                            # Debug info
                            logger.info(
                                f"Channel data - Name: {channel_name}, Identifier: {channel_identifier}, Record ID: {channel_record_id}, Username: {channel_username}"
                            )
                        else:
                            # Fallback for other formats
                            channel_name = f"Kanal {i}"
                            channel_identifier = str(channel) if channel else ''
                            channel_record_id = channel_identifier
                            channel_username = ''
                        
                        text += f"{i}. <b>{channel_name}</b>\n"
                        if channel_username:
                            if not channel_username.startswith('@'):
                                channel_username = f"@{channel_username}"
                            text += f"   {channel_username}\n"
                        text += "\n"
                        
                        # Create buttons for each channel - one to open, one to remove
                        if channel_identifier or channel_record_id:
                            # Create channel URL
                            channel_url = None
                            
                            # Try username first
                            if channel_username and channel_username.strip():
                                clean_username = channel_username.strip()
                                if clean_username.startswith('@'):
                                    clean_username = clean_username[1:]
                                
                                # Telegram username validation: 5-32 chars, letters, numbers, underscores
                                if (len(clean_username) >= 5 and len(clean_username) <= 32 and 
                                    clean_username.replace('_', '').replace('0', '').replace('1', '').replace('2', '').replace('3', '').replace('4', '').replace('5', '').replace('6', '').replace('7', '').replace('8', '').replace('9', '').isalpha()):
                                    channel_url = f"https://t.me/{clean_username}"
                                    logger.info(f"Created URL from username: {channel_url}")
                            
                            # Fallback: try channel_id if it's username format
                            if not channel_url and channel_identifier and str(channel_identifier).strip():
                                clean_id = str(channel_identifier).strip()
                                if clean_id.startswith('@'):
                                    clean_id = clean_id[1:]
                                
                                # Check if it's a username-like ID (not numeric channel ID)
                                if (not clean_id.startswith('-') and len(clean_id) >= 5 and 
                                    not clean_id.isdigit()):
                                    channel_url = f"https://t.me/{clean_id}"
                                    logger.info(f"Created URL from channel_id: {channel_url}")
                            
                            # Add channel buttons in a row
                            channel_buttons = []
                            
                            # Open channel button with URL
                            if channel_url:
                                channel_buttons.append(
                                    InlineKeyboardButton(
                                        f"📺 {channel_name}", 
                                        url=channel_url
                                    )
                                )
                            else:
                                # Fallback button without URL
                                channel_buttons.append(
                                    InlineKeyboardButton(
                                        f"� {channel_name}", 
                                        callback_data=f"view_channel_{channel_identifier or channel_record_id}"
                                    )
                                )
                            
                            # Remove button (prefer database record id if exists)
                            remove_target = channel_record_id or channel_identifier
                            if remove_target:
                                channel_buttons.append(
                                    InlineKeyboardButton(
                                        "🗑", 
                                        callback_data=f"remove_channel_{remove_target}"
                                    )
                                )
                            
                            keyboard.append(channel_buttons)
                    except Exception as e:
                        logger.error(f"Error processing channel {i}: {e}")
                        continue
            else:
                text += "❌ Hozircha kanallar yo'q.\n"
            
            keyboard.extend([
                [InlineKeyboardButton("➕ Kanal qo'shish", callback_data="channel_add")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_channels")]
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in _show_channels_list: {e}")
            await query.edit_message_text(
                "❌ Kanallar ro'yxatini ko'rsatishda xatolik yuz berdi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")
                ]])
            )

    async def _handle_subscription_message(self, query, context):
        """Handle subscription message settings"""
        try:
            bot_info = self.database.get_bot_by_id(self.bot_id)
            current_message = self.database.get_subscription_message(self.bot_id)
            
            text = f"💬 **Obuna xabari - {bot_info['name']}**\n\n"
            text += "**Hozirgi obuna xabari:**\n"
            text += f"```\n{current_message}\n```\n\n"
            text += "**Eslatma:** `{channels}` o'rniga kanallar ro'yxati avtomatik qo'shiladi.\n\n"
            text += "Yangi obuna xabarini o'zgartirish uchun \"Tahrirlash\" tugmasini bosing."
            
            keyboard = [
                [InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit_subscription_message")],
                [InlineKeyboardButton("🔄 Standart xabarga qaytarish", callback_data="reset_subscription_message")],
                [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_channels")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._safe_edit_message(
                query,
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in _handle_subscription_message: {e}")
            await query.edit_message_text(
                "❌ Obuna xabarini ko'rsatishda xatolik yuz berdi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="admin_channels")
                ]])
            )

    async def _export_referrals_excel(self, query, context):
        """Export detailed referral statistics to Excel file with top referrers and all referred users"""
        await query.answer("📊 Referral statistika tayyorlanmoqda...", show_alert=True)
        
        try:
            # Get data counts for validation
            top_referrers = self.database.get_top_referrers(self.bot_id, limit=100)
            all_referred = self.database.get_all_referred_users_detailed(self.bot_id)
            
            if not top_referrers and not all_referred:
                await query.edit_message_text(
                    "❌ **Referral statistika yo'q**\n\n"
                    "Hozircha hech kim referral orqali odam qo'shmagan yoki kelgan yo'q.\n\n"
                    "📋 Asosiy menyu",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Orqaga", callback_data="admin_referral_list")
                    ]]),
                    parse_mode='Markdown'
                )
                return
            
            # Use the new detailed referral statistics export
            filepath = self.excel_exporter.export_referral_statistics(self.bot_id)
            
            # Send success message with file
            success_text = (
                "✅ **Referral statistika tayyor!**\n\n"
                f"🏆 **TOP referrerlar**: {len(top_referrers)} ta\n"
                f"👥 **Jami referral kelgan**: {len(all_referred)} ta\n\n"
                "📋 **Excel faylda 2 ta varaq:**\n"
                "• 🥇 **TOP 100** - eng ko'p odam qo'shganlar\n"
                "• 📋 **Barcha referral kelganlar** - to'liq ro'yxat\n\n"
                "📎 Fayl pastda yuborildi:"
            )
            
            await query.edit_message_text(
                success_text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="admin_referral_list")
                ]]),
                parse_mode='Markdown'
            )
            
            # Send file to user
            bot_info = self.database.get_bot_by_id(self.bot_id)
            filename = filepath.split('/')[-1]  # Extract filename from path
            
            with open(filepath, 'rb') as file:
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=file,
                    filename=filename,
                    caption=f"🏆 **{bot_info['name']}** - Referral Statistika\n\n"
                           f"📅 **Sana:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                           f"🥇 **TOP referrerlar:** {len(top_referrers)} ta\n"
                           f"👥 **Jami referral kelgan:** {len(all_referred)} ta",
                    parse_mode='Markdown'
                )
            
            # Clean up file
            os.remove(filepath)
            
        except Exception as e:
            logger.error(f"Error exporting referrals: {e}")
            await query.edit_message_text(
                "❌ **Xatolik yuz berdi!**\n\n"
                "Excel fayl yaratishda muammo bo'ldi. Iltimos qayta urinib ko'ring.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="admin_referral_list")
                ]])
            )

    async def _handle_channel_input(self, update, context):
        """Handle channel input from user"""
        user_id = update.effective_user.id
        channel_input = update.message.text.strip()
        
        # Clear the adding_channel state
        if user_id in context.user_data:
            context.user_data[user_id].pop('adding_channel', None)
        
        try:
            # Extract channel ID from input
            if channel_input.startswith('@'):
                channel_username = channel_input[1:]  # Remove @
                channel_id = channel_input
            elif channel_input.startswith('-100'):
                channel_id = channel_input
                channel_username = channel_input
            else:
                # Format help keyboard
                keyboard = [
                    [InlineKeyboardButton("📺 Kanal boshqaruvi", callback_data="admin_channels")],
                    [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="admin")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "✅ **Kanal qo'shish**\n\n"
                    "📌 **Format:** Kanal username (@kanalim) yoki ID (-1001234567890) kiriting.\n\n"
                    "💡 **Masallar:**\n"
                    "• @kanal_majburiy\n"
                    "• -1001234567890\n\n"
                    "📝 Qaytadan kiriting:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            # Try to get channel info and check bot permissions
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title
                if hasattr(chat, 'username') and chat.username:
                    channel_username = chat.username
                
                # Check if bot is admin in the channel
                try:
                    bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
                    if bot_member.status not in ['administrator', 'creator']:
                        await update.message.reply_text(
                            f"⚠️ **Ogohlantirish!**\n\n"
                            f"📺 **Kanal:** {channel_name}\n"
                            f"🚫 Bot bu kanalda admin emas.\n\n"
                            f"**Tavsiya:** Botni kanalga admin qilib qo'ying, aks holda obuna tekshiruvi ishlamasligi mumkin.\n\n"
                            f"Shunga qaramay davom etishni xohlaysizmi? Kanal qo'shiladi..."
                        )
                except Exception as perm_error:
                    logger.warning(f"Could not check bot permissions in channel {channel_id}: {perm_error}")
                    
            except Exception as e:
                logger.error(f"Error getting channel info: {e}")
                
                # Channel not found keyboard
                keyboard = [
                    [InlineKeyboardButton("🔄 Qayta urinish", callback_data="add_new_channel")],
                    [InlineKeyboardButton("📺 Kanal boshqaruvi", callback_data="admin_channels")],
                    [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="admin")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"❌ **Kanal topilmadi!**\n\n"
                    f"🔍 **Kanal ID/Username:** {channel_id}\n\n"
                    f"**Mumkin bo'lgan sabablar:**\n"
                    f"• Kanal mavjud emas\n"
                    f"• Kanal yopiq (private)\n"
                    f"• Bot kanalga kirishga ruxsati yo'q\n\n"
                    f"**Yechim:**\n"
                    f"• Kanal ochiq ekanligini tekshiring\n"
                    f"• Botni kanalga admin qilib qo'ying\n"
                    f"• To'g'ri kanal ID/username kiritganingizni tekshiring",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
                
            # Set default channel name if not found
            if not channel_name:
                channel_name = f"Kanal ({channel_id})"
            
            # Check channel limit (maximum 10 channels per bot)
            existing_channels = self.database.get_required_channels(self.bot_id)
            MAX_CHANNELS = 10
            
            if len(existing_channels) >= MAX_CHANNELS:
                # Channel limit reached keyboard
                keyboard = [
                    [InlineKeyboardButton("📺 Kanal boshqaruvi", callback_data="admin_channels")],
                    [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="admin")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"⚠️ **Kanal limiti tugadi!**\n\n"
                    f"📊 **Joriy holat:** {len(existing_channels)}/{MAX_CHANNELS}\n\n"
                    f"🚫 Bitta bot uchun maksimal {MAX_CHANNELS} ta kanal qo'shish mumkin.\n\n"
                    f"💡 **Yechim:**\n"
                    f"• Avval keraksiz kanallarni olib tashlang\n"
                    f"• Keyin yangi kanal qo'shing\n\n"
                    f"📺 Kanal boshqaruviga o'ting va keraksiz kanallarni o'chiring.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return
            
            # Add channel to database
            success = self.database.add_required_channel(self.bot_id, channel_username, channel_name)
            if success:
                # Update channel count for display
                updated_channels = self.database.get_required_channels(self.bot_id)
                is_reactivated = any(ch.get('channel_id') == channel_id for ch in updated_channels)
                
                action_text = "qayta faollashtirildi" if is_reactivated else "qo'shildi"
                
                # Create keyboard with back to admin button
                keyboard = [
                    [InlineKeyboardButton(" Admin panelga qaytish", callback_data="admin")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ **Kanal muvaffaqiyatli {action_text}!**\n\n"
                    f"📺 **Kanal:** {channel_name}\n"
                    f"🆔 **ID:** {channel_id}\n"
                    f"📊 **Kanal hisobi:** {len(updated_channels)}/{MAX_CHANNELS}\n\n"
                    f"👤 **Username:** @{channel_username if channel_username and not channel_username.startswith('-') else 'Yo`q'}\n\n"
                    f"Endi foydalanuvchilar bu kanalga obuna bo'lmaguncha botdan foydalana olmaydi.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                # Error keyboard
                keyboard = [
                    [InlineKeyboardButton("🔄 Qayta urinish", callback_data="add_new_channel")],
                    [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="admin")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "❌ **Xatolik yuz berdi!**\n\n"
                    "Kanal qo'shishda muammo bo'ldi. Iltimos qayta urinib ko'ring yoki bot adminiga murojaat qiling.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            
            # Error keyboard
            keyboard = [
                [InlineKeyboardButton("🔄 Qayta urinish", callback_data="add_new_channel")],
                [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="admin")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "❌ **Xatolik yuz berdi!**\n\n"
                "Kanal ma'lumotlarini olishda muammo bo'ldi. Kanal ID/username to'g'ri ekanligini tekshiring.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

    async def _handle_channel_management(self, query, context):
        """Handle channel management menu - alias for _handle_channels"""
        await self._handle_channels(query, context)



    def _build_phone_settings_message(self) -> Tuple[str, InlineKeyboardMarkup]:
        """Construct phone settings text and keyboard for reuse."""
        bot_info = self.database.get_bot_by_id(self.bot_id)
        bot_settings = self.database.get_bot_settings(self.bot_id)

        phone_required = bot_settings.get('phone_required', False)
        status_icon = "✅" if phone_required else "❌"
        status_text = "Yoqilgan" if phone_required else "O'chirilgan"

        text = f"📱 <b>Telefon sozlamalari - {bot_info['name']}</b>\n\n"
        text += f"🔘 <b>Telefon talab qilish:</b> {status_icon} {status_text}\n\n"

        if phone_required:
            text += "✅ Foydalanuvchilar botni ishlatish uchun telefon raqamini kiritishi kerak.\n\n"
            text += "📋 <b>Qanday ishlaydi:</b>\n"
            text += "• Start xabaridan keyin telefon raqami so'raladi\n"
            text += "• Foydalanuvchi telefon raqamini yuborishi kerak\n"
            text += "• Telefon tasdiqlangandan keyin bot ishlaydi\n\n"
        else:
            text += "❌ Foydalanuvchilar telefon raqami kiritmasdan ham botni ishlatishlari mumkin.\n\n"

        text += "📝 <b>Matnlarni moslashtirish:</b>\n"
        text += "• &quot;Telefon so'rov matni&quot; - telefon raqamini so'raydigan xabar\n"
        text += "• &quot;Xush kelibsiz matni&quot; - telefon tasdiqlangandan keyin ko'rsatiladigan xabar\n\n"

        toggle_text = "❌ Telefonni o'chirish" if phone_required else "✅ Telefonni yoqish"
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data="phone_toggle_requirement")],
            [InlineKeyboardButton("✏️ Telefon so'rov matni", callback_data="phone_edit_request")],
            [InlineKeyboardButton("✏️ Xush kelibsiz matni", callback_data="phone_edit_post")],
            [InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="admin")]
        ]

        return text, InlineKeyboardMarkup(keyboard)

    async def _handle_phone_settings(self, query, context):
        """Handle phone settings management"""
        try:
            await query.answer()
            text, reply_markup = self._build_phone_settings_message()
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error in _handle_phone_settings: {e}")
            await query.edit_message_text("❌ Xatolik yuz berdi!")

    async def _toggle_phone_requirement(self, query, context):
        """Toggle phone requirement for bot"""
        try:
            await query.answer()
            
            # Get current phone requirement status
            bot_settings = self.database.get_bot_settings(self.bot_id)
            current_status = bot_settings.get('phone_required', False)
            
            # Toggle the status
            new_status = not current_status
            
            # Update in database
            success = self.database.update_bot_settings(self.bot_id, {'phone_required': new_status})
            
            if success:
                status_text = "yoqildi ✅" if new_status else "o'chirildi ❌"
                
                message_text = f"🔄 **Telefon talab qilish {status_text}!**\n\n"
                if new_status:
                    message_text += "✅ Endi foydalanuvchilar botni ishlatish uchun telefon raqamini kiritishi kerak."
                else:
                    message_text += "❌ Foydalanuvchilar telefon raqami kiritmasdan ham botni ishlatishlari mumkin."
                message_text += "\n\n⏳ Ozgina kuting..."
                
                await query.edit_message_text(
                    message_text,
                    parse_mode='Markdown'
                )
                
                # Wait a moment then return to phone settings
                await asyncio.sleep(2)
                await self._handle_phone_settings(query, context)
            else:
                await query.edit_message_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")
                
        except Exception as e:
            logger.error(f"Error toggling phone requirement: {e}")
            await query.edit_message_text("❌ Xatolik yuz berdi!")
            await asyncio.sleep(2)
            await self._handle_phone_settings(query, context)

    async def _show_phone_statistics(self, query, context):
        """Show phone verification statistics"""
        try:
            await query.answer()
            
            bot_info = self.database.get_bot_by_id(self.bot_id)
            
            # Get phone statistics
            participants = self.database.get_all_participants(self.bot_id)
            total_users = len(participants)
            
            # Count users with phone numbers for this bot
            users_with_phone = sum(1 for participant in participants if participant.get('phone_number'))
            users_without_phone = total_users - users_with_phone
            
            # Calculate percentage
            phone_percentage = (users_with_phone / total_users * 100) if total_users > 0 else 0
            
            text = f"📱 <b>Telefon statistikasi - {bot_info['name']}</b>\n\n"
            
            text += f"👥 <b>Umumiy foydalanuvchilar:</b> {total_users:,}\n\n"
            
            text += f"📊 <b>Telefon holati:</b>\n"
            text += f"├ Telefon kiritgan: {users_with_phone:,} ({phone_percentage:.1f}%)\n"
            no_phone_percentage = 100 - phone_percentage if total_users > 0 else 0
            text += f"└ Telefon kiritmagan: {users_without_phone:,} ({no_phone_percentage:.1f}%)\n\n"
            
            if users_with_phone > 0:
                text += f"📈 <b>Telefon to'plash samaradorligi:</b>\n"
                text += f"└ {phone_percentage:.1f}% foydalanuvchi telefon kiritgan\n\n"
            
            text += f"💡 <b>Maslahat:</b>\n"
            if phone_percentage < 50:
                text += f"Telefon talab qilishni yoqib, yanada ko'p ma'lumot to'plang"
            else:
                text += f"Yaxshi natija! Foydalanuvchilar faol telefon kiritishmoqda"
            
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_phone_settings")]]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error in phone statistics: {e}")
            await query.edit_message_text("❌ Statistika ma'lumotlarini olishda xatolik!")

    async def _handle_channel_management(self, query, context):
        """Handle channel management menu - alias for _handle_channels"""
        await self._handle_channels(query, context)

    # Missing callback handlers for additional functionality
    async def _handle_detailed_stats(self, query, context):
        """Handle detailed statistics view"""
        await query.answer("📊 Batafsil statistika hozircha ishlab chiqilmoqda...")

    async def _handle_add_new_channel(self, query, context):
        """Handle adding new channel"""
        user_id = query.from_user.id
        context.user_data[user_id] = {'adding_channel': True}
        await self._safe_edit_message(query,
            "📺 **Kanal qo'shish**\n\n"
            "Majburiy obuna qilmoqchi bo'lgan kanalingizni username yoki ID sini yuboring.\n\n"
            "**Misol:**\n"
            "• @kanalim\n"
            "• -1001234567890\n\n"
            "❗ Kanal ochiq bo'lishi kerak yoki botni kanalga admin qilib qo'ying.",
            parse_mode='Markdown'
        )



    async def handle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video submissions"""
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        
        # Check if user is in broadcast mode
        user_data = getattr(context, 'user_data', {}).get(user_id, {})
        if user_data.get('broadcast_mode'):
            await self._handle_broadcast_message(update, context)
            return

        if user_data.get('editing') == 'manual_message':
            await self._handle_manual_edit_submission(update, context)
            return

        if user_data.get('editing') == 'referral_followup_message':
            await self._handle_referral_followup_submission(update, context)
            return

        if user_data.get('editing') == 'referral_share_message':
            await self._handle_referral_share_submission(update, context)
            return
        
        # Check if user has active contest participation
        active_participation = self.database.get_active_participation(user_id, self.bot_id)
        
        if not active_participation:
            await update.message.reply_text(
                "🎥 Avval konkursga qo'shiling!\n"
                "Buning uchun /join buyrug'ini bosing."
            )
            return
            
        # Save video submission
        try:
            file_id = update.message.video.file_id
            caption = update.message.caption or ""
            
            submission_id = self.database.create_submission(
                user_id=user_id,
                contest_id=active_participation['contest_id'],
                file_id=file_id,
                file_type='video',
                caption=caption
            )
            
            await update.message.reply_text(
                "✅ Videongiz muvaffaqiyatli yuborildi!\n"
                "🏆 Omad tilaymiz!"
            )
            
        except Exception as e:
            logger.error(f"Error handling video submission: {e}")
            await update.message.reply_text(
                "❌ Video yuborishda xatolik yuz berdi. Qaytadan urinib ko'ring."
            )

    def _ensure_database_methods(self):
        """Ensure all database methods exist gracefully"""
        # This method exists to handle any missing database method calls gracefully
        pass
        
    async def _check_required_subscriptions_with_custom_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, bot_info: dict, bot_settings: dict) -> bool:
        """Check subscriptions and show custom start message with channel buttons if needed"""
        if not update.effective_user:
            return False
        user_id = update.effective_user.id
        
        if self._is_admin_user(user_id):
            return True

        # Get required channels for this bot
        required_channels = self.database.get_required_channels(self.bot_id)
        
        if not required_channels:
            # No subscription requirement - just show start message
            await self._show_start_message_only(update, bot_info, bot_settings)
            return True
        
        # Check each channel
        not_subscribed = []
        for channel in required_channels:
            channel_id = channel.get('channel_id', '').replace('@', '')
            if not channel_id:
                continue
                
            try:
                # Check if user is member of channel
                chat_member = await context.bot.get_chat_member(f"@{channel_id}", user_id)
                if chat_member.status in ['left', 'kicked']:
                    not_subscribed.append(channel)
            except Exception as e:
                logger.warning(f"Error checking subscription for channel @{channel_id}: {e}")
                not_subscribed.append(channel)
        
        if not_subscribed:
            # Show start message WITH channel buttons
            await self._show_start_message_with_channels(update, bot_info, bot_settings, not_subscribed)
            return False
        else:
            # All subscribed - show normal start message
            await self._show_start_message_only(update, bot_info, bot_settings)
            return True

    async def _show_start_message_with_channels(self, update: Update, bot_info: dict, bot_settings: dict, not_subscribed: list):
        """Show custom start message with subscription channel buttons"""
        # Get custom start message
        custom_welcome = bot_settings.get('welcome_message')
        if not custom_welcome:
            custom_welcome = f"🎉 **{bot_info['name']}ga xush kelibsiz!**\n\nKonkurslarda ishtirok eting va sovrinlar yutib oling!"
        
        instruction_block = (
            "1️⃣ Avvalo kanallarga qo'shiling.\n"
            "2️⃣ So'ng \"✅ Bajarildi\" tugmasini bosing."
        )

        if "Bajarildi" not in custom_welcome:
            custom_welcome = f"{custom_welcome}\n\n{instruction_block}"

        # Prepare keyboard with channel buttons
        reply_markup = self._build_subscription_keyboard(not_subscribed)

        # Send message with media if available
        welcome_media = bot_settings.get('welcome_media')
        media_type = bot_settings.get('welcome_media_type')
        
        try:
            if welcome_media and media_type:
                if media_type == 'photo':
                    await update.message.reply_photo(
                        photo=welcome_media, 
                        caption=custom_welcome, 
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                elif media_type == 'video':
                    await update.message.reply_video(
                        video=welcome_media, 
                        caption=custom_welcome, 
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(custom_welcome, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                await update.message.reply_text(custom_welcome, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error sending welcome message with channels: {e}")
            await update.message.reply_text(custom_welcome, reply_markup=reply_markup)

    async def _show_start_message_only(self, update: Update, bot_info: dict, bot_settings: dict):
        """Show only the custom start message without channel buttons"""
        # Get custom start message
        custom_welcome = bot_settings.get('welcome_message')
        if not custom_welcome:
            custom_welcome = f"🎉 **{bot_info['name']}ga xush kelibsiz!**\n\nKonkurslarda ishtirok eting va sovrinlar yutib oling!"
        
        # Send message with media if available
        welcome_media = bot_settings.get('welcome_media')
        media_type = bot_settings.get('welcome_media_type')
        
        try:
            if welcome_media and media_type:
                if media_type == 'photo':
                    await update.message.reply_photo(
                        photo=welcome_media, 
                        caption=custom_welcome, 
                        parse_mode='Markdown'
                    )
                elif media_type == 'video':
                    await update.message.reply_video(
                        video=welcome_media, 
                        caption=custom_welcome, 
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(custom_welcome, parse_mode='Markdown')
            else:
                await update.message.reply_text(custom_welcome, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
            await update.message.reply_text(custom_welcome)

    async def _show_subscription_requirement(self, update: Update, not_subscribed: list, bot_info: dict):
        """Show subscription requirement message with channels (improved version)"""
        subscription_text = (
            f"🔔 **{bot_info.get('name', 'Bot')}dan foydalanish uchun quyidagi kanallarga obuna bo'ling:**\n\n"
            "1️⃣ Avvalo kanallarga qo'shiling.\n"
            "2️⃣ So'ng \"✅ Bajarildi\" tugmasini bosing."
        )

        reply_markup = self._build_subscription_keyboard(not_subscribed)
        await update.message.reply_text(subscription_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    def _build_subscription_keyboard(self, channels: list) -> InlineKeyboardMarkup:
        """Build inline keyboard for subscription flow with a single confirm button."""
        keyboard = []

        for channel in channels:
            channel_username = ''
            channel_identifier = ''

            if isinstance(channel, dict):
                channel_username = (
                    channel.get('username')
                    or channel.get('channel_username')
                    or channel.get('channel_id')
                )
                channel_identifier = channel.get('channel_id') or channel.get('id') or channel_username
            elif isinstance(channel, (list, tuple)):
                if len(channel) > 3 and channel[3]:
                    channel_username = channel[3]
                elif len(channel) > 1 and channel[1]:
                    channel_username = channel[1]

                if len(channel) > 1 and channel[1]:
                    channel_identifier = channel[1]

            if channel_username and not str(channel_username).startswith('-'):
                username = str(channel_username).lstrip('@')
                keyboard.append([
                    InlineKeyboardButton(
                        "➕ Kanalga obuna bo'lish",
                        url=f"https://t.me/{username}"
                    )
                ])
            else:
                callback_data = "channel_info"
                if channel_identifier:
                    callback_data = f"channel_info:{channel_identifier}"
                keyboard.append([
                    InlineKeyboardButton(
                        "➕ Kanalga obuna bo'lish",
                        callback_data=callback_data
                    )
                ])

        keyboard.append([InlineKeyboardButton("✅ Bajarildi", callback_data="check_subscription")])
        return InlineKeyboardMarkup(keyboard)

    async def _show_final_welcome_with_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show final welcome message with referral and account buttons"""
        # Show keyboard buttons with referral and account options
        keyboard = [
            [KeyboardButton("🔗 Mening referral havolam")],
            [KeyboardButton("📊 Mening hisobim")],
            [KeyboardButton("📂 Qo'llanma")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

        if update.effective_chat:
            self._restore_reply_keyboard_flag(context, update.effective_chat.id)
        
        await update.message.reply_text(
            "🎉 **Tabriklaymiz!**\n\n"
            "✅ Barcha tekshiruvlar muvaffaqiyatli o'tdi!\n\n"
            "🏆 Endi konkursda ishtirok eta olasiz!\n"
            "👇 Quyidagi tugmalardan birini tanlang:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    async def _show_final_buttons_after_subscription(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Show final buttons after subscription is verified"""
        keyboard = [
            [KeyboardButton("🔗 Mening referral havolam")],
            [KeyboardButton("📊 Mening hisobim")],
            [KeyboardButton("📂 Qo'llanma")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        welcome_text = (
            "🎉 *Xush kelibsiz!*\n\n"
            "✅ Barcha tekshiruvlar muvaffaqiyatli o'tdi!\n\n"
            "🏆 Endi konkursda ishtirok eta olasiz!\n"
            "👇 Quyidagi tugmalardan birini tanlang:"
        )
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        self._restore_reply_keyboard_flag(context, query.message.chat_id)

        # Remove the inline message we just responded to, if possible
        try:
            await query.message.delete()
        except Exception as delete_error:
            logger.debug(f"Could not delete subscription message: {delete_error}")
    
    async def _check_required_subscriptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if user is subscribed to all required channels"""
        if not update.effective_user:
            return False
        user_id = update.effective_user.id
        
        # Get required channels for this bot
        required_channels = self.database.get_required_channels(self.bot_id)
        
        if not required_channels:
            return True  # No subscription requirement
        
        # Check each channel
        not_subscribed = []
        for channel in required_channels:
            try:
                # Handle both dict and tuple formats properly
                if isinstance(channel, dict):
                    channel_id = channel.get('channel_id') or channel.get('channel_username')
                    channel_name = channel.get('name') or channel.get('channel_name', 'Kanal')
                else:
                    # Tuple format: (id, channel_id, name, username, ...)
                    channel_id = channel[1] if len(channel) > 1 else None
                    channel_name = channel[2] if len(channel) > 2 else 'Kanal'
                
                if not channel_id:
                    logger.error(f"No channel_id found for channel: {channel}")
                    not_subscribed.append(channel)
                    continue
                
                # Clean channel_id if it has @ prefix
                if isinstance(channel_id, str) and channel_id.startswith('@'):
                    channel_id = channel_id[1:]
                
                # If it's a username, convert to @username for API call
                if isinstance(channel_id, str) and not channel_id.startswith('-'):
                    chat_id = f"@{channel_id}"
                else:
                    chat_id = channel_id
                
                # Check if user is member of channel
                chat_member = await context.bot.get_chat_member(chat_id, user_id)
                logger.info(f"User {user_id} status for {chat_id}: {chat_member.status}")
                
                if chat_member.status in ['left', 'kicked']:
                    not_subscribed.append(channel)
                    
            except Exception as e:
                logger.warning(f"Error checking subscription for channel {channel}: {e}")
                not_subscribed.append(channel)
        
        if not_subscribed:
            # Show subscription requirement
            bot_info = self.database.get_bot_by_id(self.bot_id)
            await self._show_subscription_requirement(update, not_subscribed, bot_info)
            return False
        
        return True
    
    async def _check_phone_verification(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Check if phone verification is required and handle it"""
        if not update.effective_user:
            return False
        user_id = update.effective_user.id
        
        # Check if phone verification is required for this bot
        bot_settings = self.database.get_bot_settings(self.bot_id)
        phone_required = bot_settings.get('phone_required', False)
        
        if not phone_required or self._is_admin_user(user_id):
            return True  # Phone not required
        
        # Enforce fresh phone confirmation even if previously submitted
        user_state = self._get_user_state(context, user_id)
        if user_state.get('phone_verified'):
            return True

        self._mark_phone_pending(context, user_id)
        logger.info(f"Bot {self.bot_id} - Requesting phone verification from user {user_id}")
        await self._request_phone_number(update, context)
        return False
    
    async def _request_phone_number(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Request phone number from user while keeping main menu visible."""
        reply_markup = self._build_phone_request_keyboard()
        request_text = self._get_phone_request_message()

        if update.effective_chat:
            self._restore_reply_keyboard_flag(context, update.effective_chat.id)

        await update.message.reply_text(
            request_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        await update.message.reply_text(
            self._get_phone_menu_hint(),
            parse_mode='Markdown'
        )
    
    async def _show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu with referral and account buttons"""
        reply_markup = self._build_main_menu_keyboard()
        success_text = self._get_phone_post_message()

        if update.effective_chat:
            self._restore_reply_keyboard_flag(context, update.effective_chat.id)

        await update.message.reply_text(
            success_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def handle_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle contact (phone number) from user"""
        if not update.message.contact or not update.effective_user:
            return
        
        user_id = update.effective_user.id
        contact = update.message.contact
        
        # Verify this is user's own contact
        if contact.user_id != user_id:
            await update.message.reply_text(
                "❌ Faqat o'zingizning telefon raqamingizni yuborishingiz kerak!",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        # Save phone number
        phone_number = contact.phone_number
        self.database.update_user_phone(user_id, phone_number)
        self._mark_phone_verified(context, user_id)
        
        # Continue with main menu
        await self._show_main_menu(update, context)
    
    async def _handle_phone_number_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Handle phone number sent as text message"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        # Check if bot requires phone
        bot_settings = self.database.get_bot_settings(self.bot_id)
        phone_required = bot_settings.get('phone_required', False)
        
        if not phone_required:
            return False  # Phone not required
        
        # Check if text looks like a phone number
        import re
        phone_pattern = r'^[\+]?[0-9\s\-\(\)]{9,15}$'
        
        if re.match(phone_pattern, text):
            # Clean phone number
            cleaned_phone = re.sub(r'[^\d\+]', '', text)
            
            # Validate phone number format
            if len(cleaned_phone) >= 9 and len(cleaned_phone) <= 15:
                # Save phone number
                self.database.update_user_phone(user_id, cleaned_phone)
                self._mark_phone_verified(context, user_id)
                
                await update.message.reply_text(
                    "✅ Telefon raqamingiz qabul qilindi!",
                    reply_markup=ReplyKeyboardRemove()
                )

                # Continue with main menu
                await self._show_main_menu(update, context)
                return True
            else:
                await update.message.reply_text(
                    "❌ **Noto'g'ri format!**\n\n"
                    "Telefon raqamini to'g'ri formatda yuboring:\n"
                    "• Misol: 901234567\n"
                    "• Yoki: +998901234567\n\n"
                    "📲 Yoki \"Raqamni ulashish\" tugmasini bosing."
                )
                return True
        
        return False
    
    async def _handle_statistics(self, query, context):
        """Handle statistics display"""
        try:
            await query.answer()
            
            bot_info = self.database.get_bot_by_id(self.bot_id)
            stats_raw = self.database.get_bot_statistics(self.bot_id)

            stats = stats_raw or {}
            total_users = stats.get('total_users', 0) or 0
            users_with_phone = stats.get('users_with_phone', 0) or 0
            new_users_24h = stats.get('new_users_24h', 0) or 0
            new_users_7d = stats.get('new_users_7d', 0) or 0
            required_channels = stats.get('required_channels', 0) or 0
            
            # Calculate percentages
            phone_percentage = 0
            if total_users > 0:
                phone_percentage = (users_with_phone / total_users) * 100
            
            # Create statistics message
            bot_name = bot_info['name'] if bot_info else "Bot"
            text = f"📊 **Statistika - {bot_name}**\n\n"
            
            text += "👥 **Foydalanuvchilar:**\n"
            text += f"├ Jami: {total_users:,}\n"
            text += f"├ Telefon bilan: {users_with_phone:,} ({phone_percentage:.1f}%)\n"
            text += f"├ 24 soatda yangi: {new_users_24h:,}\n"
            text += f"└ 7 kunda yangi: {new_users_7d:,}\n\n"
            
            text += "⚙️ **Tizim:**\n"
            text += f"├ Majburiy kanallar: {required_channels:,}/10\n"
            text += f"└ Bot holati: ✅ Faol\n\n"
            
            # Growth indicators
            if new_users_24h > 0:
                text += f"📈 **O'sish**: +{new_users_24h} foydalanuvchi (24h)"
            else:
                text += "📊 **Holat**: Barqaror"
            
            keyboard = [
                [InlineKeyboardButton(" Admin panelga qaytish", callback_data="admin")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in _handle_statistics: {e}")
            await self._safe_edit_message(
                query,
                "❌ Statistikani yuklashda xatolik yuz berdi.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Orqaga", callback_data="admin")
                ]])
            )
    
    async def handle_referral_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle referral link button press"""
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        bot_info = self.database.get_bot_by_id(self.bot_id)
        
        if not bot_info:
            await update.message.reply_text("❌ Bot ma'lumotlari topilmadi!")
            return
        
        referral_link = self._generate_referral_link(user_id)
        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)

        await self._send_referral_share_message(
            context,
            update.effective_chat.id,
            referral_link,
            update.effective_user,
            referral_count,
        )

    async def _handle_manual_view(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Deliver the guide/manual content to the requesting user."""
        bot_settings = self.database.get_bot_settings(self.bot_id)
        bot_info = self.database.get_bot_by_id(self.bot_id)
        manual_settings = self._get_manual_settings(bot_settings, bot_info)

        await self._send_manual_message(context, update.effective_chat.id, manual_settings)
    
    async def handle_my_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle my account button press"""
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        user_info = self.database.get_user_by_telegram_id(user_id)

        if not user_info:
            # Recreate user record to avoid missing data on fresh bots
            user = update.effective_user
            self.database.get_or_create_user(
                user_id,
                user.first_name,
                user.last_name,
                user.username
            )
            user_info = self.database.get_user_by_telegram_id(user_id)

        if not user_info:
            await update.message.reply_text("❌ Foydalanuvchi ma'lumotlari topilmadi!")
            return

        referral_count = self.database.get_user_referral_count(self.bot_id, user_id)

        def _md(value: Optional[str], fallback: str) -> str:
            return escape_markdown(value if value not in (None, "") else fallback, version=1)

        first_name = _md(user_info.get('first_name'), "N/A")
        last_name = _md(user_info.get('last_name'), "Yo'q")
        username_raw = user_info.get('username')
        username_display = f"@{escape_markdown(username_raw, version=1)}" if username_raw else "Yo'q"
        phone_number = _md(user_info.get('phone_number'), "Berilmagan")
        registration_date = _md(str(user_info.get('created_at') or "Nomalum"), "Nomalum")
        account_text = (
            " **Referral statistika:**\n"
            f"👥 Siz {referral_count} ta odam taklif qildingiz\n\n"
            "💡 **Maslahat:** Referral havolangizni do'stlaringizga ulashing va ko'proq mukofot oling!"
        )

        try:
            await update.message.reply_text(account_text, parse_mode='Markdown')
        except BadRequest as send_error:
            if "can't parse entities" in str(send_error).lower():
                await update.message.reply_text(account_text)
            else:
                logger.error(f"Error sending account info: {send_error}")
                await update.message.reply_text(
                    "❌ Hisob ma'lumotlarini ko'rsatishda xatolik yuz berdi. Keyinroq yana urinib ko'ring."
                )
    
    async def _toggle_subscription(self, query, context):
        """Toggle subscription requirement for bot"""
        try:
            await query.answer()
            
            # Get current subscription status
            bot_settings = self.database.get_bot_settings(self.bot_id)
            current_status = bot_settings.get('subscription_enabled', False)
            
            # Toggle the status
            new_status = not current_status
            
            # Update in database
            success = self.database.update_bot_settings(self.bot_id, {'subscription_enabled': new_status})
            
            if success:
                status_text = "yoqildi ✅" if new_status else "o'chirildi ❌"
                
                message_text = f"🔄 **Majburiy obuna {status_text}!**\n\n"
                if new_status:
                    message_text += "✅ Endi foydalanuvchilar botni ishlatish uchun kanallarga obuna bo'lishi kerak.\n\n"
                else:
                    message_text += "❌ Foydalanuvchilar obuna bo'lmasdan ham botni ishlatishlari mumkin.\n\n"
                message_text += "⏳ Ozgina kuting..."
                
                await query.edit_message_text(
                    message_text,
                    parse_mode='Markdown'
                )
                
                # Wait a moment then return to channel management
                await asyncio.sleep(2)
                await self._handle_channels(query, context)
            else:
                await query.edit_message_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")
                
        except Exception as e:
            logger.error(f"Error toggling subscription: {e}")
            await query.edit_message_text("❌ Xatolik yuz berdi!")
            await asyncio.sleep(2)

    # ==================== ADVANCED ADMIN PANEL METHODS ====================




            
        except Exception as e:
            logger.error(f"Error in analytics dashboard: {e}")
            await query.answer("❌ Analytics ma'lumotlarini olishda xatolik!", show_alert=True)






            await query.answer("❌ Xatolik yuz berdi!", show_alert=True)





    # ==================== NEW ADMIN PANEL METHODS ====================








    async def _handle_view_channel(self, query, context, channel_id):
        """Handle channel view when URL is not available"""
        try:
            await query.answer()
            
            # Get channel information
            channels = self.database.get_required_channels(self.bot_id)
            channel_info = None
            
            for channel in channels:
                if isinstance(channel, dict):
                    if str(channel.get('channel_id')) == str(channel_id) or str(channel.get('id')) == str(channel_id):
                        channel_info = channel
                        break
                else:
                    # Tuple format
                    if len(channel) > 1 and str(channel[1]) == str(channel_id):
                        channel_info = {
                            'channel_id': channel[1],
                            'name': channel[2] if len(channel) > 2 else 'Nomalum',
                            'username': channel[3] if len(channel) > 3 else None
                        }
                        break
            
            if not channel_info:
                await query.answer("❌ Kanal ma'lumotlari topilmadi!", show_alert=True)
                return
            
            channel_name = channel_info.get('name', 'Nomalum kanal')
            channel_username = channel_info.get('username') or channel_info.get('channel_username')
            
            text = (
                f"📺 **Kanal ma'lumotlari**\n\n"
                f"📝 **Nomi:** {channel_name}\n"
            )
            
            if channel_username:
                if not channel_username.startswith('@'):
                    channel_username = f"@{channel_username}"
                text += f"🔗 **Username:** {channel_username}\n"
                text += f"🌐 **Link:** https://t.me/{channel_username[1:]}\n\n"
            else:
                text += f"🆔 **ID:** `{channel_id}`\n\n"
            
            text += (
                f"💡 **Kanalga kirish uchun:**\n"
                f"1. Yuqoridagi linkni bosing\n"
                f"2. Yoki Telegram qidiruv bo'limida {channel_username or channel_id} ni qidiring\n\n"
                f"📱 **Mobil:** Username ni qidiruvda kiriting"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Kanallar ro'yxati", callback_data="channel_list")],
                [InlineKeyboardButton("🔙 Kanal boshqaruvi", callback_data="admin_channels")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._safe_edit_message(query, text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error viewing channel: {e}")
            await query.answer("❌ Kanal ma'lumotlarini ko'rsatishda xatolik!", show_alert=True)

    async def _handle_channel_info_callback(self, query, channel_id):
        """Show channel information to end users without altering the main message."""
        try:
            channels = self.database.get_required_channels(self.bot_id)
            channel_info = None

            for channel in channels:
                if isinstance(channel, dict):
                    identifiers = {
                        str(channel.get('channel_id')),
                        str(channel.get('id')),
                        str(channel.get('username')),
                        str(channel.get('channel_username'))
                    }
                    if channel_id and channel_id in identifiers:
                        channel_info = channel
                        break
                elif isinstance(channel, (list, tuple)):
                    potential_ids = set()
                    if len(channel) > 1 and channel[1]:
                        potential_ids.add(str(channel[1]))
                    if len(channel) > 3 and channel[3]:
                        potential_ids.add(str(channel[3]))
                    if channel_id and channel_id in potential_ids:
                        channel_info = {
                            'name': channel[2] if len(channel) > 2 else 'Nomalum kanal',
                            'channel_id': channel[1] if len(channel) > 1 else None,
                            'username': channel[3] if len(channel) > 3 else None,
                        }
                        break

            if not channel_info:
                await query.message.reply_text("❌ Kanal ma'lumotlari topilmadi!", quote=True)
                return

            channel_name = channel_info.get('name') or channel_info.get('channel_name') or 'Nomalum kanal'
            channel_username = channel_info.get('username') or channel_info.get('channel_username')
            channel_identifier = channel_info.get('channel_id') or channel_info.get('id')

            info_lines = [f"📺 **{channel_name}**"]
            if channel_username:
                username_clean = channel_username.lstrip('@')
                info_lines.append(f"🔗 https://t.me/{username_clean}")
            elif channel_identifier:
                info_lines.append(f"🆔 Kanal ID: `{channel_identifier}`")
                info_lines.append("🔍 Telegram qidiruvda ID bo'yicha qidiring yoki kanal egasidan username so'rang.")

            await query.message.reply_text(
                "\n".join(info_lines),
                parse_mode='Markdown'
            )
        except Exception as info_error:
            logger.error(f"Error providing channel info: {info_error}")
            await query.message.reply_text("❌ Kanal ma'lumotlarini yuborishda xatolik!", quote=True)


