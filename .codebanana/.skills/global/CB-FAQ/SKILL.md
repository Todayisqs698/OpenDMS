---
name: CB FAQ
description: |
  Instantly answer any question about CodeBanana (CB) — the AI-powered coding assistant platform. Ask about features, pricing, agent modes, skills, organizations, GitHub integration, and more. Answers are pulled from official CodeBanana documentation so you always get accurate, up-to-date information.

  Triggers: "CodeBanana", "CB", "codebanana.com", Team Agent, Private Agent, Skill Market, SKILL.md, SOUL, IDENTITY, HEARTBEAT.md, Forward, Restore, Request Support.
---

# CodeBanana FAQ

Answer CodeBanana product questions using official documentation. Always cite the source URL at the end.

## Trigger Rules

**Alias:** "CB" is treated as equivalent to "CodeBanana" in all trigger rules below.

**Always trigger** when the user explicitly mentions "CodeBanana", "CB", or "codebanana.com", regardless of topic.

**Also trigger (without explicit mention)** only when the user uses CodeBanana-specific terminology that does not exist in other products:
- Chat modes: **Team Agent**, **Private Agent**, **Discussion** (as a chat tab)
- **Skill Market**, **SKILL.md**, "add skill to project", publish/share a skill
- Agent Config fields: **SOUL**, **IDENTITY**, **HEARTBEAT.md**
- Chat actions: **Forward** (forwarding a message to another group/tab), **Restore** (rolling back an Agent conversation node)
- **Request Support** (the in-product support button)

**Do NOT trigger** on generic terms alone — too common in general software development:
- usage, billing, plan, quota, requests
- deploy, deployment, service, port
- git, commit, push, rollback, terminal
- preview, comment, annotation
- members, invite, organization, team
- schedule, cron, file watch
- VM, virtual machine
- login, sign up, account

When uncertain whether the user is asking about CodeBanana vs. their own product, do NOT trigger.

## Workflow

### Step 1 — Confirm this is a CodeBanana product question

If the user is asking about their own project, their own code, or a general topic unrelated to the CodeBanana platform itself, skip this skill and answer normally.

### Step 2 — Refresh pages.json

Always download the latest index before matching:

```bash
curl -s "https://prd-tc-intl-cdn.codebanana.com/docs/codebanana/cbqa/pages.json?t=$(date +%s)" \
  -o .codebanana/.skills/global/CB-FAQ/references/pages.json
```

If the download fails, fall back to the existing local `references/pages.json` and note to the user that results may not reflect the latest docs.

### Step 3 — Find relevant pages

Run the match script with the user's question:

```bash
python .codebanana/.skills/global/CB-FAQ/scripts/match_pages.py "<user question>"
```

Output format (one line per match):
```
<id>|<title>|<url>
```

If output is `NO_MATCH`, tell the user the docs don't cover this topic and suggest visiting https://www.codebanana.com.

### Step 4 — Download matched content

For each returned ID, download the corresponding reference file:

```bash
curl -s "https://prd-tc-intl-cdn.codebanana.com/docs/codebanana/cbqa/<id>.md?t=$(date +%s)" \
  -o .codebanana/.skills/global/CB-FAQ/references/<id>.md
```

Only download the files returned by the script (1–3 files). If a download fails, fall back to the existing local file at `references/<id>.md`.

### Step 5 — Answer

Answer clearly and concisely based only on the loaded content. Do not fabricate details not present in the docs.

At the end of your response, append one line in this format:

具体的信息请参照官方文档：[Title1](full_url1) [Title2](full_url2)

- Title comes from the second field of the script output
- full_url = `https://docs.codebanana.com` + third field (e.g. `/documentation/working-in-code-banana/cron-job`)
- Use Markdown hyperlink syntax: `[Title](url)`
