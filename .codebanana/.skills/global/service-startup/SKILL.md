---
name: service-startup
description: |
  General service startup guide for web/backend services (Next.js, Node.js, Express, Flask, FastAPI). Covers dependency installation, environment setup, startup verification, and port management.
  Triggers:
  - "start service", "run server", "start app"
  - "npm start", "python run", "flask run", "uvicorn"
  - "service not starting", "port already in use"
  - Manual service startup needed (not using start_web_service tool)
---

# Service Startup Guide

## Scope

Website and backend services: Next.js, Node.js, Express and similar.

## Preferred Approach

Use `start_web_service` tool for automatic port/domain allocation.

Only follow the manual steps below when the automated tool is unavailable or insufficient.

## Manual Startup Steps

### 0. Kill Existing Process

Always kill any existing process on the target port before starting:

```bash
# Kill by port
fuser -k PORT/tcp 2>/dev/null || true

# Or kill by script name (Python)
pkill -f "python.*app.py" 2>/dev/null || true

# Or kill by script name (Node.js)
pkill -f "node.*server" 2>/dev/null || true
```

Wait 1-2 seconds after killing before starting the new process.

### 1. Install Dependencies

Background install with silent flags to avoid blocking:

```bash
# Node.js
npm ci --prefer-offline --silent > /dev/null 2>&1 & wait

# Python
pip install --quiet > /dev/null 2>&1 & wait
```

### 2. Set Environment Variables

Export required framework variables before starting:

```bash
export PORT=X NEXT_PUBLIC_URL=https://xxx NEXTAUTH_URL=https://xxx
```

### 3. Start & Verify

```bash
# Start in background with logging
npm start > /tmp/[service].log 2>&1 &

# Monitor startup progress
tail -f /tmp/[service].log

# Verify service is running
netstat -tuln | grep :PORT
curl https://xxx
```

**Success criteria** — ALL must be true:
- Logs show "ready" or "listening"
- Port is bound (`netstat` confirms)
- `curl` returns a valid response

## Critical Rules

- **Never** claim "started" without port verification
- Auto-fix startup errors — don't stop at first failure
- Check `.service/service.log` for existing service state before starting a new one

## When NOT to Start a Service

Do **NOT** start a web service for:
- Static HTML files, reports, or documents — deliver via `deliver_result` instead
- Single-file outputs (HTML reports, dashboards, landing pages)
- PPT, PDF, Markdown, or any non-application files

Only start a service when the user **explicitly needs a running web application** (e.g., "start the app", "run the dev server", "launch the website").

## Port & Domain Management

Use `get_all_domains_ports` tool when:
- User asks: "show link", "what's running", "check port"
- Manual port conflict troubleshooting needed
- Custom port/domain selection required

### Selection Rules

| Service Type | Filter | Pick |
|---|---|---|
| Web / Backend | `type="general"` | First with `port_occupied=false` |
| Mobile App | `type="mobile"` | First with `port_occupied=false` |

- Don't assume ports are free — always check first
- Don't mix types (mobile domains for web or vice versa)
