"""
Admin Panel - Handles admin interface for the main bot
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError, BadRequest, Forbidden
from admin_welcome_handler import handle_edit_welcome, handle_welcome_message_input

logger = logging.getLogger(__name__)

class AdminPanel:
    """Admin panel for main bot management"""
    
    def __init__(self, database):
        self.database = database
        
    async def show_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show admin panel interface"""
        user_id = update.effective_user.id
        from config import Config
        config = Config()
        
        # Check if user is admin
        if not config.is_admin(user_id):
            await update.message.reply_text("❌ Sizda admin huquqlari yo'q!")
            return
            
        # Get system statistics
        stats = self.database.get_system_stats()
        
        # Create admin keyboard
        keyboard = [
            [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton("🤖 Barcha botlar", callback_data="admin_all_bots")],
            [InlineKeyboardButton(" Barcha foydalanuvchilarga xabar", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔄 Botlarni qayta ishga tushirish", callback_data="admin_restart_bots")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        admin_text = (
            "🔧 **Admin Panel**\n\n"
            f"📊 **Tizim statistikasi:**\n"
            f"🤖 Jami botlar: {stats['total_bots']}\n"
            f"✅ Faol botlar: {stats['active_bots']}\n"
            f"👥 Jami foydalanuvchilar: {stats['total_users']}\n\n"
            f"Quyidagi amallardan birini tanlang:"
        )
        
        await update.message.reply_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def handle_admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin panel callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        from config import Config
        config = Config()
        
        # Verify admin rights
        if not config.is_admin(user_id):
            await query.edit_message_text("❌ Sizda admin huquqlari yo'q!")
            return
            
        if query.data == "admin_stats":
            await self._show_detailed_stats(query)
        elif query.data == "admin_all_bots":
            await self._show_all_bots(query)
        elif query.data == "admin_broadcast":
            await self._show_broadcast_options(query, context)
        elif query.data == "admin_bot_settings":
            await self._show_bot_settings(query, context)
        elif query.data == "admin_restart_bots":
            await self._restart_all_bots(query, context)
        elif query.data.startswith("bot_edit_"):
            await self._handle_bot_edit(query, context)
        elif query.data.startswith("edit_welcome_"):
            await self._handle_edit_welcome(query, context)
        elif query.data.startswith("broadcast_"):
            await self._handle_broadcast_action(query, context)
        elif query.data.startswith("confirm_broadcast_"):
            await self._confirm_broadcast(query, context)
        elif query.data.startswith("edit_name_"):
            await self._handle_edit_name(query, context)
        elif query.data.startswith("edit_description_"):
            await self._handle_edit_description(query, context)
        elif query.data.startswith("toggle_phone_"):
            await self._handle_toggle_phone(query, context)
        elif query.data.startswith("toggle_subscription_"):
            await self._handle_toggle_subscription(query, context)
        elif query.data.startswith("manage_channels_"):
            await self._handle_manage_channels(query, context)
        elif query.data.startswith("add_channel_"):
            await self._handle_add_channel(query, context)
        elif query.data.startswith("remove_channels_"):
            await self._handle_remove_channels(query, context)
        elif query.data.startswith("delete_channel_"):
            await self._handle_delete_channel(query, context)
        elif query.data == "admin_back":
            # Show main admin panel again
            await self._show_main_admin_panel(query, context)
    
    async def _show_broadcast_options(self, query, context):
        """Show broadcast message options"""
        text = (
            "📢 **Barcha foydalanuvchilarga xabar yuborish**\n\n"
            "Qaysi foydalanuvchilarga xabar yubormoqchisiz?\n\n"
            "⚠️ **Diqqat:** Bu amal qaytarib bo'lmaydi!"
        )
        
        keyboard = [
            [InlineKeyboardButton("👥 Barcha foydalanuvchilar", callback_data="broadcast_all_users")],
            [InlineKeyboardButton("🤖 Faqat bot egalariga", callback_data="broadcast_bot_owners")],
            [InlineKeyboardButton("🆕 Yangi foydalanuvchilar (7 kun)", callback_data="broadcast_new_users")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_broadcast_action(self, query, context):
        """Handle broadcast action selection"""
        action = query.data.split('_', 1)[1]  # broadcast_all_users -> all_users
        
        # Store broadcast type in user context
        context.user_data['broadcast_type'] = action
        context.user_data['waiting_for_broadcast'] = True
        
        text = (
            "📝 **Xabar matni yozing**\n\n"
            "Foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yozing.\n\n"
            "📌 **Qo'llab-quvvatlanadigan formatlar:**\n"
            "• Matn xabarlari\n"
            "• Rasm + matn (caption)\n"
            "• Video + matn (caption)\n\n"
            "⚠️ **Eslatma:** Xabarni yuborganingizdan keyin bekor qila olmaysiz!"
        )
        
        keyboard = [[InlineKeyboardButton("❌ Bekor qilish", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle broadcast message input"""
        user_id = update.effective_user.id
        config = context.bot_data.get('config')
        
        # Check admin rights
        if not config.is_admin(user_id):
            return
            
        # Check if waiting for broadcast message
        if not context.user_data.get('waiting_for_broadcast'):
            return
            
        broadcast_type = context.user_data.get('broadcast_type')
        if not broadcast_type:
            await update.message.reply_text("❌ Xatolik: Broadcast turi aniqlanmagan!")
            return
        
        # Get message content
        message_text = update.message.text if update.message.text else update.message.caption
        photo = update.message.photo[-1] if update.message.photo else None
        video = update.message.video if update.message.video else None
        
        if not message_text and not photo and not video:
            await update.message.reply_text(
                "❌ Xabar matni, rasm yoki video yuborishingiz kerak!\n\n"
                "Qaytadan urinib ko'ring."
            )
            return
        
        # Get target users
        try:
            if broadcast_type == "all_users":
                users = self.database.get_all_users_for_broadcast()
                target_description = "barcha foydalanuvchilarga"
            elif broadcast_type == "bot_owners":
                users = self.database.get_bot_owners_for_broadcast()
                target_description = "bot egalariga"
            elif broadcast_type == "new_users":
                users = self.database.get_new_users_for_broadcast(days=7)
                target_description = "yangi foydalanuvchilarga (7 kun)"
            else:
                await update.message.reply_text("❌ Noto'g'ri broadcast turi!")
                return
                
            if not users:
                await update.message.reply_text("❌ Maqsadli foydalanuvchilar topilmadi!")
                context.user_data.pop('waiting_for_broadcast', None)
                context.user_data.pop('broadcast_type', None)
                return
            
            # Confirm broadcast
            keyboard = [
                [InlineKeyboardButton("✅ Ha, yuborish", callback_data=f"confirm_broadcast_{broadcast_type}")],
                [InlineKeyboardButton("❌ Yo'q, bekor qilish", callback_data="admin_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store message data
            context.user_data['broadcast_message'] = {
                'text': message_text,
                'photo': photo.file_id if photo else None,
                'video': video.file_id if video else None
            }
            
            await update.message.reply_text(
                f"📢 **Xabar tasdiqlash**\n\n"
                f"🎯 Maqsad: {target_description}\n"
                f"👥 Foydalanuvchilar soni: {len(users)}\n\n"
                f"Haqiqatan ham xabar yubormoqchimisiz?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error preparing broadcast: {e}")
            await update.message.reply_text("❌ Xabar tayyorlashda xatolik yuz berdi!")
            context.user_data.pop('waiting_for_broadcast', None)
            context.user_data.pop('broadcast_type', None)
    
    async def _confirm_broadcast(self, query, context):
        """Confirm and send broadcast message"""
        broadcast_type = query.data.split('_', 2)[2]  # confirm_broadcast_all_users -> all_users
        
        # Get message data
        message_data = context.user_data.get('broadcast_message')
        if not message_data:
            await query.edit_message_text("❌ Xabar ma'lumotlari topilmadi!")
            return
        
        # Get target users
        try:
            if broadcast_type == "all_users":
                users = self.database.get_all_users_for_broadcast()
                target_description = "barcha foydalanuvchilarga"
            elif broadcast_type == "bot_owners":
                users = self.database.get_bot_owners_for_broadcast()
                target_description = "bot egalariga"
            elif broadcast_type == "new_users":
                users = self.database.get_new_users_for_broadcast(days=7)
                target_description = "yangi foydalanuvchilarga"
            else:
                await query.edit_message_text("❌ Noto'g'ri broadcast turi!")
                return
            
            await query.edit_message_text(
                f"📤 Xabar yuborilmoqda...\n\n"
                f"🎯 {target_description}\n"
                f"👥 Jami: {len(users)} foydalanuvchi\n\n"
                f"⏳ Iltimos, kuting..."
            )
            
            # Send broadcast
            success_count, error_count = await self._send_broadcast_to_users(
                context.bot, users, message_data
            )
            
            # Show results
            keyboard = [[InlineKeyboardButton("🔙 Admin panel", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"📊 **Broadcast natijalari**\n\n"
                f"✅ Muvaffaqiyatli yuborildi: {success_count}\n"
                f"❌ Xatolik: {error_count}\n"
                f"📈 Jami: {success_count + error_count}\n\n"
                f"📢 {target_description.capitalize()} xabar yuborildi!",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error in broadcast: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Admin panel", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"❌ Xabar yuborishda xatolik yuz berdi!\n\nXatolik: {str(e)[:100]}",
                reply_markup=reply_markup
            )
        finally:
            # Clear user data
            context.user_data.pop('waiting_for_broadcast', None)
            context.user_data.pop('broadcast_type', None)
            context.user_data.pop('broadcast_message', None)
    
    async def _send_broadcast_to_users(self, bot, users, message_data):
        """Send broadcast message to list of users"""
        success_count = 0
        error_count = 0
        
        for user in users:
            try:
                user_id = user['user_id']
                
                if message_data.get('photo'):
                    # Send photo with caption
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=message_data['photo'],
                        caption=message_data.get('text', ''),
                        parse_mode='Markdown'
                    )
                elif message_data.get('video'):
                    # Send video with caption
                    await bot.send_video(
                        chat_id=user_id,
                        video=message_data['video'],
                        caption=message_data.get('text', ''),
                        parse_mode='Markdown'
                    )
                else:
                    # Send text message
                    if message_data.get('text'):
                        await bot.send_message(
                            chat_id=user_id,
                            text=message_data['text'],
                            parse_mode='Markdown'
                        )
                    else:
                        error_count += 1
                        continue
                
                success_count += 1
                
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.05)  # 50ms delay
                
            except Forbidden:
                # User blocked the bot
                error_count += 1
                logger.info(f"User {user_id} blocked the bot")
            except BadRequest as e:
                # Invalid user_id or other bad request
                error_count += 1
                logger.warning(f"Bad request for user {user_id}: {e}")
            except TelegramError as e:
                error_count += 1
                logger.warning(f"Telegram error for user {user_id}: {e}")
            except Exception as e:
                error_count += 1
                logger.error(f"Unexpected error sending to user {user_id}: {e}")
        
        return success_count, error_count
            
    async def _show_detailed_stats(self, query):
        """Show detailed system statistics"""
        try:
            stats = self.database.get_detailed_stats()
            
            stats_text = (
                f"📊 **Batafsil statistika**\n\n"
                f"🤖 **Botlar:**\n"
                f"• Jami: {stats.get('total_bots', 0)}\n"
                f"• Faol: {stats.get('active_bots', 0)}\n"
                f"• Nofaol: {stats.get('inactive_bots', 0)}\n\n"
                f"👥 **Foydalanuvchilar:**\n"
                f"• Jami: {stats.get('total_users', 0)}\n"
                f"• Faol: {stats.get('active_users', 0)}\n"
                f"• Oxirgi hafta qo'shilgan: {stats.get('new_users_week', 0)}\n\n"
                f"📈 **Oxirgi 7 kun:**\n"
                f"• Yangi botlar: {stats.get('bots_created_week', 0)}\n"
                f"• Yangi konkurslar: {stats.get('contests_created_week', 0)}\n"
                f"• Yuborilgan ishlar: {stats.get('submissions_week', 0)}"
            )
            
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing detailed stats: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ Statistikani olishda xatolik yuz berdi!",
                reply_markup=reply_markup
            )
        
    async def _show_main_admin_panel(self, query, context):
        """Show main admin panel interface"""
        config = context.bot_data.get('config')
        
        # Get system statistics
        stats = self.database.get_system_stats()
        
        # Create admin keyboard
        keyboard = [
            [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton("🤖 Barcha botlar", callback_data="admin_all_bots")],
            [InlineKeyboardButton(" Barcha foydalanuvchilarga xabar", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🔄 Botlarni qayta ishga tushirish", callback_data="admin_restart_bots")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        admin_text = (
            "🔧 **Admin Panel**\n\n"
            f"📊 **Tizim statistikasi:**\n"
            f"🤖 Jami botlar: {stats['total_bots']}\n"
            f"✅ Faol botlar: {stats['active_bots']}\n"
            f"👥 Jami foydalanuvchilar: {stats['total_users']}\n\n"
            f"Quyidagi amallardan birini tanlang:"
        )
        
        await query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _show_all_bots(self, query):
        """Show all bots in the system"""
        try:
            logger.info("Getting all bots for admin view...")
            bots = self.database.get_all_bots_admin()
            logger.info(f"Found {len(bots)} bots")
            
            if not bots:
                keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("🚫 Tizimda botlar yo'q!", reply_markup=reply_markup)
                return
        except Exception as e:
            logger.error(f"Error in _show_all_bots: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Botlar ma'lumotini olishda xatolik!", reply_markup=reply_markup)
            return
            
        try:
            logger.info("Formatting bots information...")
            bots_text = "🤖 <b>Barcha botlar:</b>\n\n"
            
            for bot in bots[:20]:  # Show first 20 bots
                status = "✅" if bot['active'] else "❌"
                # Safely handle None values and escape HTML characters
                bot_name = str(bot['name'] or 'Noma\'lum bot').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
                bot_username = str(bot['username'] or 'noma_lum').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
                owner_name = str(bot['owner_name'] or 'Noma\'lum').replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;')
                
                bots_text += (
                    f"{status} <b>{bot_name}</b>\n"
                    f"   @{bot_username}\n"
                    f"   Egasi: {owner_name} (ID: {bot.get('owner_id', 'N/A')})\n"
                    f"   Konkurslar: {bot.get('contests_count', 0)}\n"
                    f"   Yaratilgan: {bot.get('created_at', 'N/A')}\n\n"
                )
                
            if len(bots) > 20:
                bots_text += f"... va yana {len(bots) - 20} ta bot"
                
            logger.info(f"Bots text length: {len(bots_text)}")
            
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            logger.info("Sending bots list message...")
            await query.edit_message_text(bots_text, reply_markup=reply_markup, parse_mode='HTML')
            logger.info("Bots list message sent successfully")
            
        except Exception as e:
            logger.error(f"Error formatting/sending bots list: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ Botlar ro'yxatini ko'rsatishda xatolik yuz berdi!", 
                reply_markup=reply_markup
            )
        
    async def _restart_all_bots(self, query, context):
        """Restart all active bots"""
        try:
            # This would be implemented by the bot factory
            bot_factory = context.bot_data.get('bot_factory')
            if bot_factory:
                active_bots = list(bot_factory.active_bots.keys())
                restarted_count = 0
                
                for bot_id in active_bots:
                    try:
                        await bot_factory.restart_bot(bot_id)
                        restarted_count += 1
                    except Exception as e:
                        logger.error(f"Error restarting bot {bot_id}: {e}")
                        
                keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ {restarted_count}/{len(active_bots)} ta bot qayta ishga tushirildi!",
                    reply_markup=reply_markup
                )
            else:
                keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text("❌ Bot factory topilmadi!", reply_markup=reply_markup)
                
        except Exception as e:
            logger.error(f"Error restarting bots: {e}")
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ Botlarni qayta ishga tushirishda xatolik!", reply_markup=reply_markup)
    
    async def _show_bot_settings(self, query, context):
        """Show bot settings management"""
        # Get all bots for editing
        all_bots = self.database.get_all_bots()
        
        if not all_bots:
            text = "❌ Hozircha botlar mavjud emas!"
            keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)
            return
        
        text = "📝 **Bot sozlamalari**\n\nQaysi botning sozlamalarini o'zgartirmoqchisiz?\n\n"
        
        keyboard = []
        for bot in all_bots:
            status = "🟢" if bot['active'] else "🔴"
            button_text = f"{status} {bot['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"bot_edit_{bot['id']}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
    async def _handle_bot_edit(self, query, context):
        """Handle bot editing options"""
        bot_id = int(query.data.split('_')[2])
        bot_info = self.database.get_bot_by_id(bot_id)
        
        if not bot_info:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        settings = self.database.get_bot_settings(bot_id)
        current_welcome = settings.get('welcome_message', 'Standart xabar')
        welcome_preview = (current_welcome[:50] + "...") if len(current_welcome) > 50 else current_welcome
        
        text = (
            f"📝 **{bot_info['name']} sozlamalari**\n\n"
            f"🆔 Bot ID: {bot_id}\n"
            f"📛 Nomi: {bot_info['name']}\n"
            f"🤖 Username: @{bot_info['username']}\n\n"
            f"📨 **Joriy start xabari:**\n{welcome_preview}\n\n"
            f"Qaysi sozlamani o'zgartirmoqchisiz?"
        )
        
        keyboard = [
            [InlineKeyboardButton("📨 Start xabarini o'zgartirish", callback_data=f"edit_welcome_{bot_id}")],
            [InlineKeyboardButton("📛 Bot nomini o'zgartirish", callback_data=f"edit_name_{bot_id}")],
            [InlineKeyboardButton("📝 Tavsifni o'zgartirish", callback_data=f"edit_description_{bot_id}")],
            [InlineKeyboardButton("📞 Telefon talab qilish", callback_data=f"toggle_phone_{bot_id}")],
            [InlineKeyboardButton("📢 Obuna kanallari", callback_data=f"manage_channels_{bot_id}")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_bot_settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_edit_welcome(self, query, context):
        """Handle welcome message editing"""
        await handle_edit_welcome(query, context, self.database)
        
    async def _handle_edit_name(self, query, context):
        """Handle bot name editing"""
        bot_id = int(query.data.split('_')[2])
        context.user_data['editing_bot_id'] = bot_id
        context.user_data['editing_field'] = 'name'
        context.user_data['waiting_for_input'] = True
        
        keyboard = [[InlineKeyboardButton("❌ Bekor qilish", callback_data=f"bot_edit_{bot_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📛 **Yangi bot nomini kiriting:**\n\n"
            "Bot nomi qisqa va tushunarli bo'lishi kerak.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _handle_edit_description(self, query, context):
        """Handle bot description editing"""
        bot_id = int(query.data.split('_')[2])
        context.user_data['editing_bot_id'] = bot_id
        context.user_data['editing_field'] = 'description'
        context.user_data['waiting_for_input'] = True
        
        keyboard = [[InlineKeyboardButton("❌ Bekor qilish", callback_data=f"bot_edit_{bot_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 **Yangi bot tavsifini kiriting:**\n\n"
            "Tavsif botingiz haqida qisqacha ma'lumot bersin.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    async def handle_welcome_message_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle welcome message input from user"""
        return await handle_welcome_message_input(update, context, self.database)
        
    async def handle_admin_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle various text inputs for admin operations"""
        user_id = update.effective_user.id
        config = context.bot_data.get('config')
        
        # Check admin rights
        if not config.is_admin(user_id):
            return
        
        # Check if waiting for input
        if not context.user_data.get('waiting_for_input'):
            return
            
        editing_field = context.user_data.get('editing_field')
        bot_id = context.user_data.get('editing_bot_id')
        
        if not editing_field or not bot_id:
            return
        
        new_value = update.message.text.strip()
        
        try:
            if editing_field == 'name':
                success = self.database.update_bot_info(bot_id, name=new_value)
                field_name = "nomi"
            elif editing_field == 'description':
                success = self.database.update_bot_info(bot_id, description=new_value)
                field_name = "tavsifi"
            else:
                await update.message.reply_text("❌ Noto'g'ri maydon!")
                return
            
            if success:
                await update.message.reply_text(
                    f"✅ Bot {field_name} muvaffaqiyatli yangilandi!\n\n"
                    f"**Yangi qiymat:** {new_value}",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Yangilashda xatolik yuz berdi!")
                
        except Exception as e:
            logger.error(f"Error updating bot info: {e}")
            await update.message.reply_text("❌ Yangilashda xatolik yuz berdi!")
        finally:
            # Clear user data
            context.user_data.pop('waiting_for_input', None)
            context.user_data.pop('editing_field', None)
            context.user_data.pop('editing_bot_id', None)
    
    async def _handle_toggle_phone(self, query, context):
        """Handle phone requirement toggle"""
        bot_id = int(query.data.split('_')[2])
        bot_settings = self.database.get_bot_settings(bot_id)
        
        current_phone_required = bot_settings.get('phone_required', False)
        new_phone_required = not current_phone_required
        
        # Update bot settings
        self.database.update_bot_settings(bot_id, {'phone_required': new_phone_required})
        
        status = "🟢 Yoqildi" if new_phone_required else "🔴 O'chirildi"
        
        await query.edit_message_text(
            f"📱 **Telefon talab qilish sozlamasi**\n\n"
            f"Status: {status}\n\n"
            f"{'✅ Endi foydalanuvchilar botdan foydalanish uchun telefon raqamlarini tasdiqlaslari kerak.' if new_phone_required else '❌ Telefon raqam talab qilinmaydi.'}"
        )
        
        # Auto return to bot settings after 2 seconds
        await asyncio.sleep(2)
        await self._handle_bot_edit_return(query, context, bot_id)
    
    async def _handle_manage_channels(self, query, context):
        """Handle channel management"""
        bot_id = int(query.data.split('_')[2])
        
        # Get current required channels
        channels = self.database.get_required_channels(bot_id)
        
        text = f"📢 **Obuna kanallari boshqaruvi**\n\n"
        
        if channels:
            text += "**Joriy kanallar:**\n"
            for i, channel in enumerate(channels, 1):
                channel_name = channel.get('channel_name', 'Noma\'lum')
                channel_username = channel.get('channel_username', 'noma\'lum')
                text += f"{i}. {channel_name} (@{channel_username})\n"
            text += "\n"
        else:
            text += "❌ Hozircha obuna kanallari yo'q\n\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Kanal qo'shish", callback_data=f"add_channel_{bot_id}")],
            [InlineKeyboardButton("🗑 Kanallarni o'chirish", callback_data=f"remove_channels_{bot_id}")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data=f"bot_edit_{bot_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_bot_edit_return(self, query, context, bot_id):
        """Return to bot edit menu"""
        bot_info = self.database.get_bot_by_id(bot_id)
        
        if not bot_info:
            await query.edit_message_text("❌ Bot topilmadi!")
            return
            
        settings = self.database.get_bot_settings(bot_id)
        current_welcome = settings.get('welcome_message', 'Standart xabar')
        welcome_preview = (current_welcome[:50] + "...") if len(current_welcome) > 50 else current_welcome
        
        phone_status = "🟢 Yoqilgan" if settings.get('phone_required', False) else "🔴 O'chirilgan"
        subscription_status = "🟢 Yoqilgan" if settings.get('subscription_enabled', False) else "🔴 O'chirilgan"
        
        text = (
            f"📝 **{bot_info['name']} sozlamalari**\n\n"
            f"🆔 Bot ID: {bot_id}\n"
            f"📛 Nomi: {bot_info['name']}\n"
            f"🤖 Username: @{bot_info['username']}\n"
            f"📱 Telefon talab: {phone_status}\n"
            f"📺 Majburiy obuna: {subscription_status}\n\n"
            f"📨 **Joriy start xabari:**\n{welcome_preview}\n\n"
            f"Qaysi sozlamani o'zgartirmoqchisiz?"
        )
        
        keyboard = [
            [InlineKeyboardButton("📨 Start xabarini o'zgartirish", callback_data=f"edit_welcome_{bot_id}")],
            [InlineKeyboardButton("📛 Bot nomini o'zgartirish", callback_data=f"edit_name_{bot_id}")],
            [InlineKeyboardButton("📝 Tavsifni o'zgartirish", callback_data=f"edit_description_{bot_id}")],
            [InlineKeyboardButton("📱 Telefon talab qilish", callback_data=f"toggle_phone_{bot_id}")],
            [InlineKeyboardButton("� Majburiy obuna", callback_data=f"toggle_subscription_{bot_id}")],
            [InlineKeyboardButton("�📢 Obuna kanallari", callback_data=f"manage_channels_{bot_id}")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="admin_bot_settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_toggle_subscription(self, query, context):
        """Handle subscription requirement toggle"""
        bot_id = int(query.data.split('_')[2])
        bot_settings = self.database.get_bot_settings(bot_id)
        
        current_subscription_enabled = bot_settings.get('subscription_enabled', False)
        new_subscription_enabled = not current_subscription_enabled
        
        # Update bot settings
        self.database.update_bot_settings(bot_id, {'subscription_enabled': new_subscription_enabled})
        
        status = "🟢 Yoqildi" if new_subscription_enabled else "🔴 O'chirildi"
        
        enabled_message = "✅ Endi foydalanuvchilar botni ishlatish uchun kanallariga obuna bo'lishi kerak."
        disabled_message = "❌ Majburiy obuna o'chirildi, foydalanuvchilar to'g'ridan-to'g'ri botdan foydalana oladi."
        
        await query.edit_message_text(
            f"📺 **Majburiy obuna sozlamasi**\n\n"
            f"Status: {status}\n\n"
            f"{enabled_message if new_subscription_enabled else disabled_message}"
        )
        
        # Auto return to bot settings after 2 seconds
        await asyncio.sleep(2)
        await self._handle_bot_edit_return(query, context, bot_id)
    
    async def _handle_add_channel(self, query, context):
        """Handle adding new channel"""
        bot_id = int(query.data.split('_')[2])
        
        # Set user state for channel input
        context.user_data['adding_channel_for_bot'] = bot_id
        context.user_data['waiting_for_channel_input'] = True
        
        keyboard = [[InlineKeyboardButton("❌ Bekor qilish", callback_data=f"manage_channels_{bot_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📢 **Yangi kanal qo'shish**\n\n"
            "Kanal ma'lumotlarini quyidagi formatda kiriting:\n\n"
            "**Format:**\n"
            "`Kanal nomi, @kanal_username`\n\n"
            "**Misol:**\n"
            "`IT Yangiliklar, @it_news_uz`\n\n"
            "⚠️ Kanal username @ belgisi bilan boshlanishi kerak",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _handle_remove_channels(self, query, context):
        """Handle removing channels"""
        bot_id = int(query.data.split('_')[2])
        
        # Get current channels
        channels = self.database.get_required_channels(bot_id)
        
        if not channels:
            await query.edit_message_text("❌ O'chirish uchun kanallar yo'q!")
            await asyncio.sleep(2)
            await self._handle_manage_channels(query, context)
            return
        
        text = "🗑 **Kanallarni o'chirish**\n\nQaysi kanalni o'chirmoqchisiz?\n\n"
        keyboard = []
        
        for i, channel in enumerate(channels):
            channel_name = channel.get('channel_name', f'Kanal {i+1}')
            keyboard.append([InlineKeyboardButton(
                f"🗑 {channel_name}", 
                callback_data=f"delete_channel_{bot_id}_{channel['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data=f"manage_channels_{bot_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_delete_channel(self, query, context):
        """Handle deleting a specific channel"""
        parts = query.data.split('_')
        bot_id = int(parts[2])
        channel_id = int(parts[3])
        
        # Delete channel from database
        success = self.database.remove_required_channel(channel_id)
        
        if success:
            await query.answer("✅ Kanal o'chirildi!", show_alert=True)
        else:
            await query.answer("❌ Xatolik yuz berdi!", show_alert=True)
        
        # Return to channel management
        await self._handle_manage_channels(query, context)
    
    async def handle_channel_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle channel input from user"""
        user_id = update.effective_user.id
        config = context.bot_data.get('config')
        
        # Check admin rights
        if not config.is_admin(user_id):
            return False
        
        # Check if waiting for channel input
        if not context.user_data.get('waiting_for_channel_input'):
            return False
        
        bot_id = context.user_data.get('adding_channel_for_bot')
        if not bot_id:
            return False
        
        channel_input = update.message.text.strip()
        
        try:
            # Parse modern channel input format: @username or -ID
            if channel_input.startswith('@'):
                channel_username = channel_input[1:]  # Remove @
                channel_id = channel_input
                channel_name = None  # Will be fetched from API
            elif channel_input.startswith('-100'):
                channel_id = channel_input
                channel_username = channel_input
                channel_name = None  # Will be fetched from API
            else:
                await update.message.reply_text(
                    "✅ **Kanal qo'shish**\n\n"
                    "📌 **Format:** Kanal username (@kanalim) yoki ID (-1001234567890) kiriting.\n\n"
                    "💡 **Masallar:**\n"
                    "• @kanal_majburiy\n" 
                    "• -1001234567890\n\n"
                    "📝 Qaytadan kiriting:"
                )
                return True
            
            # Try to get channel info
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title
                if hasattr(chat, 'username') and chat.username:
                    channel_username = chat.username
            except Exception as e:
                logger.error(f"Error getting channel info: {e}")
                channel_name = f"Kanal ({channel_id})"
            
            # Add channel to database
            success = self.database.add_required_channel(
                bot_id, 
                channel_username, 
                channel_name
            )
            
            if success:
                await update.message.reply_text(
                    f"✅ **Kanal qo'shildi!**\n\n"
                    f"📢 Nomi: {channel_name}\n"
                    f"🔗 Username: {channel_username}\n\n"
                    f"Admin panelga qaytish uchun /admin yozing",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Kanal qo'shishda xatolik!")
            
            # Clear user state
            context.user_data.pop('adding_channel_for_bot', None)
            context.user_data.pop('waiting_for_channel_input', None)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await update.message.reply_text("❌ Xatolik yuz berdi!")
            
            # Clear user state
            context.user_data.pop('adding_channel_for_bot', None)
            context.user_data.pop('waiting_for_channel_input', None)
            
            return True