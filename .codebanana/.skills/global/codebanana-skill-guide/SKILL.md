---
name: codebanana-skill-guide
description: |
  Complete specification for Skill development and management. Use this skill for CRUD operations on Skills.
  Skills path: .codebanana/.skills/ — create user skills at .codebanana/.skills/<skill-name>/SKILL.md (NEVER inside global/). Before creating, check for name conflicts and rename if needed.
  Triggers:
  - Create: "create skill", "new skill", "init skill"
  - Read: "list skills", "show skills", "view skill"
  - Update: "update skill", "edit skill", "modify skill"
  - Delete: "delete skill", "remove skill"
  - Validate: "validate skill", "check skill"
  - Package: "package skill", "export skill"
---

# Skill Specification

## Important: Skills are inside the workspace

**All skills are stored in the `.codebanana/.skills/` directory inside the current project workspace.**

The `SKILLS_PATH` in `<runtime_config>` points to `.codebanana/.skills/`. Always use this path (or the variable) for creating, reading, updating, and deleting skills. All file tools (`read_file`, `write_file`, `list_dir`, `run_terminal_cmd`) can directly access this directory because it is part of the workspace.

**IMPORTANT: The `global/` subdirectory inside `.codebanana/.skills/` is a system-managed directory containing pre-installed skills. NEVER create, modify, or delete files inside `global/`. User skills must be created directly under `.codebanana/.skills/` (e.g., `.codebanana/.skills/my-skill/SKILL.md`).**

## File Structure

```
workspace/.codebanana/.skills/<skill-name>/
├── SKILL.md              # [Required] Main instruction file
├── scripts/              # [Optional] Executable scripts
│   └── *.py / *.sh
├── references/           # [Optional] Reference docs (loaded on demand)
│   └── *.md
└── assets/               # [Optional] Output resources (templates, images)
    └── *
```

## Naming Convention

| Rule | Correct | Incorrect |
|------|---------|----------|
| Lowercase | `my-skill` | `My-Skill`, `MySkill` |
| Hyphen-separated | `pdf-editor` | `pdf_editor`, `pdfeditor` |
| No spaces | `code-review` | `code review` |
| Descriptive | `git-workflow` | `gw`, `tool1` |

## SKILL.md Specification

### Frontmatter (Required)

```yaml
---
name: <skill-name>        # Required: must match directory name
description: |            # Required: trigger conditions
  Brief description of skill functionality.
  Triggers: list phrases that activate this skill.
---
```

**Key Points:**
- `description` determines when skill is activated
- Must include specific trigger phrases
- Keep under 100 tokens

### Body Structure

```markdown
# Skill Title

## Overview
[1-2 sentences explaining purpose]

## Workflow
[Core steps, numbered list]

## Reference Files
[Links to files in references/]
```

### Length Limits & Content Guidelines

| Component | Limit | Action if Exceeded |
|-----------|-------|--------------------|
| **SKILL.md body** | < 500 lines | Split content into `references/` files |
| **Loaded content** | < 5k words | Keep core workflow in SKILL.md, move details to references |
| **Metadata (frontmatter)** | ~100 words | Be concise, focus on triggers and core functionality |

**Progressive Disclosure Guidelines:**

| Guideline | Rule | Example |
|-----------|------|----------|
| **Reference depth** | Only 1 level deep | Link from SKILL.md → `references/file.md` (no nested links) |
| **Long reference files** | Add TOC if > 100 lines | Place table of contents at top for easy navigation |
| **Large reference files** | Provide grep patterns if > 10k words | Include search patterns in SKILL.md for targeted loading |

**Example: Grep patterns for large files**
```markdown
## Reference Files

- **API Reference** (references/api.md, 15k words)
  - Authentication: grep "auth"
  - Rate limits: grep "rate.*limit"
  - Endpoints: grep "GET\|POST\|PUT\|DELETE"
```

## Skill Creation Workflow

Follow these steps when creating a new skill:

| Step | Action | Details |
|------|--------|----------|
| 1 | **Understand** | Gather concrete examples of how skill will be used |
| 2 | **Plan** | Identify reusable resources (scripts, references, assets) needed |
| 2.5 | **Check name** | List `.codebanana/.skills/` to verify no existing skill has the same name. If conflict, rename (e.g. `pdf-editor` → `pdf-editor-v2`) |
| 3 | **Create** | Use Create operation to generate skill structure |
| 4 | **Implement** | Add resource files and write SKILL.md body |
| 5 | **Test** | Write 2-3 realistic test prompts, run skill sequentially, record outputs |
| 6 | **Evaluate** | Self-check outputs against expected results + collect user feedback |
| 7 | **Iterate** | Fix issues based on feedback, return to Step 5 until satisfied |

