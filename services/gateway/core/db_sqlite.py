import sqlite3
from pathlib import Path
from loguru import logger
from datetime import datetime

class GatewaySQLiteManager:
    """Manages SQLite database for gateway configurations."""
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        # Ensure the data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "gateway.db"
        self._init_db()

    def _init_db(self):
        """Initializes the database schema if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # App Configuration Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS app_config (
                        config_key TEXT PRIMARY KEY,
                        config_value TEXT NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                ''')
                conn.commit()
            logger.info(f"Initialized SQLite database at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")

    # --- Configuration Management ---
    
    def get_all_configs(self) -> dict:
        """Retrieves all configuration key-value pairs."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT config_key, config_value FROM app_config")
                rows = cursor.fetchall()
                return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Failed to fetch configs: {e}")
            return {}

    def save_configs(self, configs: dict) -> bool:
        """Saves a dictionary of configurations (Upsert)."""
        updated_at = datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for key, value in configs.items():
                    cursor.execute(
                        "REPLACE INTO app_config (config_key, config_value, updated_at) VALUES (?, ?, ?)",
                        (key, str(value), updated_at)
                    )
                conn.commit()
            logger.info("Successfully updated app_config")
            return True
        except Exception as e:
            logger.error(f"Failed to save configs: {e}")
            return False

sqlite_manager = GatewaySQLiteManager()
