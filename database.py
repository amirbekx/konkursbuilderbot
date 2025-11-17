"""
Database operations for Telegram Bot Builder
"""
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class Database:
    """Database manager for bot builder"""
    
    DB_VERSION = 1  # Database schema version for migrations
    
    def __init__(self, db_path: str = "bot_builder.db"):
        self.db_path = db_path
        self._enable_foreign_keys()
        self.init_database()
    
    def _enable_foreign_keys(self):
        """Enable foreign key constraints for all connections"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging for better concurrency
            conn.commit()
        
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript('''
                -- Users table
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    phone_number TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                -- Bots table
                CREATE TABLE IF NOT EXISTS bots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    username TEXT NOT NULL,
                    description TEXT,
                    telegram_bot_id INTEGER,
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users (telegram_id)
                );
                
                -- Contests table
                CREATE TABLE IF NOT EXISTS contests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    contest_type TEXT DEFAULT 'photo',
                    prize TEXT,
                    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_date TIMESTAMP NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    max_participants INTEGER DEFAULT 1000,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bot_id) REFERENCES bots (id)
                );
                
                -- Contest participants table
                CREATE TABLE IF NOT EXISTS contest_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contest_id) REFERENCES contests (id),
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                    UNIQUE(contest_id, user_id)
                );
                
                -- Submissions table
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    contest_id INTEGER NOT NULL,
                    file_id TEXT,
                    file_type TEXT DEFAULT 'photo',
                    caption TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    votes INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                    FOREIGN KEY (contest_id) REFERENCES contests (id)
                );
                
                -- Bot settings table
                CREATE TABLE IF NOT EXISTS bot_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER UNIQUE NOT NULL,
                    welcome_message TEXT,
                    auto_approve BOOLEAN DEFAULT FALSE,
                    max_submissions_per_user INTEGER DEFAULT 1,
                    subscription_enabled BOOLEAN DEFAULT FALSE,
                    subscription_channels TEXT,
                    broadcast_enabled BOOLEAN DEFAULT TRUE,
                    phone_required BOOLEAN DEFAULT FALSE,
                    phone_request_message TEXT,
                    phone_post_message TEXT,
                    guide_text TEXT,
                    guide_media TEXT,
                    guide_media_type TEXT,
                    referral_enabled BOOLEAN DEFAULT FALSE,
                    referral_message TEXT DEFAULT 'Do''stlaringizni taklif qiling!',
                    settings_json TEXT,
                    referral_share_text TEXT,
                    referral_share_media TEXT,
                    referral_share_media_type TEXT,
                    referral_button_text TEXT,
                    referral_followup_text TEXT,
                    FOREIGN KEY (bot_id) REFERENCES bots (id)
                );
                
                -- Broadcast logs table
                CREATE TABLE IF NOT EXISTS broadcast_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    message_type TEXT,
                    total_sent INTEGER DEFAULT 0,
                    total_failed INTEGER DEFAULT 0,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bot_id) REFERENCES bots (id)
                );
                
                -- Contest winners table
                CREATE TABLE IF NOT EXISTS contest_winners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    submission_id INTEGER,
                    position INTEGER DEFAULT 1,
                    prize_description TEXT,
                    announced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (contest_id) REFERENCES contests (id),
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                    FOREIGN KEY (submission_id) REFERENCES submissions (id),
                    UNIQUE(contest_id, user_id, position)
                );
                
                -- Required channels table
                CREATE TABLE IF NOT EXISTS required_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    name TEXT,
                    username TEXT,
                    url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bot_id) REFERENCES bots (id),
                    UNIQUE(bot_id, channel_id)
                );
                
                -- Referrals table
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    referrer_id INTEGER NOT NULL,
                    referred_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bot_id) REFERENCES bots (id),
                    FOREIGN KEY (referrer_id) REFERENCES users (telegram_id),
                    FOREIGN KEY (referred_id) REFERENCES users (telegram_id),
                    UNIQUE(bot_id, referred_id)
                );

                -- Bot users table (must exist before creating indexes)
                CREATE TABLE IF NOT EXISTS bot_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    first_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bot_id) REFERENCES bots (id),
                    FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                    UNIQUE(bot_id, user_id)
                );
                -- Channels table for mandatory subscriptions
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    channel_name TEXT,
                    channel_username TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bot_id) REFERENCES bots (id),
                    UNIQUE(bot_id, channel_id)
                );
                
                -- Create indexes for better performance
                CREATE INDEX IF NOT EXISTS idx_bots_owner ON bots(owner_id);
                CREATE INDEX IF NOT EXISTS idx_contests_bot ON contests(bot_id);
                CREATE INDEX IF NOT EXISTS idx_participants_contest ON contest_participants(contest_id);
                CREATE INDEX IF NOT EXISTS idx_submissions_contest ON submissions(contest_id);
                CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id);
                
                -- Additional performance indexes
                CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
                CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
                CREATE INDEX IF NOT EXISTS idx_referrals_bot_referrer ON referrals(bot_id, referrer_id);
                CREATE INDEX IF NOT EXISTS idx_referrals_bot_referred ON referrals(bot_id, referred_id);
                CREATE INDEX IF NOT EXISTS idx_bot_users_bot_user ON bot_users(bot_id, user_id);
                CREATE INDEX IF NOT EXISTS idx_required_channels_bot ON required_channels(bot_id);
                CREATE INDEX IF NOT EXISTS idx_bots_active ON bots(active);
                CREATE INDEX IF NOT EXISTS idx_contests_active ON contests(active, bot_id);
                
                -- Migration version tracking table
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                );
            ''')
            
            # Add new columns if they don't exist (migration)
            self._migrate_database()
            
    def _migrate_database(self):
        """Handle database migrations for new features"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create bot_users table for tracking bot interactions
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS bot_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        bot_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        first_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (bot_id) REFERENCES bots (id),
                        FOREIGN KEY (user_id) REFERENCES users (telegram_id),
                        UNIQUE(bot_id, user_id)
                    )
                """)
            except sqlite3.OperationalError:
                pass  # Table already exists
            
            # Add new columns to bot_settings if they don't exist
            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN bot_description TEXT DEFAULT 'Konkurs boti'")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN admin_ids TEXT DEFAULT '[]'")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN auto_contest_enabled BOOLEAN DEFAULT FALSE")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN subscription_message TEXT DEFAULT '📺 **Botdan foydalanish uchun quyidagi kanallarga obuna bo''ling:**\n\n{channels}\n\n1️⃣ Avvalo kanallarga qo''shiling.\n2️⃣ So''ng \"✅ Bajarildi\" tugmasini bosing.'")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            try:
                cursor.execute("ALTER TABLE bots ADD COLUMN restart_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            # Add welcome media support columns
            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN welcome_media TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN welcome_media_type TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            try:
                cursor.execute("ALTER TABLE bots ADD COLUMN last_restart TIMESTAMP")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN phone_request_message TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN phone_post_message TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Manual/guide support columns
            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN guide_text TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN guide_media TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN guide_media_type TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN referral_share_text TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN referral_share_media TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN referral_share_media_type TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN referral_button_text TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

            try:
                cursor.execute("ALTER TABLE bot_settings ADD COLUMN referral_followup_text TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
    def get_or_create_user(self, telegram_id: int, first_name: str = None, 
                          last_name: str = None, username: str = None, 
                          phone_number: str = None) -> int:
        """Get or create user record"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Try to get existing user
            cursor = conn.cursor()
            cursor.execute(
                "SELECT telegram_id FROM users WHERE telegram_id = ?", 
                (telegram_id,)
            )
            
            if cursor.fetchone():
                # Update user info including phone if provided
                conn.execute(
                    """UPDATE users SET 
                       first_name = COALESCE(?, first_name),
                       last_name = COALESCE(?, last_name),
                       username = COALESCE(?, username),
                       phone_number = COALESCE(?, phone_number),
                       last_active = CURRENT_TIMESTAMP 
                       WHERE telegram_id = ?""",
                    (first_name, last_name, username, phone_number, telegram_id)
                )
                return telegram_id
            else:
                # Create new user
                conn.execute(
                    """INSERT INTO users (telegram_id, first_name, last_name, username, phone_number) 
                       VALUES (?, ?, ?, ?, ?)""",
                    (telegram_id, first_name, last_name, username, phone_number)
                )
                return telegram_id
                
    def create_bot(self, user_id: int, token: str, name: str, username: str,
                   description: str = None, telegram_bot_id: int = None) -> int:
        """Create a new bot record with transaction safety"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            
            # Start transaction
            conn.execute("BEGIN TRANSACTION")
            
            cursor.execute(
                """INSERT INTO bots (owner_id, token, name, username, description, telegram_bot_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, token, name, username, description, telegram_bot_id)
            )
            bot_id = cursor.lastrowid
            
            # Create default bot settings
            default_settings = {
                'welcome_message': None,  # Will use default until user sets custom
                'phone_required': False,  # Default off
                'referral_enabled': True,  # Default on
                'subscription_enabled': False,  # Default off - admin must enable
                'auto_approve': False,
                'max_submissions_per_user': 1,
                'broadcast_enabled': True,
                'referral_share_text': None,
                'referral_share_media': None,
                'referral_share_media_type': None,
                'referral_button_text': "Qo'shilish",
                'referral_followup_text': None
            }
            self._create_default_bot_settings_in_transaction(cursor, bot_id, default_settings)
            
            # Commit transaction
            conn.commit()
            logger.info(f"Bot {bot_id} created successfully with settings")
            return bot_id
            
        except Exception as e:
            # Rollback on error
            if conn:
                conn.rollback()
                logger.error(f"Transaction rolled back for bot creation: {e}")
            logger.error(f"Error creating bot: {e}")
            raise
        finally:
            if conn:
                conn.close()
            
    def get_user_bots(self, user_id: int) -> List[Dict]:
        """Get all bots owned by user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT b.*, 
                          COUNT(c.id) as contests_count,
                          COUNT(cp.id) as total_participants
                   FROM bots b
                   LEFT JOIN contests c ON b.id = c.bot_id AND c.active = TRUE
                   LEFT JOIN contest_participants cp ON c.id = cp.contest_id
                   WHERE b.owner_id = ?
                   GROUP BY b.id
                   ORDER BY b.created_at DESC""",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def bot_exists_by_token(self, token: str) -> bool:
        """Check if bot with token already exists"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM bots WHERE token = ?", (token,))
            return cursor.fetchone() is not None
            
    def get_bot_by_id(self, bot_id: int) -> Optional[Dict]:
        """Get bot by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bots WHERE id = ?", (bot_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_bot(self, bot_id: int) -> bool:
        """Delete bot and all related data with transaction safety"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            
            # Start transaction
            conn.execute("BEGIN TRANSACTION")
            
            # Delete in correct order to avoid foreign key conflicts
            # Delete submissions first
            cursor.execute("DELETE FROM submissions WHERE contest_id IN (SELECT id FROM contests WHERE bot_id = ?)", (bot_id,))
            
            # Delete contest participants
            cursor.execute("DELETE FROM contest_participants WHERE contest_id IN (SELECT id FROM contests WHERE bot_id = ?)", (bot_id,))
            
            # Delete contest winners
            cursor.execute("DELETE FROM contest_winners WHERE contest_id IN (SELECT id FROM contests WHERE bot_id = ?)", (bot_id,))
            
            # Delete contests
            cursor.execute("DELETE FROM contests WHERE bot_id = ?", (bot_id,))
            
            # Delete bot settings
            cursor.execute("DELETE FROM bot_settings WHERE bot_id = ?", (bot_id,))
            
            # Delete broadcast logs
            cursor.execute("DELETE FROM broadcast_logs WHERE bot_id = ?", (bot_id,))
            
            # Delete referrals
            cursor.execute("DELETE FROM referrals WHERE bot_id = ?", (bot_id,))
            
            # Delete required channels
            cursor.execute("DELETE FROM required_channels WHERE bot_id = ?", (bot_id,))
            
            # Delete bot_users
            cursor.execute("DELETE FROM bot_users WHERE bot_id = ?", (bot_id,))
            
            # Finally delete the bot itself
            cursor.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
            
            # Commit transaction
            conn.commit()
            logger.info(f"Bot {bot_id} and all related data deleted successfully")
            return True
                
        except Exception as e:
            # Rollback on error
            if conn:
                conn.rollback()
                logger.error(f"Transaction rolled back for bot {bot_id}")
            logger.error(f"Error deleting bot {bot_id}: {e}")
            return False
        finally:
            if conn:
                conn.close()
            
    def create_contest(self, bot_id: int, title: str, description: str,
                      prize: str = None, end_date: datetime = None, 
                      contest_type: str = 'photo', active: bool = True) -> int:
        """Create a new contest"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO contests (bot_id, title, description, contest_type, prize, end_date, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (bot_id, title, description, contest_type, prize, end_date, active)
            )
            return cursor.lastrowid
            
    def get_active_contests(self, bot_id: int) -> List[Dict]:
        """Get active contests for a bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT c.*, COUNT(cp.id) as participants_count
                   FROM contests c
                   LEFT JOIN contest_participants cp ON c.id = cp.contest_id
                   WHERE c.bot_id = ? AND c.active = TRUE AND c.end_date > CURRENT_TIMESTAMP
                   GROUP BY c.id
                   ORDER BY c.created_at DESC""",
                (bot_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def join_contest(self, user_id: int, contest_id: int) -> bool:
        """Add user to contest"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO contest_participants (contest_id, user_id) VALUES (?, ?)",
                    (contest_id, user_id)
                )
                return True
        except sqlite3.IntegrityError:
            return False  # User already joined
            
    def get_active_participation(self, user_id: int, bot_id: int) -> Optional[Dict]:
        """Get user's active contest participation for a bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT cp.*, c.title, c.description
                   FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   WHERE cp.user_id = ? AND c.bot_id = ? AND c.active = TRUE 
                         AND c.end_date > CURRENT_TIMESTAMP
                   ORDER BY cp.joined_at DESC
                   LIMIT 1""",
                (user_id, bot_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
            
    def create_submission(self, user_id: int, contest_id: int, file_id: str,
                         file_type: str = 'photo', caption: str = None) -> int:
        """Create a contest submission"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO submissions (user_id, contest_id, file_id, file_type, caption)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, contest_id, file_id, file_type, caption)
            )
            return cursor.lastrowid
            
    def get_system_stats(self) -> Dict:
        """Get system-wide statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Total bots
            cursor.execute("SELECT COUNT(*) FROM bots")
            stats['total_bots'] = cursor.fetchone()[0]
            
            # Active bots
            cursor.execute("SELECT COUNT(*) FROM bots WHERE active = TRUE")
            stats['active_bots'] = cursor.fetchone()[0]
            
            # Total users
            cursor.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = cursor.fetchone()[0]
            
            # Active contests
            cursor.execute(
                "SELECT COUNT(*) FROM contests WHERE active = TRUE AND end_date > CURRENT_TIMESTAMP"
            )
            stats['active_contests'] = cursor.fetchone()[0]
            
            # Total submissions
            cursor.execute("SELECT COUNT(*) FROM submissions")
            stats['total_submissions'] = cursor.fetchone()[0]
            
            return stats
            
    def get_detailed_stats(self) -> Dict:
        """Get detailed system statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = self.get_system_stats()
            
            # Additional detailed stats
            cursor.execute("SELECT COUNT(*) FROM bots WHERE active = FALSE")
            stats['inactive_bots'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE last_active > datetime('now', '-7 days')"
            )
            stats['active_users'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE created_at > datetime('now', '-7 days')"
            )
            stats['new_users_week'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM contests WHERE active = FALSE"
            )
            stats['completed_contests'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM contest_participants")
            stats['total_participations'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM bots WHERE created_at > datetime('now', '-7 days')"
            )
            stats['bots_created_week'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM contests WHERE created_at > datetime('now', '-7 days')"
            )
            stats['contests_created_week'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM submissions WHERE submitted_at > datetime('now', '-7 days')"
            )
            stats['submissions_week'] = cursor.fetchone()[0]
            
            return stats
    
    def get_all_bots(self) -> List[Dict]:
        """Get all bots"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, name, username, description, active, created_at, owner_id
                   FROM bots 
                   ORDER BY created_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_all_bots_admin(self) -> List[Dict]:
        """Get all bots for admin view"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT b.*, u.first_name || ' ' || COALESCE(u.last_name, '') as owner_name,
                          COUNT(c.id) as contests_count
                   FROM bots b
                   JOIN users u ON b.owner_id = u.telegram_id
                   LEFT JOIN contests c ON b.id = c.bot_id
                   GROUP BY b.id
                   ORDER BY b.created_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_active_bots(self) -> List[Dict]:
        """Get all active bots from database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, token, name, username FROM bots WHERE active = 1"
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_bots_with_owners(self) -> List[Dict]:
        """Get all bots with owner information (for super admin)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT b.id, b.name, b.username, b.description, b.active, 
                          b.created_at, b.owner_id, b.token
                   FROM bots b
                   ORDER BY b.created_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_users_stats(self) -> Dict:
        """Get users statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            cursor.execute("SELECT COUNT(*) FROM users")
            stats['total'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE last_active > datetime('now', '-7 days')"
            )
            stats['active'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(DISTINCT u.telegram_id) FROM users u JOIN bots b ON u.telegram_id = b.owner_id"
            )
            stats['bot_owners'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE created_at > datetime('now', '-1 day')"
            )
            stats['joined_today'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE created_at > datetime('now', '-7 days')"
            )
            stats['joined_week'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM users WHERE created_at > datetime('now', '-30 days')"
            )
            stats['joined_month'] = cursor.fetchone()[0]
            
            return stats
            
    def get_top_users(self, limit: int = 5) -> List[Dict]:
        """Get top users by bot count"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT u.first_name || ' ' || COALESCE(u.last_name, '') as name,
                          u.username, COUNT(b.id) as bots_count
                   FROM users u
                   JOIN bots b ON u.telegram_id = b.owner_id
                   GROUP BY u.telegram_id
                   ORDER BY bots_count DESC
                   LIMIT ?""",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_all_contests_admin(self) -> List[Dict]:
        """Get all contests for admin view"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT c.*, b.username as bot_username,
                          COUNT(cp.id) as participants,
                          CASE WHEN c.end_date > CURRENT_TIMESTAMP AND c.active = TRUE 
                               THEN 1 ELSE 0 END as active
                   FROM contests c
                   JOIN bots b ON c.bot_id = b.id
                   LEFT JOIN contest_participants cp ON c.id = cp.contest_id
                   GROUP BY c.id
                   ORDER BY c.created_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_contest_by_id(self, contest_id: int) -> Optional[Dict]:
        """Get contest by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM contests WHERE id = ?", (contest_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
            
    def get_contest_participants_detailed(self, contest_id: int) -> List[Dict]:
        """Get detailed participants info for Excel export"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT 
                    u.telegram_id as user_id,
                    u.first_name || ' ' || COALESCE(u.last_name, '') as full_name,
                    u.username,
                    u.phone_number,
                    cp.joined_at,
                    COUNT(s.id) as submissions_count,
                    (SELECT caption FROM submissions WHERE user_id = u.telegram_id AND contest_id = ? 
                     ORDER BY submitted_at DESC LIMIT 1) as latest_caption
                   FROM contest_participants cp
                   JOIN users u ON cp.user_id = u.telegram_id
                   LEFT JOIN submissions s ON s.user_id = u.telegram_id AND s.contest_id = ?
                   WHERE cp.contest_id = ?
                   GROUP BY u.telegram_id
                   ORDER BY cp.joined_at""",
                (contest_id, contest_id, contest_id)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_user_bots_detailed(self, user_id: int) -> List[Dict]:
        """Get detailed bots info for user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT b.*,
                          COUNT(DISTINCT c.id) as contests_count,
                          COUNT(DISTINCT cp.id) as total_participants,
                          COUNT(DISTINCT s.id) as total_submissions
                   FROM bots b
                   LEFT JOIN contests c ON b.id = c.bot_id
                   LEFT JOIN contest_participants cp ON c.id = cp.contest_id
                   LEFT JOIN submissions s ON c.id = s.contest_id
                   WHERE b.owner_id = ?
                   GROUP BY b.id
                   ORDER BY b.created_at DESC""",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_contest_submissions_detailed(self, contest_id: int) -> List[Dict]:
        """Get detailed submissions info for contest"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT s.*,
                          u.first_name || ' ' || COALESCE(u.last_name, '') as participant_name,
                          u.username
                   FROM submissions s
                   JOIN users u ON s.user_id = u.telegram_id
                   WHERE s.contest_id = ?
                   ORDER BY s.submitted_at""",
                (contest_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_bot_users_count(self, bot_id: int) -> int:
        """Get count of users who interacted with specific bot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(DISTINCT cp.user_id) 
                   FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   WHERE c.bot_id = ?""",
                (bot_id,)
            )
            result = cursor.fetchone()
            return result[0] if result else 0
            
    def get_bot_all_users(self, bot_id: int) -> List[Dict]:
        """Get all users who interacted with specific bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT DISTINCT u.*
                   FROM users u
                   JOIN bot_users bu ON u.telegram_id = bu.user_id
                   WHERE bu.bot_id = ?
                   ORDER BY bu.last_interaction DESC""",
                (bot_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def add_bot_user(self, bot_id: int, user_id: int):
        """Add or update bot user interaction"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO bot_users 
                   (bot_id, user_id, first_interaction, last_interaction)
                   VALUES (?, ?, 
                   COALESCE((SELECT first_interaction FROM bot_users WHERE bot_id = ? AND user_id = ?), CURRENT_TIMESTAMP),
                   CURRENT_TIMESTAMP)""",
                (bot_id, user_id, bot_id, user_id)
            )
            
    def log_broadcast(self, bot_id: int, message_type: str, total_sent: int, total_failed: int):
        """Log broadcast statistics"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO broadcast_logs (bot_id, message_type, total_sent, total_failed)
                   VALUES (?, ?, ?, ?)""",
                (bot_id, message_type, total_sent, total_failed)
            )
            
    def get_broadcast_stats(self, bot_id: int) -> List[Dict]:
        """Get broadcast statistics for a bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM broadcast_logs 
                   WHERE bot_id = ? 
                   ORDER BY sent_at DESC 
                   LIMIT 10""",
                (bot_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def select_contest_winners(self, contest_id: int, winners_data: List[Dict]) -> bool:
        """Select and save contest winners"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Clear existing winners for this contest
                conn.execute("DELETE FROM contest_winners WHERE contest_id = ?", (contest_id,))
                
                # Insert new winners
                for winner in winners_data:
                    conn.execute(
                        """INSERT INTO contest_winners 
                           (contest_id, user_id, submission_id, position, prize_description)
                           VALUES (?, ?, ?, ?, ?)""",
                        (contest_id, winner['user_id'], winner.get('submission_id'), 
                         winner['position'], winner.get('prize_description', ''))
                    )
                return True
        except Exception as e:
            logger.error(f"Error selecting winners: {e}")
            return False
            
    def get_contest_winners(self, contest_id: int) -> List[Dict]:
        """Get contest winners"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT cw.*, 
                          u.first_name || ' ' || COALESCE(u.last_name, '') as winner_name,
                          u.username,
                          s.file_id, s.caption
                   FROM contest_winners cw
                   JOIN users u ON cw.user_id = u.telegram_id
                   LEFT JOIN submissions s ON cw.submission_id = s.id
                   WHERE cw.contest_id = ?
                   ORDER BY cw.position""",
                (contest_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_contest_submissions_for_voting(self, contest_id: int) -> List[Dict]:
        """Get contest submissions for winner selection"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT s.*, 
                          u.first_name || ' ' || COALESCE(u.last_name, '') as participant_name,
                          u.username
                   FROM submissions s
                   JOIN users u ON s.user_id = u.telegram_id
                   WHERE s.contest_id = ?
                   ORDER BY s.votes DESC, s.submitted_at""",
                (contest_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def add_vote_to_submission(self, submission_id: int) -> bool:
        """Add vote to submission"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE submissions SET votes = votes + 1 WHERE id = ?",
                    (submission_id,)
                )
                return True
        except Exception as e:
            logger.error(f"Error adding vote: {e}")
            return False
            
    def end_contest(self, contest_id: int) -> bool:
        """End contest and mark as inactive"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE contests SET active = FALSE WHERE id = ?",
                    (contest_id,)
                )
                return True
        except Exception as e:
            logger.error(f"Error ending contest: {e}")
            return False
            
    def get_user_overall_stats(self, user_id: int) -> Dict:
        """Get overall statistics for user's bots"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Total bots
            cursor.execute("SELECT COUNT(*) FROM bots WHERE owner_id = ?", (user_id,))
            stats['total_bots'] = cursor.fetchone()[0]
            
            # Active bots
            cursor.execute("SELECT COUNT(*) FROM bots WHERE owner_id = ? AND active = TRUE", (user_id,))
            stats['active_bots'] = cursor.fetchone()[0]
            
            # Total contests
            cursor.execute(
                """SELECT COUNT(*) FROM contests c 
                   JOIN bots b ON c.bot_id = b.id 
                   WHERE b.owner_id = ?""", (user_id,)
            )
            stats['total_contests'] = cursor.fetchone()[0]
            
            # Total participants
            cursor.execute(
                """SELECT COUNT(DISTINCT cp.user_id) FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   JOIN bots b ON c.bot_id = b.id
                   WHERE b.owner_id = ?""", (user_id,)
            )
            stats['total_participants'] = cursor.fetchone()[0]
            
            # Total submissions
            cursor.execute(
                """SELECT COUNT(*) FROM submissions s
                   JOIN contests c ON s.contest_id = c.id
                   JOIN bots b ON c.bot_id = b.id
                   WHERE b.owner_id = ?""", (user_id,)
            )
            stats['total_submissions'] = cursor.fetchone()[0]
            
            # New contests this week
            cursor.execute(
                """SELECT COUNT(*) FROM contests c
                   JOIN bots b ON c.bot_id = b.id
                   WHERE b.owner_id = ? AND c.created_at > datetime('now', '-7 days')""", (user_id,)
            )
            stats['new_contests_week'] = cursor.fetchone()[0]
            
            # New participants this week
            cursor.execute(
                """SELECT COUNT(*) FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   JOIN bots b ON c.bot_id = b.id
                   WHERE b.owner_id = ? AND cp.joined_at > datetime('now', '-7 days')""", (user_id,)
            )
            stats['new_participants_week'] = cursor.fetchone()[0]
            
            # Most active bot
            cursor.execute(
                """SELECT b.name, COUNT(cp.id) as participants
                   FROM bots b
                   LEFT JOIN contests c ON b.id = c.bot_id
                   LEFT JOIN contest_participants cp ON c.id = cp.contest_id
                   WHERE b.owner_id = ?
                   GROUP BY b.id
                   ORDER BY participants DESC
                   LIMIT 1""", (user_id,)
            )
            result = cursor.fetchone()
            stats['most_active_bot'] = result[0] if result else "Yo'q"
            
            return stats
            
    def user_has_phone(self, user_id: int) -> bool:
        """Check if user has phone number saved"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT phone_number FROM users WHERE telegram_id = ? AND phone_number IS NOT NULL",
                (user_id,)
            )
            return cursor.fetchone() is not None
            
    def save_user_phone(self, user_id: int, phone_number: str) -> bool:
        """Save user phone number"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE users SET phone_number = ? WHERE telegram_id = ?",
                    (phone_number, user_id)
                )
                return True
        except Exception as e:
            logger.error(f"Error saving phone number: {e}")
            return False
            
    def get_bot_phone_requirement(self, bot_id: int) -> bool:
        """Check if bot requires phone number"""
        settings = self.get_bot_settings(bot_id)
        return bool(settings.get('phone_required', False))
            
    def set_bot_phone_requirement(self, bot_id: int, required: bool) -> bool:
        """Set phone requirement for bot"""
        return self.update_bot_settings(bot_id, {'phone_required': required})
            
    def get_bot_referral_settings(self, bot_id: int) -> dict:
        """Get bot referral settings"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT referral_enabled, referral_message FROM bot_settings WHERE bot_id = ?",
                (bot_id,)
            )
            result = cursor.fetchone()
            
            if result:
                return {
                    'enabled': bool(result['referral_enabled']),
                    'message': result['referral_message'] or "Do'stlaringizni taklif qiling!"
                }
            else:
                return {'enabled': False, 'message': "Do'stlaringizni taklif qiling!"}
                
    def set_bot_referral_settings(self, bot_id: int, enabled: bool, message: str = None) -> bool:
        """Set bot referral settings"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if message:
                    conn.execute(
                        """INSERT OR REPLACE INTO bot_settings 
                           (bot_id, referral_enabled, referral_message) VALUES (?, ?, ?)
                           ON CONFLICT(bot_id) DO UPDATE SET 
                           referral_enabled = ?, referral_message = ?""",
                        (bot_id, enabled, message, enabled, message)
                    )
                else:
                    conn.execute(
                        """INSERT OR REPLACE INTO bot_settings 
                           (bot_id, referral_enabled) VALUES (?, ?)
                           ON CONFLICT(bot_id) DO UPDATE SET referral_enabled = ?""",
                        (bot_id, enabled, enabled)
                    )
                return True
        except Exception as e:
            logger.error(f"Error setting referral settings: {e}")
            return False
            
    def add_referral(self, bot_id: int, referrer_id: int, referred_id: int) -> bool:
        """Add referral relationship"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO referrals (bot_id, referrer_id, referred_id) VALUES (?, ?, ?)",
                    (bot_id, referrer_id, referred_id)
                )
                return True
        except Exception as e:
            logger.error(f"Error adding referral: {e}")
            return False
            
    def get_user_referral_count(self, bot_id: int, user_id: int) -> int:
        """Get count of users referred by specific user for specific bot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM referrals WHERE bot_id = ? AND referrer_id = ?",
                (bot_id, user_id)
            )
            return cursor.fetchone()[0]
            
    def get_bot_total_referrals(self, bot_id: int) -> int:
        """Get total referrals for a bot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM referrals WHERE bot_id = ?",
                (bot_id,)
            )
            return cursor.fetchone()[0]
            
    def get_user_referred_by(self, bot_id: int, user_id: int) -> Optional[int]:
        """Check who referred this user"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT referrer_id FROM referrals WHERE bot_id = ? AND referred_id = ?",
                (bot_id, user_id)
            )
            result = cursor.fetchone()
            return result[0] if result else None
            
    def get_referral_statistics(self, bot_id: int) -> List[Dict]:
        """Get referral statistics for a bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.referrer_id,
                          u.first_name || ' ' || COALESCE(u.last_name, '') as referrer_name,
                          u.username,
                          COUNT(r.referred_id) as referral_count,
                          MIN(r.created_at) as first_referral,
                          MAX(r.created_at) as last_referral
                   FROM referrals r
                   JOIN users u ON r.referrer_id = u.telegram_id
                   WHERE r.bot_id = ?
                   GROUP BY r.referrer_id
                   ORDER BY referral_count DESC""",
                (bot_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
            
    def get_all_referrals_admin(self) -> List[Dict]:
        """Get all referrals across all bots for admin"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """SELECT r.*,
                          b.name as bot_name,
                          b.username as bot_username,
                          u1.first_name || ' ' || COALESCE(u1.last_name, '') as referrer_name,
                          u2.first_name || ' ' || COALESCE(u2.last_name, '') as referred_name
                   FROM referrals r
                   JOIN bots b ON r.bot_id = b.id
                   JOIN users u1 ON r.referrer_id = u1.telegram_id
                   JOIN users u2 ON r.referred_id = u2.telegram_id
                   ORDER BY r.created_at DESC
                   LIMIT 100"""
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_total_referrals(self) -> int:
        """Get total number of referrals across all bots"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM referrals")
            return cursor.fetchone()[0]
    
    def get_top_referrers(self, limit: int = 10) -> List[tuple]:
        """Get top referrers across all bots"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT u.first_name || ' ' || COALESCE(u.last_name, '') as name,
                          COUNT(r.id) as referral_count
                   FROM referrals r
                   JOIN users u ON r.referrer_id = u.telegram_id
                   GROUP BY r.referrer_id
                   ORDER BY referral_count DESC
                   LIMIT ?""",
                (limit,)
            )
            return cursor.fetchall()
    
    def get_referrals_by_bot(self) -> List[tuple]:
        """Get referral count by bot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT b.name,
                          COUNT(r.id) as referral_count
                   FROM bots b
                   LEFT JOIN referrals r ON b.id = r.bot_id
                   GROUP BY b.id
                   HAVING referral_count > 0
                   ORDER BY referral_count DESC"""
            )
            return cursor.fetchall()
            
    def get_bot_contests(self, bot_id: int) -> List[Dict]:
        """Get contests for specific bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM contests WHERE bot_id = ? ORDER BY created_at DESC",
                (bot_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_contest_participants_count(self, contest_id: int) -> int:
        """Get number of participants in contest"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM contest_participants WHERE contest_id = ?",
                (contest_id,)
            )
            return cursor.fetchone()[0]
    
    def get_bot_settings(self, bot_id: int) -> Dict:
        """Get bot settings"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM bot_settings WHERE bot_id = ?",
                (bot_id,)
            )
            result = cursor.fetchone()
            if result:
                return dict(result)
            else:
                # Create default settings if not exist
                default_settings = {
                    'welcome_message': None,
                    'phone_required': False,
                    'referral_enabled': True,
                    'subscription_enabled': False,
                    'auto_approve': False,
                    'max_submissions_per_user': 1,
                    'broadcast_enabled': True,
                    'phone_request_message': None,
                    'phone_post_message': None,
                    'guide_text': None,
                    'guide_media': None,
                    'guide_media_type': None,
                    'referral_share_text': None,
                    'referral_share_media': None,
                    'referral_share_media_type': None,
                    'referral_button_text': "Qo'shilish",
                    'referral_followup_text': None
                }
                self._create_default_bot_settings(bot_id, default_settings)
                return default_settings
    
    def _create_default_bot_settings_in_transaction(self, cursor, bot_id: int, settings: Dict):
        """Create default bot settings within an existing transaction"""
        cursor.execute(
            """INSERT INTO bot_settings 
                   (bot_id, welcome_message, phone_required, referral_enabled, subscription_enabled,
                    auto_approve, max_submissions_per_user, broadcast_enabled,
                    phone_request_message, phone_post_message,
                    guide_text, guide_media, guide_media_type,
           referral_share_text, referral_share_media,
           referral_share_media_type, referral_button_text, referral_followup_text)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bot_id,
                settings.get('welcome_message', None),
                settings.get('phone_required', False),  # Default False
                settings.get('referral_enabled', True),
                settings.get('subscription_enabled', False),  # Default False
                settings.get('auto_approve', False),
                settings.get('max_submissions_per_user', 1),
                settings.get('broadcast_enabled', True),
                settings.get('phone_request_message', None),
                settings.get('phone_post_message', None),
                settings.get('guide_text', None),
                settings.get('guide_media', None),
                settings.get('guide_media_type', None),
                settings.get('referral_share_text', None),
                settings.get('referral_share_media', None),
                settings.get('referral_share_media_type', None),
                settings.get('referral_button_text', None),
                settings.get('referral_followup_text', None),
            )
        )
    
    def _create_default_bot_settings(self, bot_id: int, settings: Dict):
        """Create default bot settings (legacy method, prefer using _create_default_bot_settings_in_transaction)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO bot_settings 
                       (bot_id, welcome_message, phone_required, referral_enabled, subscription_enabled,
                        auto_approve, max_submissions_per_user, broadcast_enabled,
                        phone_request_message, phone_post_message,
                        guide_text, guide_media, guide_media_type,
               referral_share_text, referral_share_media,
               referral_share_media_type, referral_button_text, referral_followup_text)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bot_id,
                    settings.get('welcome_message', None),
                    settings.get('phone_required', False),  # Default False
                    settings.get('referral_enabled', True),
                    settings.get('subscription_enabled', False),  # Default False
                    settings.get('auto_approve', False),
                    settings.get('max_submissions_per_user', 1),
                    settings.get('broadcast_enabled', True),
                    settings.get('phone_request_message', None),
                    settings.get('phone_post_message', None),
                    settings.get('guide_text', None),
                    settings.get('guide_media', None),
                    settings.get('guide_media_type', None),
                    settings.get('referral_share_text', None),
                    settings.get('referral_share_media', None),
                    settings.get('referral_share_media_type', None),
                    settings.get('referral_button_text', None),
                    settings.get('referral_followup_text', None),
                )
            )
    
    def update_bot_settings(self, bot_id: int, updates: Dict):
        """Update bot settings"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get current settings
                current = self.get_bot_settings(bot_id)
                if not current:
                    # Ensure settings row exists before updating
                    self._create_default_bot_settings(bot_id, updates)
                    current = self.get_bot_settings(bot_id)
                    if not current:
                        return False
                
                # Prepare update fields
                fields = []
                values = []
                
                for key, value in updates.items():
                    if key == 'welcome_message':
                        fields.append('welcome_message = ?')
                        values.append(value)
                    elif key == 'welcome_media':
                        fields.append('welcome_media = ?')
                        values.append(value)
                    elif key == 'welcome_media_type':
                        fields.append('welcome_media_type = ?')
                        values.append(value)
                    elif key == 'require_phone':
                        fields.append('phone_required = ?')
                        values.append(value)
                    elif key == 'phone_required':
                        fields.append('phone_required = ?')
                        values.append(value)
                    elif key == 'referral_enabled':
                        fields.append('referral_enabled = ?')
                        values.append(value)
                    elif key == 'subscription_enabled':
                        fields.append('subscription_enabled = ?')
                        values.append(value)
                    elif key == 'phone_request_message':
                        fields.append('phone_request_message = ?')
                        values.append(value)
                    elif key == 'phone_post_message':
                        fields.append('phone_post_message = ?')
                        values.append(value)
                    elif key == 'guide_text':
                        fields.append('guide_text = ?')
                        values.append(value)
                    elif key == 'guide_media':
                        fields.append('guide_media = ?')
                        values.append(value)
                    elif key == 'guide_media_type':
                        fields.append('guide_media_type = ?')
                        values.append(value)
                    elif key == 'referral_share_text':
                        fields.append('referral_share_text = ?')
                        values.append(value)
                    elif key == 'referral_share_media':
                        fields.append('referral_share_media = ?')
                        values.append(value)
                    elif key == 'referral_share_media_type':
                        fields.append('referral_share_media_type = ?')
                        values.append(value)
                    elif key == 'referral_button_text':
                        fields.append('referral_button_text = ?')
                        values.append(value)
                    elif key == 'referral_followup_text':
                        fields.append('referral_followup_text = ?')
                        values.append(value)
                        
                if fields:
                    values.append(bot_id)
                    placeholders = ', '.join(fields)
                    query = f"UPDATE bot_settings SET {placeholders} WHERE bot_id = ?"
                    cursor.execute(query, values)
                    logger.info(f"Updated bot {bot_id} settings")
                    return True
                return False
                    
        except Exception as e:
            logger.error(f"Error updating bot settings: {e}")
            return False
    
    def get_required_channels(self, bot_id: int) -> List[Dict]:
        """Get required subscription channels for bot"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM required_channels WHERE bot_id = ?",
                (bot_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def add_required_channel(self, bot_id: int, channel_username: str, channel_name: str) -> bool:
        """Add required subscription channel for bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Remove @ from username if present
                channel_id = channel_username.replace('@', '')
                
                cursor.execute(
                    """INSERT INTO required_channels 
                       (bot_id, channel_id, name, username, url) 
                       VALUES (?, ?, ?, ?, ?)""",
                    (bot_id, channel_id, channel_name, channel_username, f"https://t.me/{channel_id}")
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding required channel: {e}")
            return False
    
    def remove_required_channel(self, channel_id: int) -> bool:
        """Remove required subscription channel"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM required_channels WHERE id = ?", (channel_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error removing required channel: {e}")
            return False
    
    def get_bot_referral_stats(self, bot_id: int) -> Dict:
        """Get referral statistics for specific bot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total referrals
            cursor.execute(
                "SELECT COUNT(*) FROM referrals WHERE bot_id = ?",
                (bot_id,)
            )
            total_referrals = cursor.fetchone()[0]
            
            # Top referrer
            cursor.execute(
                """SELECT u.first_name || ' ' || COALESCE(u.last_name, '') as name
                   FROM referrals r
                   JOIN users u ON r.referrer_id = u.telegram_id
                   WHERE r.bot_id = ?
                   GROUP BY r.referrer_id
                   ORDER BY COUNT(*) DESC
                   LIMIT 1""",
                (bot_id,)
            )
            top_referrer_result = cursor.fetchone()
            top_referrer = top_referrer_result[0] if top_referrer_result else "Mavjud emas"
            
            return {
                'total_referrals': total_referrals,
                'top_referrer': top_referrer
            }
    
    def get_bot_participants_count(self, bot_id: int) -> int:
        """Get total participants count for bot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(DISTINCT cp.user_id)
                   FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   WHERE c.bot_id = ?""",
                (bot_id,)
            )
            return cursor.fetchone()[0]
    
    def get_bot_detailed_stats(self, bot_id: int) -> Dict:
        """Get detailed statistics for specific bot"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # Total users
            cursor.execute(
                """SELECT COUNT(DISTINCT cp.user_id)
                   FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   WHERE c.bot_id = ?""",
                (bot_id,)
            )
            stats['total_users'] = cursor.fetchone()[0]
            
            # Active users (participated in last 7 days)
            cursor.execute(
                """SELECT COUNT(DISTINCT cp.user_id)
                   FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   WHERE c.bot_id = ? AND cp.joined_at > datetime('now', '-7 days')""",
                (bot_id,)
            )
            stats['active_users'] = cursor.fetchone()[0]
            
            # New users this week
            cursor.execute(
                """SELECT COUNT(DISTINCT cp.user_id)
                   FROM contest_participants cp
                   JOIN contests c ON cp.contest_id = c.id
                   WHERE c.bot_id = ? AND cp.joined_at > datetime('now', '-7 days')""",
                (bot_id,)
            )
            stats['new_users_week'] = cursor.fetchone()[0]
            
            # Contest statistics
            cursor.execute(
                "SELECT COUNT(*) FROM contests WHERE bot_id = ?",
                (bot_id,)
            )
            stats['total_contests'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM contests WHERE bot_id = ? AND active = 1",
                (bot_id,)
            )
            stats['active_contests'] = cursor.fetchone()[0]
            
            cursor.execute(
                "SELECT COUNT(*) FROM contests WHERE bot_id = ? AND active = 0",
                (bot_id,)
            )
            stats['completed_contests'] = cursor.fetchone()[0]
            
            # Submission statistics
            cursor.execute(
                """SELECT COUNT(*) FROM submissions s
                   JOIN contests c ON s.contest_id = c.id
                   WHERE c.bot_id = ?""",
                (bot_id,)
            )
            stats['total_submissions'] = cursor.fetchone()[0]
            
            # Winners
            cursor.execute(
                """SELECT COUNT(*) FROM winners w
                   JOIN contests c ON w.contest_id = c.id
                   WHERE c.bot_id = ?""",
                (bot_id,)
            )
            stats['total_winners'] = cursor.fetchone()[0]
            
            # Average participation
            if stats['total_contests'] > 0:
                stats['avg_participation'] = round(stats['total_submissions'] / stats['total_contests'], 1)
            else:
                stats['avg_participation'] = 0
            
            # Referral stats
            referral_stats = self.get_bot_referral_stats(bot_id)
            stats.update(referral_stats)
            
            return stats
    
    def update_bot_info(self, bot_id: int, name: str = None, description: str = None) -> bool:
        """Update bot information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                fields = []
                values = []
                
                if name:
                    fields.append('name = ?')
                    values.append(name)
                if description:
                    fields.append('description = ?')
                    values.append(description)
                    
                if fields:
                    values.append(bot_id)
                    # Build safe query with predetermined field names to prevent SQL injection
                    placeholders = ', '.join(fields)
                    query = f"UPDATE bots SET {placeholders}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
                    cursor.execute(query, values)
                    conn.commit()
                    logger.info(f"Updated bot {bot_id} info")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Error updating bot info: {e}")
            return False
            
    def add_winner(self, bot_id: int, user_id: int):
        """Add contest winner"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get active contest for this bot
                cursor.execute(
                    "SELECT id FROM contests WHERE bot_id = ? AND active = 1 LIMIT 1",
                    (bot_id,)
                )
                contest = cursor.fetchone()
                
                if contest:
                    cursor.execute(
                        "INSERT OR REPLACE INTO contest_winners (contest_id, user_id, position, announced_at) VALUES (?, ?, 1, CURRENT_TIMESTAMP)",
                        (contest['id'], user_id)
                    )
                    conn.commit()
                    logger.info(f"Added winner {user_id} for bot {bot_id}")
                
        except Exception as e:
            logger.error(f"Error adding winner: {e}")
            
    def get_detailed_referral_stats(self, bot_id: int):
        """Get detailed referral statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                stats = {}
                
                # Total referrals
                cursor.execute(
                    "SELECT COUNT(*) as count FROM referrals WHERE bot_id = ?",
                    (bot_id,)
                )
                total = cursor.fetchone()
                stats['total'] = total['count'] if total else 0
                
                # Top referrer
                cursor.execute(
                    """SELECT u.first_name, COUNT(r.id) as count 
                       FROM referrals r
                       JOIN users u ON r.referrer_id = u.telegram_id
                       WHERE r.bot_id = ?
                       GROUP BY r.referrer_id
                       ORDER BY count DESC
                       LIMIT 1""",
                    (bot_id,)
                )
                top_referrer = cursor.fetchone()
                
                if top_referrer:
                    stats['top_referrer'] = f"{top_referrer['first_name']} ({top_referrer['count']} ta)"
                else:
                    stats['top_referrer'] = "Yoq"
                    
                # This month
                this_month = datetime.now().replace(day=1).isoformat()
                cursor.execute(
                    "SELECT COUNT(*) as count FROM referrals WHERE bot_id = ? AND created_at >= ?",
                    (bot_id, this_month)
                )
                month_count = cursor.fetchone()
                stats['this_month'] = month_count['count'] if month_count else 0
                
                # Today
                today = datetime.now().date().isoformat()
                cursor.execute(
                    "SELECT COUNT(*) as count FROM referrals WHERE bot_id = ? AND date(created_at) = ?",
                    (bot_id, today)
                )
                today_count = cursor.fetchone()
                stats['today'] = today_count['count'] if today_count else 0
                
                return stats
                
        except Exception as e:
            logger.error(f"Error getting detailed referral stats: {e}")
            return {}
    
    def get_all_participants(self, bot_id: int) -> List[Dict]:
        """Get all users who joined the bot and shared their phone numbers."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                        SELECT DISTINCT
                            u.telegram_id,
                            u.telegram_id AS user_id,
                            u.first_name,
                            u.last_name,
                            u.username,
                            u.phone_number,
                            u.created_at,
                            COALESCE(bu.first_interaction, c.created_at, u.created_at) AS joined_at,
                            bu.last_interaction,
                            r.referrer_id AS referred_by
                        FROM users u
                        LEFT JOIN bot_users bu 
                            ON bu.user_id = u.telegram_id 
                           AND bu.bot_id = ?
                        LEFT JOIN contest_participants cp 
                            ON cp.user_id = u.id
                        LEFT JOIN contests c 
                            ON cp.contest_id = c.id 
                           AND c.bot_id = ?
                        LEFT JOIN referrals r 
                            ON r.referred_id = u.telegram_id 
                           AND r.bot_id = ?
                        WHERE (bu.bot_id IS NOT NULL OR c.bot_id = ?)
                          AND COALESCE(u.phone_number, '') != ''
                        ORDER BY COALESCE(bu.first_interaction, c.created_at, u.created_at) DESC
                    """,
                    (bot_id, bot_id, bot_id, bot_id)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all participants: {e}")
            return []
    
    def get_contests_by_bot(self, bot_id: int) -> List[Dict]:
        """Get all contests for a specific bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM contests WHERE bot_id = ? ORDER BY created_at DESC",
                    (bot_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting contests by bot: {e}")
            return []
    
    # New methods for enhanced admin panel - Note: duplicate method removed
            
    def update_welcome_message(self, bot_id: int, message: str):
        """Update bot welcome message"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE bot_settings SET welcome_message = ? WHERE bot_id = ?""",
                    (message, bot_id)
                )
                conn.commit()
                logger.info(f"Updated welcome message for bot {bot_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating welcome message: {e}")
            return False

    def update_subscription_message(self, bot_id: int, message: str):
        """Update bot subscription message"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE bot_settings SET subscription_message = ? WHERE bot_id = ?""",
                    (message, bot_id)
                )
                conn.commit()
                logger.info(f"Updated subscription message for bot {bot_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating subscription message: {e}")
            return False

    def get_subscription_message(self, bot_id: int):
        """Get bot subscription message"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT subscription_message FROM bot_settings WHERE bot_id = ?""",
                    (bot_id,)
                )
                result = cursor.fetchone()
                if result and result[0]:
                    return result[0]
                else:
                    # Default subscription message
                    return (
                        "📺 **Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:**\n\n"
                        "{channels}\n\n"
                        "1️⃣ Avvalo kanallarga qo'shiling.\n"
                        "2️⃣ So'ng \"✅ Bajarildi\" tugmasini bosing."
                    )
        except Exception as e:
            logger.error(f"Error getting subscription message: {e}")
            return (
                "📺 **Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:**\n\n"
                "{channels}\n\n"
                "1️⃣ Avvalo kanallarga qo'shiling.\n"
                "2️⃣ So'ng \"✅ Bajarildi\" tugmasini bosing."
            )
            
    def get_bot_admins(self, bot_id: int) -> List[int]:
        """Get list of bot admin IDs"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT admin_ids FROM bot_settings WHERE bot_id = ?", (bot_id,))
                result = cursor.fetchone()
                if result and result[0]:
                    import json
                    return json.loads(result[0])
                return []
        except Exception as e:
            logger.error(f"Error getting bot admins: {e}")
            return []
            
    def add_bot_admin(self, bot_id: int, user_id: int):
        """Add admin to bot"""
        try:
            admins = self.get_bot_admins(bot_id)
            if user_id not in admins:
                admins.append(user_id)
                import json
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """UPDATE bot_settings SET admin_ids = ? WHERE bot_id = ?""",
                        (json.dumps(admins), bot_id)
                    )
                    conn.commit()
                logger.info(f"Added admin {user_id} to bot {bot_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding bot admin: {e}")
            return False
            
    def remove_bot_admin(self, bot_id: int, user_id: int):
        """Remove admin from bot"""
        try:
            admins = self.get_bot_admins(bot_id)
            if user_id in admins:
                admins.remove(user_id)
                import json
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """UPDATE bot_settings SET admin_ids = ? WHERE bot_id = ?""",
                        (json.dumps(admins), bot_id)
                    )
                    conn.commit()
                logger.info(f"Removed admin {user_id} from bot {bot_id}")
                return True
        except Exception as e:
            logger.error(f"Error removing bot admin: {e}")
            return False
            
    def update_bot_restart_info(self, bot_id: int):
        """Update bot restart count and timestamp"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE bots SET 
                       restart_count = COALESCE(restart_count, 0) + 1,
                       last_restart = CURRENT_TIMESTAMP 
                       WHERE id = ?""",
                    (bot_id,)
                )
                conn.commit()
                logger.info(f"Updated restart info for bot {bot_id}")
                return True
        except Exception as e:
            logger.error(f"Error updating bot restart info: {e}")
            return False
    
    def get_connection(self):
        """Get database connection for context manager"""
        return sqlite3.connect(self.db_path)
    
    def get_bot_referral_count(self, bot_id: int) -> int:
        """Get referral count for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM referrals WHERE bot_id = ?",
                    (bot_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting bot referral count: {e}")
            return 0

    # Channel management methods
    def add_channel(self, bot_id: int, channel_id: str, channel_name: str = None, channel_username: str = None):
        """Add a mandatory subscription channel"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if channel already exists (including deactivated ones)
                cursor.execute(
                    "SELECT id, is_active FROM channels WHERE bot_id = ? AND channel_id = ?",
                    (bot_id, channel_id)
                )
                existing = cursor.fetchone()
                
                if existing:
                    # Channel exists, reactivate it and update info
                    cursor.execute(
                        """UPDATE channels SET 
                           channel_name = COALESCE(?, channel_name),
                           channel_username = COALESCE(?, channel_username),
                           is_active = 1,
                           created_at = CURRENT_TIMESTAMP
                           WHERE bot_id = ? AND channel_id = ?""",
                        (channel_name, channel_username, bot_id, channel_id)
                    )
                    logger.info(f"Reactivated existing channel {channel_id} for bot {bot_id}")
                else:
                    # Channel doesn't exist, create new
                    cursor.execute(
                        """INSERT INTO channels (bot_id, channel_id, channel_name, channel_username) 
                           VALUES (?, ?, ?, ?)""",
                        (bot_id, channel_id, channel_name, channel_username)
                    )
                    logger.info(f"Added new channel {channel_id} for bot {bot_id}")
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            return False

    def get_channels(self, bot_id: int):
        """Get all channels for a bot (alias for get_bot_channels)"""
        return self.get_bot_channels(bot_id)
        
    def get_mandatory_channels(self, bot_id: int):
        """Get mandatory subscription channels for a bot"""
        return self.get_bot_channels(bot_id)

    def get_bot_channels(self, bot_id: int):
        """Get all channels for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # First check if channels table exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='channels'
                """)
                table_exists = cursor.fetchone()
                
                if not table_exists:
                    logger.warning(f"Channels table does not exist for bot {bot_id}")
                    return []
                
                cursor.execute(
                    """SELECT id, channel_id, channel_name as name, channel_username as username, 
                              is_active, created_at 
                       FROM channels WHERE bot_id = ? AND is_active = 1 ORDER BY created_at""",
                    (bot_id,)
                )
                rows = cursor.fetchall()
                channels = [dict(row) for row in rows]
                logger.info(f"Found {len(channels)} channels for bot {bot_id}")
                return channels
        except Exception as e:
            logger.error(f"Error getting bot channels for bot {bot_id}: {e}")
            return []

    def remove_channel(self, bot_id: int, channel_id: str):
        """Remove a channel (deactivate)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if channel exists and is active
                cursor.execute(
                    "SELECT id FROM channels WHERE bot_id = ? AND channel_id = ? AND is_active = 1",
                    (bot_id, channel_id)
                )
                existing = cursor.fetchone()
                
                if not existing:
                    logger.warning(f"Channel {channel_id} not found or already inactive for bot {bot_id}")
                    return False
                
                cursor.execute(
                    "UPDATE channels SET is_active = 0 WHERE bot_id = ? AND channel_id = ?",
                    (bot_id, channel_id)
                )
                conn.commit()
                logger.info(f"Deactivated channel {channel_id} for bot {bot_id}")
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            return False

    def get_referrals_list(self, bot_id: int):
        """Get list of users who came via referral"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT u.first_name, u.last_name, u.phone_number, u.username, u.telegram_id, r.created_at
                       FROM referrals r
                       JOIN users u ON r.referred_id = u.telegram_id
                       WHERE r.bot_id = ?
                       ORDER BY r.created_at DESC""",
                    (bot_id,)
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting referrals list: {e}")
            return []

    def get_total_users(self, bot_id: int) -> int:
        """Get total number of users for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM bot_users WHERE bot_id = ?",
                    (bot_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total users: {e}")
            return 0

    def get_active_users_today(self, bot_id: int) -> int:
        """Get number of active users today"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT COUNT(DISTINCT u.telegram_id) 
                       FROM users u 
                       JOIN bot_users bu ON u.telegram_id = bu.user_id 
                       WHERE bu.bot_id = ? AND DATE(u.last_active) = ?""",
                    (bot_id, today)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting active users today: {e}")
            return 0

    def get_active_users_week(self, bot_id: int) -> int:
        """Get number of active users this week"""
        try:
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT COUNT(DISTINCT u.telegram_id) 
                       FROM users u 
                       JOIN bot_users bu ON u.telegram_id = bu.user_id 
                       WHERE bu.bot_id = ? AND DATE(u.last_active) >= ?""",
                    (bot_id, week_ago)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting active users week: {e}")
            return 0

    def get_total_contests(self, bot_id: int) -> int:
        """Get total number of contests for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM contests WHERE bot_id = ?",
                    (bot_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total contests: {e}")
            return 0

    def get_active_contests_count(self, bot_id: int) -> int:
        """Get number of active contests for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM contests WHERE bot_id = ? AND is_active = TRUE",
                    (bot_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting active contests: {e}")
            return 0

    def get_total_submissions(self, bot_id: int) -> int:
        """Get total number of submissions for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT COUNT(*) FROM submissions s 
                       JOIN contests c ON s.contest_id = c.id 
                       WHERE c.bot_id = ?""",
                    (bot_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total submissions: {e}")
            return 0

    def get_submissions_today(self, bot_id: int) -> int:
        """Get number of submissions today for a bot"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT COUNT(*) FROM submissions s 
                       JOIN contests c ON s.contest_id = c.id 
                       WHERE c.bot_id = ? AND DATE(s.created_at) = ?""",
                    (bot_id, today)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting submissions today: {e}")
            return 0

    def get_total_referrals(self, bot_id: int) -> int:
        """Get total number of referrals for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM referrals WHERE bot_id = ?",
                    (bot_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting total referrals: {e}")
            return 0

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Get user by telegram ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting user by telegram ID: {e}")
            return None

    def get_user_phone(self, telegram_id: int) -> Optional[str]:
        """Get user phone number"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT phone_number FROM users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.error(f"Error getting user phone: {e}")
            return None

    def update_user_phone(self, telegram_id: int, phone_number: str) -> bool:
        """Update user phone number"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET phone_number = ? WHERE telegram_id = ?",
                    (phone_number, telegram_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating user phone: {e}")
            return False
    
    def get_user_referrals(self, bot_id: int, user_id: int) -> List[Dict]:
        """Get list of users referred by this user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT u.telegram_id, u.first_name, u.last_name, u.username, r.created_at
                       FROM referrals r
                       JOIN users u ON r.referred_id = u.telegram_id
                       WHERE r.bot_id = ? AND r.referrer_id = ?
                       ORDER BY r.created_at DESC""",
                    (bot_id, user_id)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting user referrals: {e}")
            return []
    
    def get_all_users_for_broadcast(self) -> List[Dict]:
        """Get all users for broadcast messaging"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT DISTINCT telegram_id as user_id, first_name 
                       FROM users 
                       ORDER BY last_active DESC"""
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all users for broadcast: {e}")
            return []
    
    def get_bot_owners_for_broadcast(self) -> List[Dict]:
        """Get bot owners for broadcast messaging"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT DISTINCT u.telegram_id as user_id, u.first_name
                       FROM users u
                       JOIN bots b ON u.telegram_id = b.owner_id
                       ORDER BY u.last_active DESC"""
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting bot owners for broadcast: {e}")
            return []
    
    def get_new_users_for_broadcast(self, days: int = 7) -> List[Dict]:
        """Get new users for broadcast messaging"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT telegram_id as user_id, first_name
                       FROM users 
                       WHERE created_at > datetime('now', '-{} days')
                       ORDER BY created_at DESC""".format(days)
                )
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting new users for broadcast: {e}")
            return []
    
    def get_all_users_with_referrals_for_export(self, bot_id: int) -> List[Dict]:
        """Get all users with their referral counts for Excel export"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT 
                        u.first_name, 
                        u.last_name, 
                        u.phone_number,
                        COALESCE(r.referral_count, 0) as referral_count
                       FROM users u
                       LEFT JOIN (
                           SELECT referrer_id, COUNT(*) as referral_count
                           FROM referrals 
                           WHERE bot_id = ?
                           GROUP BY referrer_id
                       ) r ON u.telegram_id = r.referrer_id
                       WHERE u.telegram_id IN (
                           SELECT DISTINCT user_id FROM bot_users
                           WHERE bot_id = ?
                       )
                       ORDER BY u.first_name""",
                    (bot_id, bot_id)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting users for export: {e}")
            return []

    # Broadcast metodlar
    def get_all_users_for_broadcast(self) -> List[Dict]:
        """Barcha foydalanuvchilar ro'yxatini broadcast uchun olish"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT telegram_id as user_id, first_name, last_name, username 
                       FROM users ORDER BY created_at DESC"""
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all users for broadcast: {e}")
            return []

    def get_bot_owners_for_broadcast(self) -> List[Dict]:
        """Bot egalariga broadcast uchun ro'yxat"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT DISTINCT u.telegram_id as user_id, u.first_name, u.last_name, u.username 
                       FROM users u 
                       INNER JOIN bots b ON u.telegram_id = b.owner_id
                       ORDER BY u.created_at DESC"""
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting bot owners for broadcast: {e}")
            return []

    def get_new_users_for_broadcast(self, days: int = 7) -> List[Dict]:
        """So'nggi N kun ichida qo'shilgan foydalanuvchilar"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                since_date = datetime.now() - timedelta(days=days)
                cursor.execute(
                    """SELECT telegram_id as user_id, first_name, last_name, username 
                       FROM users 
                       WHERE created_at >= ?
                       ORDER BY created_at DESC""",
                    (since_date,)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting new users for broadcast: {e}")
            return []
    
    def get_top_referrers(self, bot_id: int, limit: int = 100) -> List[Dict]:
        """Get top referrers by referral count for a specific bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT 
                        u.first_name, 
                        u.last_name, 
                        u.username, 
                        u.phone_number,
                        u.telegram_id,
                        COUNT(r.referred_id) as referral_count
                    FROM users u
                    LEFT JOIN referrals r ON u.telegram_id = r.referrer_id AND r.bot_id = ?
                    WHERE u.telegram_id IN (
                        SELECT DISTINCT referrer_id FROM referrals WHERE bot_id = ?
                    )
                    GROUP BY u.telegram_id, u.first_name, u.last_name, u.username, u.phone_number
                    HAVING referral_count > 0
                    ORDER BY referral_count DESC, u.first_name ASC
                    LIMIT ?""",
                    (bot_id, bot_id, limit)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting top referrers: {e}")
            return []
    
    def get_all_referred_users_detailed(self, bot_id: int) -> List[Dict]:
        """Get all users who joined via referral with their referrer info"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT 
                        referred_user.first_name,
                        referred_user.last_name,
                        referred_user.username,
                        referred_user.phone_number,
                        referred_user.telegram_id,
                        referrer_user.first_name as referrer_name,
                        r.created_at as joined_at
                    FROM referrals r
                    JOIN users referred_user ON r.referred_id = referred_user.telegram_id
                    JOIN users referrer_user ON r.referrer_id = referrer_user.telegram_id
                    WHERE r.bot_id = ?
                    ORDER BY r.created_at DESC""",
                    (bot_id,)
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all referred users detailed: {e}")
            return []
    
    def get_all_users_for_export(self) -> List[Dict]:
        """Get all users in the system for export"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT 
                        first_name,
                        last_name,
                        username,
                        phone_number,
                        telegram_id,
                        created_at
                    FROM users
                    ORDER BY created_at DESC"""
                )
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all users for export: {e}")
            return []
    
    def get_users_with_referrals_detailed(self, bot_id: int) -> List[Dict]:
        """Get all users with their referral counts and list of referred users"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Get all users who have referred someone
                cursor.execute(
                    """SELECT 
                        u.telegram_id,
                        u.first_name,
                        u.last_name,
                        u.username,
                        u.phone_number,
                        COUNT(r.referred_id) as referral_count
                    FROM users u
                    LEFT JOIN referrals r ON u.telegram_id = r.referrer_id AND r.bot_id = ?
                    WHERE u.telegram_id IN (
                        SELECT DISTINCT referrer_id FROM referrals WHERE bot_id = ?
                    )
                    GROUP BY u.telegram_id, u.first_name, u.last_name, u.username, u.phone_number
                    HAVING referral_count > 0
                    ORDER BY referral_count DESC, u.first_name ASC""",
                    (bot_id, bot_id)
                )
                
                users_with_refs = []
                for row in cursor.fetchall():
                    user = dict(row)
                    telegram_id = user['telegram_id']
                    
                    # Get list of users referred by this user
                    cursor.execute(
                        """SELECT 
                            referred_user.first_name,
                            referred_user.last_name,
                            referred_user.username,
                            referred_user.phone_number,
                            referred_user.telegram_id,
                            r.created_at
                        FROM referrals r
                        JOIN users referred_user ON r.referred_id = referred_user.telegram_id
                        WHERE r.referrer_id = ? AND r.bot_id = ?
                        ORDER BY r.created_at DESC""",
                        (telegram_id, bot_id)
                    )
                    
                    referred_users = [dict(r) for r in cursor.fetchall()]
                    user['referred_users'] = referred_users
                    users_with_refs.append(user)
                
                return users_with_refs
        except Exception as e:
            logger.error(f"Error getting users with referrals detailed: {e}")
            return []
    
    def get_referral_count(self, user_id: int, bot_id: int) -> int:
        """Get count of users referred by a specific user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND bot_id = ?",
                    (user_id, bot_id)
                )
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting referral count: {e}")
            return 0

    # ==================== ADVANCED ADMIN PANEL DATABASE METHODS ====================
    
    def get_bot_detailed_stats(self, bot_id: int) -> dict:
        """Get detailed statistics for analytics dashboard"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get comprehensive stats
                stats = {}
                
                # User statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_users,
                        COUNT(CASE WHEN bu.last_interaction >= datetime('now', '-1 day') THEN 1 END) as active_24h,
                        COUNT(CASE WHEN bu.last_interaction >= datetime('now', '-7 days') THEN 1 END) as active_week
                    FROM bot_users bu
                    WHERE bu.bot_id = ?
                """, (bot_id,))
                user_stats = cursor.fetchone()
                if user_stats:
                    stats['total_users'] = user_stats[0]
                    stats['active_24h'] = user_stats[1] 
                    stats['active_week'] = user_stats[2]
                
                # Contest statistics
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_contests,
                        COUNT(CASE WHEN active = 1 THEN 1 END) as active_contests,
                        AVG(CASE WHEN active = 0 THEN 
                            (SELECT COUNT(*) FROM contest_participants cp WHERE cp.contest_id = contests.id)
                        END) as avg_participants
                    FROM contests WHERE bot_id = ?
                """, (bot_id,))
                contest_stats = cursor.fetchone()
                if contest_stats:
                    stats['total_contests'] = contest_stats[0]
                    stats['active_contests'] = contest_stats[1]
                    stats['avg_participants'] = contest_stats[2] or 0
                
                return stats
                
        except Exception as e:
            logger.error(f"Error getting detailed stats: {e}")
            return {}

    def get_top_referrers(self, bot_id: int, limit: int = 5) -> list:
        """Get top referrers for the bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        u.first_name || ' ' || COALESCE(u.last_name, '') as name,
                        COUNT(r.referred_id) as count,
                        u.telegram_id
                    FROM referrals r
                    JOIN users u ON r.referrer_id = u.telegram_id
                    WHERE r.bot_id = ?
                    GROUP BY r.referrer_id
                    ORDER BY count DESC
                    LIMIT ?
                """, (bot_id, limit))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'name': row[0].strip(),
                        'count': row[1],
                        'telegram_id': row[2]
                    })
                return results
                
        except Exception as e:
            logger.error(f"Error getting top referrers: {e}")
            return []

    def get_contest_performance_stats(self, bot_id: int) -> dict:
        """Get contest performance analytics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Most popular contest
                cursor.execute("""
                    SELECT c.title, COUNT(cp.user_id) as participants
                    FROM contests c
                    LEFT JOIN contest_participants cp ON c.id = cp.contest_id
                    WHERE c.bot_id = ?
                    GROUP BY c.id
                    ORDER BY participants DESC
                    LIMIT 1
                """, (bot_id,))
                most_popular = cursor.fetchone()
                
                # Average participation rate
                cursor.execute("""
                    SELECT 
                        AVG(participant_count * 1.0 / total_users * 100) as avg_participation
                    FROM (
                        SELECT 
                            c.id,
                            COUNT(cp.user_id) as participant_count,
                            (SELECT COUNT(*) FROM bot_users WHERE bot_id = ?) as total_users
                        FROM contests c
                        LEFT JOIN contest_participants cp ON c.id = cp.contest_id
                        WHERE c.bot_id = ?
                        GROUP BY c.id
                    )
                """, (bot_id, bot_id))
                avg_participation = cursor.fetchone()
                
                return {
                    'most_popular': most_popular[0] if most_popular else 'Yo\'q',
                    'avg_participation': avg_participation[0] if avg_participation and avg_participation[0] else 0,
                    'success_rate': 85.0  # Mock data, can be calculated based on completion rates
                }
                
        except Exception as e:
            logger.error(f"Error getting contest performance: {e}")
            return {}

    def get_user_management_stats(self, bot_id: int) -> dict:
        """Get user management statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total users
                cursor.execute("SELECT COUNT(*) FROM bot_users WHERE bot_id = ?", (bot_id,))
                total_users = cursor.fetchone()[0]
                
                # Active users in last 24h  
                cursor.execute("""
                    SELECT COUNT(*) FROM bot_users 
                    WHERE bot_id = ? AND last_interaction >= datetime('now', '-1 day')
                """, (bot_id,))
                active_24h = cursor.fetchone()[0]
                
                # Mock data for other stats (can be implemented with proper tables)
                return {
                    'total_users': total_users,
                    'active_24h': active_24h,
                    'blocked_users': 0,  # Need to add blocked_users table
                    'admin_users': 1     # Bot owner + additional admins
                }
                
        except Exception as e:
            logger.error(f"Error getting user management stats: {e}")
            return {}

    def get_backup_info(self, bot_id: int) -> dict:
        """Get backup information"""
        try:
            # This would need to be implemented with a proper backup system
            return {
                'last_backup': 'Hech qachon',
                'backup_size': '0',
                'backup_status': 'Sozlanmagan'
            }
        except Exception as e:
            logger.error(f"Error getting backup info: {e}")
            return {}

    def get_bot_logs(self, bot_id: int, limit: int = 50) -> list:
        """Get bot logs (mock implementation)"""
        try:
            # This would need a proper logging table
            return [
                {'level': 'INFO', 'message': 'Bot started successfully', 'timestamp': '2024-01-01 12:00:00'},
                {'level': 'WARNING', 'message': 'High memory usage detected', 'timestamp': '2024-01-01 11:30:00'},
                {'level': 'ERROR', 'message': 'Database connection timeout', 'timestamp': '2024-01-01 11:00:00'},
                {'level': 'INFO', 'message': 'New contest created', 'timestamp': '2024-01-01 10:30:00'},
                {'level': 'INFO', 'message': 'User registered', 'timestamp': '2024-01-01 10:00:00'}
            ][:limit]
        except Exception as e:
            logger.error(f"Error getting bot logs: {e}")
            return []







    def get_bot_configuration(self, bot_id: int) -> dict:
        """Get bot configuration settings"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM bot_settings WHERE bot_id = ?", 
                    (bot_id,)
                )
                result = cursor.fetchone()
                
                if result:
                    # Convert row to dict (column names depend on your schema)
                    return {
                        'auto_responses': True,
                        'welcome_enabled': True,
                        'spam_protection': True,
                        'file_uploads': True,
                        'debug_mode': False
                    }
                else:
                    return {
                        'auto_responses': True,
                        'welcome_enabled': True,
                        'spam_protection': True,
                        'file_uploads': True,
                        'debug_mode': False
                    }
        except Exception as e:
            logger.error(f"Error getting bot configuration: {e}")
            return {}

    def get_all_contests(self, bot_id: int) -> list:
        """Get all contests for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, title, description, status, created_at, end_date,
                           (SELECT COUNT(*) FROM contest_participants WHERE contest_id = contests.id) as participants
                    FROM contests 
                    WHERE bot_id = ? 
                    ORDER BY created_at DESC
                """, (bot_id,))
                
                contests = []
                for row in cursor.fetchall():
                    contests.append({
                        'id': row[0],
                        'title': row[1],
                        'description': row[2],
                        'status': row[3],
                        'created_at': row[4],
                        'end_date': row[5],
                        'participants': row[6]
                    })
                return contests
                
        except Exception as e:
            logger.error(f"Error getting all contests: {e}")
            return []

    def get_recent_users(self, bot_id: int, limit: int = 10) -> list:
        """Get recent users for a bot"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT u.first_name, u.last_name, u.username, u.telegram_id, bu.first_interaction
                    FROM bot_users bu
                    JOIN users u ON bu.user_id = u.telegram_id
                    WHERE bu.bot_id = ?
                    ORDER BY bu.first_interaction DESC
                    LIMIT ?
                """, (bot_id, limit))
                
                users = []
                for row in cursor.fetchall():
                    users.append({
                        'first_name': row[0],
                        'last_name': row[1],
                        'username': row[2],
                        'telegram_id': row[3],
                        'join_date': row[4][:10] if row[4] else 'Noma\'lum'
                    })
                return users
                
        except Exception as e:
            logger.error(f"Error getting recent users: {e}")
            return []

    def get_bot_admins(self, bot_id: int) -> list:
        """Get bot admins list"""
        try:
            # This would need a bot_admins table
            # For now, return empty list (only owner has access)
            return []
        except Exception as e:
            logger.error(f"Error getting bot admins: {e}")
            return []
    
    def get_bot_statistics(self, bot_id: int):
        """Get comprehensive bot statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                stats = {}
                
                # Total users
                cursor.execute(
                    "SELECT COUNT(*) as count FROM bot_users WHERE bot_id = ?",
                    (bot_id,)
                )
                result = cursor.fetchone()
                stats['total_users'] = result['count'] if result else 0
                
                # Users with phone numbers
                cursor.execute(
                    """SELECT COUNT(*) as count FROM bot_users bu 
                       JOIN users u ON bu.user_id = u.telegram_id 
                       WHERE bu.bot_id = ? AND u.phone_number IS NOT NULL""",
                    (bot_id,)
                )
                result = cursor.fetchone()
                stats['users_with_phone'] = result['count'] if result else 0
                
                # Required channels count
                cursor.execute(
                    "SELECT COUNT(*) as count FROM required_channels WHERE bot_id = ?",
                    (bot_id,)
                )
                result = cursor.fetchone()
                stats['required_channels'] = result['count'] if result else 0
                
                # Users joined in last 24 hours
                cursor.execute(
                    """SELECT COUNT(*) as count FROM bot_users bu 
                       WHERE bu.bot_id = ? AND bu.first_interaction > datetime('now', '-1 day')""",
                    (bot_id,)
                )
                result = cursor.fetchone()
                stats['new_users_24h'] = result['count'] if result else 0
                
                # Users joined in last 7 days
                cursor.execute(
                    """SELECT COUNT(*) as count FROM bot_users bu 
                       WHERE bu.bot_id = ? AND bu.first_interaction > datetime('now', '-7 days')""",
                    (bot_id,)
                )
                result = cursor.fetchone()
                stats['new_users_7d'] = result['count'] if result else 0
                
                return stats
                
        except Exception as e:
            logger.error(f"Error getting bot statistics: {e}")
            return {}