**Note:** For detailed instructions on Validate and Package operations, see CRUD Operations section below.

**Quick Start Example:**
```bash
# Steps 1-2: Understand + Plan (manual analysis)
# Example: User wants PDF processing skill with rotate/extract capabilities

# Step 3: Create skill structure
write_file(
  operation: "write",
  path: ".codebanana/.skills/pdf-processor/SKILL.md",
  content: "---\nname: pdf-processor\ndescription: |\n  PDF processing...\n---\n\n# PDF Processor\n..."
)

# Step 4: Implement resources
write_file(
  operation: "write",
  path: ".codebanana/.skills/pdf-processor/scripts/rotate.py",
  content: "#!/usr/bin/env python3\n# Rotate PDF pages\n..."
)

# Step 5-7: Test → Evaluate → Iterate
run_terminal_cmd(
  command: "python scripts/validate_skill.py .codebanana/.skills/pdf-processor"
)
```

### Testing & Evaluation

After creating a skill (Step 5-7), verify it works correctly before publishing.

**Step 5 — Write test prompts:**

Create 2-3 realistic prompts that a real user would say. Cover the main use case and at least one edge case.

```
Test prompts for pdf-processor:
1. "Help me extract all text from quarterly-report.pdf"       (core feature)
2. "Rotate pages 3-5 of my document by 90 degrees"            (specific params)
3. "Merge these three PDF files into one"                      (multi-file edge case)
```

**Step 6 — Run and evaluate:**

Execute each test prompt sequentially using the skill. For each run, check:

| Check | Question |
|-------|----------|
| **Correctness** | Does the output match what the user would expect? |
| **Completeness** | Are all requested operations performed? |
| **Error handling** | Does the skill handle missing files or bad input gracefully? |
| **Efficiency** | Does the skill avoid unnecessary steps or redundant tool calls? |

Present outputs to the user for review. Empty feedback means the output was acceptable.

**Step 7 — Iterate:**

Focus improvements on test cases where issues were found. When modifying the skill:
- Generalize fixes rather than overfitting to specific test cases
- Remove instructions that didn't contribute to better outputs
- If the same helper code was generated in every test run, bundle it as a script

## CRUD Operations

**Important:** Use file tools (`write_file`, `read_file`, `delete_file`, `list_dir`) for skill operations.

### Create

Use `write_file` tool to create SKILL.md (directory is auto-created):
```
write_file(
  operation: "write",
  path: "${SKILLS_PATH}/<skill-name>/SKILL.md",
  content: "---\nname: <skill-name>\ndescription: |\n  Description here.\n  Triggers: ...\n---\n\n# Skill Title\n\n## Workflow\n..."
)
```

After creation, call `load_skill` to use it immediately (no restart needed).

### Read

Use `list_dir` to list skills directory:
```
list_dir(relative_workspace_path: "${SKILLS_PATH}")
```

Use `read_file` to view skill content:
```
read_file(target_file: "${SKILLS_PATH}/<skill-name>/SKILL.md", should_read_entire_file: true)
```

### Update

Use `write_file` with `edit` operation:
```
write_file(
  operation: "edit",
  path: "${SKILLS_PATH}/<skill-name>/SKILL.md",
  old_text: "original text",
  new_text: "updated text"
)
```

Or use `write` operation to replace entire file.

### Delete

Use `delete_file` tool:
```
delete_file(target_file: "${SKILLS_PATH}/<skill-name>/SKILL.md")
```

To delete entire skill directory, delete all files first.

⚠️ **Warning**: Deletion is irreversible. Confirm with user first.

### Validate

Use `run_terminal_cmd` to run validation script:
```
run_terminal_cmd(command: "python ${CURRENT_SKILL_PATH}/scripts/validate_skill.py ${SKILLS_PATH}/<skill-name>")
```

Validation checks:
- [ ] SKILL.md exists
- [ ] Frontmatter format correct (name + description)
- [ ] name field matches directory name
- [ ] description includes trigger phrases
- [ ] Line count < 500

### Package

Use `run_terminal_cmd` to package skill as ZIP:
```
run_terminal_cmd(command: "python ${CURRENT_SKILL_PATH}/scripts/package_skill.py ${SKILLS_PATH}/<skill-name> [output_dir]")
```

Generates `<skill-name>.skill` file (ZIP format) for sharing.

## Resource Files

### scripts/ Directory

For code requiring deterministic execution:

```python
#!/usr/bin/env python3
"""Script description"""
import sys

def main():
    # Implementation
    pass

if __name__ == "__main__":
    main()
```

