"""
Subscription Manager - Handles mandatory subscription (majburiy obuna) functionality
"""
import logging
import sqlite3
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

class SubscriptionManager:
    """Manages mandatory subscription requirements for bots"""
    
    def __init__(self, database):
        self.database = database
        
    async def check_subscription(self, user_id: int, bot_token: str, required_channels: list) -> dict:
        """Check if user is subscribed to required channels"""
        try:
            bot = Bot(token=bot_token)
            subscription_status = {
                'is_subscribed': True,
                'missing_channels': [],
                'subscription_details': []
            }
            
            for channel in required_channels:
                try:
                    # Get chat member info
                    member = await bot.get_chat_member(chat_id=channel['channel_id'], user_id=user_id)
                    
                    # Check if user is member (not left or kicked)
                    is_member = member.status in [
                        ChatMember.CREATOR, ChatMember.ADMINISTRATOR, 
                        ChatMember.MEMBER, ChatMember.RESTRICTED
                    ]
                    
                    subscription_status['subscription_details'].append({
                        'channel_id': channel['channel_id'],
                        'channel_name': channel['name'],
                        'is_subscribed': is_member,
                        'status': member.status
                    })
                    
                    if not is_member:
                        subscription_status['is_subscribed'] = False
                        subscription_status['missing_channels'].append(channel)
                        
                except TelegramError as e:
                    logger.error(f"Error checking subscription for channel {channel['channel_id']}: {e}")
                    # If we can't check, assume not subscribed for safety
                    subscription_status['is_subscribed'] = False
                    subscription_status['missing_channels'].append(channel)
                    
            return subscription_status
            
        except Exception as e:
            logger.error(f"Error in subscription check: {e}")
            return {
                'is_subscribed': False,
                'missing_channels': required_channels,
                'subscription_details': [],
                'error': str(e)
            }
            
    def create_subscription_keyboard(self, channels: list, check_callback: str = "check_subscription") -> InlineKeyboardMarkup:
        """Create inline keyboard for subscription channels"""
        keyboard = []
        
        # Add channel subscription buttons
        for channel in channels:
            if channel.get('invite_link'):
                keyboard.append([
                    InlineKeyboardButton(
                        "➕ Kanalga obuna bo'ling",
                        url=channel['invite_link']
                    )
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton(
                        "➕ Kanalga obuna bo'ling",
                        url=f"https://t.me/{channel['username']}"
                    )
                ])
                
        # Add check subscription button
        keyboard.append([
            InlineKeyboardButton("✅ Bajarildi", callback_data=check_callback)
        ])
        
        return InlineKeyboardMarkup(keyboard)
        
    async def handle_subscription_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                       bot_id: int, required_channels: list):
        """Handle subscription check callback"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get bot token
        bot_info = self.database.get_bot_by_id(bot_id)
        if not bot_info:
            await query.answer("❌ Bot topilmadi!", show_alert=True)
            return False
            
        # Check subscription
        subscription_status = await self.check_subscription(
            user_id, bot_info['token'], required_channels
        )
        
        if subscription_status['is_subscribed']:
            await query.answer("✅ Barcha kanallarga obuna bo'lgansiz!", show_alert=True)
            await query.edit_message_text(
                "✅ Obuna tasdiqlandi!\n\n"
                "Endi botdan to'liq foydalanishingiz mumkin.",
                reply_markup=None
            )
            return True
        else:
            missing_channels_text = "\n".join([
                f"• {ch['name']}" for ch in subscription_status['missing_channels']
            ])
            
            await query.answer("Kanalga a'zo bo'lmagansiz ⚠️", show_alert=True)
            return False
            
    def get_subscription_message(self, bot_id: int, channels: list) -> str:
        """Get subscription requirement message"""
        # Get custom subscription message from database
        custom_message = self.database.get_subscription_message(bot_id)
        
        # Get bot info for default message
        bot_info = self.database.get_bot_by_id(bot_id)
        bot_name = bot_info['name'] if bot_info else "Bot"
        
        # Format channels list
        channels_text = "\n".join([
            f"📢 {channel.get('name', channel.get('channel_name', 'Kanal'))}" 
            for channel in channels
        ])
        
        # Replace {channels} placeholder with actual channels
        if custom_message and "{channels}" in custom_message:
            return custom_message.replace("{channels}", channels_text)
        elif custom_message:
            # If custom message exists but no placeholder, add channels at the end
            return f"{custom_message}\n\n{channels_text}"
        else:
            # Fallback to default message
            return (
                f"🔔 <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:</b>\n\n"
                f"{channels_text}\n\n"
                "1️⃣ Avvalo kanallarga qo'shiling.\n"
                "2️⃣ So'ng \"✅ Bajarildi\" tugmasini bosing."
            )
        
    def add_subscription_requirement(self, bot_id: int, channels: list) -> bool:
        """Add subscription requirement to bot settings"""
        try:
            # Convert channels to JSON string for storage
            import json
            channels_json = json.dumps(channels)
            
            with self.database.get_connection() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO bot_settings 
                       (bot_id, subscription_channels, subscription_enabled) 
                       VALUES (?, ?, ?)""",
                    (bot_id, channels_json, True)
                )
            return True
        except Exception as e:
            logger.error(f"Error adding subscription requirement: {e}")
            return False
            
    def get_bot_subscription_settings(self, bot_id: int) -> dict:
        """Get bot subscription settings"""
        try:
            with self.database.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM bot_settings WHERE bot_id = ?",
                    (bot_id,)
                )
                row = cursor.fetchone()
                
                if row and row['subscription_enabled']:
                    import json
                    channels = json.loads(row['subscription_channels']) if row['subscription_channels'] else []
                    return {
                        'enabled': True,
                        'channels': channels
                    }
                    
            return {'enabled': False, 'channels': []}
            
        except Exception as e:
            logger.error(f"Error getting subscription settings: {e}")
            return {'enabled': False, 'channels': []}
            
    async def middleware_check_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                           bot_id: int) -> bool:
        """Middleware to check subscription before allowing bot usage"""
        user_id = update.effective_user.id
        
        # Get subscription settings
        settings = self.get_bot_subscription_settings(bot_id)
        
        if not settings['enabled'] or not settings['channels']:
            return True  # No subscription required
            
        # Check if user is subscribed
        bot_info = self.database.get_bot_by_id(bot_id)
        subscription_status = await self.check_subscription(
            user_id, bot_info['token'], settings['channels']
        )
        
        if not subscription_status['is_subscribed']:
            # Send subscription requirement message
            bot_name = bot_info['name']
            message = self.get_subscription_message(bot_id, bot_name, settings['channels'])
            keyboard = self.create_subscription_keyboard(
                settings['channels'], 
                f"check_sub_{bot_id}"
            )
            
            if update.message:
                await update.message.reply_text(
                    message, 
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    message,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            
            return False  # Block further processing
            
        return True  # Allow processing