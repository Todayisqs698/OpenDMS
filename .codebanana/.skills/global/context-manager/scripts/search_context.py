#!/usr/bin/env python3
"""Search conversation history in .codebanana/contexts/.

Returns results as complete conversation rounds (user→assistant pairs),
reverse chronological order, with pagination support.

Usage:
    python search_context.py <query> [options]

Examples:
    python search_context.py "生日" --skip 1
    python search_context.py "auth" --before 2026-03-04T12:42:58
    python search_context.py "database OR schema" --limit 10 --skip 1
"""

import json
import sys
import argparse
import re
from datetime import datetime
from pathlib import Path


def find_message_files(workspace, start_date=None, end_date=None):
    """Find message files sorted by date descending (newest first)."""
    contexts_dir = Path(workspace) / ".codebanana" / "contexts"
    if not contexts_dir.exists():
        return []

    message_files = list(contexts_dir.glob("messages_*.txt"))

    if start_date or end_date:
        filtered = []
        for fp in message_files:
            m = re.search(r'messages_(\d{4}-\d{2}-\d{2})\.txt', fp.name)
            if m:
                d = m.group(1)
                if start_date and d < start_date:
                    continue
                if end_date and d > end_date:
                    continue
                filtered.append(fp)
        return sorted(filtered, reverse=True)

    return sorted(message_files, reverse=True)


def parse_query(query, case_sensitive=False, is_regex=False):
    """Parse query into a matcher function.

    Supports:
      - Plain substring: "authentication"
      - Regex: "def \\w+_handler" (with --regex)
      - AND: "auth AND JWT" (all terms must match)
      - OR:  "database OR schema" (any term must match)
    """
    flags = 0 if case_sensitive else re.IGNORECASE

    if is_regex:
        try:
            pattern = re.compile(query, flags)
        except re.error as e:
            print(f"Invalid regex: {e}", file=sys.stderr)
            sys.exit(1)
        return lambda text: bool(pattern.search(text))

    if " AND " in query:
        terms = [t.strip() for t in query.split(" AND ") if t.strip()]
        if case_sensitive:
            return lambda text: all(t in text for t in terms)
        else:
            terms_lower = [t.lower() for t in terms]
            return lambda text: all(t in text.lower() for t in terms_lower)

    if " OR " in query:
        terms = [t.strip() for t in query.split(" OR ") if t.strip()]
        if case_sensitive:
            return lambda text: any(t in text for t in terms)
        else:
            terms_lower = [t.lower() for t in terms]
            return lambda text: any(t in text.lower() for t in terms_lower)

    if case_sensitive:
        return lambda text: query in text
    else:
        q = query.lower()
        return lambda text: q in text.lower()


def parse_messages(filepath):
    """Parse a message file into a list of message dicts."""
    try:
        content = filepath.read_text(encoding='utf-8')
    except Exception:
        return []

    messages = []
    for block in content.strip().split('\n---\n'):
        block = block.strip()
        if not block:
            continue
        try:
            msg = json.loads(block)
            messages.append(msg)
        except json.JSONDecodeError:
            continue
    return messages


