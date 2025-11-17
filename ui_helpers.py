"""
UI Helper Functions
Reusable functions for creating keyboards and formatting messages
"""
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Tuple, Optional


class KeyboardBuilder:
    """Builder class for creating Telegram keyboards"""
    
    @staticmethod
    def create_main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
        """
        Create main menu keyboard
        
        Args:
            is_admin: Whether user is admin (shows additional options)
            
        Returns:
            ReplyKeyboardMarkup with main menu buttons
        """
        if is_admin:
            keyboard = [
                [KeyboardButton("🤖 Botlarni boshqarish"), KeyboardButton("🏆 Konkurslar")],
                [KeyboardButton("⚙️ Admin panel")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
        else:
            keyboard = [
                [KeyboardButton("🤖 Botlar"), KeyboardButton("🏆 Konkurslar")],
                [KeyboardButton("🇺🇿 Qo'llanma")]
            ]
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    @staticmethod
    def create_cancel_keyboard() -> ReplyKeyboardMarkup:
        """Create keyboard with cancel button only"""
        keyboard = [[KeyboardButton("❌ Bekor qilish")]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    @staticmethod
    def create_back_keyboard() -> ReplyKeyboardMarkup:
        """Create keyboard with back button only"""
        keyboard = [[KeyboardButton("🔙 Orqaga")]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    @staticmethod
    def create_yes_no_keyboard() -> ReplyKeyboardMarkup:
        """Create keyboard with Yes/No buttons"""
        keyboard = [
            [KeyboardButton("✅ Ha"), KeyboardButton("❌ Yo'q")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    @staticmethod
    def create_inline_keyboard(buttons: List[List[Tuple[str, str]]]) -> InlineKeyboardMarkup:
        """
        Create inline keyboard from button data
        
        Args:
            buttons: List of rows, each row is list of (text, callback_data) tuples
            
        Returns:
            InlineKeyboardMarkup
            
        Example:
            buttons = [
                [("Button 1", "callback_1"), ("Button 2", "callback_2")],
                [("Button 3", "callback_3")]
            ]
        """
        keyboard = []
        for row in buttons:
            keyboard.append([
                InlineKeyboardButton(text, callback_data=callback)
                for text, callback in row
            ])
        return InlineKeyboardMarkup(keyboard)


class MessageFormatter:
    """Helper class for formatting messages"""
    
    @staticmethod
    def format_bot_info(bot: dict, include_stats: bool = False) -> str:
        """
        Format bot information message
        
        Args:
            bot: Bot dictionary from database
            include_stats: Whether to include statistics
            
        Returns:
            Formatted message string
        """
        desc = bot.get('description', "Tavsif yo'q")
        created = bot.get('created_at', "Noma'lum")
        text = (
            f"🤖 **{bot['name']}**\n\n"
            f"📝 Tavsif: {desc}\n"
            f"🆔 Bot ID: {bot['id']}\n"
            f"👤 Username: @{bot['username']}\n"
            f"📅 Yaratilgan: {created}\n"
            f"🔘 Holat: {'✅ Faol' if bot.get('is_active') else '❌ Nofaol'}"
        )
        
        if include_stats and 'stats' in bot:
            stats = bot['stats']
            text += (
                f"\n\n📊 **Statistika:**\n"
                f"👥 Foydalanuvchilar: {stats.get('users', 0)}\n"
                f"🏆 Konkurslar: {stats.get('contests', 0)}\n"
                f"📩 Ishtirokchilar: {stats.get('participants', 0)}"
            )
        
        return text
    
    @staticmethod
    def format_error_message(error_type: str, details: Optional[str] = None) -> str:
        """
        Format error message
        
        Args:
            error_type: Type of error (validation, permission, etc)
            details: Additional error details
            
        Returns:
            Formatted error message
        """
        error_messages = {
            'validation': '❌ Noto\'g\'ri ma\'lumot kiritildi!',
            'permission': '❌ Sizda bu amal uchun ruxsat yo\'q!',
            'not_found': '❌ Ma\'lumot topilmadi!',
            'rate_limit': '⏳ Juda ko\'p so\'rov! Iltimos kuting.',
            'server_error': '❌ Server xatosi! Qayta urinib ko\'ring.',
            'unknown': '❌ Noma\'lum xatolik yuz berdi!'
        }
        
        message = error_messages.get(error_type, error_messages['unknown'])
        
        if details:
            message += f"\n\n📝 Tafsilot: {details}"
        
        return message
    
    @staticmethod
    def format_success_message(action: str, details: Optional[str] = None) -> str:
        """
        Format success message
        
        Args:
            action: Action that was successful
            details: Additional details
            
        Returns:
            Formatted success message
        """
        message = f"✅ {action} muvaffaqiyatli bajarildi!"
        
        if details:
            message += f"\n\n{details}"
        
        return message
    
    @staticmethod
    def format_list_items(items: List[dict], item_formatter) -> str:
        """
        Format list of items
        
        Args:
            items: List of item dictionaries
            item_formatter: Function to format each item
            
        Returns:
            Formatted list string
        """
        if not items:
            return "📝 Ro'yxat bo'sh"
        
        formatted_items = []
        for idx, item in enumerate(items, 1):
            formatted_items.append(f"{idx}. {item_formatter(item)}")
        
        return "\n".join(formatted_items)
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
        """
        Truncate text to maximum length
        
        Args:
            text: Text to truncate
            max_length: Maximum length
            suffix: Suffix to add if truncated
            
        Returns:
            Truncated text
        """
        if not text or len(text) <= max_length:
            return text
        
        return text[:max_length - len(suffix)] + suffix
    
    @staticmethod
    def format_phone_number(phone: str) -> str:
        """
        Format phone number for display
        
        Args:
            phone: Raw phone number
            
        Returns:
            Formatted phone number
        """
        # Remove non-digits
        digits = ''.join(c for c in phone if c.isdigit())
        
        if len(digits) >= 12:  # +998901234567
            return f"+{digits[0:3]} {digits[3:5]} {digits[5:8]} {digits[8:10]} {digits[10:]}"
        
        return phone


class ValidationHelper:
    """Helper functions for validation"""
    
    @staticmethod
    def is_valid_telegram_id(user_id: int) -> bool:
        """Check if telegram user ID is valid"""
        return isinstance(user_id, int) and user_id > 0
    
    @staticmethod
    def is_valid_bot_id(bot_id: int) -> bool:
        """Check if bot ID is valid"""
        return isinstance(bot_id, int) and bot_id > 0
    
    @staticmethod
    def normalize_username(username: str) -> str:
        """
        Normalize username (remove @, lowercase)
        
        Args:
            username: Raw username
            
        Returns:
            Normalized username
        """
        if not username:
            return ""
        
        # Remove @
        username = username.strip().lstrip('@')
        
        # Lowercase
        return username.lower()


class PaginationHelper:
    """Helper for paginated lists"""
    
    @staticmethod
    def paginate(items: List, page: int = 1, per_page: int = 10) -> Tuple[List, dict]:
        """
        Paginate a list of items
        
        Args:
            items: List of items to paginate
            page: Current page number (1-indexed)
            per_page: Items per page
            
        Returns:
            Tuple of (paginated_items, pagination_info)
        """
        total = len(items)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        
        # Ensure page is valid
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        paginated_items = items[start_idx:end_idx]
        
        pagination_info = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages
        }
        
        return paginated_items, pagination_info
    
    @staticmethod
    def create_pagination_keyboard(pagination_info: dict, callback_prefix: str) -> InlineKeyboardMarkup:
        """
        Create pagination keyboard
        
        Args:
            pagination_info: Pagination info from paginate()
            callback_prefix: Prefix for callback data
            
        Returns:
            InlineKeyboardMarkup with pagination buttons
        """
        buttons = []
        
        page = pagination_info['page']
        total_pages = pagination_info['total_pages']
        
        # Navigation buttons
        nav_buttons = []
        
        if pagination_info['has_prev']:
            nav_buttons.append(
                InlineKeyboardButton("⬅️ Oldingi", callback_data=f"{callback_prefix}_page_{page - 1}")
            )
        
        # Current page indicator
        nav_buttons.append(
            InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop")
        )
        
        if pagination_info['has_next']:
            nav_buttons.append(
                InlineKeyboardButton("Keyingi ➡️", callback_data=f"{callback_prefix}_page_{page + 1}")
            )
        
        buttons.append(nav_buttons)
        
        return InlineKeyboardMarkup(buttons)
