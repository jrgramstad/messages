# iMessage MCP Server - Phase 1

A Model Context Protocol (MCP) server that connects Claude to the macOS iMessage database, enabling real-time message thread queries without manual copy-paste.

## Overview

This MCP server provides Claude with access to your iMessage conversations through a set of query tools. Instead of manually copying message threads, you can ask Claude questions like:
- "What did Christian say today?"
- "Show me recent messages about funding"
- "Who did I message most this week?"

## Requirements

- **macOS** (Messages app with iMessage enabled)
- **Python 3.10+**
- **Full Disk Access** permission for Terminal/Python

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install FastMCP directly:

```bash
pip install fastmcp
```

### 2. Grant Full Disk Access

The iMessage database requires special permissions to access:

1. Open **System Preferences** (or **System Settings** on newer macOS)
2. Go to **Privacy & Security** > **Full Disk Access**
3. Click the lock to make changes (enter your password)
4. Click the **+** button
5. Add **Terminal** (or the Python executable you're using)
6. Restart Terminal

**Alternative:** If using a specific Python installation:
- Navigate to `/usr/local/bin/python3` (or your Python path)
- Add that executable to Full Disk Access

### 3. Verify Database Access

Check that the iMessage database exists:

```bash
ls -la ~/Library/Messages/chat.db
```

You should see the database file. If you get a permission error, Full Disk Access is not properly configured.

## Running the Server

### Standard Mode

Start the MCP server:

```bash
python server.py
```

You should see output like:

```
Starting iMessage MCP Server...
Available tools:
  - get_recent_messages: Get recent thread with a contact
  - search_messages: Search all messages for keywords
  - get_threads_by_date: Get message activity for a specific date
  - list_active_contacts: Show most active contacts
  - get_thread_summary: Get condensed thread summary with daily breakdowns
```

### Running as an MCP Server

To use with Claude Desktop or other MCP clients, configure your MCP settings to point to this server:

```json
{
  "mcpServers": {
    "imessage": {
      "command": "python",
      "args": ["/path/to/messages/server.py"]
    }
  }
}
```

Replace `/path/to/messages/` with the actual path to this repository.

## Available Tools

### 1. `get_recent_messages`

Get recent message thread with a specific contact.

**Parameters:**
- `contact` (required): Name, phone number, or email
- `days_back` (optional, default: 3): Days of history to retrieve
- `limit` (optional, default: 50): Maximum messages to return

**Example:**
```
Get recent messages from Christian, last 3 days
```

**Returns:**
```json
{
  "contact": "Christian Rojas",
  "phone": "+1-555-0123",
  "messages": [
    {
      "timestamp": "2025-10-28 09:15:00",
      "sender": "Christian",
      "text": "Chatham drywall done",
      "is_from_me": false
    },
    {
      "timestamp": "2025-10-28 09:17:00",
      "sender": "JR",
      "text": "Good. What about paint?",
      "is_from_me": true
    }
  ],
  "message_count": 12,
  "date_range": "2025-10-26 to 2025-10-28"
}
```

### 2. `search_messages`

Search all messages for a keyword or phrase.

**Parameters:**
- `keyword` (required): Search term
- `days_back` (optional, default: 7): Time window in days
- `limit` (optional, default: 20): Maximum results

**Example:**
```
Search for "funding" in the last 7 days
```

**Returns:**
```json
{
  "keyword": "funding",
  "results": [
    {
      "contact": "Erin",
      "timestamp": "2025-10-27 14:30:00",
      "text": "Following up on funding options",
      "is_from_me": false
    }
  ],
  "result_count": 8
}
```

### 3. `get_threads_by_date`

Get all message activity for a specific date.

**Parameters:**
- `date` (required): Date in YYYY-MM-DD format
- `exclude_group_chats` (optional, default: false): Exclude group conversations

**Example:**
```
Get all threads from 2025-10-27
```

**Returns:**
```json
{
  "date": "2025-10-27",
  "threads": [
    {
      "contact": "+1-555-0123",
      "message_count": 18,
      "last_message": "Will finish Chatham by Friday",
      "last_timestamp": "2025-10-27 17:45:00"
    }
  ],
  "total_threads": 8,
  "total_messages": 52
}
```

### 4. `list_active_contacts`

Show most active message contacts.

**Parameters:**
- `days_back` (optional, default: 7): Time window in days
- `min_messages` (optional, default: 3): Minimum messages to include
- `limit` (optional, default: 20): Maximum contacts to return

**Example:**
```
List active contacts from the last 7 days
```

**Returns:**
```json
{
  "timeframe": "Last 7 days",
  "contacts": [
    {
      "name": "+1-555-0123",
      "phone": "+1-555-0123",
      "message_count": 45,
      "last_contact": "2025-10-28 09:15:00"
    }
  ]
}
```

### 5. `get_thread_summary`

Get condensed summary of a thread with daily breakdowns.

**Parameters:**
- `contact` (required): Name, phone number, or email
- `days_back` (optional, default: 7): Days of history to summarize
- `include_timestamps` (optional, default: true): Include timestamps

**Example:**
```
Get thread summary for Christian, last 7 days
```

**Returns:**
```json
{
  "contact": "Christian",
  "date_range": "2025-10-21 to 2025-10-28",
  "total_messages": 87,
  "daily_breakdown": [
    {
      "date": "2025-10-28",
      "count": 12,
      "first_message": "Morning - starting on Chatham",
      "last_message": "Drywall done, moving to paint"
    }
  ],
  "key_topics": ["chatham", "drywall", "paint", "vendor", "crew"]
}
```

## Testing

### Manual Testing

Test the server is working by running it and checking for errors:

```bash
python server.py
```

### Test Individual Tools

Create a test script (`test_tools.py`):

```python
from database import (
    get_messages_by_contact,
    search_messages_by_keyword,
    list_active_contacts
)

# Test getting messages
result = get_messages_by_contact("Christian", days_back=3)
print(f"Found {result['message_count']} messages")

# Test search
result = search_messages_by_keyword("funding", days_back=7)
print(f"Found {result['result_count']} matching messages")

# Test active contacts
result = list_active_contacts(days_back=7)
print(f"Found {len(result['contacts'])} active contacts")
```

Run with:

```bash
python test_tools.py
```

## Troubleshooting

### "Database not found" Error

**Problem:** Cannot find `~/Library/Messages/chat.db`

**Solutions:**
- Verify Messages app is installed and has been used
- Check the file exists: `ls ~/Library/Messages/chat.db`
- Make sure you're running on macOS

### "Permission denied" Error

**Problem:** Cannot access the database file

**Solutions:**
- Grant Full Disk Access (see Installation step 2)
- Restart Terminal after granting access
- Try using `sudo` (not recommended for security reasons)

### "No messages found" for Known Contact

**Problem:** Contact exists but returns empty results

**Solutions:**
- Try using the phone number instead of name: `"+1-555-0123"`
- Try partial match: `"Chris"` instead of `"Christian Rojas"`
- Check the contact has messages in the specified time window
- Verify messages are synced to your Mac (not just iPhone)

### Group Chats Not Working

**Known Issue:** Group chat handling is basic in Phase 1.

**Workaround:** Use `exclude_group_chats=True` in `get_threads_by_date`

## Architecture

### Files

- `server.py` - Main MCP server with FastMCP tool definitions
- `database.py` - SQLite query functions for iMessage database
- `config.py` - Configuration constants
- `requirements.txt` - Python dependencies

### Database Schema

The iMessage database (`chat.db`) contains several key tables:

- **message** - Individual message records
- **handle** - Contact identifiers (phone/email)
- **chat** - Conversation threads
- **chat_message_join** - Links messages to chats
- **chat_handle_join** - Links contacts to chats

### Timestamp Handling

iMessage uses Apple epoch time (nanoseconds since 2001-01-01). The server automatically converts these to Unix timestamps and human-readable formats.

## Security & Privacy

### Data Access

- **Read-only access** - Server never writes to the database
- **Local only** - Messages never leave your Mac except when sent to Claude
- **No caching** - Message content is not stored or logged
- **Permission required** - User must explicitly grant Full Disk Access

### Best Practices

- Don't share logs that may contain message snippets
- Be careful with search queries that might log sensitive keywords
- Consider the privacy implications of giving Claude access to messages
- Review the code to understand what data is accessed

## Auto-Start on Boot (Optional)

To run the MCP server automatically when your Mac starts:

### Using launchd (macOS)

1. Create a plist file: `~/Library/LaunchAgents/com.imessage.mcp.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.imessage.mcp</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/path/to/messages/server.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

2. Load the agent:

```bash
launchctl load ~/Library/LaunchAgents/com.imessage.mcp.plist
```

3. Verify it's running:

```bash
launchctl list | grep imessage
```

## Phase 1 Success Criteria

✅ All 5 MCP tools work reliably
✅ Claude can query iMessage threads on demand
✅ Message data returns accurately (names, timestamps, content)
✅ No manual copy-paste needed
✅ Faster than manual method
✅ Server runs stably (no crashes)

## Phase 2A: Automated Daily Summaries

**Status: ✅ IMPLEMENTED**

Automatic daily iMessage activity summaries generated at 8:00 PM and saved to `~/Documents/Daily_Summaries/`.

### Features

- **Automated Generation**: Runs daily at 8:00 PM via launchd
- **Summary Statistics**: Total conversations and messages
- **Active Conversations Table**: Top contacts with message counts
- **Detailed Snippets**: Recent messages from top 5 contacts
- **Activity Timeline**: Hourly breakdown with visual bars
- **Quick Insights**: Most active contact, peak hour, averages
- **Error Handling**: Graceful handling of no messages, permission errors
- **Logging**: Activity logs saved to `~/Documents/Daily_Summaries/logs/`

### Installation

Run the setup script:

```bash
./setup_daily_summary.sh
```

This will:
1. Detect your Python path
2. Create necessary directories
3. Install launchd job for 8:00 PM execution
4. Verify installation

### Manual Testing

Generate a summary for today immediately:

```bash
python3 generate_daily_summary.py
```

Check the output:

```bash
open ~/Documents/Daily_Summaries/
```

### Files

- `generate_daily_summary.py` - Main summary generation script
- `com.imessage.daily-summary.plist` - launchd configuration template
- `setup_daily_summary.sh` - Installation and setup script

### Output Format

Summaries are saved as markdown files:
- **Location**: `~/Documents/Daily_Summaries/YYYY-MM-DD.md`
- **Format**: Markdown with tables, lists, and visual elements
- **Logs**: `~/Documents/Daily_Summaries/logs/daily_summary.log`

### Example Summary

```markdown
# iMessage Daily Summary - 2025-11-10

## 📊 Summary Statistics

- **Total Conversations:** 8
- **Total Messages:** 52

## 💬 Active Conversations

| Contact | Messages | Last Activity |
|---------|----------|---------------|
| (555) 012-3456 | 18 | 17:45 |
| (555) 987-6543 | 12 | 16:30 |

## 📝 Conversation Details

### (555) 012-3456 (18 messages)

- **09:15** - Christian: Chatham drywall done
- **09:17** - You: Good. What about paint?
...
```

### Troubleshooting

**Check if job is running:**
```bash
launchctl list | grep imessage
```

**View logs:**
```bash
tail -f ~/Documents/Daily_Summaries/logs/daily_summary.log
```

**Manually trigger (for testing):**
```bash
launchctl start com.imessage.daily-summary
```

**Uninstall:**
```bash
launchctl unload ~/Library/LaunchAgents/com.imessage.daily-summary.plist
rm ~/Library/LaunchAgents/com.imessage.daily-summary.plist
```

### Success Criteria

✅ Script runs without errors
✅ Summary files created in ~/Documents/Daily_Summaries/
✅ Markdown format is correct and readable
✅ Data is accurate (matches actual messages)
✅ Runs automatically at 8:00 PM via launchd
✅ Handles errors gracefully (no crashes)
✅ Logs activity for debugging
✅ Works on days with no messages

### Validation Period

**Run Phase 2A for 1 week before considering Phase 2B features.**

Monitor daily summaries to ensure:
- Accuracy of message data
- Reliability of scheduling
- Quality of insights generated
- No performance issues

## Future Phases (Not Yet Implemented)

### Phase 2B: Advanced Analysis
- Conflict detection
- Decision routing
- Meeting prep automation
- Pattern analysis
- Action item tracking

### Phase 3+: Advanced Features
- Email integration
- Calendar integration
- Multi-device support
- Voice message transcription
- Group chat analysis
- Response time analytics

**Do not build these until Phase 1 is proven and stable.**

## Contributing

This is a personal project for business message management. If you find bugs or have suggestions:

1. Test thoroughly on your own iMessage database first
2. Document the issue with examples
3. Consider privacy implications of any new features

## License

This project is for personal use. Handle message data responsibly and respect privacy.

## Support

For issues:
1. Check the Troubleshooting section above
2. Verify Full Disk Access is granted
3. Test with a known contact/message
4. Review server logs for error details

## Changelog

### v1.1.0 - Phase 2A (2025-11-10)
- Automated daily summary generation
- Runs at 8:00 PM via launchd
- Markdown summaries with statistics, conversations, timeline, and insights
- Handles days with no messages gracefully
- Comprehensive error handling and logging
- One-command setup script
- Saved to ~/Documents/Daily_Summaries/

### v1.0.0 - Phase 1 (2025-11-10)
- Initial release
- 5 core MCP tools implemented
- Read-only iMessage database access
- Contact search and thread retrieval
- Keyword search across messages
- Date-based thread analysis
- Active contact listing
- Thread summaries with daily breakdowns
