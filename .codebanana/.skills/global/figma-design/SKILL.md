---
name: figma-design
description: |
  Figma design file analysis and UI implementation: fetch design data, download assets, generate matching code.
  Triggers:
  - "Figma", "figma.com/design", "figma.com/file"
  - "implement this design", "convert Figma to code"
  - "Figma design", "design specs"
  - User provides Figma URL
  - User provides Figma API key (figd_xxx)
---

# Figma Design Implementation

## Overview

Analyze Figma design files and implement pixel-accurate UI in code. Supports fetching design data, downloading image assets, and generating HTML/CSS or React components.

## When to Use

- User provides a Figma URL (e.g., `figma.com/design/...` or `figma.com/file/...`)
- User asks to implement/convert a Figma design
- User provides a Figma API key (`figd_xxx`)

## Workflow

### Step 1: Parse Figma URL

Extract from URL:
- `file_key` — from `figma.com/file/<fileKey>/...` or `figma.com/design/<fileKey>/...`
- `node_id` — from URL parameter `node-id=<nodeId>` (optional)

**Example URL:**
```
https://www.figma.com/design/abc123/MyDesign?node-id=1-2
→ file_key: "abc123", node_id: "1-2"
```

### Step 2: Fetch Design Data

Call figma tool:
```
figma(action="get_data", file_key="abc123", node_id="1-2")
```

If user provides API key (`figd_xxx`), include it:
```
figma(action="get_data", file_key="abc123", node_id="1-2", api_key="figd_abc123")
```

### Step 3: Analyze Design Specs

From returned data, extract:
- **Layout**: Flexbox/Grid structure, spacing, padding
- **Colors**: Background, text, border colors
- **Typography**: Font family, size, weight, line-height
- **Spacing**: Margins, paddings, gaps

### Step 4: Generate Code

Create HTML/CSS or React components matching the design:
- Match layout structure exactly
- Use extracted color values
- Replicate typography settings
- Maintain spacing proportions

### Step 5: Download Images (if needed)

For bitmap images or icons in the design:

```
figma(
  action="download_images",
  file_key="abc123",
  local_path="./figma_images",
  nodes=[
    {"nodeId": "24:3", "fileName": "logo.png", "imageRef": "0eb18b43..."},
    {"nodeId": "25:4", "fileName": "icon.svg"}
  ]
)
```

**Notes:**
- SVG exports don't need `imageRef`
- PNG/JPG exports require `imageRef` from the design data
- Save to `./figma_images` or project's public assets directory

## API Key Handling

| Scenario | Action |
|---|---|
| User provides `figd_xxx` key | Include as `api_key` parameter in all figma calls |
| Auth error without key | Ask user: "Could you provide your Figma API key? (starts with `figd_`)" |
| Key provided earlier in conversation | Reuse the same key for subsequent calls |
