"""Database interaction functions for iMessage chat.db."""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from pathlib import Path

from config import DB_PATH, APPLE_EPOCH_OFFSET, MAX_MESSAGES

logger = logging.getLogger(__name__)


def apple_to_unix(apple_timestamp: int) -> float:
    """Convert Apple epoch (nanoseconds since 2001-01-01) to Unix timestamp."""
    if apple_timestamp == 0:
        return 0
    return (apple_timestamp / 1000000000) + APPLE_EPOCH_OFFSET


def unix_to_apple(unix_timestamp: float) -> int:
    """Convert Unix timestamp to Apple epoch (nanoseconds since 2001-01-01)."""
    return int((unix_timestamp - APPLE_EPOCH_OFFSET) * 1000000000)


def format_timestamp(unix_timestamp: float) -> str:
    """Format Unix timestamp as YYYY-MM-DD HH:MM:SS."""
    if unix_timestamp == 0:
        return "Unknown"
    return datetime.fromtimestamp(unix_timestamp).strftime('%Y-%m-%d %H:%M:%S')


def get_db_connection() -> sqlite3.Connection:
    """Create and return a read-only connection to the iMessage database."""
    if not Path(DB_PATH).exists():
        raise FileNotFoundError(
            f"iMessage database not found at {DB_PATH}. "
            "Make sure you're running on macOS with Messages enabled."
        )

    try:
        # Open in read-only mode with URI
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        raise PermissionError(
            f"Cannot access iMessage database: {e}. "
            "You may need to grant Full Disk Access to Terminal/Python in "
            "System Preferences > Privacy & Security > Full Disk Access"
        )


def find_contact_handle(contact_query: str, conn: sqlite3.Connection) -> Optional[Tuple[int, str]]:
    """
    Find a contact's handle_id and identifier from the database.

    Returns: (handle_id, identifier) or None if not found
    """
    cursor = conn.cursor()

    # Try exact match on phone/email first
    cursor.execute("""
        SELECT ROWID, id FROM handle
        WHERE id = ? OR id LIKE ?
    """, (contact_query, f"%{contact_query}%"))

    result = cursor.fetchone()
    if result:
        return (result[0], result[1])

    # Try partial match on any part of the identifier
    cursor.execute("""
        SELECT ROWID, id FROM handle
        WHERE id LIKE ?
        LIMIT 1
    """, (f"%{contact_query}%",))

    result = cursor.fetchone()
    if result:
        return (result[0], result[1])

    return None


def get_messages_by_contact(
    contact: str,
    days_back: int = 3,
    limit: int = 50,
    conn: Optional[sqlite3.Connection] = None
) -> Dict:
    """
    Get recent message thread with a specific contact.

    Args:
        contact: Name, phone number, or email
        days_back: Number of days of history to retrieve
        limit: Maximum number of messages to return
        conn: Database connection (creates new one if None)

    Returns:
        Dictionary with contact info and messages
    """
    should_close = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        # Find the contact
        handle_info = find_contact_handle(contact, conn)
        if not handle_info:
            return {
                "contact": contact,
                "phone": None,
                "messages": [],
                "message_count": 0,
                "date_range": None,
                "error": "Contact not found"
            }

        handle_id, contact_identifier = handle_info

        # Calculate date range
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cutoff_apple = unix_to_apple(cutoff_date.timestamp())

        # Query messages
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                m.ROWID,
                m.text,
                m.date,
                m.is_from_me,
                h.id as sender_id
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat_handle_join chj ON cmj.chat_id = chj.chat_id
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE chj.handle_id = ?
                AND m.date >= ?
            ORDER BY m.date DESC
            LIMIT ?
        """, (handle_id, cutoff_apple, min(limit, MAX_MESSAGES)))

        rows = cursor.fetchall()

        # Format messages
        messages = []
        for row in rows:
            unix_time = apple_to_unix(row['date'])
            messages.append({
                "timestamp": format_timestamp(unix_time),
                "sender": "JR" if row['is_from_me'] else contact.split()[0],
                "text": row['text'] or "[media/attachment]",
                "is_from_me": bool(row['is_from_me'])
            })

        # Reverse to show oldest first
        messages.reverse()

        # Get date range
        date_range = None
        if messages:
            first_date = messages[0]['timestamp'].split()[0]
            last_date = messages[-1]['timestamp'].split()[0]
            date_range = f"{first_date} to {last_date}" if first_date != last_date else first_date

        return {
            "contact": contact,
            "phone": contact_identifier,
            "messages": messages,
            "message_count": len(messages),
            "date_range": date_range
        }

    finally:
        if should_close:
            conn.close()


def search_messages_by_keyword(
    keyword: str,
    days_back: int = 7,
    limit: int = 20,
    conn: Optional[sqlite3.Connection] = None
) -> Dict:
    """
    Search all messages for a keyword.

    Args:
        keyword: Search term
        days_back: Time window in days
        limit: Maximum number of results
        conn: Database connection (creates new one if None)

    Returns:
        Dictionary with search results
    """
    should_close = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        # Calculate date range
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cutoff_apple = unix_to_apple(cutoff_date.timestamp())

        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                m.text,
                m.date,
                m.is_from_me,
                h.id as contact_id
            FROM message m
            LEFT JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.text LIKE ?
                AND m.date >= ?
            ORDER BY m.date DESC
            LIMIT ?
        """, (f"%{keyword}%", cutoff_apple, min(limit, MAX_MESSAGES)))

        rows = cursor.fetchall()

        # Format results
        results = []
        for row in rows:
            unix_time = apple_to_unix(row['date'])
            contact = "JR" if row['is_from_me'] else (row['contact_id'] or "Unknown")

            results.append({
                "contact": contact,
                "timestamp": format_timestamp(unix_time),
                "text": row['text'] or "[media/attachment]",
                "is_from_me": bool(row['is_from_me'])
            })

        return {
            "keyword": keyword,
            "results": results,
            "result_count": len(results)
        }

    finally:
        if should_close:
            conn.close()


