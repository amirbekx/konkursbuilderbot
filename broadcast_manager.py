"""
Broadcast Manager - Handles mass messaging functionality
"""
import logging
import asyncio
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class BroadcastManager:
    """Manages broadcast messaging to all bot users"""
    
    def __init__(self, database):
        self.database = database
        self.broadcast_states = {}  # Track broadcast creation process
        
    def start_broadcast_creation(self, user_id: int, bot_id: int):
        """Start broadcast message creation process"""
        self.broadcast_states[user_id] = {
            'bot_id': bot_id,
            'step': 'waiting_for_message',
            'message_data': {}
        }
        
    def is_user_creating_broadcast(self, user_id: int) -> bool:
        """Check if user is currently creating a broadcast"""
        return user_id in self.broadcast_states
        
    async def handle_broadcast_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle broadcast creation steps"""
        user_id = update.effective_user.id
        state = self.broadcast_states.get(user_id)
        
        if not state:
            return False
            
        if state['step'] == 'waiting_for_message':
            await self._handle_message_input(update, context, state)
            return True
        elif state['step'] == 'waiting_for_confirmation':
            await self._handle_confirmation(update, context, state)
            return True
            
        return False
        
    async def _handle_message_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
        """Handle broadcast message input"""
        message = update.message
        
        # Store message data
        state['message_data'] = {
            'text': message.text,
            'photo': message.photo[-1].file_id if message.photo else None,
            'video': message.video.file_id if message.video else None,
            'document': message.document.file_id if message.document else None,
            'caption': message.caption,
            'entities': message.entities
        }
        
        # Get recipient count
        recipients_count = self.database.get_bot_users_count(state['bot_id'])
        
        state['step'] = 'waiting_for_confirmation'
        
        await update.message.reply_text(
            f"📢 **Xabaringiz tayyorlandi!**\n\n"
            f"👥 Qabul qiluvchilar: {recipients_count} ta foydalanuvchi\n\n"
            f"❓ Xabarni yuborishni tasdiqlaysizmi?\n\n"
            f"✅ Ha - xabarni yuborish\n"
            f"❌ Yo'q - bekor qilish",
            parse_mode='Markdown'
        )
        
    async def _handle_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
        """Handle broadcast confirmation"""
        user_id = update.effective_user.id
        text = update.message.text.lower()
        
        if text in ['ha', 'yes', '✅', '+']:
            # Start broadcast
            await update.message.reply_text("📤 Xabar yuborilmoqda...")
            
            result = await self._send_broadcast(
                state['bot_id'], 
                state['message_data']
            )
            
            await update.message.reply_text(
                f"✅ **Xabar yuborildi!**\n\n"
                f"📊 **Natijalar:**\n"
                f"✅ Muvaffaqiyatli: {result['success_count']}\n"
                f"❌ Xatolik: {result['error_count']}\n"
                f"👥 Jami: {result['total_count']}",
                parse_mode='Markdown'
            )
            
        else:
            await update.message.reply_text("❌ Xabar yuborish bekor qilindi.")
            
        # Clean up state
        del self.broadcast_states[user_id]
        
    async def _send_broadcast(self, bot_id: int, message_data: dict) -> dict:
        """Send broadcast message to all bot users"""
        try:
            # Get bot info and users
            bot_info = self.database.get_bot_by_id(bot_id)
            users = self.database.get_bot_all_users(bot_id)
            
            bot = Bot(token=bot_info['token'])
            
            success_count = 0
            error_count = 0
            total_count = len(users)
            
            # Send messages with rate limiting
            for i, user in enumerate(users):
                try:
                    # Add delay to avoid rate limits
                    if i > 0 and i % 30 == 0:  # Every 30 messages
                        await asyncio.sleep(1)
                        
                    user_id = user['telegram_id']
                    
                    if message_data['photo']:
                        await bot.send_photo(
                            chat_id=user_id,
                            photo=message_data['photo'],
                            caption=message_data['caption'],
                            caption_entities=message_data['entities']
                        )
                    elif message_data['video']:
                        await bot.send_video(
                            chat_id=user_id,
                            video=message_data['video'],
                            caption=message_data['caption'],
                            caption_entities=message_data['entities']
                        )
                    elif message_data['document']:
                        await bot.send_document(
                            chat_id=user_id,
                            document=message_data['document'],
                            caption=message_data['caption'],
                            caption_entities=message_data['entities']
                        )
                    else:
                        await bot.send_message(
                            chat_id=user_id,
                            text=message_data['text'],
                            entities=message_data['entities']
                        )
                        
                    success_count += 1
                    
                except TelegramError as e:
                    error_count += 1
                    logger.warning(f"Failed to send message to user {user_id}: {e}")
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Unexpected error sending to user {user_id}: {e}")
                    
            # Log broadcast statistics
            self.database.log_broadcast(
                bot_id=bot_id,
                message_type=self._get_message_type(message_data),
                total_sent=success_count,
                total_failed=error_count
            )
            
            return {
                'success_count': success_count,
                'error_count': error_count,
                'total_count': total_count
            }
            
        except Exception as e:
            logger.error(f"Error in broadcast: {e}")
            return {
                'success_count': 0,
                'error_count': total_count if 'total_count' in locals() else 0,
                'total_count': total_count if 'total_count' in locals() else 0
            }
            
    def _get_message_type(self, message_data: dict) -> str:
        """Determine message type for logging"""
        if message_data['photo']:
            return 'photo'
        elif message_data['video']:
            return 'video'
        elif message_data['document']:
            return 'document'
        else:
            return 'text'
            
    async def send_contest_announcement(self, bot_id: int, contest_id: int, announcement_type: str):
        """Send contest-related announcements"""
        try:
            contest = self.database.get_contest_by_id(contest_id)
            bot_info = self.database.get_bot_by_id(bot_id)
            
            if announcement_type == 'new_contest':
                message = (
                    f"🎉 **Yangi konkurs e'lon qilinadi!**\n\n"
                    f"📌 **{contest['title']}**\n"
                    f"📝 {contest['description']}\n\n"
                    f"🎁 **Sovg'a:** {contest['prize']}\n"
                    f"⏰ **Tugash vaqti:** {contest['end_date']}\n\n"
                    f"Ishtirok etish uchun /join buyrug'ini bosing!"
                )
            elif announcement_type == 'contest_ending':
                message = (
                    f"⏰ **Konkurs tugashiga oz qoldi!**\n\n"
                    f"📌 **{contest['title']}**\n"
                    f"🎁 **Sovg'a:** {contest['prize']}\n\n"
                    f"Ishtirok etish uchun shoshiling!\n"
                    f"/join - Konkursga qo'shilish"
                )
            elif announcement_type == 'contest_ended':
                message = (
                    f"🏁 **Konkurs yakunlandi!**\n\n"
                    f"📌 **{contest['title']}**\n"
                    f"🎁 **Sovg'a:** {contest['prize']}\n\n"
                    f"G'oliblar tez orada e'lon qilinadi! 🏆"
                )
            else:
                return {'success': False, 'error': 'Unknown announcement type'}
                
            # Send to all bot users
            users = self.database.get_bot_all_users(bot_id)
            bot = Bot(token=bot_info['token'])
            
            success_count = 0
            error_count = 0
            
            for user in users:
                try:
                    await bot.send_message(
                        chat_id=user['telegram_id'],
                        text=message,
                        parse_mode='Markdown'
                    )
                    success_count += 1
                    
                except TelegramError:
                    error_count += 1
                    
            return {
                'success': True,
                'success_count': success_count,
                'error_count': error_count,
                'total_count': len(users)
            }
            
        except Exception as e:
            logger.error(f"Error sending contest announcement: {e}")
            return {'success': False, 'error': str(e)}