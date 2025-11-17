"""
Database Backup Manager
Automatic backup and restore functionality
"""
import os
import shutil
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional, List
import gzip

logger = logging.getLogger(__name__)


class BackupManager:
    """Manage database backups"""
    
    def __init__(self, db_path: str = "bot_builder.db", backup_dir: str = "backups"):
        self.db_path = db_path
        self.backup_dir = backup_dir
        
        # Create backup directory if it doesn't exist
        os.makedirs(backup_dir, exist_ok=True)
    
    def create_backup(self, compress: bool = True) -> Optional[str]:
        """
        Create a backup of the database
        
        Args:
            compress: Whether to compress the backup with gzip
            
        Returns:
            Path to backup file or None if failed
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_{timestamp}.db"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # Use SQLite backup API for safe backup while db is in use
            source_conn = sqlite3.connect(self.db_path)
            backup_conn = sqlite3.connect(backup_path)
            
            with backup_conn:
                source_conn.backup(backup_conn)
            
            source_conn.close()
            backup_conn.close()
            
            # Compress if requested
            if compress:
                compressed_path = f"{backup_path}.gz"
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Remove uncompressed file
                os.remove(backup_path)
                backup_path = compressed_path
            
            file_size = os.path.getsize(backup_path)
            logger.info(f"Backup created: {backup_path} ({file_size / 1024:.2f} KB)")
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None
    
    def restore_backup(self, backup_path: str) -> bool:
        """
        Restore database from backup
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(backup_path):
                logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Create a safety backup of current db before restore
            safety_backup = f"{self.db_path}.before_restore"
            shutil.copy2(self.db_path, safety_backup)
            logger.info(f"Created safety backup: {safety_backup}")
            
            # Handle compressed backups
            temp_db_path = backup_path
            if backup_path.endswith('.gz'):
                temp_db_path = backup_path[:-3]  # Remove .gz extension
                with gzip.open(backup_path, 'rb') as f_in:
                    with open(temp_db_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
            
            # Restore the backup
            shutil.copy2(temp_db_path, self.db_path)
            
            # Clean up temporary file if it was extracted
            if temp_db_path != backup_path:
                os.remove(temp_db_path)
            
            logger.info(f"Database restored from: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return False
    
    def list_backups(self) -> List[dict]:
        """
        List all available backups
        
        Returns:
            List of backup info dictionaries
        """
        backups = []
        
        try:
            for filename in os.listdir(self.backup_dir):
                if filename.startswith('backup_') and (filename.endswith('.db') or filename.endswith('.db.gz')):
                    filepath = os.path.join(self.backup_dir, filename)
                    stat = os.stat(filepath)
                    
                    backups.append({
                        'filename': filename,
                        'path': filepath,
                        'size': stat.st_size,
                        'created': datetime.fromtimestamp(stat.st_mtime),
                        'compressed': filename.endswith('.gz')
                    })
            
            # Sort by creation time (newest first)
            backups.sort(key=lambda x: x['created'], reverse=True)
            
        except Exception as e:
            logger.error(f"Error listing backups: {e}")
        
        return backups
    
    def cleanup_old_backups(self, keep_days: int = 7, keep_count: int = 10) -> int:
        """
        Clean up old backups
        
        Args:
            keep_days: Keep backups newer than this many days
            keep_count: Always keep at least this many recent backups
            
        Returns:
            Number of backups deleted
        """
        try:
            backups = self.list_backups()
            
            if len(backups) <= keep_count:
                logger.info(f"Only {len(backups)} backups, keeping all (min: {keep_count})")
                return 0
            
            cutoff_date = datetime.now() - timedelta(days=keep_days)
            deleted_count = 0
            
            # Keep the most recent backups
            backups_to_check = backups[keep_count:]
            
            for backup in backups_to_check:
                if backup['created'] < cutoff_date:
                    os.remove(backup['path'])
                    logger.info(f"Deleted old backup: {backup['filename']}")
                    deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old backups")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")
            return 0
    
    def auto_backup(self, compress: bool = True, cleanup: bool = True) -> bool:
        """
        Perform automatic backup with cleanup
        
        Args:
            compress: Whether to compress backup
            cleanup: Whether to clean up old backups
            
        Returns:
            True if successful
        """
        logger.info("Starting automatic backup...")
        
        # Create backup
        backup_path = self.create_backup(compress=compress)
        if not backup_path:
            logger.error("Automatic backup failed!")
            return False
        
        # Clean up old backups
        if cleanup:
            deleted = self.cleanup_old_backups()
            logger.info(f"Cleaned up {deleted} old backups")
        
        logger.info("Automatic backup completed successfully")
        return True
    
    def get_backup_stats(self) -> dict:
        """Get backup statistics"""
        backups = self.list_backups()
        
        if not backups:
            return {
                'total_backups': 0,
                'total_size': 0,
                'oldest_backup': None,
                'newest_backup': None
            }
        
        total_size = sum(b['size'] for b in backups)
        
        return {
            'total_backups': len(backups),
            'total_size': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'oldest_backup': backups[-1]['created'],
            'newest_backup': backups[0]['created'],
            'compressed_count': sum(1 for b in backups if b['compressed'])
        }


# Global backup manager instance
_backup_manager = None


def get_backup_manager(db_path: str = "bot_builder.db") -> BackupManager:
    """Get global backup manager instance"""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager(db_path)
    return _backup_manager
