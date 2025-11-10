"""Configuration settings for iMessage MCP Server."""

import os
from pathlib import Path

# Database path (macOS default location)
DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")

# Default query parameters
DEFAULT_DAYS_BACK = 3
DEFAULT_SEARCH_DAYS = 7
DEFAULT_MESSAGE_LIMIT = 50
MAX_MESSAGES = 100

# Apple epoch offset (seconds between 2001-01-01 and 1970-01-01)
APPLE_EPOCH_OFFSET = 978307200

# Contact matching settings
FUZZY_MATCH_THRESHOLD = 0.6

# Logging
LOG_LEVEL = "INFO"
