"""
Configuration management for Telegram Bot Builder
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for the bot builder"""
    
    def __init__(self):
        # Main bot token (for the builder bot itself)
        self.MAIN_BOT_TOKEN = os.getenv('MAIN_BOT_TOKEN')
        if not self.MAIN_BOT_TOKEN:
            raise ValueError("MAIN_BOT_TOKEN environment variable is required")
        
        # Database configuration
        self.DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///bot_builder.db')
        
        # Admin user IDs (comma-separated)
        admin_ids = os.getenv('ADMIN_USER_IDS', '')
        self.ADMIN_USER_IDS = [int(id.strip()) for id in admin_ids.split(',') if id.strip().isdigit()]
        
        # Super Admin ID (can delete any bot)
        super_admin = os.getenv('SUPER_ADMIN_ID', '')
        self.SUPER_ADMIN_ID = int(super_admin) if super_admin.strip().isdigit() else None
        
        # Bot creation limits
        self.MAX_BOTS_PER_USER = int(os.getenv('MAX_BOTS_PER_USER', '100'))
        self.MAX_CONTESTS_PER_BOT = int(os.getenv('MAX_CONTESTS_PER_BOT', '10'))
        
        # File upload limits
        self.MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '20'))
        
        # Contest settings
        self.DEFAULT_CONTEST_DURATION_HOURS = int(os.getenv('DEFAULT_CONTEST_DURATION_HOURS', '24'))
        
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.ADMIN_USER_IDS
    
    def is_super_admin(self, user_id: int) -> bool:
        """Check if user is super admin (can delete any bot)"""
        return self.SUPER_ADMIN_ID is not None and user_id == self.SUPER_ADMIN_ID
        
    def validate_bot_token(self, token: str) -> bool:
        """Validate bot token format"""
        import re
        
        if not token or not isinstance(token, str):
            return False
            
        # Remove any whitespace
        token = token.strip()
        
        # Telegram bot token pattern: bot_id:hash
        # bot_id: 8-10 digits, hash: exactly 35 characters (letters, numbers, underscore, dash)
        pattern = r'^\d{8,10}:[A-Za-z0-9_-]{35}$'
        
        if not re.match(pattern, token):
            return False
            
        parts = token.split(':')
        if len(parts) != 2:
            return False
        
        bot_id, hash_part = parts
        
        # Check bot_id is digits and reasonable length
        if not bot_id.isdigit() or len(bot_id) < 8 or len(bot_id) > 10:
            return False
            
        # Check hash part is exactly 35 characters and contains valid characters
        if len(hash_part) != 35:
            return False
            
        # Allow letters, numbers, underscore and dash
        valid_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-')
        if not all(c in valid_chars for c in hash_part):
            return False
            
        return True
        
    def get_database_config(self) -> dict:
        """Get database configuration"""
        return {
            'url': self.DATABASE_URL,
            'echo': os.getenv('DATABASE_ECHO', 'False').lower() == 'true'
        }