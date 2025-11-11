#!/usr/bin/env python3
"""
Generate daily iMessage activity summary with Claude API analysis.

Runs automatically at 8:00 PM via launchd to create a markdown summary
of the day's message activity. Saves to ~/Documents/Daily_Summaries/
"""

import os
import sys
import logging
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from database import (
    get_db_connection,
    apple_to_unix,
    unix_to_apple,
    format_timestamp,
)

# Try to import Anthropic SDK
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logging.warning("Anthropic SDK not available. Install with: pip install anthropic")

# Configuration
SUMMARY_DIR = os.path.expanduser("~/Documents/Daily_Summaries")
LOG_DIR = os.path.expanduser("~/Documents/Daily_Summaries/logs")
LOG_FILE = os.path.join(LOG_DIR, "daily_summary.log")

# API Configuration
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Summary settings
MIN_MESSAGES_TO_INCLUDE = 2
MAX_MESSAGES_TO_ANALYZE = 500  # Limit for API


def setup_logging():
    """Configure logging to file and console."""
    # Create log directory if it doesn't exist
    os.makedirs(LOG_DIR, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )


def ensure_summary_directory():
    """Create summary directory if it doesn't exist."""
    os.makedirs(SUMMARY_DIR, exist_ok=True)
    logging.info(f"Summary directory: {SUMMARY_DIR}")


def format_contact_name(contact_id: str) -> str:
    """Format contact identifier for display."""
    # Remove country code for US numbers
    if contact_id.startswith('+1'):
        formatted = contact_id[2:]
        # Format as (XXX) XXX-XXXX
        if len(formatted) == 10:
            return f"({formatted[:3]}) {formatted[3:6]}-{formatted[6:]}"
    return contact_id


def get_messages_for_date(date_str: str, conn: sqlite3.Connection) -> List[Dict]:
    """
    Get ALL messages for a specific date with full text.

    Args:
        date_str: Date in YYYY-MM-DD format
        conn: Database connection

    Returns:
        List of message dictionaries with contact, time, sender, and text
    """
    # Ensure row factory is set for dict-like column access
    conn.row_factory = sqlite3.Row

    # Create datetime strings for start and end of day
    start_datetime = f"{date_str} 00:00:00"
    end_datetime = f"{date_str} 23:59:59"

    logging.info(f"Querying messages for {date_str} ({start_datetime} to {end_datetime})")

    cursor = conn.cursor()

    # Query all messages for the date with contact information
    # Use SQLite's datetime conversion directly on Apple epoch timestamps
    # Apple epoch: nanoseconds since 2001-01-01
    # Conversion: date/1000000000 (to seconds) + Unix timestamp of 2001-01-01
    cursor.execute("""
        SELECT
            m.ROWID,
            m.text,
            m.date,
            m.is_from_me,
            h.id as contact_id,
            c.chat_identifier
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
        LEFT JOIN chat c ON cmj.chat_id = c.ROWID
        WHERE datetime(m.date/1000000000 + strftime('%s', '2001-01-01'), 'unixepoch')
            BETWEEN ? AND ?
            AND m.text IS NOT NULL
            AND m.text != ''
        ORDER BY m.date ASC
        LIMIT ?
    """, (start_datetime, end_datetime, MAX_MESSAGES_TO_ANALYZE))

    rows = cursor.fetchall()
    logging.info(f"Found {len(rows)} messages for {date_str}")

    # Format messages
    messages = []
    for row in rows:
        unix_time = apple_to_unix(row['date'])
        contact = row['contact_id'] or row['chat_identifier'] or "Unknown"

        messages.append({
            "timestamp": format_timestamp(unix_time),
            "time": datetime.fromtimestamp(unix_time).strftime('%H:%M'),
            "contact": contact,
            "sender": "You" if row['is_from_me'] else contact,
            "text": row['text'],
            "is_from_me": bool(row['is_from_me'])
        })

    return messages


def group_messages_by_contact(messages: List[Dict]) -> Dict[str, List[Dict]]:
    """Group messages by contact."""
    grouped = {}
    for msg in messages:
        contact = msg['contact']
        if contact not in grouped:
            grouped[contact] = []
        grouped[contact].append(msg)
    return grouped


