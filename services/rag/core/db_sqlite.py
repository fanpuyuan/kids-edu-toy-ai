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
                        md5_hash TEXT,
                        embedding_provider TEXT,
                        upload_time DATETIME NOT NULL,
                        status TEXT NOT NULL
                    )
                ''')
                
                # Check if md5_hash column exists (Migration for existing databases)
                cursor.execute("PRAGMA table_info(documents)")
                columns = [info[1] for info in cursor.fetchall()]
                if 'md5_hash' not in columns:
                    logger.info("Migrating database: adding md5_hash column to documents table.")
                    cursor.execute("ALTER TABLE documents ADD COLUMN md5_hash TEXT")
                
                if 'embedding_provider' not in columns:
                    logger.info("Migrating database: adding embedding_provider column to documents table.")
                    cursor.execute("ALTER TABLE documents ADD COLUMN embedding_provider TEXT")


                conn.commit()
            logger.info(f"Initialized/Migrated SQLite database at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite database: {e}")

    def add_document(self, filename: str, md5_hash: str = None, provider: str = "local") -> str:
        """Adds a new document record and returns the generated doc_id."""
        doc_id = str(uuid.uuid4())
        upload_time = datetime.now().isoformat()
        status = "processing"
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO documents (doc_id, filename, md5_hash, embedding_provider, upload_time, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (doc_id, filename, md5_hash, provider, upload_time, status)
                )
                conn.commit()
            logger.info(f"Added document record: {filename} (Hash: {md5_hash})")
            return doc_id
        except Exception as e:
            logger.error(f"Failed to add document record {filename}: {e}")
            return ""

    def get_doc_by_filename(self, filename: str) -> dict:
        """Checks if a document with the same filename exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM documents WHERE filename = ?", (filename,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get document by filename {filename}: {e}")
            return None

    def get_doc_by_hash(self, md5_hash: str, provider: str = None) -> dict:
        """Checks if a document with the same MD5 hash exists."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if provider:
                    cursor.execute("SELECT * FROM documents WHERE md5_hash = ? AND embedding_provider = ?", (md5_hash, provider))
                else:
                    cursor.execute("SELECT * FROM documents WHERE md5_hash = ?", (md5_hash,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get document by hash {md5_hash}: {e}")
            return None

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

    def get_all_documents(self, provider: str = None) -> list[dict]:
        """Retrieves all document records, optionally filtered by provider."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row # To return dicts
                cursor = conn.cursor()
                if provider:
                    cursor.execute("SELECT * FROM documents WHERE embedding_provider = ? ORDER BY upload_time DESC", (provider,))
                else:
                    cursor.execute("SELECT * FROM documents ORDER BY upload_time DESC")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
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
