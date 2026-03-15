import sqlite3
from pathlib import Path
from loguru import logger
import uuid
from datetime import datetime

class SQLiteManager:
    """Manages SQLite database for document metadata."""
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        # Ensure the data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "documents.db"
        self._init_db()

    def _init_db(self):
        """Initializes the database schema if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS documents (
                        doc_id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        upload_time DATETIME NOT NULL,
                        status TEXT NOT NULL
                    )
                ''')
                conn.commit()
            logger.info(f"Initialized SQLite database at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")

    def add_document(self, filename: str) -> str:
        """Adds a new document record and returns the generated doc_id."""
        doc_id = str(uuid.uuid4())
        upload_time = datetime.now().isoformat()
        status = "processing"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO documents (doc_id, filename, upload_time, status) VALUES (?, ?, ?, ?)",
                    (doc_id, filename, upload_time, status)
                )
                conn.commit()
            logger.info(f"Added document record: {filename} ({doc_id})")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to add document record {filename}: {e}")
            return ""

    def update_document_status(self, doc_id: str, status: str):
        """Updates the status of an existing document."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE documents SET status = ? WHERE doc_id = ?",
                    (status, doc_id)
                )
                conn.commit()
            logger.info(f"Updated document status: {doc_id} -> {status}")
        except Exception as e:
            logger.error(f"Failed to update document status for {doc_id}: {e}")

    def get_all_documents(self) -> list[dict]:
        """Retrieves all document records."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row # To return dicts
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM documents ORDER BY upload_time DESC")
                rows = cursor.fetchall()
                result = [dict(row) for row in rows]
                # Fallback to an empty list on failure isn't technically needed with empty DBs, but nice to have.
                return result
        except Exception as e:
            logger.error(f"Failed to retrieve documents: {e}")
            return []

    def delete_document(self, doc_id: str):
        """Deletes a document record."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
                conn.commit()
            logger.info(f"Deleted document record: {doc_id}")
        except Exception as e:
            logger.error(f"Failed to delete document record {doc_id}: {e}")

sqlite_manager = SQLiteManager()
