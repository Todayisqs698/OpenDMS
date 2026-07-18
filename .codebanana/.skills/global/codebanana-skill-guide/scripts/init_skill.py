#!/usr/bin/env python3
"""Initialize a new Skill

Usage:
    python init_skill.py <skill-name> [--path <output-path>]

Examples:
    python init_skill.py my-skill
    python init_skill.py pdf-editor --path .agent/skills/
"""

import argparse
import os
import re
import sys
from pathlib import Path


def validate_skill_name(name: str) -> tuple[bool, str]:
    """Validate skill name against naming conventions"""
    if not name:
        return False, "Name cannot be empty"
    
    if not re.match(r'^[a-z][a-z0-9-]*$', name):
        return False, "Name must start with lowercase letter, contain only lowercase letters, numbers, and hyphens"
    
    if name.endswith('-'):
        return False, "Name cannot end with hyphen"
    
    if '--' in name:
        return False, "Name cannot contain consecutive hyphens"
    
    if len(name) > 50:
        return False, "Name cannot exceed 50 characters"
    
    return True, "Valid"


def create_skill_template(skill_name: str, base_path: Path) -> Path:
    """Create skill directory structure and template files"""
    skill_dir = base_path / skill_name
    
    # Check if exists
    if skill_dir.exists():
        raise FileExistsError(f"Skill '{skill_name}' already exists at {skill_dir}")
    
    # Create directory structure
    (skill_dir / 'scripts').mkdir(parents=True, exist_ok=True)
    (skill_dir / 'references').mkdir(exist_ok=True)
    (skill_dir / 'assets').mkdir(exist_ok=True)
    
    # Create SKILL.md template
    skill_md_content = f'''---
name: {skill_name}
description: |
  [TODO: Brief description of this skill's functionality]
  Triggers:
  - "[TODO: Add trigger phrase 1]"
  - "[TODO: Add trigger phrase 2]"
---

# {skill_name.replace('-', ' ').title()}

## Overview

[TODO: Describe the purpose and functionality of this skill]

## Workflow

1. **Step 1** - [TODO: Description]
2. **Step 2** - [TODO: Description]
3. **Step 3** - [TODO: Description]

## Reference Files

- [Reference doc](references/reference.md) - [TODO: Describe when to use]
'''
    
    (skill_dir / 'SKILL.md').write_text(skill_md_content, encoding='utf-8')
    
    # Create example reference file
    reference_content = '''# Reference Document

## Table of Contents

- [Section 1](#section-1)
- [Section 2](#section-2)

## Section 1

[TODO: Add detailed reference content]

## Section 2

[TODO: Add more content]
'''
    
    (skill_dir / 'references' / 'reference.md').write_text(reference_content, encoding='utf-8')
    
    # Create example script
    script_content = '''#!/usr/bin/env python3
"""Example script

Usage:
    python example.py <args>
"""

import sys


def main():
    """Main function"""
    # TODO: Implement script logic
    print("Hello from example script!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''
    
    script_path = skill_dir / 'scripts' / 'example.py'
    script_path.write_text(script_content, encoding='utf-8')
    script_path.chmod(0o755)
    
    return skill_dir


def main():
    parser = argparse.ArgumentParser(
        description='Initialize a new Skill',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s my-skill                    # Create in current directory
  %(prog)s pdf-editor --path ./skills  # Specify output path
        '''
    )
    parser.add_argument('name', help='Skill name (lowercase, numbers, hyphens)')
    parser.add_argument('--path', '-p', default='.', help='Output directory path (default: current directory)')
    
    args = parser.parse_args()
    
    # Validate name
    valid, message = validate_skill_name(args.name)
    if not valid:
        print(f"❌ Error: {message}", file=sys.stderr)
        print(f"   Naming rules: Start with lowercase, only lowercase letters, numbers, and hyphens", file=sys.stderr)
        print(f"   Examples: my-skill, pdf-editor, code-review", file=sys.stderr)
        return 1
    
    # Create skill
    try:
        base_path = Path(args.path).resolve()
        skill_dir = create_skill_template(args.name, base_path)
        
        print(f"✅ Skill '{args.name}' created successfully!")
        print(f"")
        print(f"📁 Directory structure:")
        print(f"   {skill_dir}/")
        print(f"   ├── SKILL.md           # Main instruction file (edit this)")
        print(f"   ├── scripts/")
        print(f"   │   └── example.py     # Example script (modify/delete)")
        print(f"   ├── references/")
        print(f"   │   └── reference.md   # Reference doc (modify/delete)")
        print(f"   └── assets/            # Resource files (empty)")
        print(f"")
        print(f"📝 Next steps:")
        print(f"   1. Edit [TODO] sections in SKILL.md")
        print(f"   2. Fill in description and triggers")
        print(f"   3. Write the workflow")
        print(f"   4. Validate: python validate_skill.py {skill_dir}")
        
        return 0
        
    except FileExistsError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Creation failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
