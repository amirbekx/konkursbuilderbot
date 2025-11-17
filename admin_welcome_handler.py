"""
Admin welcome message handler - separate module for welcome editing
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def handle_edit_welcome(query, context, database):
    """Handle welcome message editing"""
    bot_id = int(query.data.split('_')[2])
    bot_info = database.get_bot_by_id(bot_id)
    
    if not bot_info:
        await query.edit_message_text("❌ Bot topilmadi!")
        return
        
    # Set editing state
    user_id = query.from_user.id
    if 'editing_states' not in context.bot_data:
        context.bot_data['editing_states'] = {}
    context.bot_data['editing_states'][user_id] = {
        'action': 'edit_welcome',
        'bot_id': bot_id,
        'step': 'waiting_content'
    }
    
    settings = database.get_bot_settings(bot_id)
    current_welcome = settings.get('welcome_message', '')
    current_media = settings.get('welcome_media', '')
    media_type = settings.get('welcome_media_type', '')
    
    media_info = ""
    if current_media:
        media_info = f"\n\n🎬 **Joriy media:** {media_type.upper()}\n{current_media[:50]}..."
    
    text = (
        f"📨 **{bot_info['name']} uchun start xabari**\n\n"
        f"📝 **Joriy xabar:**\n{current_welcome or 'Xabar mavjud emas'}\n"
        f"{media_info}\n\n"
        f"📋 **Yangi start xabarini yuboring:**\n"
        f"• Matn xabari\n"
        f"• Rasm + matn\n"
        f"• Video + matn\n\n"
        f"⚠️ Agar faqat matn yubormoqchi bo'lsangiz, oddiy matn yuboring.\n"
        f"Rasm yoki video bilan yubormoqchi bo'lsangiz, media bilan birga caption (izoh) qo'shing."
    )
    
    keyboard = [[InlineKeyboardButton("❌ Bekor qilish", callback_data=f"bot_edit_{bot_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_welcome_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE, database):
    """Handle welcome message input (text, photo, or video)"""
    user_id = update.effective_user.id
    
    # Check if user is in editing state
    editing_states = context.bot_data.get('editing_states', {})
    if user_id not in editing_states or editing_states[user_id]['action'] != 'edit_welcome':
        return False
    
    state = editing_states[user_id]
    bot_id = state['bot_id']
    
    try:
        welcome_text = ""
        media_file_id = ""
        media_type = ""
        
        # Handle different message types
        if update.message.text:
            # Pure text message
            welcome_text = update.message.text
        elif update.message.photo:
            # Photo with caption
            welcome_text = update.message.caption or ""
            media_file_id = update.message.photo[-1].file_id
            media_type = "photo"
        elif update.message.video:
            # Video with caption
            welcome_text = update.message.caption or ""
            media_file_id = update.message.video.file_id
            media_type = "video"
        else:
            await update.message.reply_text("❌ Faqat matn, rasm yoki video yuborishingiz mumkin!")
            return True
        
        # Save to database
        settings = {
            'welcome_message': welcome_text,
            'welcome_media': media_file_id,
            'welcome_media_type': media_type
        }
        
        database.update_bot_settings(bot_id, settings)
        
        # Clear editing state
        del editing_states[user_id]
        
        # Show success message
        bot_info = database.get_bot_by_id(bot_id)
        success_text = (
            f"✅ **{bot_info['name']} uchun start xabari yangilandi!**\n\n"
            f"📝 **Yangi xabar:**\n{welcome_text}\n\n"
        )
        
        if media_file_id:
            success_text += f"🎬 **Media turi:** {media_type.upper()}\n\n"
            
        success_text += "Yangi start xabari keyingi /start buyrug'idan boshlab qo'llanadi."
        
        keyboard = [[InlineKeyboardButton("🔙 Bot sozlamalari", callback_data=f"bot_edit_{bot_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(success_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error updating welcome message: {e}")
        await update.message.reply_text("❌ Xabarni yangilashda xatolik yuz berdi!")
        
    return True