# Skill File Structure Specification

## Table of Contents

- [Standard Structure](#standard-structure)
- [Directory Descriptions](#directory-descriptions)
- [File Naming Conventions](#file-naming-conventions)
- [Examples](#examples)

## Standard Structure

```
.skills/<skill-name>/
├── SKILL.md              # [Required] Main instruction file
├── scripts/              # [Optional] Executable scripts
│   ├── main.py
│   └── utils.py
├── references/           # [Optional] Reference documents
│   ├── api.md
│   └── examples.md
└── assets/               # [Optional] Output resources
    ├── templates/
    └── images/
```

## Directory Descriptions

### SKILL.md (Required)

Main instruction file. Agent reads this first when skill is triggered.

**Requirements:**
- Must be in skill root directory
- Must contain YAML frontmatter
- Line limit: < 500 lines

### scripts/ (Optional)

Executable scripts for tasks requiring deterministic execution.

**Use Cases:**
- Data processing/transformation
- File operations
- API calls
- Validation/checks

**Requirements:**
- Python scripts: add shebang `#!/usr/bin/env python3`
- Include docstring explaining usage
- Handle CLI arguments
- Return appropriate exit codes

### references/ (Optional)

Reference documents loaded on demand to save context.

**Use Cases:**
- API documentation
- Database schemas
- Detailed examples
- Domain knowledge

**Requirements:**
- Use Markdown format
- Add TOC for files > 100 lines
- Explain when to read in SKILL.md

### assets/ (Optional)

Resource files for output. Not loaded into context.

**Use Cases:**
- HTML/React templates
- Images/icons
- Configuration templates
- Sample files

## File Naming Conventions

| Type | Convention | Examples |
|------|------------|----------|
| Skill directory | lowercase+hyphens | `pdf-editor`, `code-review` |
| Script files | lowercase+underscores | `process_data.py`, `validate_input.py` |
| Reference docs | lowercase+hyphens | `api-reference.md`, `getting-started.md` |
| Asset files | context-dependent | `template.html`, `logo.png` |

## Examples

### Simple Skill (SKILL.md only)

```
code-review/
└── SKILL.md
```

### Standard Skill (with scripts and references)

```
pdf-editor/
├── SKILL.md
├── scripts/
│   ├── rotate.py
│   ├── merge.py
│   └── extract_text.py
└── references/
    └── pdf-operations.md
```

### Full Skill (all components)

```
frontend-builder/
├── SKILL.md
├── scripts/
│   ├── init_project.py
│   └── add_component.py
├── references/
│   ├── react-patterns.md
│   └── css-guidelines.md
└── assets/
    ├── templates/
    │   ├── react-app/
    │   └── next-app/
    └── components/
        └── Button.tsx
```
