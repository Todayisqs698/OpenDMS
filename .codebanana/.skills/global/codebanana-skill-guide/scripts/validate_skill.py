#!/usr/bin/env python3
"""Validate Skill format

Usage:
    python validate_skill.py <skill-path>

Examples:
    python validate_skill.py .agent/skills/my-skill
"""

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


class ValidationResult(NamedTuple):
    passed: bool
    message: str
    severity: str  # 'error', 'warning', 'info'


def validate_skill(skill_path: Path) -> list[ValidationResult]:
    """Validate skill directory"""
    results = []
    
    # 1. Check directory exists
    if not skill_path.exists():
        results.append(ValidationResult(False, f"Directory not found: {skill_path}", "error"))
        return results
    
    if not skill_path.is_dir():
        results.append(ValidationResult(False, f"Not a directory: {skill_path}", "error"))
        return results
    
    results.append(ValidationResult(True, "Directory exists", "info"))
    
    # 2. Check SKILL.md exists
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        results.append(ValidationResult(False, "SKILL.md file not found", "error"))
        return results
    
    results.append(ValidationResult(True, "SKILL.md exists", "info"))
    
    # 3. Read and parse SKILL.md
    try:
        content = skill_md.read_text(encoding='utf-8')
    except Exception as e:
        results.append(ValidationResult(False, f"Cannot read SKILL.md: {e}", "error"))
        return results
    
    # 4. Check frontmatter
    frontmatter_match = re.match(r'^---\s*\n(.+?)\n---\s*\n', content, re.DOTALL)
    if not frontmatter_match:
        results.append(ValidationResult(False, "Missing YAML frontmatter (---)", "error"))
    else:
        frontmatter = frontmatter_match.group(1)
        results.append(ValidationResult(True, "Frontmatter format correct", "info"))
        
        # 5. Check name field
        name_match = re.search(r'^name:\s*(.+?)\s*$', frontmatter, re.MULTILINE)
        if not name_match:
            results.append(ValidationResult(False, "Missing 'name' field", "error"))
        else:
            name_value = name_match.group(1).strip()
            skill_dir_name = skill_path.name
            
            if name_value != skill_dir_name:
                results.append(ValidationResult(
                    False, 
                    f"name field '{name_value}' does not match directory name '{skill_dir_name}'", 
                    "error"
                ))
            else:
                results.append(ValidationResult(True, f"name field correct: {name_value}", "info"))
            
            # Validate naming convention
            if not re.match(r'^[a-z][a-z0-9-]*$', name_value):
                results.append(ValidationResult(
                    False,
                    f"name '{name_value}' violates naming convention (must start with lowercase, contain only lowercase, numbers, hyphens)",
                    "error"
                ))
        
        # 6. Check description field
        desc_match = re.search(r'^description:\s*(.+?)(?=^[a-z]|\Z)', frontmatter, re.MULTILINE | re.DOTALL)
        if not desc_match:
            results.append(ValidationResult(False, "Missing 'description' field", "error"))
        else:
            desc_value = desc_match.group(1).strip()
            if len(desc_value) < 10:
                results.append(ValidationResult(False, "description too short (minimum 10 characters)", "error"))
            elif len(desc_value) < 50:
                results.append(ValidationResult(True, "description is short, consider adding more triggers", "warning"))
            else:
                results.append(ValidationResult(True, "description length adequate", "info"))
    
    # 7. Check line count
    lines = content.count('\n') + 1
    if lines > 500:
        results.append(ValidationResult(
            False, 
            f"SKILL.md line count ({lines}) exceeds 500 line limit, split into references/", 
            "error"
        ))
    elif lines > 400:
        results.append(ValidationResult(
            True, 
            f"SKILL.md line count ({lines}) approaching limit, consider splitting", 
            "warning"
        ))
    else:
        results.append(ValidationResult(True, f"SKILL.md line count: {lines}", "info"))
    
    # 8. Check TODO markers
    todo_count = content.count('[TODO')
    if todo_count > 0:
        results.append(ValidationResult(
            True, 
            f"Found {todo_count} incomplete [TODO] markers", 
            "warning"
        ))
    
    # 9. Check referenced files exist
    ref_links = re.findall(r'\[.+?\]\(references/(.+?)\)', content)
    for ref_file in ref_links:
        ref_path = skill_path / 'references' / ref_file
        if not ref_path.exists():
            results.append(ValidationResult(
                False, 
                f"Referenced file not found: references/{ref_file}", 
                "error"
            ))
        else:
            results.append(ValidationResult(True, f"Referenced file exists: references/{ref_file}", "info"))
    
    # 10. Check script files
    scripts_dir = skill_path / 'scripts'
    if scripts_dir.exists():
        for script in scripts_dir.glob('*.py'):
            script_content = script.read_text(encoding='utf-8')
            if not script_content.startswith('#!'):
                results.append(ValidationResult(
                    True, 
                    f"Script {script.name} missing shebang line", 
                    "warning"
                ))
            if '"""' not in script_content and "'''" not in script_content:
                results.append(ValidationResult(
                    True, 
                    f"Script {script.name} missing docstring", 
                    "warning"
                ))
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Validate Skill format',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('path', help='Skill directory path')
    parser.add_argument('--strict', '-s', action='store_true', help='Strict mode: treat warnings as failures')
    
    args = parser.parse_args()
    skill_path = Path(args.path).resolve()
    
    print(f"🔍 Validating Skill: {skill_path}")
    print("=" * 50)
    
    results = validate_skill(skill_path)
    
    errors = [r for r in results if r.severity == 'error' and not r.passed]
    warnings = [r for r in results if r.severity == 'warning']
    passed = [r for r in results if r.passed and r.severity == 'info']
    
    # Display results
    for r in results:
        if r.severity == 'error' and not r.passed:
            print(f"❌ {r.message}")
        elif r.severity == 'warning':
            print(f"⚠️  {r.message}")
        elif r.passed and r.severity == 'info':
            print(f"✅ {r.message}")
    
    print("=" * 50)
    
    # Summary
    if errors:
        print(f"\n❌ Validation failed: {len(errors)} errors, {len(warnings)} warnings")
        return 1
    elif warnings and args.strict:
        print(f"\n⚠️  Strict mode: {len(warnings)} warnings need fixing")
        return 1
    elif warnings:
        print(f"\n✅ Validation passed (with {len(warnings)} warnings)")
        return 0
    else:
        print(f"\n✅ Validation passed! Skill format is correct.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
