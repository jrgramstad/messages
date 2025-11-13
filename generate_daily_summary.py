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


def extract_text_from_attributed_body(attributed_body: bytes) -> Optional[str]:
    """
    Extract plain text from iMessage attributedBody binary blob.

    The attributedBody is an NSAttributedString stored as a binary plist.
    We use a simple heuristic to extract readable text from it.

    Args:
        attributed_body: Binary blob from message.attributedBody column

    Returns:
        Extracted text string or None if unable to extract
    """
    if not attributed_body:
        return None

    try:
        # The attributedBody contains UTF-8 text interspersed with binary data
        # Simple approach: split by null bytes and extract printable UTF-8 strings
        text_parts = []

        for chunk in attributed_body.split(b'\x00'):
            try:
                # Try to decode as UTF-8
                decoded = chunk.decode('utf-8', errors='ignore').strip()
                # Keep strings that are at least 2 chars and mostly printable
                if len(decoded) >= 2 and sum(c.isprintable() or c.isspace() for c in decoded) / len(decoded) > 0.8:
                    text_parts.append(decoded)
            except:
                continue

        if text_parts:
            # Join parts and clean up
            text = ' '.join(text_parts)
            # Remove common binary artifacts
            text = text.replace('NSNumber', '').replace('NSString', '').replace('NSDictionary', '')
            text = text.replace('__kIMMessagePartAttributeName', '')
            text = ' '.join(text.split())  # Normalize whitespace

            # Return if we got something meaningful
            if len(text) >= 2:
                return text

        return None

    except Exception as e:
        logging.debug(f"Failed to extract text from attributedBody: {e}")
        return None