def extract_display_content(msg):
    """Extract human-readable content from a message.
    
    For assistant_response: parse the JSON wrapper and extract display_to_user.
    For user_message: return content directly.
    For tool_execution: return content directly.
    """
    content = msg.get('content', '')
    msg_type = msg.get('type', '')

    if msg_type == 'assistant_response':
        # Try to extract display_to_user from JSON wrapper
        # Content format: ```json\n{...}\n```
        json_match = re.search(r'```json\s*\n(.*?)\n\s*```', content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                return parsed.get('display_to_user', content)
            except json.JSONDecodeError:
                pass
        return content

    return content


def group_into_rounds(messages):
    """Group messages into conversation rounds.
    
    A round = one user_message + its following assistant_response.
    Tool executions between them are skipped.
    The round's timestamp is the user_message's timestamp.
    
    Returns list of rounds, each: {
        'timestamp': str,
        'user': str,
        'assistant': str,
    }
    """
    rounds = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get('type') == 'user_message':
            user_content = msg.get('content', '')
            user_ts = msg.get('timestamp', '')
            # Find the next assistant_response (skip tool_execution)
            assistant_content = ''
            j = i + 1
            while j < len(messages):
                if messages[j].get('type') == 'assistant_response':
                    assistant_content = extract_display_content(messages[j])
                    j += 1
                    break
                elif messages[j].get('type') == 'tool_execution':
                    j += 1
                    continue
                else:
                    # Next user_message without assistant response
                    break
            rounds.append({
                'timestamp': user_ts,
                'user': user_content,
                'assistant': assistant_content,
            })
            i = j
        else:
            i += 1
    return rounds


def search_rounds(workspace, matcher, message_type=None,
                  start_date=None, end_date=None, limit=5,
                  skip=0, before=None):
    """Search across message files, return matching rounds.
    
    - Files scanned newest-first
    - Rounds within each file are reversed (newest first)
    - matcher is applied to both user and assistant content in a round
    - Returns (matched_rounds, total_match_count)
    """
    files = find_message_files(workspace, start_date, end_date)
    if not files:
        return [], 0

    all_matching_rounds = []

    for fp in files:
        messages = parse_messages(fp)
        rounds = group_into_rounds(messages)
        # Reverse: newest round first within each file
        rounds.reverse()

        for rnd in rounds:
            # Apply --before filter
            if before and rnd['timestamp'] >= before:
                continue

            # Check if this round matches the query
            # Search in user content
            user_matches = matcher(rnd['user'])
            # Search in assistant content  
            assistant_matches = matcher(rnd['assistant'])

            # Apply type filter
            if message_type:
                if message_type == 'user_message' and not user_matches:
                    continue
                elif message_type == 'assistant_response' and not assistant_matches:
                    continue
                elif not message_type == 'user_message' and not message_type == 'assistant_response':
                    if not (user_matches or assistant_matches):
                        continue
            else:
                if not (user_matches or assistant_matches):
                    continue

            all_matching_rounds.append(rnd)

    total_matches = len(all_matching_rounds)

    # Apply skip and limit
    result_rounds = all_matching_rounds[skip:skip + limit]

    return result_rounds, total_matches


def format_output(rounds, total_matches, skip, limit):
    """Format rounds into human-readable output."""
    if not rounds:
        print(f"Found {total_matches} matches, returning 0 rounds.")
        return

    start_idx = skip + 1
    end_idx = skip + len(rounds)
    last_ts = rounds[-1]['timestamp']
    # Normalize timestamp for output (remove timezone info for cleaner display)
    last_ts_clean = last_ts[:19] if len(last_ts) > 19 else last_ts

    print(f"Found {total_matches} matches, returning rounds {start_idx}-{end_idx}. Last: {last_ts_clean}")
    print()

    for i, rnd in enumerate(rounds):
        ts = rnd['timestamp'][:19] if len(rnd['timestamp']) > 19 else rnd['timestamp']
        print(f"--- Round {start_idx + i} [{ts}] ---")

        # Truncate long content
        user_text = rnd['user']
        if len(user_text) > 500:
            user_text = user_text[:500] + '...'
        print(f"[user] {user_text}")

        assistant_text = rnd['assistant']
        if len(assistant_text) > 500:
            assistant_text = assistant_text[:500] + '...'
        if assistant_text:
            print(f"[assistant] {assistant_text}")

        print()


def main():
    p = argparse.ArgumentParser(description='Search conversation history')
    p.add_argument('query', help='Search query (substring, "A AND B", "A OR B", or regex with --regex)')
    p.add_argument('--workspace', default='.', help='Workspace root (default: .)')
    p.add_argument('--regex', action='store_true', help='Treat query as regex pattern')
    p.add_argument('--case-sensitive', action='store_true', help='Case-sensitive matching')
    p.add_argument('--type', dest='message_type', help='Filter: user_message, assistant_response')
    p.add_argument('--start-date', help='From date (YYYY-MM-DD)')
    p.add_argument('--end-date', help='To date (YYYY-MM-DD)')
    p.add_argument('--limit', type=int, default=5, help='Max rounds to return (default: 5)')
    p.add_argument('--skip', type=int, default=0, help='Skip first N matched rounds (default: 0)')
    p.add_argument('--before', help='Only return rounds before this timestamp (ISO format, for pagination)')
    args = p.parse_args()

    for label, val in [('start-date', args.start_date), ('end-date', args.end_date)]:
        if val:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                print(f"Invalid {label}: {val} (use YYYY-MM-DD)", file=sys.stderr)
                sys.exit(1)

    matcher = parse_query(args.query, args.case_sensitive, args.regex)
    rounds, total_matches = search_rounds(
        args.workspace, matcher, args.message_type,
        args.start_date, args.end_date, args.limit,
        args.skip, args.before,
    )

    format_output(rounds, total_matches, args.skip, args.limit)


if __name__ == '__main__':
    main()
