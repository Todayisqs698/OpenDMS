---
name: git-workflow
description: |
  Git workflow guide: commit, push, conflict resolution, and approval rules for version control operations.
  Triggers:
  - "commit", "push", "git", "version control"
  - "save to git", "submit code", "push code"
  - "git conflict", "merge conflict", "rebase"
  - User requests any git commit/push operation
---

# Git Operation Guide

## Scope

Git workflow operations — ONLY when user explicitly requests.

## Commit Process

1. **Pre-check**: `git status`, `git branch --show-current`
2. **Stage**: `git add <files>`
3. **Review**: `git diff --cached` (analyze actual changes)
4. **Commit**: `git commit -m "type(scope): description"` (Conventional Commits format)
   - Example: `feat(auth): add JWT token validation middleware`

## Push Process

1. Call `update_git_token` tool before any network operation
2. Stash: `git stash` (always stash first — workspace files like `.codebanana/` are often dirty and will block rebase)
3. Pull: `git pull --rebase origin <branch>`
4. Pop: `git stash pop`
5. Push: `git push origin <branch>`
6. On failure: Auto-retry with `git pull --rebase` → resolve conflicts → `git rebase --continue` → retry push

> **Why stash first**: `git pull --rebase` fails with "You have unstaged changes" if any tracked files are modified. Workspace-internal files (`.codebanana/`, `.coding-agent/`) are frequently dirty and trigger this. Always stash before pulling.

## Conflict Resolution

Automatic during approved push:

| File Type | Strategy |
|---|---|
| Lock files (`*.lock`, `*.snap`) | Delete and regenerate (`rm <file> && npm install`) |
| Config files | Prefer incoming for deps, keep local for custom configs |
| Source code | Keep both if additive, prefer complete if conflicting, preserve signatures |
| Docs | Merge non-conflicting content, remove duplicates |

Complete: `git add <resolved>` → `git rebase --continue` → verify with tests

## Timeout

`git checkout`, `git fetch`, `git pull`, `git clone` on large repos can be slow — always pass `timeout=300` (or higher) when calling `run_terminal_cmd` for these operations.

## Risky Operations

Always ask first:
- `git push --force`, `git reset --hard`, destructive commands
- Always confirm before executing

## User Approval Rules

| Operation | Approval |
|---|---|
| `git status`, `git log`, `git diff`, `git branch`, `git add` | Safe — no approval needed |
| `git commit`, `git push`, any add/commit/push combination | **Requires explicit approval** |

**When to proceed**: Only when user explicitly says "commit", "push", "submit code", "save to git"

**When NOT to proceed**: "done", "finished", "complete", "save" — clarify first

## Hard Rule: git push requires explicit user approval

**Never execute `git push` without explicit user approval — no exceptions.**

- A previous push in the same session does NOT authorize the next push.
- Even if the workflow "naturally leads to push", always ask first.
- "Submit code" or "save" only authorizes `git commit` — push requires separate confirmation.
- No implicit authorization, no exceptions.

**Correct behavior**: After committing, explicitly ask the user: "Do you want to push to remote?" — only proceed after the user confirms with "yes" / "push" / or equivalent.
