---
name: html-ppt-generation
description: |
  Create and modify HTML-based presentations (PPT/slides).
  Triggers: "make PPT", "create presentation", "make slides", "制作PPT", "做幻灯片"
---

# HTML Presentation Guide

## Format

- **HTML format**: Use HTML to build presentations, adapt to any screen size and resolution
- **Self-contained**: All CSS, JavaScript must be inline within the HTML file itself — no external scripts or stylesheets
- **Responsive**: "Fluid-first, fixed as fallback" — use relative/flexible units for responsive scaling, fixed units only when necessary
- **Aesthetic**: Modern design, generous whitespace, clear visual hierarchy, engaging interactions
- **CDN resources**: Use overseas CDNs such as jsDelivr to ensure global access

## Best Practices

- **Images**: Search for relevant images when needed. Always set `object-fit: cover` and provide a fallback `background-color` behind images to handle broken links
- **Fonts**: Prefer `system-ui, -apple-system, sans-serif`. Load web fonts via CDN only when a specific style is required
- **Color**: Define a consistent palette (3-5 colors) and reuse across all slides for visual coherence
- **Interaction**: Support basic slide navigation (e.g., keyboard, click, or swipe)