def generate_basic_summary(date_str: str, messages: List[Dict], grouped: Dict[str, List[Dict]]) -> str:
    """
    Generate basic summary without Claude API (fallback).

    Args:
        date_str: Date string
        messages: All messages
        grouped: Messages grouped by contact

    Returns:
        Markdown summary
    """
    lines = []
    lines.append(f"# Daily Communication Summary")
    lines.append(f"**Date:** {date_str}")
    lines.append(f"**Generated:** {datetime.now().strftime('%I:%M %p')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    if not messages:
        lines.append("*No message activity today.*")
        lines.append("")
        return "\n".join(lines)

    # Summary statistics
    lines.append("## 📊 Summary Statistics")
    lines.append("")
    lines.append(f"- **Total Messages:** {len(messages)}")
    lines.append(f"- **Total Conversations:** {len(grouped)}")
    lines.append("")

    # Most active conversations
    lines.append("## 💬 Most Active Conversations")
    lines.append("")

    # Sort by message count
    sorted_contacts = sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)

    for contact, contact_messages in sorted_contacts[:10]:
        contact_display = format_contact_name(contact)
        msg_count = len(contact_messages)

        lines.append(f"**{contact_display} ({msg_count} messages)**")
        lines.append("")

        # Show recent messages
        for msg in contact_messages[-5:]:
            sender = "You" if msg['is_from_me'] else contact_display.split()[0]
            text = msg['text'][:100] + ("..." if len(msg['text']) > 100 else "")
            lines.append(f"- **{msg['time']}** - {sender}: {text}")

        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Generated by iMessage MCP Server - Phase 2A (Basic Mode)*")
    lines.append("")

    return "\n".join(lines)


def analyze_with_claude(date_str: str, messages: List[Dict], grouped: Dict[str, List[Dict]]) -> str:
    """
    Use Claude API to analyze messages and generate structured summary.

    Args:
        date_str: Date string
        messages: All messages
        grouped: Messages grouped by contact

    Returns:
        Claude-generated markdown summary
    """
    if not ANTHROPIC_AVAILABLE:
        logging.warning("Anthropic SDK not available, using basic summary")
        return generate_basic_summary(date_str, messages, grouped)

    if not ANTHROPIC_API_KEY:
        logging.warning("ANTHROPIC_API_KEY not set, using basic summary")
        return generate_basic_summary(date_str, messages, grouped)

    try:
        # Prepare conversation data for Claude
        conversations = []
        for contact, contact_messages in grouped.items():
            conversations.append({
                "contact": format_contact_name(contact),
                "message_count": len(contact_messages),
                "messages": [
                    {
                        "time": msg['time'],
                        "sender": "You" if msg['is_from_me'] else "Them",
                        "text": msg['text']
                    }
                    for msg in contact_messages
                ]
            })

        # Sort by message count
        conversations.sort(key=lambda x: x['message_count'], reverse=True)

        # Create prompt for Claude
        prompt = f"""Analyze these iMessage conversations from {date_str} and generate a structured daily summary.

CONTEXT:
- User is a busy CFO running a 75-property real estate business
- Focus on actionable information
- Be concise and prioritize business-critical items

CONVERSATIONS:
{json.dumps(conversations, indent=2)}

Generate a markdown summary with these sections:

## 📊 Most Active Conversations
List top 5-10 contacts with:
- Message count
- Brief topic summary (what was discussed?)
- Key points (1-3 bullets)

## 💬 Key Topics Discussed
Main themes across ALL conversations (3-5 bullet points)

## ✅ Decisions Made
Any approvals, commitments, conclusions made today. If none, say "None recorded."

## ⏳ Pending Decisions
Anything awaiting response or action. If none, say "None identified."

## 🚨 Urgent Items
Messages marked urgent/ASAP or critical issues. If none, say "No urgent items."

## 📋 Follow-ups Needed
Unanswered questions or pending responses. If none, say "None."

IMPORTANT:
- Keep it concise - this is an 8 PM daily summary for quick review
- Focus on business-relevant items
- If a section has nothing, say so briefly
- Don't include timestamps in the summary (already have them in raw data)
- Use natural language, not formal business-speak

Start with:
# Daily Communication Summary
**Date:** {date_str}
**Generated:** {datetime.now().strftime('%I:%M %p')}

---
"""

        # Call Claude API
        logging.info("Calling Claude API for message analysis...")
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract summary from response
        summary = message.content[0].text

        # Add footer
        summary += "\n\n---\n\n"
        summary += "*Generated by iMessage MCP Server - Phase 2A (Claude Analysis)*\n"

        logging.info("Claude API analysis completed successfully")
        return summary

    except Exception as e:
        logging.error(f"Error calling Claude API: {e}", exc_info=True)
        logging.warning("Falling back to basic summary")
        return generate_basic_summary(date_str, messages, grouped)


