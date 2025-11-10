#!/usr/bin/env python3
"""iMessage MCP Server - Provides Claude access to iMessage database."""

import logging
from typing import Optional

from fastmcp import FastMCP

from database import (
    get_messages_by_contact,
    search_messages_by_keyword,
    get_threads_for_date,
    get_active_contacts,
    get_thread_summary,
)
from config import (
    DEFAULT_DAYS_BACK,
    DEFAULT_SEARCH_DAYS,
    DEFAULT_MESSAGE_LIMIT,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("imessage-server")


@mcp.tool()
def get_recent_messages(
    contact: str,
    days_back: int = DEFAULT_DAYS_BACK,
    limit: int = DEFAULT_MESSAGE_LIMIT
) -> dict:
    """
    Get recent message thread with a specific contact.

    Args:
        contact: Name, phone number, or email of the contact
        days_back: Number of days of message history to retrieve (default: 3)
        limit: Maximum number of messages to return (default: 50, max: 100)

    Returns:
        Dictionary containing:
        - contact: Contact identifier
        - phone: Phone number or email
        - messages: List of messages with timestamp, sender, text, and direction
        - message_count: Total number of messages
        - date_range: Date range of messages
    """
    logger.info(f"get_recent_messages called for contact: {contact}, days_back: {days_back}, limit: {limit}")

    try:
        result = get_messages_by_contact(
            contact=contact,
            days_back=days_back,
            limit=limit
        )
        logger.info(f"Retrieved {result['message_count']} messages for {contact}")
        return result

    except FileNotFoundError as e:
        logger.error(f"Database not found: {e}")
        return {
            "error": str(e),
            "contact": contact,
            "messages": [],
            "message_count": 0
        }

    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        return {
            "error": str(e),
            "contact": contact,
            "messages": [],
            "message_count": 0
        }

    except Exception as e:
        logger.error(f"Unexpected error in get_recent_messages: {e}", exc_info=True)
        return {
            "error": f"Unexpected error: {str(e)}",
            "contact": contact,
            "messages": [],
            "message_count": 0
        }


@mcp.tool()
def search_messages(
    keyword: str,
    days_back: int = DEFAULT_SEARCH_DAYS,
    limit: int = 20
) -> dict:
    """
    Search all messages for a keyword or phrase.

    Args:
        keyword: The search term to look for in message content
        days_back: Number of days to search back (default: 7)
        limit: Maximum number of results to return (default: 20, max: 100)

    Returns:
        Dictionary containing:
        - keyword: The search term used
        - results: List of matching messages with contact, timestamp, and text
        - result_count: Total number of matches found
    """
    logger.info(f"search_messages called for keyword: '{keyword}', days_back: {days_back}, limit: {limit}")

    try:
        result = search_messages_by_keyword(
            keyword=keyword,
            days_back=days_back,
            limit=limit
        )
        logger.info(f"Found {result['result_count']} messages matching '{keyword}'")
        return result

    except FileNotFoundError as e:
        logger.error(f"Database not found: {e}")
        return {
            "error": str(e),
            "keyword": keyword,
            "results": [],
            "result_count": 0
        }

    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        return {
            "error": str(e),
            "keyword": keyword,
            "results": [],
            "result_count": 0
        }

    except Exception as e:
        logger.error(f"Unexpected error in search_messages: {e}", exc_info=True)
        return {
            "error": f"Unexpected error: {str(e)}",
            "keyword": keyword,
            "results": [],
            "result_count": 0
        }


@mcp.tool()
def get_threads_by_date(
    date: str,
    exclude_group_chats: bool = False
) -> dict:
    """
    Get all message activity for a specific date.

    Args:
        date: Date in YYYY-MM-DD format
        exclude_group_chats: If True, exclude group conversations (default: False)

    Returns:
        Dictionary containing:
        - date: The queried date
        - threads: List of active threads with message counts and last message
        - total_threads: Number of active threads
        - total_messages: Total messages across all threads
    """
    logger.info(f"get_threads_by_date called for date: {date}, exclude_group_chats: {exclude_group_chats}")

    try:
        result = get_threads_for_date(
            date=date,
            exclude_group_chats=exclude_group_chats
        )
        logger.info(f"Retrieved {result.get('total_threads', 0)} threads for {date}")
        return result

    except FileNotFoundError as e:
        logger.error(f"Database not found: {e}")
        return {
            "error": str(e),
            "date": date,
            "threads": [],
            "total_threads": 0,
            "total_messages": 0
        }

    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        return {
            "error": str(e),
            "date": date,
            "threads": [],
            "total_threads": 0,
            "total_messages": 0
        }

    except Exception as e:
        logger.error(f"Unexpected error in get_threads_by_date: {e}", exc_info=True)
        return {
            "error": f"Unexpected error: {str(e)}",
            "date": date,
            "threads": [],
            "total_threads": 0,
            "total_messages": 0
        }


@mcp.tool()
def list_active_contacts(
    days_back: int = DEFAULT_SEARCH_DAYS,
    min_messages: int = 3,
    limit: int = 20
) -> dict:
    """
    Show most active message contacts based on message frequency.

    Args:
        days_back: Time window in days to analyze (default: 7)
        min_messages: Minimum messages required to include a contact (default: 3)
        limit: Maximum number of contacts to return (default: 20)

    Returns:
        Dictionary containing:
        - timeframe: Description of the time period analyzed
        - contacts: List of contacts with message counts and last contact time
    """
    logger.info(f"list_active_contacts called, days_back: {days_back}, min_messages: {min_messages}, limit: {limit}")

    try:
        result = get_active_contacts(
            days_back=days_back,
            min_messages=min_messages,
            limit=limit
        )
        logger.info(f"Retrieved {len(result.get('contacts', []))} active contacts")
        return result

    except FileNotFoundError as e:
        logger.error(f"Database not found: {e}")
        return {
            "error": str(e),
            "timeframe": f"Last {days_back} days",
            "contacts": []
        }

    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        return {
            "error": str(e),
            "timeframe": f"Last {days_back} days",
            "contacts": []
        }

    except Exception as e:
        logger.error(f"Unexpected error in list_active_contacts: {e}", exc_info=True)
        return {
            "error": f"Unexpected error: {str(e)}",
            "timeframe": f"Last {days_back} days",
            "contacts": []
        }


@mcp.tool()
def get_thread_summary(
    contact: str,
    days_back: int = DEFAULT_SEARCH_DAYS,
    include_timestamps: bool = True
) -> dict:
    """
    Get a condensed summary of a message thread with daily breakdowns.

    Args:
        contact: Name, phone number, or email of the contact
        days_back: Number of days of history to summarize (default: 7)
        include_timestamps: Whether to include timestamps in results (default: True)

    Returns:
        Dictionary containing:
        - contact: Contact identifier
        - date_range: Range of dates covered
        - total_messages: Total message count
        - daily_breakdown: Messages grouped by day with first/last message
        - key_topics: List of frequently mentioned keywords
    """
    logger.info(f"get_thread_summary called for contact: {contact}, days_back: {days_back}")

    try:
        result = get_thread_summary(
            contact=contact,
            days_back=days_back,
            include_timestamps=include_timestamps
        )
        logger.info(f"Retrieved summary for {contact}: {result.get('total_messages', 0)} total messages")
        return result

    except FileNotFoundError as e:
        logger.error(f"Database not found: {e}")
        return {
            "error": str(e),
            "contact": contact,
            "date_range": None,
            "total_messages": 0,
            "daily_breakdown": [],
            "key_topics": []
        }

    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        return {
            "error": str(e),
            "contact": contact,
            "date_range": None,
            "total_messages": 0,
            "daily_breakdown": [],
            "key_topics": []
        }

    except Exception as e:
        logger.error(f"Unexpected error in get_thread_summary: {e}", exc_info=True)
        return {
            "error": f"Unexpected error: {str(e)}",
            "contact": contact,
            "date_range": None,
            "total_messages": 0,
            "daily_breakdown": [],
            "key_topics": []
        }


if __name__ == "__main__":
    logger.info("Starting iMessage MCP Server...")
    logger.info("Available tools:")
    logger.info("  - get_recent_messages: Get recent thread with a contact")
    logger.info("  - search_messages: Search all messages for keywords")
    logger.info("  - get_threads_by_date: Get message activity for a specific date")
    logger.info("  - list_active_contacts: Show most active contacts")
    logger.info("  - get_thread_summary: Get condensed thread summary with daily breakdowns")

    # Run the MCP server
    mcp.run()
