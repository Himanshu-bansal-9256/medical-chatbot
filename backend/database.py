import sqlite3
import os
import json
import secrets
from datetime import datetime

# Database path — same directory as this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "medicare.db")


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'New Chat',
            messages TEXT NOT NULL DEFAULT '[]',
            share_token TEXT UNIQUE,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Ensure share_token column exists if table was created previously
    try:
        cursor.execute("ALTER TABLE chat_sessions ADD COLUMN share_token TEXT")
    except sqlite3.OperationalError:
        pass

    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_sessions_share_token ON chat_sessions(share_token)")

    conn.commit()
    conn.close()
    print("Database initialized.")


# ---- User Operations ----

def create_user(name, email, password_hash):
    """Create a new user. Returns user dict or None if email exists."""
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash)
        )
        conn.commit()
        user = conn.execute(
            "SELECT id, name, email, created_at FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        return dict(user)
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_email(email):
    """Get user by email. Returns dict with password_hash."""
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    """Get user by ID (without password)."""
    conn = get_db()
    user = conn.execute(
        "SELECT id, name, email, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_with_password(user_id):
    """Get user by ID with password_hash (internal use only)."""
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def update_user_password(user_id, new_password_hash):
    """Update user's password."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (new_password_hash, user_id)
    )
    conn.commit()
    conn.close()


# ---- Chat Session Operations ----

def create_chat_session(user_id, title="New Chat"):
    """Create a new chat session."""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
        (user_id, title)
    )
    session_id = cursor.lastrowid
    conn.commit()
    session = conn.execute(
        "SELECT * FROM chat_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()
    conn.close()
    result = dict(session)
    result["messages"] = json.loads(result["messages"])
    return result


def get_user_sessions(user_id):
    """Get all chat sessions for a user, ordered by most recent."""
    conn = get_db()
    sessions = conn.execute(
        "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(s) for s in sessions]


def get_session(session_id, user_id):
    """Get a specific chat session (with ownership check)."""
    conn = get_db()
    session = conn.execute(
        "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id)
    ).fetchone()
    conn.close()
    if session:
        result = dict(session)
        result["messages"] = json.loads(result["messages"])
        return result
    return None


def update_session(session_id, user_id, title=None, messages=None):
    """Update a chat session's title and/or messages."""
    conn = get_db()
    now = datetime.utcnow().isoformat()

    if title is not None and messages is not None:
        conn.execute(
            "UPDATE chat_sessions SET title = ?, messages = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (title, json.dumps(messages), now, session_id, user_id)
        )
    elif title is not None:
        conn.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (title, now, session_id, user_id)
        )
    elif messages is not None:
        conn.execute(
            "UPDATE chat_sessions SET messages = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(messages), now, session_id, user_id)
        )

    conn.commit()
    conn.close()


def delete_session(session_id, user_id):
    """Delete a chat session (with ownership check)."""
    conn = get_db()
    conn.execute(
        "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id)
    )
    conn.commit()
    conn.close()


def create_or_get_share_token(session_id, user_id):
    """Generate or retrieve unique share token for a chat session."""
    conn = get_db()
    session = conn.execute(
        "SELECT share_token FROM chat_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id)
    ).fetchone()
    if not session:
        conn.close()
        return None

    token = session["share_token"]
    if not token:
        token = secrets.token_urlsafe(12)
        conn.execute(
            "UPDATE chat_sessions SET share_token = ? WHERE id = ?",
            (token, session_id)
        )
        conn.commit()
    conn.close()
    return token


def get_shared_session_by_token(share_token):
    """Retrieve shared session by share_token without auth requirement."""
    conn = get_db()
    session = conn.execute("""
        SELECT s.id, s.title, s.messages, s.created_at, u.name as user_name
        FROM chat_sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.share_token = ?
    """, (share_token,)).fetchone()
    conn.close()
    if session:
        res = dict(session)
        res["messages"] = json.loads(res["messages"])
        return res
    return None


# Initialize on import
init_db()
