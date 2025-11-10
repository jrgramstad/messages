#!/usr/bin/env python3
"""
Generate daily iMessage activity summary.

Runs automatically at 8:00 PM via launchd to create a markdown summary
of the day's message activity. Saves to ~/Documents/Daily_Summaries/
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from database import (
    get_threads_for_date,
    get_active_contacts,
    get_messages_by_contact,
    get_db_connection
)

# Configuration
SUMMARY_DIR = os.path.expanduser("~/Documents/Daily_Summaries")
LOG_DIR = os.path.expanduser("~/Documents/Daily_Summaries/logs")
LOG_FILE = os.path.join(LOG_DIR, "daily_summary.log")

# Summary settings
MIN_MESSAGES_TO_INCLUDE = 2
TOP_CONTACTS_COUNT = 10
RECENT_MESSAGES_PER_CONTACT = 5


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


def generate_summary_markdown(date_str: str) -> str:
    """
    Generate markdown summary for the given date.

    Args:
        date_str: Date in YYYY-MM-DD format

    Returns:
        Markdown-formatted summary string
    """
    logging.info(f"Generating summary for {date_str}")

    # Start markdown document
    lines = []
    lines.append(f"# iMessage Daily Summary - {date_str}")
    lines.append("")
    lines.append(f"*Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    try:
        # Get database connection
        conn = get_db_connection()

        # Get threads for the day
        threads_data = get_threads_for_date(date_str, exclude_group_chats=False, conn=conn)

        # Check if there are any messages
        total_messages = threads_data.get('total_messages', 0)
        total_threads = threads_data.get('total_threads', 0)

        # Summary statistics
        lines.append("## 📊 Summary Statistics")
        lines.append("")
        lines.append(f"- **Total Conversations:** {total_threads}")
        lines.append(f"- **Total Messages:** {total_messages}")
        lines.append("")

        if total_messages == 0:
            lines.append("*No message activity today.*")
            lines.append("")
            return "\n".join(lines)

        # Active conversations
        lines.append("## 💬 Active Conversations")
        lines.append("")

        threads = threads_data.get('threads', [])
        if threads:
            lines.append("| Contact | Messages | Last Activity |")
            lines.append("|---------|----------|---------------|")

            for thread in threads[:TOP_CONTACTS_COUNT]:
                contact = format_contact_name(thread['contact'])
                msg_count = thread['message_count']
                last_time = thread['last_timestamp'].split()[1]  # Just the time
                lines.append(f"| {contact} | {msg_count} | {last_time} |")

            lines.append("")
        else:
            lines.append("*No conversations found.*")
            lines.append("")

        # Detailed thread summaries for top contacts
        lines.append("## 📝 Conversation Details")
        lines.append("")

        # Get top 5 most active threads
        top_threads = [t for t in threads if t['message_count'] >= MIN_MESSAGES_TO_INCLUDE][:5]

        if top_threads:
            for thread in top_threads:
                contact_id = thread['contact']
                contact_display = format_contact_name(contact_id)
                msg_count = thread['message_count']

                lines.append(f"### {contact_display} ({msg_count} messages)")
                lines.append("")

                # Get recent messages for this contact
                try:
                    messages_data = get_messages_by_contact(
                        contact_id,
                        days_back=1,
                        limit=RECENT_MESSAGES_PER_CONTACT,
                        conn=conn
                    )

                    messages = messages_data.get('messages', [])
                    if messages:
                        # Show last few messages
                        for msg in messages[-RECENT_MESSAGES_PER_CONTACT:]:
                            time = msg['timestamp'].split()[1]  # Just the time
                            sender = "You" if msg['is_from_me'] else contact_display.split()[0]
                            text = msg['text']

                            # Truncate long messages
                            if len(text) > 100:
                                text = text[:97] + "..."

                            lines.append(f"- **{time}** - {sender}: {text}")

                        lines.append("")
                    else:
                        lines.append("*No messages available.*")
                        lines.append("")

                except Exception as e:
                    logging.warning(f"Could not get messages for {contact_id}: {e}")
                    lines.append("*Could not retrieve messages.*")
                    lines.append("")

        else:
            lines.append("*No significant conversations today.*")
            lines.append("")

        # Activity timeline
        lines.append("## ⏰ Activity Timeline")
        lines.append("")

        # Group messages by hour
        hour_counts = {}
        for thread in threads:
            try:
                timestamp = thread['last_timestamp']
                hour = int(timestamp.split()[1].split(':')[0])  # Extract hour
                hour_counts[hour] = hour_counts.get(hour, 0) + thread['message_count']
            except (ValueError, IndexError):
                continue

        if hour_counts:
            # Create a simple bar chart
            max_count = max(hour_counts.values())
            for hour in sorted(hour_counts.keys()):
                count = hour_counts[hour]
                bar_length = int((count / max_count) * 20)  # Scale to 20 chars max
                bar = '█' * bar_length
                time_str = f"{hour:02d}:00"
                lines.append(f"{time_str} | {bar} ({count} messages)")

            lines.append("")
        else:
            lines.append("*No timeline data available.*")
            lines.append("")

        # Quick insights
        lines.append("## 💡 Quick Insights")
        lines.append("")

        if threads:
            most_active = threads[0]
            most_active_name = format_contact_name(most_active['contact'])
            most_active_count = most_active['message_count']
            lines.append(f"- **Most Active:** {most_active_name} ({most_active_count} messages)")

            # Calculate message velocity (messages per conversation)
            avg_messages = total_messages / total_threads if total_threads > 0 else 0
            lines.append(f"- **Average Messages per Conversation:** {avg_messages:.1f}")

            # Peak hour
            if hour_counts:
                peak_hour = max(hour_counts.items(), key=lambda x: x[1])
                lines.append(f"- **Peak Activity Hour:** {peak_hour[0]:02d}:00 ({peak_hour[1]} messages)")

            lines.append("")

        conn.close()

    except FileNotFoundError as e:
        logging.error(f"Database not found: {e}")
        lines.append("## ⚠️ Error")
        lines.append("")
        lines.append("Could not access iMessage database. Make sure:")
        lines.append("- You're running on macOS")
        lines.append("- Messages app is installed")
        lines.append("- Full Disk Access is granted")
        lines.append("")

    except PermissionError as e:
        logging.error(f"Permission denied: {e}")
        lines.append("## ⚠️ Error")
        lines.append("")
        lines.append("Permission denied accessing iMessage database.")
        lines.append("")
        lines.append("Grant Full Disk Access:")
        lines.append("1. System Preferences > Privacy & Security > Full Disk Access")
        lines.append("2. Add Python or Terminal")
        lines.append("3. Restart Terminal")
        lines.append("")

    except Exception as e:
        logging.error(f"Unexpected error generating summary: {e}", exc_info=True)
        lines.append("## ⚠️ Error")
        lines.append("")
        lines.append(f"An unexpected error occurred: {str(e)}")
        lines.append("")
        lines.append("Check the log file for details:")
        lines.append(f"`{LOG_FILE}`")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append("*Generated by iMessage MCP Server - Phase 2A*")
    lines.append("")

    return "\n".join(lines)


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