def get_threads_for_date(
    date: str,
    exclude_group_chats: bool = False,
    conn: Optional[sqlite3.Connection] = None
) -> Dict:
    """
    Get all message activity for a specific date.

    Args:
        date: Date in YYYY-MM-DD format
        exclude_group_chats: Whether to exclude group conversations
        conn: Database connection (creates new one if None)

    Returns:
        Dictionary with thread activity for the date
    """
    should_close = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        # Parse date
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return {
                "date": date,
                "threads": [],
                "total_threads": 0,
                "total_messages": 0,
                "error": "Invalid date format. Use YYYY-MM-DD"
            }

        # Calculate date range (start and end of day)
        start_of_day = target_date.replace(hour=0, minute=0, second=0)
        end_of_day = target_date.replace(hour=23, minute=59, second=59)

        start_apple = unix_to_apple(start_of_day.timestamp())
        end_apple = unix_to_apple(end_of_day.timestamp())

        cursor = conn.cursor()

        # Get threads with message counts
        query = """
            SELECT
                h.id as contact_id,
                COUNT(m.ROWID) as msg_count,
                MAX(m.date) as last_date,
                (SELECT text FROM message m2
                 WHERE m2.ROWID = (SELECT message_id FROM chat_message_join
                                   WHERE chat_id = cmj.chat_id
                                   ORDER BY message_id DESC LIMIT 1)
                ) as last_text
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat_handle_join chj ON cmj.chat_id = chj.chat_id
            JOIN handle h ON chj.handle_id = h.ROWID
            WHERE m.date >= ? AND m.date <= ?
        """

        if exclude_group_chats:
            query += " AND (SELECT COUNT(*) FROM chat_handle_join WHERE chat_id = cmj.chat_id) = 1"

        query += """
            GROUP BY h.id
            ORDER BY msg_count DESC
        """

        cursor.execute(query, (start_apple, end_apple))
        rows = cursor.fetchall()

        # Format threads
        threads = []
        total_messages = 0

        for row in rows:
            unix_time = apple_to_unix(row['last_date'])
            threads.append({
                "contact": row['contact_id'],
                "message_count": row['msg_count'],
                "last_message": row['last_text'] or "[media/attachment]",
                "last_timestamp": format_timestamp(unix_time)
            })
            total_messages += row['msg_count']

        return {
            "date": date,
            "threads": threads,
            "total_threads": len(threads),
            "total_messages": total_messages
        }

    finally:
        if should_close:
            conn.close()


