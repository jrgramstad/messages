#!/usr/bin/env python3
"""
Historical Backfill Script for Daily Summaries

Generates daily summaries for historical date range: Sept 1 - Nov 10, 2025
Run once to populate historical data for pattern analysis.

Usage:
    python3 backfill_summaries.py
"""

import os
import sys
import logging
import time
from datetime import datetime, date, timedelta
from pathlib import Path

# Import from existing daily summary script
from generate_daily_summary import (
    get_messages_for_date,
    group_messages_by_contact,
    analyze_with_claude,
    save_summary,
    setup_logging,
    ensure_summary_directory,
    get_db_connection,
    SUMMARY_DIR,
    ANTHROPIC_API_KEY,
    ANTHROPIC_AVAILABLE
)

# Cost estimates (rough)
COST_PER_SUMMARY = 0.02  # ~$0.02 per API call
TIME_PER_SUMMARY = 1.5   # ~1.5 seconds per summary


def check_prerequisites():
    """Check that API key is set and Anthropic is available."""
    if not ANTHROPIC_AVAILABLE:
        print("ERROR: Anthropic SDK not installed")
        print("Install with: pip install anthropic")
        return False

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        print("Set with: export ANTHROPIC_API_KEY=your_key_here")
        return False

    return True


def get_existing_summaries():
    """Get list of existing summary files."""
    summary_dir = Path(SUMMARY_DIR)
    if not summary_dir.exists():
        return set()

    existing = set()
    for file in summary_dir.glob("*.md"):
        # Extract date from filename (YYYY-MM-DD.md)
        date_str = file.stem
        try:
            # Validate it's a date
            datetime.strptime(date_str, '%Y-%m-%d')
            existing.add(date_str)
        except ValueError:
            # Not a date file, skip
            continue

    return existing


def backfill_summaries(start_date: date, end_date: date, force: bool = False):
    """
    Generate daily summaries for historical date range.

    Args:
        start_date: datetime.date object for start
        end_date: datetime.date object for end
        force: If True, overwrite existing files
    """

    # Calculate total days
    total_days = (end_date - start_date).days + 1

    # Get existing summaries
    existing = get_existing_summaries()

    logging.info("=" * 60)
    logging.info("HISTORICAL BACKFILL STARTING")
    logging.info("=" * 60)
    logging.info(f"Date Range: {start_date} to {end_date}")
    logging.info(f"Total Days: {total_days}")
    logging.info(f"Existing Summaries: {len(existing)}")
    logging.info(f"Estimated Cost: ${total_days * COST_PER_SUMMARY:.2f}")
    logging.info(f"Estimated Time: {(total_days * TIME_PER_SUMMARY) / 60:.1f} minutes")
    logging.info("=" * 60)

    # Display info to user
    print("\n" + "=" * 60)
    print("HISTORICAL BACKFILL - Daily Summaries")
    print("=" * 60)
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Total Days: {total_days}")
    print(f"Existing Summaries: {len(existing)}")
    print(f"To Process: {total_days - len(existing)}" if not force else f"To Process: {total_days} (force mode)")
    print(f"Estimated Cost: ${total_days * COST_PER_SUMMARY:.2f}")
    print(f"Estimated Time: {(total_days * TIME_PER_SUMMARY) / 60:.1f} minutes")
    print("=" * 60)

    # Confirm before proceeding
    if not force and len(existing) > 0:
        print(f"\nNote: {len(existing)} summaries already exist and will be skipped.")

    proceed = input("\nProceed with backfill? (yes/no): ").strip().lower()
    if proceed != 'yes':
        logging.info("Backfill cancelled by user")
        print("Backfill cancelled.")
        return

    print("\nStarting backfill...\n")

    # Track progress
    completed = 0
    skipped = 0
    failed = 0
    no_messages = 0

    current_date = start_date
    start_time = time.time()

    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        progress = completed + skipped + failed + no_messages + 1

        try:
            # Check if summary already exists
            if not force and date_str in existing:
                print(f"[{progress:2d}/{total_days}] SKIP: {date_str} (already exists)")
                logging.info(f"[{progress}/{total_days}] SKIP: {date_str} (already exists)")
                skipped += 1
                current_date += timedelta(days=1)
                continue

            print(f"[{progress:2d}/{total_days}] Processing: {date_str}...", end=" ", flush=True)
            logging.info(f"[{progress}/{total_days}] Processing: {date_str}")

            # Get database connection
            conn = get_db_connection()

            # Get messages for this date
            messages = get_messages_for_date(date_str, conn)

            # Close connection
            conn.close()

            # Check if any messages
            if not messages or len(messages) == 0:
                print(f"No messages")
                logging.info(f"  → No messages found for {date_str}")

                # Create empty summary
                summary_content = f"""# Daily Communication Summary
**Date:** {date_str}
**Generated:** {datetime.now().strftime('%I:%M %p')}

---

*No message activity on this date.*

---

*Generated by iMessage MCP Server - Phase 2A (Backfill)*
"""
                save_summary(date_str, summary_content)
                no_messages += 1

            else:
                msg_count = len(messages)
                print(f"{msg_count} messages...", end=" ", flush=True)
                logging.info(f"  → Found {msg_count} messages")

                # Group messages by contact
                grouped = group_messages_by_contact(messages)

                # Analyze with Claude
                summary_content = analyze_with_claude(date_str, messages, grouped)

                # Save summary
                save_summary(date_str, summary_content)

                print(f"✓ Saved")
                logging.info(f"  ✓ Summary saved for {date_str}")
                completed += 1

            # Rate limiting: small delay between API calls
            time.sleep(1)

        except KeyboardInterrupt:
            print("\n\nBackfill interrupted by user")
            logging.warning("Backfill interrupted by user")
            break

        except Exception as e:
            print(f"✗ ERROR: {str(e)[:50]}")
            logging.error(f"  ✗ ERROR processing {date_str}: {e}", exc_info=True)
            failed += 1
            # Continue to next day even if this one fails

        current_date += timedelta(days=1)

    # Calculate stats
    elapsed_time = time.time() - start_time
    total_processed = completed + skipped + failed + no_messages

    # Final summary
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"✓ Completed: {completed} (with messages)")
    print(f"⊘ No Messages: {no_messages} (empty days)")
    print(f"⊘ Skipped: {skipped} (already existed)")
    print(f"✗ Failed: {failed}")
    print(f"Total Processed: {total_processed}/{total_days}")
    print(f"Time Elapsed: {elapsed_time / 60:.1f} minutes")
    print("=" * 60)
    print(f"\nSummaries saved to: {SUMMARY_DIR}/")

    logging.info("=" * 60)
    logging.info("BACKFILL COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Completed: {completed}")
    logging.info(f"No Messages: {no_messages}")
    logging.info(f"Skipped: {skipped}")
    logging.info(f"Failed: {failed}")
    logging.info(f"Total: {total_processed}/{total_days}")
    logging.info(f"Time: {elapsed_time / 60:.1f} minutes")
    logging.info("=" * 60)


def main():
    """Main execution."""

    # Setup logging
    setup_logging()

    # Ensure directory exists
    ensure_summary_directory()

    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)

    # Define date range: Sept 1 - Nov 10, 2025
    start_date = date(2025, 9, 1)
    end_date = date(2025, 11, 10)

    # Check for --force flag
    force = '--force' in sys.argv

    # Run backfill
    try:
        backfill_summaries(start_date, end_date, force=force)
    except Exception as e:
        logging.error(f"Backfill failed: {e}", exc_info=True)
        print(f"\nERROR: Backfill failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
