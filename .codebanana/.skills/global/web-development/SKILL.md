---
name: web-development
description: |
  Next.js web application development workflow: template setup, coding guide, CSS/interaction requirements, service startup, and URL response patterns.
  Triggers:
  - "website", "web app", "Next.js", "landing page"
  - "create website", "build web app"
  - "web development", "web template"
  - User confirms website after clarification
---

# Web Application Development

## Overview

Complete workflow for building Next.js web applications — from template setup through development to service startup. Covers coding standards, CSS/interaction requirements, and URL response patterns.

## When to Use

- User mentions "website", "web", "Next.js", "landing page"
- User confirms website after platform clarification
- **SKIP IF**: Platform already determined as mobile

## Workflow

### Step 1: Template Setup

**If web template already imported (template project):**
- Template is already in current workspace — no download needed
- User has selected WEB template — ONLY do website development
- This workspace is LIMITED to Next.js web applications
- If user asks for mobile app features: Decline politely and remind them this is a web-only environment
- DO NOT run download commands — proceed directly to Step 2

**If starting from scratch (hard mode / no template):**
```bash
wget https://codebanana-1308581983.cos.na-siliconvalley.myqcloud.com/templates/codebanana_web_base_template-latest.zip

# unzip, rename to [project-name] (lowercase-with-hyphens), remove zip
```

### Step 2: Develop Application

1. **Read CODING_GUIDE.md** for best practices and conventions
2. **Understand template structure** and existing files
3. **Template Philosophy**: MINIMAL base template — start simple, iterate when needed

**Implementation Approach:**
- Focus on CORE functionality first (main user flow)
- Add basic interactions — buttons should work, not just display
- Use state management (useState/Zustand) for dynamic features
- Implement essential event handlers (onClick, onChange, onSubmit)
- Start with client-side logic, add API/persistence later if requested

**Iteration Strategy:**
- Avoid over-engineering — don't add features not requested
- If complex: break into phases, complete one phase at a time
> **After Step 2**: If the feature requires storing or querying data (user accounts, posts, orders, records, history, settings) → proceed to **Step 2.5**. Otherwise skip directly to **Step 3**.

### Step 2.5: Database Setup (when data persistence is needed)

**When to apply**: User's feature involves storing or querying data — e.g. user accounts, posts, orders, records, history, settings.

**When to skip**: Pure UI / display-only pages with no data storage requirement.

**Workflow:**

1. **Find or create a Supabase project**
   - Call `supabase` tool with `action: list_projects` to check if a suitable project already exists
   - If yes: reuse it (note the `project_id`)
   - If no: call `action: create_project` with a meaningful `project_name`
   - After creating: call `action: get_project` and poll until `status === "ACTIVE_HEALTHY"` before proceeding (project provisioning takes 30–60 seconds)

2. **Create tables**
   - Call `action: apply_migration` for each table needed
   - Use `IF NOT EXISTS` to avoid errors on re-runs
   - Example:
     ```sql
     CREATE TABLE IF NOT EXISTS users (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       email TEXT UNIQUE NOT NULL,
       created_at TIMESTAMPTZ DEFAULT now()
     );
     ```

3. **Get connection credentials**
   - Call `action: get_project_url` → get `NEXT_PUBLIC_SUPABASE_URL`
   - Call `action: get_publishable_keys` → get `NEXT_PUBLIC_SUPABASE_ANON_KEY`

4. **Write credentials to env files** in the project workspace root:
   - Always write `.env.local` (local development):
     ```
     NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
     NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
     ```
   - If deployment is needed, also write `.env.prd` with the same content (required for production builds to pick up the correct credentials)
   - Confirm both files are listed in `.gitignore` to avoid leaking keys

5. **Update `src/types/database.types.ts`** — add a TypeScript interface for every table just created:
   ```ts
   export interface MyTable {
     id: string
     // ... columns matching the SQL schema
     created_at: string
   }
   ```

6. **Create `src/lib/supabase.ts`** if it doesn't already exist:
   ```ts
   import { createClient } from '@supabase/supabase-js'
   const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
   const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
   export const supabase = createClient(supabaseUrl, supabaseAnonKey)
   ```

7. **Proceed to code** — CODING_GUIDE.md has all Supabase patterns (Server Components, Server Actions, types)

**Code Organization:**
- Components: `src/components/` | Pages: `src/app/`
- State stores: `src/store/` (only if needed)
- TypeScript + Tailwind CSS

**CSS & Interaction Requirements (CRITICAL):**

> **Project Understanding**: Read existing CSS files and style definitions before adding styles

- **CSS Correctness**:
  - Verify custom Tailwind classes exist in CSS variables (e.g., `border-border` needs `--border` defined)
  - Check for z-index conflicts — ensure proper layering (content: 1-10, modals: 100+, tooltips: 1000+)
  - Use semantic CSS class names matching existing patterns

- **Layout Requirements**:
  - NO content obscured by fixed/sticky elements (headers, footers, sidebars)
  - Add proper padding/margin to prevent overlap (e.g., `pb-20` if footer is `h-16`)
  - Test scroll behavior — all content must be accessible via scrolling

- **Scroll Functionality**:
  - Never disable default scroll with `overflow: hidden` on body unless intentional (modals)
  - Use `overflow-y-auto` for scrollable containers
  - Ensure mouse wheel works for scrolling (don't block wheel events)
  - Mobile: enable touch scrolling with `-webkit-overflow-scrolling: touch`

- **Keyboard Shortcuts**:
  - Check existing keyboard handlers before adding new shortcuts
  - Don't override browser defaults (Ctrl+F, Ctrl+R, etc.)
  - Document custom shortcuts clearly (e.g., arrow keys for slides, Space for next)
  - Prevent event bubbling conflicts with `e.stopPropagation()` when needed

- **Before Deployment**: Manually test scroll, keyboard navigation, and responsive layout

### Step 3: Start Service

**If web template project (service may already be running):**
1. First check if service is already running: read `.service/service.log`
2. If log shows service is running with URL: Skip `start_web_service`, use existing URL
3. If no service or service failed: Call `start_web_service({workspace: "[PATH]", timeout: 400})`

**If starting fresh:**
- Call `start_web_service({workspace: "[PATH]", timeout: 400})`

### Step 4: Error Check & URL Response

**Error Detection (Check `.service/service.log`):**
- Look for compilation errors, runtime errors, or build failures in log
- Common issues: syntax errors, missing dependencies, type errors, port conflicts
- If errors found: Debug and fix the code issues before proceeding

**URL Response Rules:**
- Display URL in response text with markdown link:
  ```
  ✅ Website ready at [https://example.com](https://example.com)
  ```

**Key Rules:**
- Always check for errors in `.service/service.log` first
- Fix any bugs before reporting service ready
