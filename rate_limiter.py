"""
Rate Limiting Module
Prevents spam and abuse by limiting user actions
"""
import time
from typing import Dict, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter to prevent spam and abuse"""
    
    def __init__(self):
        # user_id -> action_type -> list of timestamps
        self.user_actions: Dict[int, Dict[str, list]] = defaultdict(lambda: defaultdict(list))
        
        # Rate limits (action_type -> (max_actions, time_window_seconds))
        self.limits = {
            'message': (20, 60),           # 20 messages per minute
            'button_click': (30, 60),      # 30 button clicks per minute
            # Make bot creation effectively unlimited to avoid 1-hour blocking
            'bot_creation': (9999, 3600),  # ~unlimited creations per hour (practically no block)
            'contest_creation': (5, 3600), # 5 contest creations per hour
            'broadcast': (10, 3600),       # 10 broadcasts per hour
            'file_upload': (10, 60),       # 10 file uploads per minute
            'edit_action': (15, 60),       # 15 edits per minute
            'query': (50, 60),             # 50 database queries per minute
        }
    
    def check_rate_limit(self, user_id: int, action_type: str = 'message') -> tuple[bool, Optional[int]]:
        """
        Check if user has exceeded rate limit
        
        Args:
            user_id: Telegram user ID
            action_type: Type of action being performed
            
        Returns:
            (is_allowed, cooldown_seconds)
            - is_allowed: True if action is allowed, False if rate limited
            - cooldown_seconds: Seconds to wait if rate limited, None if allowed
        """
        current_time = time.time()
        
        # Get or create limit for this action
        if action_type not in self.limits:
            # Default limit for unknown actions
            max_actions, time_window = 10, 60
        else:
            max_actions, time_window = self.limits[action_type]
        
        # Get user's action history for this action type
        action_history = self.user_actions[user_id][action_type]
        
        # Remove old actions outside the time window
        cutoff_time = current_time - time_window
        action_history[:] = [ts for ts in action_history if ts > cutoff_time]
        
        # Check if limit exceeded
        if len(action_history) >= max_actions:
            # Calculate cooldown (time until oldest action expires)
            oldest_action = action_history[0]
            cooldown = int(time_window - (current_time - oldest_action))
            
            logger.warning(
                f"Rate limit exceeded for user {user_id}, action: {action_type}. "
                f"Count: {len(action_history)}/{max_actions}, Cooldown: {cooldown}s"
            )
            
            return False, cooldown
        
        # Record this action
        action_history.append(current_time)
        return True, None
    
    def reset_user(self, user_id: int, action_type: Optional[str] = None):
        """
        Reset rate limit for a user
        
        Args:
            user_id: Telegram user ID
            action_type: Specific action type to reset, or None to reset all
        """
        if action_type:
            if user_id in self.user_actions and action_type in self.user_actions[user_id]:
                self.user_actions[user_id][action_type].clear()
                logger.info(f"Reset rate limit for user {user_id}, action: {action_type}")
        else:
            if user_id in self.user_actions:
                self.user_actions[user_id].clear()
                logger.info(f"Reset all rate limits for user {user_id}")
    
    def get_remaining_actions(self, user_id: int, action_type: str = 'message') -> int:
        """
        Get number of remaining actions for user
        
        Args:
            user_id: Telegram user ID
            action_type: Type of action
            
        Returns:
            Number of remaining actions allowed
        """
        current_time = time.time()
        
        if action_type not in self.limits:
            max_actions, time_window = 10, 60
        else:
            max_actions, time_window = self.limits[action_type]
        
        action_history = self.user_actions[user_id][action_type]
        cutoff_time = current_time - time_window
        action_history[:] = [ts for ts in action_history if ts > cutoff_time]
        
        return max(0, max_actions - len(action_history))
    
    def cleanup_old_data(self, max_age_seconds: int = 7200):
        """
        Clean up old rate limit data to prevent memory bloat
        Should be called periodically (e.g., every hour)
        
        Args:
            max_age_seconds: Remove data older than this (default: 2 hours)
        """
        current_time = time.time()
        cutoff_time = current_time - max_age_seconds
        
        users_to_remove = []
        
        for user_id, actions in list(self.user_actions.items()):
            # Clean up each action type
            for action_type, timestamps in list(actions.items()):
                timestamps[:] = [ts for ts in timestamps if ts > cutoff_time]
                
                # Remove empty action types
                if not timestamps:
                    del actions[action_type]
            
            # Mark user for removal if no actions left
            if not actions:
                users_to_remove.append(user_id)
        
        # Remove users with no recent actions
        for user_id in users_to_remove:
            del self.user_actions[user_id]
        
        if users_to_remove:
            logger.info(f"Cleaned up rate limit data for {len(users_to_remove)} users")
    
    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        return {
            'total_users': len(self.user_actions),
            'total_actions': sum(
                len(timestamps)
                for user_actions in self.user_actions.values()
                for timestamps in user_actions.values()
            ),
            'limits_configured': len(self.limits)
        }


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def check_rate_limit(user_id: int, action_type: str = 'message') -> tuple[bool, Optional[int]]:
    """
    Convenience function to check rate limit
    
    Args:
        user_id: Telegram user ID
        action_type: Type of action being performed
        
    Returns:
        (is_allowed, cooldown_seconds)
    """
    return get_rate_limiter().check_rate_limit(user_id, action_type)
