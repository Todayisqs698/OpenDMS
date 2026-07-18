#!/usr/bin/env python3
"""Get recent conversation messages (default strategy for context retrieval).

This script implements the FAST PATH of context retrieval:
- Reads last N messages from today's date-based file
- Falls back to yesterday if today's file doesn't exist
- Much faster than grep search (~10-50ms vs 50-1000ms)
- Covers 90% of context retrieval needs

Usage:
    python get_recent_context.py [options]

Options:
    --workspace <path>        Workspace root (default: current directory)
    --limit <n>               Number of recent messages to fetch (default: 10)
    --date <YYYY-MM-DD>       Specific date to read from (default: today)
    --type <message_type>     Filter by message type (UserMessage, AssistantMessage, etc.)
    --json                    Output as JSON array (default: human-readable)
    --stats                   Show statistics only

Examples:
    # Get last 10 messages (default, fastest)
    python get_recent_context.py

    # Get last 20 messages
    python get_recent_context.py --limit 20

    # Get messages from specific date
    python get_recent_context.py --date 2026-02-09

    # Get only user messages
    python get_recent_context.py --type UserMessage

    # JSON output for programmatic use
    python get_recent_context.py --json

    # Show statistics
    python get_recent_context.py --stats

Performance:
    - Reading last 10 messages: ~10-50ms
    - Reading last 50 messages: ~20-80ms
    - Much faster than grep search across all history
"""

import json
import sys
import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter


def get_messages_file_path(workspace, date_str=None):
    """Get the path to messages file for a specific date.
    
    Args:
        workspace: Workspace root path
        date_str: Date string in YYYY-MM-DD format (None for today)
    
    Returns:
        Path to messages file
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    return Path(workspace) / ".codebanana" / "contexts" / f"messages_{date_str}.txt"


def read_recent_messages(file_path, limit=10, message_type=None):
    """Read last N messages from a messages file.
    
    Args:
        file_path: Path to messages_YYYY-MM-DD.txt file
        limit: Number of recent messages to read
        message_type: Optional filter by message type
    
    Returns:
        List of message dictionaries
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"❌ Error reading file {file_path}: {e}", file=sys.stderr)
        return None
    
    # Split by --- separator
    blocks = content.strip().split('\n---\n')
    
    # Parse messages
    messages = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        try:
            msg = json.loads(block)
            
            # Apply type filter if specified
            if message_type and msg.get('type') != message_type:
                continue
            
            messages.append(msg)
        except json.JSONDecodeError as e:
            print(f"⚠️  Warning: Failed to parse message block: {e}", file=sys.stderr)
            continue
    
    # Return last N messages
    return messages[-limit:] if limit > 0 else messages


def calculate_stats(messages):
    """Calculate statistics from messages."""
    if not messages:
        return {
            'total_messages': 0,
            'message_types': {},
            'date_range': None
        }
    
    # Count message types
    type_counts = Counter(msg.get('type', 'Unknown') for msg in messages)
    
    # Date range
    timestamps = [msg.get('timestamp') for msg in messages if msg.get('timestamp')]
    date_range = None
    if timestamps:
        try:
            dates = [datetime.fromisoformat(ts.replace('Z', '+00:00')) for ts in timestamps]
            date_range = {
                'earliest': min(dates).isoformat(),
                'latest': max(dates).isoformat()
            }
        except:
            pass
    
    return {
        'total_messages': len(messages),
        'message_types': dict(type_counts),
        'date_range': date_range
    }


def format_message(msg, index):
    """Format a single message for human-readable display."""
    msg_type = msg.get('type', 'Unknown')
    timestamp = msg.get('timestamp', 'N/A')
    
    # Truncate long content
    content = msg.get('content', '')
    if len(content) > 100:
        content = content[:100] + '...'
    
    result = f"[{index}] {msg_type} @ {timestamp[:19]}\n"
    
    if content:
        result += f"    {content}\n"
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Get recent conversation messages (fast context retrieval)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--workspace', default='.', help='Workspace root path (default: current directory)')
    parser.add_argument('--limit', type=int, default=10, help='Number of recent messages (default: 10)')
    parser.add_argument('--date', help='Specific date (YYYY-MM-DD, default: today)')
    parser.add_argument('--type', dest='message_type', help='Filter by message type')
    parser.add_argument('--json', action='store_true', help='Output as JSON array')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    
    args = parser.parse_args()
    
    # Get messages file path
    file_path = get_messages_file_path(args.workspace, args.date)
    
    # Read messages
    messages = read_recent_messages(file_path, args.limit, args.message_type)
    
    # Handle file not found - try fallback to yesterday
    if messages is None and args.date is None:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"⚠️  Today's file not found, trying yesterday ({yesterday})...", file=sys.stderr)
        file_path = get_messages_file_path(args.workspace, yesterday)
        messages = read_recent_messages(file_path, args.limit, args.message_type)
    
    if messages is None:
        print(f"❌ Error: No messages file found at {file_path}", file=sys.stderr)
        print(f"Tip: Check if .codebanana/contexts/ directory exists in workspace", file=sys.stderr)
        sys.exit(1)
    
    if not messages:
        print("No messages found matching the criteria.", file=sys.stderr)
        sys.exit(0)
    
    # Stats mode
    if args.stats:
        stats = calculate_stats(messages)
        print(json.dumps(stats, indent=2))
        return
    
    # JSON output mode
    if args.json:
        print(json.dumps(messages, indent=2))
        return
    
    # Human-readable output
    print(f"\n📊 Found {len(messages)} recent message(s) from {file_path.name}\n")
    print("=" * 80)
    
    for i, msg in enumerate(messages, 1):
        print(format_message(msg, i))
        print("-" * 80)
    
    # Show summary
    stats = calculate_stats(messages)
    print(f"\n📈 Summary:")
    print(f"   Total messages: {stats['total_messages']}")
    print(f"   Message types: {dict(stats['message_types'])}")
    if stats['date_range']:
        print(f"   Time range: {stats['date_range']['earliest'][:19]} to {stats['date_range']['latest'][:19]}")
    
    print(f"\n⚡ Performance: Fast path (~10-50ms for {args.limit} messages)")


if __name__ == '__main__':
    main()