def generate_summary_markdown(date_str: str) -> str:
    """
    Generate markdown summary for the given date.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Markdown-formatted summary string
    """
    logging.info(f"Generating summary for {date_str}")

    try:
        # Get database connection
        conn = get_db_connection()

        # Get all messages for the date
        messages = get_messages_for_date(date_str, conn)

        # Close connection
        conn.close()

        if not messages:
            logging.info("No messages found for this date")
            return f"""# Daily Communication Summary
**Date:** {date_str}
**Generated:** {datetime.now().strftime('%I:%M %p')}

---

*No message activity today.*

---

*Generated by iMessage MCP Server - Phase 2A*
"""

        # Group messages by contact
        grouped = group_messages_by_contact(messages)

        logging.info(f"Found {len(messages)} messages across {len(grouped)} conversations")

        # Use Claude API to analyze (or fallback to basic summary)
        summary = analyze_with_claude(date_str, messages, grouped)

        return summary

    except FileNotFoundError as e:
        logging.error(f"Database not found: {e}")
        return f"""# Daily Communication Summary
**Date:** {date_str}

---

## ⚠️ Error

Could not access iMessage database. Make sure:
- You're running on macOS
- Messages app is installed
- Full Disk Access is granted

---
"""

    except PermissionError as e:
        logging.error(f"Permission denied: {e}")
        return f"""# Daily Communication Summary
**Date:** {date_str}

---

## ⚠️ Error

Permission denied accessing iMessage database.

Grant Full Disk Access:
1. System Preferences > Privacy & Security > Full Disk Access
2. Add Python or Terminal
3. Restart Terminal

---
"""

    except Exception as e:
        logging.error(f"Unexpected error generating summary: {e}", exc_info=True)
        return f"""# Daily Communication Summary
**Date:** {date_str}

---

## ⚠️ Error

An unexpected error occurred: {str(e)}

Check the log file for details: `{LOG_FILE}`

---
"""


def save_summary(date_str: str, content: str) -> str:
    """
    Save summary to file.

    Args:
        date_str: Date in YYYY-MM-DD format
        content: Markdown content to save

    Returns:
        Path to saved file
    """
    filename = f"{date_str}.md"
    filepath = os.path.join(SUMMARY_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    logging.info(f"Summary saved to: {filepath}")
    return filepath


def main():
    """Main entry point."""
    setup_logging()

    logging.info("=" * 60)
    logging.info("Starting daily summary generation")
    logging.info("=" * 60)

    try:
        # Check for API key
        if ANTHROPIC_AVAILABLE and not ANTHROPIC_API_KEY:
            logging.warning("ANTHROPIC_API_KEY environment variable not set")
            logging.warning("Using basic summary mode (no Claude analysis)")

        # Ensure output directory exists
        ensure_summary_directory()

        # Get today's date
        today = datetime.now().strftime('%Y-%m-%d')
        logging.info(f"Generating summary for: {today}")

        # Generate summary
        summary_content = generate_summary_markdown(today)

        # Save to file
        filepath = save_summary(today, summary_content)

        # Success
        logging.info("=" * 60)
        logging.info(f"✓ Summary generated successfully: {filepath}")
        logging.info("=" * 60)

        return 0

    except Exception as e:
        logging.error("=" * 60)
        logging.error(f"✗ Failed to generate summary: {e}", exc_info=True)
        logging.error("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
