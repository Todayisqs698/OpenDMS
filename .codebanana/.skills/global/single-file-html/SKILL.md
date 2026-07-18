---
name: single-file-html
description: |
  Single-file HTML development with Tailwind CSS CDN + Alpine.js. No build tools, no npm, no frameworks — just one index.html.
  Triggers:
  - "simple HTML page", "static page", "single file website"
  - "no build tools", "CDN only", "vanilla HTML"
  - "make a page", "create a webpage", "build a webpage", "modify HTML", "edit HTML", "update HTML"
  - "做网页", "制作网页", "制作页面", "做一个页面", "修改html", "改一下html", "改网页", "改页面"
  - Easy mode project (template_level = "easy")
  - User has easy-mode template workspace
  - Existing HTML contains `href="#..."` anchor links (auto-fix: convert to scrollToSection pattern)
---

# Easy Mode — Pure HTML Development

## Overview

Generate or modify a SINGLE `index.html` file that can be opened directly in a browser. No build tools, no npm, no frameworks — just HTML5 + CSS3 + JavaScript with CDN libraries.

## Hard Constraints (MUST FOLLOW)

1. **Output ONLY valid HTML code**
   - No explanations outside HTML
   - No markdown
   - No comments outside HTML

2. **Use ONLY:**
   - HTML5
   - CSS3 (inline `<style>`)
   - JavaScript (inline `<script>`)

3. **NO:**
   - Node.js / npm
   - Build tools
   - React / Next.js
   - TypeScript / SCSS

4. Do NOT reference local file paths in the HTML — all resources must be CDN URLs (see **Resource Handling** below)

5. **NO `<a href="#...">` anchor navigation** — NEVER use `<a href="#sectionId">` for in-page navigation. This causes page reload/redirect bugs in preview environments (iframes/srcdoc). Use JS `scrollIntoView` instead.

   **Standard pattern — always use this:**
   ```html
   <!-- WRONG: causes reload/redirect in iframe preview -->
   <a href="#about">About</a>

   <!-- CORRECT: JS-driven scroll, no navigation side-effects -->
   <a href="#" onclick="event.preventDefault(); scrollToSection('about')">About</a>
   ```

   **Always include this helper in `<script>`:**
   ```js
   function scrollToSection(id) {
     const el = document.getElementById(id);
     if (el) el.scrollIntoView({ behavior: 'smooth' });
   }
   ```

   - Apply to ALL in-page links: nav menus, TOC, "back to top", section jumps
   - External links (`href="https://..."`) are NOT affected
   - When editing existing HTML, convert every `href="#..."` to this pattern

## Resource Handling (CRITICAL)

When the page references local resource files (images, videos, audio, fonts, data files, etc.):

1. **Upload first** — call `upload_resource_to_oss` with the local file paths
2. **Replace paths** — use the returned CDN URLs in `<img src>`, `<video src>`, `url()`, etc.
3. **Then write HTML** — the final `index.html` must contain only CDN URLs, never local paths

This ensures the page works when opened directly in a browser — no server needed.

**Example flow:**
- User provides `assets/logo.png` and `assets/bg.jpg`
- Call `upload_resource_to_oss` with `["assets/logo.png", "assets/bg.jpg"]`
- Use returned CDN URLs in the HTML: `<img src="https://...logo.png">`

## Preferred Stack

- **Default**: Tailwind CSS CDN + Alpine.js
- Use Vue 3 CDN **ONLY** if user explicitly requests complex state management

## Design & UX Rules

- Mobile-first responsive layout
- Modern UI (rounded corners, shadows, smooth transitions)
- Accessible HTML (semantic tags, alt, aria where needed)
- Fast loading (CDN only)

## CSS & Interaction Requirements (CRITICAL)

### CSS Quality
- Use standard CSS properties (check compatibility)
- Proper z-index layering to prevent content overlap
- Responsive sizing with viewport units or percentages

### Layout & Scroll
- NO content hidden or obscured by fixed elements
- Enable smooth scrolling: `html { scroll-behavior: smooth; }`
- Ensure all content is reachable via mouse wheel scrolling
- Add proper padding to prevent overlap (headers/footers)

### Keyboard & Mouse
- Don't override default browser shortcuts (Ctrl+F, F5, etc.)
- Mouse wheel must work for page scrolling (don't block wheel events)
- If implementing custom shortcuts, use simple keys (letters, arrows) only
- Document any custom keyboard interactions clearly

### Testing
- Verify page scrolls properly, no content cutoff, all interactions work

## Output Rules

- Always return a **FULL** `index.html`
- Overwrite previous content entirely

## Template Reference

Use this structure strictly:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  ...
</head>
<body>
  ...
</body>
</html>
```

## Delivery

- **DO NOT** start any web service or server to preview this file
- **DO NOT** call `start_web_service` — the file is static and needs no server
- After creating the file, call `deliver_result` with the file path — the frontend handles preview and download

## Capability Boundary

If the user's request exceeds Easy Mode capability:
- Still generate the **BEST POSSIBLE** static version
- Do NOT introduce backend or build tools