def get_messages_for_date(date_str: str, conn: sqlite3.Connection) -> List[Dict]:
    """
    Get ALL messages for a specific date with full text.

    Uses direct SQLite datetime conversion on Apple epoch timestamps
    to find all messages for the specified date.

    Args:
        date_str: Date in YYYY-MM-DD format
        conn: Database connection

    Returns:
        List of message dictionaries with contact, time, sender, and text
    """
    # Ensure row factory is set for dict-like column access
    conn.row_factory = sqlite3.Row

    logging.info(f"Querying messages for {date_str}")

    cursor = conn.cursor()

    # Query messages directly from message table
    # Use SQLite's date() function to extract just the date part in local timezone
    # This avoids timezone/DST issues with BETWEEN comparisons
    # Apple timestamps: nanoseconds since 2001-01-01, convert to Unix epoch seconds
    # NOTE: attributedBody contains text for newer macOS versions
    cursor.execute("""
        SELECT
            m.ROWID,
            m.text,
            m.attributedBody,
            m.date,
            m.is_from_me,
            h.id as contact_id
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        WHERE date(datetime(m.date/1000000000 + strftime('%s', '2001-01-01'), 'unixepoch', 'localtime')) = ?
        ORDER BY m.date ASC
        LIMIT ?
    """, (date_str, MAX_MESSAGES_TO_ANALYZE))

    rows = cursor.fetchall()
    logging.info(f"Found {len(rows)} messages for {date_str}")

    # Format messages
    messages = []
    for row in rows:
        unix_time = apple_to_unix(row['date'])
        contact = row['contact_id'] or "Unknown"

        # Extract text from either text column or attributedBody
        # Newer macOS versions store text in attributedBody as binary blob
        text = None

        # Try text column first (older format)
        if row['text'] and row['text'].strip():
            text = row['text'].strip()

        # If no text, try attributedBody (newer format)
        if not text and row['attributedBody']:
            text = extract_text_from_attributed_body(row['attributedBody'])

        # If still no text, mark as media/attachment
        if not text:
            text = "[media/attachment]"

        messages.append({
            "timestamp": format_timestamp(unix_time),
            "time": datetime.fromtimestamp(unix_time).strftime('%H:%M'),
            "contact": contact,
            "sender": "You" if row['is_from_me'] else contact,
            "text": text,
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
    Save summary to file with -summary suffix.

    Args:
        date_str: Date in YYYY-MM-DD format
        content: Markdown content to save

    Returns:
        Path to saved file
    """
    filename = f"{date_str}-summary.md"
    filepath = os.path.join(SUMMARY_DIR, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    logging.info(f"Summary saved to: {filepath}")
    return filepath


def save_raw_context(messages: List[Dict], grouped: Dict[str, List[Dict]], date_str: str) -> str:
    """
    Save raw message context with actual message text.

    Args:
        messages: List of all messages for the date
        grouped: Messages grouped by contact
        date_str: Date in YYYY-MM-DD format

    Returns:
        Path to saved file
    """
    try:
        # Sort contacts by message count (most active first)
        sorted_contacts = sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True)

        # Build markdown content
        lines = []
        lines.append(f"# Daily Message Context - Raw Data")
        lines.append(f"**Date:** {date_str}")
        lines.append(f"**Generated:** {datetime.now().strftime('%I:%M %p')}")
        lines.append(f"**Total Messages:** {len(messages)}")
        lines.append(f"**Conversations:** {len(grouped)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Add each conversation
        for idx, (contact, contact_messages) in enumerate(sorted_contacts, 1):
            contact_display = format_contact_name(contact)
            msg_count = len(contact_messages)

            # Get time range
            first_time = contact_messages[0]['time']
            last_time = contact_messages[-1]['time']

            lines.append(f"## CONVERSATION {idx}: {contact_display}")
            lines.append(f"**Messages:** {msg_count} | **Time Range:** {first_time} - {last_time}")
            lines.append("")
            lines.append("### Message Thread:")
            lines.append("")

            # Add each message
            for msg in contact_messages:
                time = msg['time']
                sender = "You" if msg['is_from_me'] else contact_display
                text = msg['text']

                lines.append(f"**[{time}] {sender}:**")
                lines.append(f"> {text}")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Add metadata section
        lines.append("## METADATA")
        lines.append("")

        # Calculate time-based statistics
        morning_count = sum(1 for m in messages if 6 <= int(m['time'].split(':')[0]) < 9)
        midday_count = sum(1 for m in messages if 9 <= int(m['time'].split(':')[0]) < 15)
        evening_count = sum(1 for m in messages if 15 <= int(m['time'].split(':')[0]) < 21)
        late_count = sum(1 for m in messages if int(m['time'].split(':')[0]) >= 21 or int(m['time'].split(':')[0]) < 6)

        lines.append("**Busiest Times:**")
        lines.append(f"- Morning (6-9 AM): {morning_count} messages")
        lines.append(f"- Midday (9 AM-3 PM): {midday_count} messages")
        lines.append(f"- Evening (3-9 PM): {evening_count} messages")
        lines.append(f"- Late (9 PM+): {late_count} messages")
        lines.append("")

        # Message direction breakdown
        from_you = sum(1 for m in messages if m['is_from_me'])
        from_others = len(messages) - from_you

        lines.append("**Message Breakdown:**")
        lines.append(f"- From You: {from_you} messages")
        lines.append(f"- From Others: {from_others} messages")
        lines.append(f"- Total: {len(messages)} messages")
        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("*Raw context file generated for executive analysis*")
        lines.append(f"*Companion summary: {date_str}-summary.md*")
        lines.append("")

        # Save to file
        filename = f"{date_str}-raw.md"
        filepath = os.path.join(SUMMARY_DIR, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

        logging.info(f"Raw context saved to: {filepath}")
        return filepath

    except Exception as e:
        logging.error(f"Error saving raw context: {e}", exc_info=True)
        # Don't fail if raw context save fails - summary is more important
        return None


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

        # Get date from command line argument or use today
        if len(sys.argv) > 1:
            target_date = sys.argv[1]
            # Validate date format
            try:
                datetime.strptime(target_date, '%Y-%m-%d')
            except ValueError:
                logging.error(f"Invalid date format: {target_date}")
                logging.error("Use format: YYYY-MM-DD")
                return 1
        else:
            target_date = datetime.now().strftime('%Y-%m-%d')

        logging.info(f"Generating summaries for: {target_date}")

        # Get database connection
        conn = get_db_connection()

        # Get all messages for the date
        messages = get_messages_for_date(target_date, conn)

        # Close connection
        conn.close()

        if not messages:
            logging.info("No messages found for this date")
            # Create empty summary
            summary_content = f"""# Daily Communication Summary
**Date:** {target_date}
**Generated:** {datetime.now().strftime('%I:%M %p')}

---

*No message activity today.*

---

*Generated by iMessage MCP Server - Phase 2A*
"""
            filepath = save_summary(target_date, summary_content)
            logging.info(f"✓ Summary generated: {filepath}")
            return 0

        # Group messages by contact
        grouped = group_messages_by_contact(messages)

        logging.info(f"Found {len(messages)} messages across {len(grouped)} conversations")

        # Generate Claude-analyzed summary
        summary_content = analyze_with_claude(target_date, messages, grouped)

        # Save both files
        summary_path = save_summary(target_date, summary_content)
        raw_path = save_raw_context(messages, grouped, target_date)

        # Success
        logging.info("=" * 60)
        logging.info(f"✓ Summary saved: {summary_path}")
        if raw_path:
            logging.info(f"✓ Raw context saved: {raw_path}")
        logging.info("=" * 60)

        return 0

    except Exception as e:
        logging.error("=" * 60)
        logging.error(f"✗ Failed to generate summary: {e}", exc_info=True)
        logging.error("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
