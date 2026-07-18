---
name: web-deployment
description: |
  Vercel deployment workflow for web projects: deploy to production, get public URL, domain management.
  Triggers:
  - "deploy", "publish", "deploy to production"
  - "deploy website", "deploy web project"
  - "publish to Vercel", "go live"
---

# Web Deployment to Vercel

## Overview

Deploy Next.js web projects to Vercel production. Returns a public production URL accessible to anyone.

## When to Use

- User explicitly requests: "deploy", "publish", "deploy to production", "go live"
- **NEVER** deploy without user's explicit request
- **NEVER** suggest or ask "do you want to deploy?"

## Workflow

### Step 1: Deploy

Call `deploy_to_vercel` directly:
- Tool automatically uses directory name as project name
- Returns public production URL
- No authentication required for access

### Step 2: Return URL

After successful deployment, return the production URL to user.

## Important Rules

| Rule | Details |
|---|---|
| **Explicit request only** | Only deploy when user says "deploy", "publish", or similar |
| **Don't suggest** | DO NOT ask "do you want to deploy?" or suggest deployment proactively |
| **Project naming** | Project name = directory name (automatic) |
| **Public access** | Deployment URL is public and accessible to anyone |
| **Idempotent** | Each deployment updates the production site |
