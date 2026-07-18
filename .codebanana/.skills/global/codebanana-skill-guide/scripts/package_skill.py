#!/usr/bin/env python3
"""Package a Skill for distribution

Usage:
    python package_skill.py <skill-path> [output-dir]

Examples:
    python package_skill.py .agent/skills/my-skill
    python package_skill.py .agent/skills/my-skill ./dist

Output:
    Generates <skill-name>.skill file (ZIP format)
"""

import argparse
import os
import re
import sys
import zipfile
from pathlib import Path
from datetime import datetime


def validate_skill_quick(skill_path: Path) -> tuple[bool, list[str]]:
    """Quick validation of skill basic requirements"""
    errors = []
    
    # Check directory
    if not skill_path.exists():
        errors.append(f"Directory not found: {skill_path}")
        return False, errors
    
    # Check SKILL.md
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        errors.append("Missing SKILL.md file")
        return False, errors
    
    # Check frontmatter
    content = skill_md.read_text(encoding='utf-8')
    if not re.match(r'^---\s*\n.+?\n---\s*\n', content, re.DOTALL):
        errors.append("SKILL.md missing YAML frontmatter")
    
    # Check name field
    name_match = re.search(r'^name:\s*(.+?)\s*$', content, re.MULTILINE)
    if not name_match:
        errors.append("Missing 'name' field")
    else:
        name = name_match.group(1).strip()
        if name != skill_path.name:
            errors.append(f"name '{name}' does not match directory name '{skill_path.name}'")
    
    # Check description field
    if 'description:' not in content:
        errors.append("Missing 'description' field")
    
    # Check line count
    lines = content.count('\n') + 1
    if lines > 500:
        errors.append(f"SKILL.md line count ({lines}) exceeds 500 line limit")
    
    # Check TODO
    if '[TODO' in content:
        errors.append("SKILL.md still contains incomplete [TODO] markers")
    
    return len(errors) == 0, errors


def package_skill(skill_path: Path, output_dir: Path) -> Path:
    """Package skill as .skill file"""
    skill_name = skill_path.name
    output_file = output_dir / f"{skill_name}.skill"
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create ZIP file
    with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in skill_path.rglob('*'):
            if file_path.is_file():
                # Skip hidden files and __pycache__
                if any(part.startswith('.') or part == '__pycache__' 
                       for part in file_path.parts):
                    continue
                
                # Calculate relative path
                arc_name = file_path.relative_to(skill_path)
                zf.write(file_path, arc_name)
    
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Package Skill for distribution',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Output format:
  .skill file is ZIP format, can be extracted directly.
  
Examples:
  %(prog)s .agent/skills/my-skill          # Output to current directory
  %(prog)s .agent/skills/my-skill ./dist   # Output to dist directory
        '''
    )
    parser.add_argument('path', help='Skill directory path')
    parser.add_argument('output', nargs='?', default='.', help='Output directory (default: current directory)')
    parser.add_argument('--force', '-f', action='store_true', help='Skip validation and force package')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode')
    
    args = parser.parse_args()
    
    skill_path = Path(args.path).resolve()
    output_dir = Path(args.output).resolve()
    
    if not args.quiet:
        print(f"📦 Packaging Skill: {skill_path.name}")
        print("=" * 50)
    
    # Validate
    if not args.force:
        valid, errors = validate_skill_quick(skill_path)
        if not valid:
            print("❌ Validation failed, cannot package:", file=sys.stderr)
            for err in errors:
                print(f"   - {err}", file=sys.stderr)
            print("\nUse --force to skip validation (not recommended)", file=sys.stderr)
            return 1
        
        if not args.quiet:
            print("✅ Validation passed")
    
    # Package
    try:
        output_file = package_skill(skill_path, output_dir)
        
        # Get file size
        size = output_file.stat().st_size
        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
        
        if not args.quiet:
            print(f"✅ Packaging successful!")
            print(f"")
            print(f"📄 Output file: {output_file}")
            print(f"📊 File size: {size_str}")
            print(f"📅 Packaged at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"")
            print(f"Usage:")
            print(f"  1. Share {output_file.name} file")
            print(f"  2. Recipient extracts to .agent/skills/ directory")
            print(f"     unzip {output_file.name} -d .agent/skills/{skill_path.name}")
        else:
            print(output_file)
        
        return 0
        
    except Exception as e:
        print(f"❌ Packaging failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
