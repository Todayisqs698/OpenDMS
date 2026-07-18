# Skill Naming Conventions

## Table of Contents

- [Basic Rules](#basic-rules)
- [Naming Format](#naming-format)
- [Good Naming Examples](#good-naming-examples)
- [Names to Avoid](#names-to-avoid)
- [Special Cases](#special-cases)

## Basic Rules

| Rule | Description |
|------|-------------|
| Lowercase | Use only a-z |
| Numbers | Allowed 0-9, but cannot start with |
| Hyphens | Use `-` to separate words |
| Length | 3-50 characters |
| Descriptive | Name should clearly express functionality |

## Naming Format

```
<function>[-<modifier>][-<version>]
```

### Format Description

1. **Function** (required): Main functionality description
2. **Modifier** (optional): Scope or type qualifier
3. **Version** (optional): Version identifier (only when multiple versions needed)

## Good Naming Examples

### Tool-based

```
pdf-editor          # PDF editor
image-converter     # Image converter
code-formatter      # Code formatter
json-validator      # JSON validator
```

### Workflow-based

```
code-review         # Code review
git-workflow        # Git workflow
release-manager     # Release management
test-runner         # Test execution
```

### Domain-based

```
brand-guidelines    # Brand guidelines
api-integration     # API integration
data-analysis       # Data analysis
ml-pipeline         # Machine learning pipeline
```

### Technology-specific

```
react-components    # React components
next-starter        # Next.js starter
python-utils        # Python utilities
docker-helper       # Docker helper
```

## Names to Avoid

### ❌ Format Violations

| Wrong | Reason | Correct |
|-------|--------|--------|
| `MySkill` | Uses uppercase | `my-skill` |
| `pdf_editor` | Uses underscores | `pdf-editor` |
| `pdfEditor` | Camel case | `pdf-editor` |
| `PDF-Editor` | Uppercase letters | `pdf-editor` |
| `pdf editor` | Contains spaces | `pdf-editor` |

### ❌ Not Descriptive Enough

| Wrong | Reason | Correct |
|-------|--------|--------|
| `tool` | Too generic | `pdf-tool`, `git-tool` |
| `util` | Not specific | `string-utils`, `file-utils` |
| `helper` | Unclear | `deploy-helper`, `test-helper` |
| `v2` | Missing function name | `pdf-editor-v2` |
| `new` | Meaningless | Use function name |

### ❌ Too Long or Redundant

| Wrong | Reason | Correct |
|-------|--------|--------|
| `pdf-file-editor-tool` | Redundant | `pdf-editor` |
| `my-awesome-skill-for-coding` | Too long | `code-assistant` |
| `the-best-formatter` | Subjective words | `code-formatter` |

## Special Cases

### Version Naming

When maintaining multiple versions:

```
pdf-editor          # Main/latest version
pdf-editor-v1       # Legacy version
pdf-editor-legacy   # Deprecated (kept for compatibility)
```

### Variant Naming

Different implementations of same functionality:

```
code-review         # General code review
code-review-strict  # Strict mode
code-review-quick   # Quick mode
```

### Technology Prefix

Skills for specific tech stacks:

```
react-dashboard     # React dashboard
vue-dashboard       # Vue dashboard
next-dashboard      # Next.js dashboard
```

## Naming Checklist

- [ ] All lowercase
- [ ] Words separated by hyphens
- [ ] 3-50 characters
- [ ] Starts with letter
- [ ] Does not end with hyphen
- [ ] No consecutive hyphens
- [ ] Clear and descriptive
- [ ] No subjective adjectives
