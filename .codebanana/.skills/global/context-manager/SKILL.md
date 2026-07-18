---
name: context-manager
description: |
  Search historical conversation messages when current context is insufficient.

  Triggers:
  - Explicit history reference: "上个月提到的...", "之前讨论的...", "找一下历史记录"
  - Explicit search intent: "search history", "find previous discussion", "what did we say about"
  - User asks about something they presumably told us before, but it's NOT in current context
    (e.g. "我的幸运数字是多少", "my favorite color?", "what's my API key",
     "还记得我说的那个名字吗", "你知道我叫什么吗")
  - User references past work/decisions not in current context
  
  Key rule: If user expects you to "remember" something and you don't see it
  in the current conversation, load this skill and search.
---

# Context Manager

Search `.codebanana/contexts/messages_YYYY-MM-DD.txt` for past conversations.

**Only use when current context lacks the information** — the system prompt already
contains recent history, so most requests don't need this.

## When to Use

| Use search | Don't search |
|---|---|
| "上个月提到的 API…" (old time ref) | "刚才说的…" (recent, already in context) |
| "Find the DB schema we discussed" (topic missing from context) | "继续上次的工作" (continuation, context has it) |
| "我的幸运数字是多少" (user expects you to recall personal info) | General new requests with no historical reference |
| "还记得我说的密码吗" (recall something user told you before) | Information already visible in current conversation |

## Tool

```bash
python .codebanana/.skills/global/context-manager/scripts/search_context.py \
  "<query>" [options]
```

### Query Syntax

| Pattern | Meaning | Example |
|---|---|---|
| `"keyword"` | Substring match | `"authentication"` |
| `"A AND B"` | All terms must match | `"JWT AND token"` |
| `"A OR B"` | Any term matches | `"database OR schema"` |
| `--regex "pattern"` | Regex | `--regex "def \w+_handler"` |

### Options

| Flag | Default | Description |
|---|---|---|
| `--start-date YYYY-MM-DD` | none | Filter from date |
| `--end-date YYYY-MM-DD` | none | Filter to date |
| `--limit N` | 5 | Max conversation rounds to return |
| `--skip N` | 0 | Skip first N matched rounds |
| `--before TIMESTAMP` | none | Only return rounds before this timestamp (for pagination) |
| `--type TYPE` | all | `user_message`, `assistant_response` |
| `--case-sensitive` | off | Exact case matching |
| `--regex` | off | Treat query as regex |

### Output Format

```
Found 12 matches, returning rounds 1-5. Last: 2026-03-04T12:42:58

--- Round 1 [2026-03-04 12:43:36] ---
[user] 我喜欢吃西红柿
[assistant] 知道了！您喜欢吃西红柿 🍅

--- Round 2 [2026-03-04 12:42:58] ---
[user] 我的生日是1998年9月
[assistant] 好的，我记住了！您的生日是1998年9月 🎂
```

Key points:
- **Round** = one complete user→assistant exchange
- Results are **reverse chronological** (newest first)
- Header shows total matches and **Last timestamp** for pagination

## Search Strategy

### First call: always skip 1
The current conversation round (user asking + assistant saying "let me search")
is already written to the messages file before the script runs.
It will match the keyword but is never the answer. **Always use `--skip 1`
on the first call.**

```bash
# First call — skip current round
python .codebanana/.skills/global/context-manager/scripts/search_context.py "生日" --skip 1
# Output: "Found 12 matches, returning rounds 2-6. Last: 2026-03-04T12:42:58"
```

### Pagination: use --before from previous output
If the first call didn't find the answer, use the `Last` timestamp to continue:

```bash
# Second call — continue from where we left off
python .codebanana/.skills/global/context-manager/scripts/search_context.py "生日" --before 2026-03-04T12:42:58
# Output: "Found 12 matches, returning rounds 7-11. Last: 2026-02-20T09:15:00"
```

`--before` anchors by timestamp so new messages added between calls don't
shift the results. No `--skip` needed after the first call — `--before`
naturally continues from the last returned round.

### When to stop
- **Found the answer** → stop, respond to user
- **No more matches** (returned < limit, or "Found 0 matches") → tell user not found, ask for more details
- **Tried 2-3 calls without finding** → stop, likely not in history. Ask user to clarify or rephrase

### Switching keywords
If the keyword yields 0 matches, try rephrasing before giving up:
- "birthday" → "生日"
- "database config" → "数据库" 
- "API key" → specific key name if known

## Examples

**Recall personal info (first call, skip current round):**
```bash
python .codebanana/.skills/global/context-manager/scripts/search_context.py "生日" --skip 1
```

**Search last month for a topic:**
```bash
python .codebanana/.skills/global/context-manager/scripts/search_context.py \
  "API endpoint" --start-date 2026-02-01 --end-date 2026-02-28 --skip 1
```

**Paginate through results:**
```bash
# Page 1
python .codebanana/.skills/global/context-manager/scripts/search_context.py "auth" --skip 1
# Page 2 (use Last timestamp from page 1 output)
python .codebanana/.skills/global/context-manager/scripts/search_context.py "auth" --before 2026-03-01T14:30:00
```

**Find all mentions (increase limit):**
```bash
python .codebanana/.skills/global/context-manager/scripts/search_context.py "JWT" --limit 20 --skip 1
```

## Result Handling

- **Has results** → Summarize the relevant findings, reference dates/content naturally.
- **No results** → Try rephrasing keyword once. If still nothing, ask user for more details.
- **Script error** → Continue without historical context, don't block the user.
