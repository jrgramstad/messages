#!/bin/bash
# Setup script for Phase 2A - Daily Summary Automation
# This script installs the launchd job that runs at 8:00 PM daily

set -e  # Exit on error

echo "=========================================="
echo "iMessage Daily Summary - Setup"
echo "Phase 2A Installation"
echo "=========================================="
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Project directory: $SCRIPT_DIR"
echo ""

# Find Python path
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "ERROR: python3 not found in PATH"
    echo "Please install Python 3 first"
    exit 1
fi
echo "Python path: $PYTHON_PATH"

# Get current user
CURRENT_USER=$(whoami)
echo "Current user: $CURRENT_USER"
echo ""

# Path to generate script
SCRIPT_PATH="$SCRIPT_DIR/generate_daily_summary.py"
if [ ! -f "$SCRIPT_PATH" ]; then
    echo "ERROR: generate_daily_summary.py not found at $SCRIPT_PATH"
    exit 1
fi

# Make script executable
chmod +x "$SCRIPT_PATH"
echo "✓ Made generate_daily_summary.py executable"

# Create plist from template
PLIST_TEMPLATE="$SCRIPT_DIR/com.imessage.daily-summary.plist"
PLIST_FILE="$HOME/Library/LaunchAgents/com.imessage.daily-summary.plist"

echo ""
echo "Creating launchd plist..."

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Replace placeholders in plist
sed -e "s|/usr/local/bin/python3|$PYTHON_PATH|g" \
    -e "s|/Users/YOUR_USERNAME/path/to/messages|$SCRIPT_DIR|g" \
    "$PLIST_TEMPLATE" > "$PLIST_FILE"

echo "✓ Created plist at: $PLIST_FILE"

# Create summary directory
SUMMARY_DIR="$HOME/Documents/Daily_Summaries"
mkdir -p "$SUMMARY_DIR"
echo "✓ Created summary directory: $SUMMARY_DIR"

# Create log directory
LOG_DIR="$SUMMARY_DIR/logs"
mkdir -p "$LOG_DIR"
echo "✓ Created log directory: $LOG_DIR"

echo ""
echo "Loading launchd job..."

# Unload if already loaded (ignore errors)
launchctl unload "$PLIST_FILE" 2>/dev/null || true

# Load the new job
launchctl load "$PLIST_FILE"
echo "✓ Loaded launchd job"

# Verify it's loaded
if launchctl list | grep -q "com.imessage.daily-summary"; then
    echo "✓ Job is active"
else
    echo "⚠ Warning: Job may not be loaded properly"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "The daily summary will run automatically at 8:00 PM."
echo ""
echo "Summaries will be saved to:"
echo "  $SUMMARY_DIR/"
echo ""
echo "Logs will be saved to:"
echo "  $LOG_DIR/daily_summary.log"
echo ""
echo "To test immediately, run:"
echo "  python3 $SCRIPT_PATH"
echo ""
echo "To check job status:"
echo "  launchctl list | grep imessage"
echo ""
echo "To view logs:"
echo "  tail -f $LOG_DIR/daily_summary.log"
echo ""
echo "To uninstall:"
echo "  launchctl unload $PLIST_FILE"
echo "  rm $PLIST_FILE"
echo ""
