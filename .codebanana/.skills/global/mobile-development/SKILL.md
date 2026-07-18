---
name: mobile-development
description: |
  React Native/Expo mobile app development workflow: template setup, context pattern, cross-platform requirements, and service startup.
  Triggers:
  - "mobile app", "iOS", "Android", "Expo", "React Native"
  - "create mobile app", "build app"
  - "mobile development", "app template"
  - User confirms mobile after clarification
---

# Mobile App Development

## Overview

Complete workflow for building React Native/Expo mobile applications — from template setup through development to service startup. Covers context pattern, cross-platform requirements, and URL response patterns.

## When to Use

- User mentions "mobile app", "iOS", "Android", "Expo", "React Native"
- User confirms mobile after platform clarification
- **SKIP IF**: User explicitly mentions "website", "Next.js", "web app", "API"

## Workflow

### Step 1: Template Setup

**If mobile template already imported (template project):**
- Mobile app template already imported by frontend — no download needed
- Template location: Current workspace
- User has selected MOBILE APP template — you can ONLY do mobile app development
- This workspace is LIMITED to React Native/Expo applications (iOS/Android)
- If user asks for website or web app features: Decline politely and remind them this is a mobile-only environment
- Focus exclusively on implementing mobile features
- DO NOT run download commands — proceed directly to Step 2

**If starting from scratch (hard mode / no template):**
```bash
wget https://codebanana-1308581983.cos.na-siliconvalley.myqcloud.com/templates/codebanana_app_template-latest.zip
# unzip, rename to [project-name] (lowercase-with-hyphens), remove zip
```

### Step 2: Generate Business Code

1. **Read `doc/AI_CODING_GUIDE.md`** from template to understand:
   - Context pattern (mandatory for state management)
   - Type definitions (TypeScript strict mode)
   - Component structure (React Native conventions)

2. **Generate files following the template structure:**
   - `types/[business].ts` — Data type definitions (extend BaseModel)
   - `contexts/[Business]Context.tsx` — State management (Context + Hooks pattern)
   - `app/(tabs)/index.tsx` — Main screen implementation (replace template)
   - `app/_layout.tsx` — Add Provider wrapper (DO NOT modify base structure)

3. **Cross-Platform Requirements** (must work on Web + iOS + Android):

   | Requirement | Details |
   |---|---|
   | **No `Alert.alert`** | Causes iOS/Web display mismatch — use custom Modal instead |
   | **No platform-specific APIs** | Avoid `Platform.OS` checks, native modules |
   | **Safe area handling** | Use `useSafeAreaInsets` for iOS notch/home indicator (read template pattern) |
   | **Modal dialogs** | Custom `<Modal>` with overlay (not Alert.alert) |
   | **Data operations** | All via `storage` utility (already in template) |
   | **Testing order** | Test on Web first, then verify iOS rendering matches |

### Step 3: Start Server

Call `start_mobile_service({workspace: "[PATH]", timeout: 400})`

### Step 4: Display URLs

After successfully starting the service, display URLs in response text:

**URL Formats:**
- `exp://xxx.codebanana.app` — for mobile device (Expo Go)
- `https://xxx.codebanana.app` — for browser preview

**Display Example:**
```
✅ Mobile app ready!
- 📱 Mobile: exp://xxx.codebanana.app
- 🌐 Browser: [https://xxx.codebanana.app](https://xxx.codebanana.app)
```

**Key Rules:**
- Display BOTH URLs (exp:// + https://) as clickable links
- Do not report service as "started" without displaying URLs

## Completion Checklist

- [ ] Both URLs returned (exp:// + https://)
- [ ] Providers added to `_layout.tsx`
- [ ] Don't modify: `package.json`, `tsconfig.json`, `app.json`
