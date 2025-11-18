"""
Database layer for personal assistant memory storage.

Uses SQLite to store conversations and metadata with semantic embeddings
for intelligent retrieval and context-aware responses.
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class AssistantDatabase:
    """SQLite database for storing conversation history and metadata."""

    def __init__(self, db_path: str = "assistant_memory.db"):
        """
        Initialize the assistant database.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        self._local = threading.local()  # Thread-local storage for connections
        self._write_lock = threading.Lock()  # Lock for write operations
        self._pending_commits = []  # Buffer for batch commits
        self._commit_threshold = 10  # Commit after N operations
        self._all_connections: list[sqlite3.Connection] = []  # Track all connections for cleanup
        self._connections_lock = threading.Lock()  # Lock for connection tracking
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                isolation_level="DEFERRED",  # Allow concurrent reads during writes
            )
            self._local.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn.execute(
                "PRAGMA busy_timeout=60000"
            )  # 60 second busy timeout

            # Track this connection for cleanup
            with self._connections_lock:
                self._all_connections.append(self._local.conn)

            logger.debug(
                f"Created new connection for thread {threading.current_thread().name}"
            )
        return self._local.conn

    def _initialize_database(self):
        """Create database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Create conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                session_id TEXT
            )
        """)

        # Create indexes for conversations
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp
            ON conversations(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session
            ON conversations(session_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_role
            ON conversations(role)
        """)

        # Create metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                people TEXT,
                topics TEXT,
                dates_mentioned TEXT,
                sentiment TEXT,
                category TEXT,
                embedding BLOB,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        # Create indexes for metadata
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_id
            ON metadata(conversation_id)
        """)

        # Create calendar credentials table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calendar_credentials (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                token_data TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        logger.debug(f"Database initialized: {self.db_path}")

    @contextmanager
    def _batch_commit(self):
        """Context manager for batch commits."""
        yield
        # Only lock during the commit check/flush
        with self._write_lock:
            self._pending_commits.append(1)
            if len(self._pending_commits) >= self._commit_threshold:
                self._flush_commits()

    def _flush_commits(self):
        """Flush pending commits to database."""
        if self._pending_commits:
            conn = self._get_connection()
            conn.commit()
            self._pending_commits.clear()
            logger.debug("Flushed batch commits")

    def add_conversation(
        self,
        role: str,
        content: str,
        session_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> int:
        """
        Add a conversation message to the database.

        Args:
            role: Message role ('user' or 'assistant')
            content: Message content
            session_id: Optional session identifier
            timestamp: Optional custom timestamp

        Returns:
            The ID of the inserted conversation
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        with self._batch_commit():
            if timestamp:
                cursor.execute(
                    """
                    INSERT INTO conversations (timestamp, role, content, session_id)
                    VALUES (?, ?, ?, ?)
                """,
                    (timestamp, role, content, session_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO conversations (role, content, session_id)
                    VALUES (?, ?, ?)
                """,
                    (role, content, session_id),
                )

            conversation_id = cursor.lastrowid
            logger.debug(f"Added conversation {conversation_id}: {role}")
            return conversation_id

    def add_metadata(
        self,
        conversation_id: int,
        people: list[str | None] = None,
        topics: list[str | None] = None,
        dates_mentioned: str | None = None,
        sentiment: str | None = None,
        category: str | None = None,
        embedding: bytes | None = None,
    ) -> int:
        """
        Add metadata for a conversation.

        Args:
            conversation_id: ID of the conversation
            people: List of people mentioned
            topics: List of topics discussed
            dates_mentioned: Dates/times mentioned (JSON string)
            sentiment: Sentiment classification
            category: Category classification
            embedding: Binary embedding vector

        Returns:
            The ID of the inserted metadata
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Convert lists to JSON strings
        people_json = json.dumps(people) if people else None
        topics_json = json.dumps(topics) if topics else None

        with self._batch_commit():
            cursor.execute(
                """
                INSERT INTO metadata
                (conversation_id, people, topics, dates_mentioned, sentiment, category, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    conversation_id,
                    people_json,
                    topics_json,
                    dates_mentioned,
                    sentiment,
                    category,
                    embedding,
                ),
            )

            metadata_id = cursor.lastrowid
            logger.debug(
                f"Added metadata {metadata_id} for conversation {conversation_id}"
            )
            return metadata_id

    def get_conversations(
        self,
        limit: int | None = None,
        role: str | None = None,
        session_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[Dict]:
        """
        Retrieve conversations with optional filters.

        Args:
            limit: Maximum number of conversations to return
            role: Filter by role ('user' or 'assistant')
            session_id: Filter by session ID
            start_date: Filter conversations after this date
            end_date: Filter conversations before this date

        Returns:
            List of conversation dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM conversations WHERE 1=1"
        params = []

        if role:
            query += " AND role = ?"
            params.append(role)

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)

        query += " ORDER BY timestamp DESC"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def get_conversation_with_metadata(self, conversation_id: int) -> Dict | None:
        """
        Get a conversation with its metadata.

        Args:
            conversation_id: ID of the conversation

        Returns:
            Dictionary with conversation and metadata, or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT c.*, m.people, m.topics, m.dates_mentioned,
                   m.sentiment, m.category, m.embedding
            FROM conversations c
            LEFT JOIN metadata m ON c.id = m.conversation_id
            WHERE c.id = ?
        """,
            (conversation_id,),
        )

        row = cursor.fetchone()
        if row:
            result = dict(row)
            # Parse JSON fields, ensuring they're always lists (never None)
            result["people"] = (
                json.loads(result["people"]) if result.get("people") else []
            )
            result["topics"] = (
                json.loads(result["topics"]) if result.get("topics") else []
            )
            return result
        return None

    def search_by_people(self, person: str, limit: int = 10) -> list[Dict]:
        """
        Search conversations mentioning a specific person.

        Args:
            person: Person name to search for
            limit: Maximum number of results

        Returns:
            List of conversations with metadata
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT c.*, m.people, m.topics, m.sentiment
            FROM conversations c
            JOIN metadata m ON c.id = m.conversation_id
            WHERE m.people LIKE ?
            ORDER BY c.timestamp DESC
            LIMIT ?
        """,
            (f'%"{person}"%', limit),
        )

        rows = cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            # Parse JSON fields, ensuring they're always lists (never None)
            result["people"] = (
                json.loads(result["people"]) if result.get("people") else []
            )
            result["topics"] = (
                json.loads(result["topics"]) if result.get("topics") else []
            )
            results.append(result)

        return results

    def search_by_topic(self, topic: str, limit: int = 10) -> list[Dict]:
        """
        Search conversations by topic.

        Args:
            topic: Topic to search for
            limit: Maximum number of results

        Returns:
            List of conversations with metadata
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT c.*, m.people, m.topics, m.sentiment
            FROM conversations c
            JOIN metadata m ON c.id = m.conversation_id
            WHERE m.topics LIKE ?
            ORDER BY c.timestamp DESC
            LIMIT ?
        """,
            (f'%"{topic}"%', limit),
        )

        rows = cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            # Parse JSON fields, ensuring they're always lists (never None)
            result["people"] = (
                json.loads(result["people"]) if result.get("people") else []
            )
            result["topics"] = (
                json.loads(result["topics"]) if result.get("topics") else []
            )
            results.append(result)

        return results

    def get_all_people(self) -> list[str]:
        """
        Get all unique people mentioned in conversations.

        Returns:
            List of unique person names
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT people FROM metadata WHERE people IS NOT NULL
        """)

        rows = cursor.fetchall()
        people_set = set()

        for row in rows:
            if row["people"]:
                people_list = json.loads(row["people"])
                people_set.update(people_list)

        return sorted(list(people_set))

    def get_all_topics(self) -> list[str]:
        """
        Get all unique topics discussed in conversations.

        Returns:
            List of unique topics
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT topics FROM metadata WHERE topics IS NOT NULL
        """)

        rows = cursor.fetchall()
        topics_set = set()

        for row in rows:
            if row["topics"]:
                topics_list = json.loads(row["topics"])
                topics_set.update(topics_list)

        return sorted(list(topics_set))

    def get_embeddings_for_search(
        self, limit: int | None = None
    ) -> list[tuple[int, bytes]]:
        """
        Get all conversation embeddings for similarity search.

        Args:
            limit: Optional limit on number of embeddings to return

        Returns:
            List of (conversation_id, embedding) tuples
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        query = """
            SELECT conversation_id, embedding
            FROM metadata
            WHERE embedding IS NOT NULL
            ORDER BY conversation_id DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        return cursor.fetchall()

    def get_stats(self) -> Dict:
        """
        Get database statistics.

        Returns:
            Dictionary with statistics
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM conversations")
        total_conversations = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM conversations WHERE role = 'user'"
        )
        user_messages = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM conversations WHERE role = 'assistant'"
        )
        assistant_messages = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT COUNT(*) as count FROM metadata WHERE embedding IS NOT NULL"
        )
        embeddings_count = cursor.fetchone()["count"]

        cursor.execute(
            "SELECT MIN(timestamp) as first, MAX(timestamp) as last FROM conversations"
        )
        dates = cursor.fetchone()

        return {
            "total_conversations": total_conversations,
            "user_messages": user_messages,
            "assistant_messages": assistant_messages,
            "embeddings_count": embeddings_count,
            "first_conversation": dates["first"],
            "last_conversation": dates["last"],
            "unique_people": len(self.get_all_people()),
            "unique_topics": len(self.get_all_topics()),
        }

    def close(self):
        """Close the database connection and flush pending commits."""
        # Flush any pending commits
        with self._write_lock:
            if self._pending_commits:
                self._flush_commits()

        # Close ALL thread-local connections (not just the current thread)
        with self._connections_lock:
            connections_to_close = list(self._all_connections)
            self._all_connections.clear()

        for conn in connections_to_close:
            try:
                if conn:
                    conn.close()
            except Exception as e:
                logger.debug(f"Error closing connection: {e}")

        # Clean up thread-local storage in current thread
        if hasattr(self._local, "conn"):
            self._local.conn = None

        # Close main connection if it exists (legacy)
        if self.conn:
            self.conn.close()
            self.conn = None

        logger.info(f"Closed {len(connections_to_close)} database connection(s)")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
