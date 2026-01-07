import sqlite3
import json
import uuid
import datetime
from pathlib import Path

DB_PATH = "chat_history.db"

class ChatHistoryManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Sessions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        ''')
        
        # Messages table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        ''')
        
        conn.commit()
        conn.close()

    def create_session(self, title="New Chat"):
        """Create a new chat session."""
        session_id = str(uuid.uuid4())
        now = datetime.datetime.now()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)',
            (session_id, title, now, now)
        )
        conn.commit()
        conn.close()
        return session_id

    def update_session_title(self, session_id, title):
        """Update the title of a session."""
        now = datetime.datetime.now()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?',
            (title, now, session_id)
        )
        conn.commit()
        conn.close()

    def add_message(self, session_id, role, content):
        """Add a message to a session."""
        now = datetime.datetime.now()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)',
            (session_id, role, content, now)
        )
        # Update session timestamp
        cursor.execute(
            'UPDATE sessions SET updated_at = ? WHERE id = ?',
            (now, session_id)
        )
        conn.commit()
        conn.close()

    def get_sessions(self):
        """Get all sessions, ordered by most recent update."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, created_at FROM sessions ORDER BY updated_at DESC')
        sessions = [
            {'id': row[0], 'title': row[1], 'created_at': row[2]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return sessions

    def get_messages(self, session_id):
        """Get all messages for a session."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC',
            (session_id,)
        )
        messages = [
            {'role': row[0], 'content': row[1]}
            for row in cursor.fetchall()
        ]
        conn.close()
        return messages

    def delete_session(self, session_id):
        """Delete a session and all its messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()
        conn.close()

# Global Instance
history_manager = ChatHistoryManager()