def get_active_contacts(
    days_back: int = 7,
    min_messages: int = 3,
    limit: int = 20,
    conn: Optional[sqlite3.Connection] = None
) -> Dict:
    """
    Get list of most active message contacts.

    Args:
        days_back: Time window in days
        min_messages: Minimum messages to include contact
        limit: Maximum number of contacts to return
        conn: Database connection (creates new one if None)

    Returns:
        Dictionary with active contacts
    """
    should_close = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        # Calculate date range
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cutoff_apple = unix_to_apple(cutoff_date.timestamp())

        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                h.id as contact_id,
                COUNT(m.ROWID) as msg_count,
                MAX(m.date) as last_date
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE m.date >= ?
            GROUP BY h.id
            HAVING msg_count >= ?
            ORDER BY msg_count DESC
            LIMIT ?
        """, (cutoff_apple, min_messages, min(limit, MAX_MESSAGES)))

        rows = cursor.fetchall()

        # Format contacts
        contacts = []
        for row in rows:
            unix_time = apple_to_unix(row['last_date'])
            contacts.append({
                "name": row['contact_id'],
                "phone": row['contact_id'],
                "message_count": row['msg_count'],
                "last_contact": format_timestamp(unix_time)
            })

        return {
            "timeframe": f"Last {days_back} days",
            "contacts": contacts
        }

    finally:
        if should_close:
            conn.close()


def get_thread_summary(
    contact: str,
    days_back: int = 7,
    include_timestamps: bool = True,
    conn: Optional[sqlite3.Connection] = None
) -> Dict:
    """
    Get condensed summary of a message thread.

    Args:
        contact: Contact name, phone number, or email
        days_back: Number of days of history
        include_timestamps: Whether to include timestamps
        conn: Database connection (creates new one if None)

    Returns:
        Dictionary with thread summary
    """
    should_close = conn is None
    if conn is None:
        conn = get_db_connection()

    try:
        # Find the contact
        handle_info = find_contact_handle(contact, conn)
        if not handle_info:
            return {
                "contact": contact,
                "date_range": None,
                "total_messages": 0,
                "daily_breakdown": [],
                "key_topics": [],
                "error": "Contact not found"
            }

        handle_id, contact_identifier = handle_info

        # Calculate date range
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cutoff_apple = unix_to_apple(cutoff_date.timestamp())

        # Get all messages
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                m.text,
                m.date,
                m.is_from_me
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat_handle_join chj ON cmj.chat_id = chj.chat_id
            WHERE chj.handle_id = ?
                AND m.date >= ?
            ORDER BY m.date ASC
        """, (handle_id, cutoff_apple))

        rows = cursor.fetchall()

        # Group by day
        daily_messages = {}
        for row in rows:
            unix_time = apple_to_unix(row['date'])
            date_str = datetime.fromtimestamp(unix_time).strftime('%Y-%m-%d')

            if date_str not in daily_messages:
                daily_messages[date_str] = []

            daily_messages[date_str].append({
                'text': row['text'] or "[media/attachment]",
                'timestamp': format_timestamp(unix_time) if include_timestamps else None,
                'is_from_me': bool(row['is_from_me'])
            })

        # Create daily breakdown
        daily_breakdown = []
        for date_str in sorted(daily_messages.keys()):
            msgs = daily_messages[date_str]
            daily_breakdown.append({
                "date": date_str,
                "count": len(msgs),
                "first_message": msgs[0]['text'][:100],
                "last_message": msgs[-1]['text'][:100]
            })

        # Calculate date range
        date_range = None
        if daily_breakdown:
            first_date = daily_breakdown[0]['date']
            last_date = daily_breakdown[-1]['date']
            date_range = f"{first_date} to {last_date}" if first_date != last_date else first_date

        # Simple keyword extraction for key topics (frequency-based)
        all_text = " ".join([row['text'] or "" for row in rows])
        words = all_text.lower().split()
        # Filter common words and get top words
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'can', 'may', 'might', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'this', 'that', 'these', 'those'}
        word_freq = {}
        for word in words:
            if word not in common_words and len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1

        # Get top 5 keywords
        key_topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        key_topics = [word for word, freq in key_topics]

        return {
            "contact": contact,
            "date_range": date_range,
            "total_messages": sum(len(msgs) for msgs in daily_messages.values()),
            "daily_breakdown": daily_breakdown,
            "key_topics": key_topics
        }

    finally:
        if should_close:
            conn.close()