**Requirements:**
- Add shebang line
- Include docstring
- Handle CLI arguments
- Test after creation

### references/ Directory

For on-demand reference documents:

```markdown
# Reference Title

## Table of Contents
- [Section 1](#section-1)
- [Section 2](#section-2)

## Section 1
...
```

**Requirements:**
- Add TOC for files > 100 lines
- Explain when to read in SKILL.md
- Avoid duplicating SKILL.md content

**CRITICAL - How to reference these files in SKILL.md:**
Always use `${CURRENT_SKILL_PATH}/references/filename.md` — never bare relative paths like `references/filename.md`, which resolve from workspace root and will fail.

```markdown
# ✅ Correct — use CURRENT_SKILL_PATH prefix
Read `${CURRENT_SKILL_PATH}/references/api.md` for full API details.

# ❌ Wrong — bare relative path fails (resolves from workspace root, not skill dir)
Read `references/api.md` for full API details.
```

### assets/ Directory

For output resources:
- Templates (HTML, React, etc.)
- Images, icons
- Font files
- Example documents

**Note:** Assets are not loaded into context, only used for output.

## Files NOT to Include

❌ README.md
❌ CHANGELOG.md
❌ INSTALLATION.md
❌ Human-oriented documentation

Skills are for Agents, not humans.

## Progressive Disclosure

Three-level loading mechanism:

| Level | Content | When Loaded | Size Limit |
|-------|---------|-------------|------------|
| 1 | name + description | Always in context | ~100 tokens |
| 2 | SKILL.md body | On skill trigger | < 5k tokens |
| 3 | references/* | On demand | Unlimited |

## Best Practices

### Writing Principles

| Principle | Rule | Example |
|-----------|------|---------|
| **Concise first** | Only add what the agent doesn't already know; challenge each paragraph's token cost | ❌ "PDF is a common format..." → ✅ Direct code example |
| **Imperative form** | Use direct instructions, not passive descriptions | ❌ "You can use..." → ✅ "Use pdfplumber for extraction" |
| **Explain why** | Prefer reasoning over rigid MUST/NEVER; help the agent understand intent | ❌ "ALWAYS use UTC" → ✅ "Use UTC to avoid timezone bugs in cross-region reports" |
| **Match freedom to fragility** | High freedom for flexible tasks, low freedom for fragile operations | Review guidelines → text instructions; DB migrations → exact scripts |
| **One term, one meaning** | Pick one term and use it throughout | ❌ mixing "URL"/"route"/"endpoint" → ✅ always "endpoint" |

### Writing Descriptions

| Rule | Detail | Example |
|------|--------|---------|
| **WHAT + WHEN** | Description must cover both capability and trigger scenarios | "Extract/rotate/merge PDFs. Use when working with .pdf files or user mentions PDF operations" |
| **Third person** | Description is injected into system prompt context | ❌ "I can process..." → ✅ "Process PDF files and generate reports" |
| **Be specific** | Include concrete trigger terms, not vague categories | ❌ "Handle documents" → ✅ "Extract text, rotate pages, merge/split PDF files" |

```yaml
# ❌ Poor description
description: Process PDF files

# ✅ Good description
description: |
  PDF file processing: extract text, rotate pages, merge/split.
  Triggers:
  - "extract text from PDF"
  - "rotate PDF"
  - "merge PDFs"
  - "split PDF into pages"
```

### Writing Workflows

```markdown
## Workflow

1. **Analyze request** - Determine specific operation needed
2. **Read file** - Use read_file to get content
3. **Execute** - Call appropriate script based on type
4. **Validate** - Check output is correct
5. **Return result** - Display to user
```

### Common Patterns

| Pattern | When to Use | Example |
|---------|-------------|---------|
| **Template** | Output must follow a fixed format | Provide a markdown/code template with `[placeholders]` |
| **Examples** | Output quality depends on seeing input→output pairs | Show 2-3 concrete Input/Output examples |
| **Conditional** | Multiple paths depending on context | "Creating new? → Follow A. Editing existing? → Follow B" |
| **Feedback Loop** | Quality-critical, needs validation | "Execute → Validate → Fix if failed → Proceed only when passed" |

### Anti-Patterns

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| **Too many options** | Agent gets confused choosing | Provide one default + escape hatch for edge cases |
| **Time-sensitive info** | Will become outdated | Use "Current method" vs "Legacy (deprecated)" sections |
| **Vague names** | Hard to discover and distinguish | ❌ `helper`, `utils` → ✅ `pdf-editor`, `git-workflow` |
