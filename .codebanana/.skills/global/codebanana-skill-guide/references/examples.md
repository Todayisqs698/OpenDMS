# Skill Examples Collection

## Table of Contents

- [Simple Skill Example](#simple-skill-example)
- [Skill with Scripts](#skill-with-scripts)
- [Full Skill Example](#full-skill-example)
- [Description Writing Examples](#description-writing-examples)

## Simple Skill Example

### code-review (Code Review)

**Structure:**
```
code-review/
└── SKILL.md
```

**SKILL.md:**
```markdown
---
name: code-review
description: |
  Perform code review, checking code quality and potential issues.
  Triggers:
  - "review this code"
  - "check this PR"
  - "audit this file"
  - "code quality check"
---

# Code Review

## Workflow

1. **Read code** - Read target file completely
2. **Checklist** - Check by category
   - 🔴 Critical: Security vulnerabilities, logic errors
   - 🟡 Warning: Performance issues, maintainability
   - 🔵 Suggestion: Code style, best practices
3. **Output report** - List issues by priority

## Output Format

### Summary
[1-2 sentence summary]

### Findings
| Line | Level | Issue | Suggestion |
|------|-------|-------|------------|
| 42 | 🔴 | SQL injection risk | Use parameterized queries |
```

---

## Skill with Scripts

### json-validator (JSON Validator)

**Structure:**
```
json-validator/
├── SKILL.md
└── scripts/
    └── validate.py
```

**SKILL.md:**
```markdown
---
name: json-validator
description: |
  Validate JSON file format and schema.
  Triggers:
  - "validate JSON"
  - "check JSON format"
  - "verify JSON schema"
---

# JSON Validator

## Workflow

1. Read target JSON file
2. Run validation script: `python scripts/validate.py <file>`
3. Report validation results

## Script Usage

```bash
python scripts/validate.py input.json                 # Basic validation
python scripts/validate.py input.json --schema s.json # Schema validation
```
```

**scripts/validate.py:**
```python
#!/usr/bin/env python3
"""JSON validation script"""
import json
import sys
import argparse

def validate_json(file_path, schema_path=None):
    try:
        with open(file_path) as f:
            data = json.load(f)
        print(f"✅ JSON format valid")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ JSON format error: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('file', help='JSON file path')
    parser.add_argument('--schema', help='Schema file path')
    args = parser.parse_args()
    sys.exit(0 if validate_json(args.file, args.schema) else 1)
```

---

## Full Skill Example

### pdf-editor (PDF Editor)

**Structure:**
```
pdf-editor/
├── SKILL.md
├── scripts/
│   ├── rotate.py
│   ├── merge.py
│   └── extract.py
├── references/
│   └── operations.md
└── assets/
    └── watermark.png
```

**SKILL.md:**
```markdown
---
name: pdf-editor
description: |
  PDF file processing: rotate, merge, split, extract text.
  Triggers:
  - "rotate PDF"
  - "merge PDFs"
  - "split PDF"
  - "extract text from PDF"
---

# PDF Editor

## Workflow

1. **Determine operation type**
   - Rotate → `scripts/rotate.py`
   - Merge → `scripts/merge.py`
   - Extract → `scripts/extract.py`

2. **Execute operation**
   ```bash
   python scripts/rotate.py input.pdf 90
   python scripts/merge.py file1.pdf file2.pdf -o output.pdf
   python scripts/extract.py input.pdf
   ```

3. **Return results**

## References

- See [references/operations.md](references/operations.md) for detailed operation guide
```

---

## Description Writing Examples

### ❌ Poor Descriptions

```yaml
# Too short, no triggers
description: Process PDF files

# Too vague
description: A useful tool

# No specific triggers
description: Process and edit PDF files
```

### ✅ Good Descriptions

```yaml
# Clear structure with triggers
description: |
  PDF file processing: rotate, merge, split, extract text.
  Triggers:
  - "rotate PDF"
  - "merge PDFs"
  - "extract text"
  - "split PDF into pages"

# Multiple scenarios covered
description: |
  Code review and quality checks. Use cases:
  - Review PR code
  - Check security vulnerabilities
  - Evaluate code quality
  Triggers: "review code", "check PR", "code audit", "quality check"

# Clear boundaries
description: |
  Git workflow management: branching, commits, merging.
  Applies to: Daily Git operation guidance
  Not for: Git server configuration, CI/CD setup
  Triggers: "git workflow", "branch strategy", "git operations"
```

---

## Quick Templates

### Minimal Skill

```markdown
---
name: my-skill
description: |
  [Function description]
  Triggers: "keyword1", "keyword2", "keyword3"
---

# My Skill

## Workflow

1. Step 1
2. Step 2
3. Step 3
```

### Skill with Resources

```markdown
---
name: my-skill
description: |
  [Function description]
  Triggers: "keyword1", "keyword2"
---

# My Skill

## Workflow

1. Step 1 - Use `scripts/process.py`
2. Step 2 - Reference `references/guide.md`
3. Step 3 - Output using `assets/template.html`

## Scripts

- `scripts/process.py` - Data processing

## References

- [Detailed guide](references/guide.md)
```
