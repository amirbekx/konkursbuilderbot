"""
Input Validation and Security Utilities
"""
import re
import html
from typing import Optional, Tuple

class InputValidator:
    """Input validation for security and data integrity"""
    
    # Text length limits
    MAX_BOT_NAME_LENGTH = 100
    MAX_MESSAGE_LENGTH = 4096  # Telegram limit
    MAX_DESCRIPTION_LENGTH = 500
    MAX_CAPTION_LENGTH = 1024
    MAX_USERNAME_LENGTH = 32
    
    # File size limits (in bytes)
    MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB
    MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB
    MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20 MB
    
    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize text input by escaping HTML and removing dangerous characters"""
        if not text:
            return ""
        
        # Escape HTML to prevent injection
        text = html.escape(text.strip())
        
        # Remove null bytes and control characters except newlines and tabs
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
        
        return text
    
    @staticmethod
    def validate_bot_name(name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate bot name
        Returns: (is_valid, error_message)
        """
        if not name or not isinstance(name, str):
            return False, "❌ Bot nomi kiritilmagan!"
        
        name = name.strip()
        
        if len(name) < 3:
            return False, "❌ Bot nomi kamida 3 ta belgi bo'lishi kerak!"
        
        if len(name) > InputValidator.MAX_BOT_NAME_LENGTH:
            return False, f"❌ Bot nomi {InputValidator.MAX_BOT_NAME_LENGTH} belgidan oshmasligi kerak!"
        
        # Allow letters (including Cyrillic), numbers, spaces, and basic punctuation
        if not re.match(r'^[a-zA-Z0-9\s\u0400-\u04FF._-]+$', name):
            return False, "❌ Bot nomida faqat harflar, raqamlar va asosiy belgilar bo'lishi mumkin!"
        
        return True, None
    
    @staticmethod
    def validate_message_text(text: str) -> Tuple[bool, Optional[str]]:
        """
        Validate message text
        Returns: (is_valid, error_message)
        """
        if not text or not isinstance(text, str):
            return False, "❌ Matn kiritilmagan!"
        
        text = text.strip()
        
        if len(text) == 0:
            return False, "❌ Matn bo'sh bo'lmasligi kerak!"
        
        if len(text) > InputValidator.MAX_MESSAGE_LENGTH:
            return False, f"❌ Matn {InputValidator.MAX_MESSAGE_LENGTH} belgidan oshmasligi kerak!"
        
        return True, None
    
    @staticmethod
    def validate_description(text: str) -> Tuple[bool, Optional[str]]:
        """
        Validate description text
        Returns: (is_valid, error_message)
        """
        if not text or not isinstance(text, str):
            return False, "❌ Tavsif kiritilmagan!"
        
        text = text.strip()
        
        if len(text) < 5:
            return False, "❌ Tavsif kamida 5 ta belgi bo'lishi kerak!"
        
        if len(text) > InputValidator.MAX_DESCRIPTION_LENGTH:
            return False, f"❌ Tavsif {InputValidator.MAX_DESCRIPTION_LENGTH} belgidan oshmasligi kerak!"
        
        return True, None
    
    @staticmethod
    def validate_username(username: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Telegram username
        Returns: (is_valid, error_message)
        """
        if not username or not isinstance(username, str):
            return False, "❌ Username kiritilmagan!"
        
        # Remove @ if present
        username = username.strip().lstrip('@')
        
        if len(username) < 5:
            return False, "❌ Username kamida 5 ta belgi bo'lishi kerak!"
        
        if len(username) > InputValidator.MAX_USERNAME_LENGTH:
            return False, f"❌ Username {InputValidator.MAX_USERNAME_LENGTH} belgidan oshmasligi kerak!"
        
        # Telegram username rules: a-z, 0-9, underscore
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False, "❌ Username faqat harflar, raqamlar va _ dan iborat bo'lishi kerak!"
        
        return True, None
    
    @staticmethod
    def validate_phone_number(phone: str) -> Tuple[bool, Optional[str]]:
        """
        Validate phone number
        Returns: (is_valid, error_message)
        """
        if not phone or not isinstance(phone, str):
            return False, "❌ Telefon raqami kiritilmagan!"
        
        # Remove spaces, dashes, parentheses
        phone = re.sub(r'[\s\-\(\)]', '', phone)
        
        # Must start with + and contain only digits after that
        if not re.match(r'^\+?\d{10,15}$', phone):
            return False, "❌ Telefon raqami noto'g'ri formatda! Format: +998901234567"
        
        return True, None
    
    @staticmethod
    def validate_file_size(file_size: int, file_type: str = 'photo') -> Tuple[bool, Optional[str]]:
        """
        Validate file size
        Returns: (is_valid, error_message)
        """
        if file_type == 'photo':
            max_size = InputValidator.MAX_PHOTO_SIZE
            max_mb = max_size // (1024 * 1024)
        elif file_type == 'video':
            max_size = InputValidator.MAX_VIDEO_SIZE
            max_mb = max_size // (1024 * 1024)
        else:  # document
            max_size = InputValidator.MAX_DOCUMENT_SIZE
            max_mb = max_size // (1024 * 1024)
        
        if file_size > max_size:
            return False, f"❌ Fayl hajmi {max_mb} MB dan oshmasligi kerak!"
        
        return True, None
    
    @staticmethod
    def validate_integer(value: str, min_val: int = None, max_val: int = None) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Validate integer input
        Returns: (is_valid, error_message, parsed_value)
        """
        try:
            parsed = int(value)
            
            if min_val is not None and parsed < min_val:
                return False, f"❌ Qiymat {min_val} dan kichik bo'lmasligi kerak!", None
            
            if max_val is not None and parsed > max_val:
                return False, f"❌ Qiymat {max_val} dan katta bo'lmasligi kerak!", None
            
            return True, None, parsed
            
        except (ValueError, TypeError):
            return False, "❌ Faqat raqam kiriting!", None
    
    @staticmethod
    def is_safe_url(url: str) -> bool:
        """Check if URL is safe (no javascript:, data:, etc.)"""
        if not url:
            return False
        
        url_lower = url.lower().strip()
        
        # Block dangerous protocols
        dangerous_protocols = ['javascript:', 'data:', 'vbscript:', 'file:']
        if any(url_lower.startswith(proto) for proto in dangerous_protocols):
            return False
        
        # Must be http or https
        if not url_lower.startswith(('http://', 'https://', 't.me/')):
            return False
        
        return True
    
    @staticmethod
    def validate_channel_username(channel: str) -> Tuple[bool, Optional[str]]:
        """
        Validate channel username or link
        Returns: (is_valid, error_message)
        """
        if not channel or not isinstance(channel, str):
            return False, "❌ Kanal username yoki havolasi kiritilmagan!"
        
        channel = channel.strip()
        
        # Remove @ if present
        if channel.startswith('@'):
            channel = channel[1:]
        
        # Handle t.me links
        if 't.me/' in channel:
            channel = channel.split('t.me/')[-1].split('?')[0]
        
        # Validate username format
        if not re.match(r'^[a-zA-Z0-9_]+$', channel):
            return False, "❌ Kanal username noto'g'ri formatda!"
        
        if len(channel) < 5:
            return False, "❌ Kanal username kamida 5 ta belgi bo'lishi kerak!"
        
        return True, None
