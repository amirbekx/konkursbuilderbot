"""
Error Handler Module
Centralized error handling and logging
"""
import logging
import traceback
from typing import Optional
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class ErrorHandler:
    """Centralized error handling"""
    
    @staticmethod
    async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Global error handler for telegram bot
        Logs errors and sends user-friendly messages
        """
        # Log the error
        logger.error("Exception while handling an update:", exc_info=context.error)
        
        # Get traceback
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = ''.join(tb_list)
        
        # Log full traceback
        logger.error(f"Traceback:\n{tb_string}")
        
        # Try to send a message to the user
        try:
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Xatolik yuz berdi!\n\n"
                    "Iltimos, qayta urinib ko'ring yoki admin bilan bog'laning."
                )
        except Exception as e:
            logger.error(f"Could not send error message to user: {e}")
    
    @staticmethod
    def log_user_action(user_id: int, action: str, details: Optional[dict] = None):
        """Log user action with structured logging"""
        log_data = {
            'user_id': user_id,
            'action': action,
            'details': details or {}
        }
        logger.info(f"User action: {log_data}")
    
    @staticmethod
    def log_bot_action(bot_id: int, action: str, details: Optional[dict] = None):
        """Log bot action with structured logging"""
        log_data = {
            'bot_id': bot_id,
            'action': action,
            'details': details or {}
        }
        logger.info(f"Bot action: {log_data}")
    
    @staticmethod
    def log_error(error_type: str, error_message: str, context: Optional[dict] = None):
        """Log error with structured logging"""
        log_data = {
            'error_type': error_type,
            'error_message': error_message,
            'context': context or {}
        }
        logger.error(f"Error: {log_data}")


def handle_exceptions(func):
    """
    Decorator for handling exceptions in async functions
    Usage: @handle_exceptions
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            # Try to extract update from args
            update = None
            for arg in args:
                if isinstance(arg, Update):
                    update = arg
                    break
            
            if update and update.effective_message:
                try:
                    await update.effective_message.reply_text(
                        "❌ Xatolik yuz berdi!\n\n"
                        "Iltimos, qayta urinib ko'ring."
                    )
                except:
                    pass
            raise
    return wrapper


def safe_execute(func):
    """
    Decorator for safe execution without raising exceptions
    Returns None on error
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            return None
    return wrapper
