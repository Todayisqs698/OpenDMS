#!/usr/bin/env python3
"""List all Skills

Usage:
    python list_skills.py [--path <skills-dir>] [--validate]

Examples:
    python list_skills.py
    python list_skills.py --path .agent/skills
    python list_skills.py --validate
"""

import argparse
import re
import sys
from pathlib import Path


def parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter"""
    match = re.match(r'^---\s*\n(.+?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return {}
    
    frontmatter = match.group(1)
    result = {}
    
    # Simple parse name
    name_match = re.search(r'^name:\s*(.+?)\s*$', frontmatter, re.MULTILINE)
    if name_match:
        result['name'] = name_match.group(1).strip()
    
    # Simple parse description (may be multiline)
    desc_match = re.search(r'^description:\s*\|?\s*\n?(.*?)(?=^[a-z]|\Z)', frontmatter, re.MULTILINE | re.DOTALL)
    if desc_match:
        desc = desc_match.group(1).strip()
        # Take first line as summary
        first_line = desc.split('\n')[0].strip()
        result['description'] = first_line[:80] + ('...' if len(first_line) > 80 else '')
    
    return result


def get_skill_info(skill_dir: Path) -> dict | None:
    """Get info for a single skill"""
    skill_md = skill_dir / 'SKILL.md'
    if not skill_md.exists():
        return None
    
    try:
        content = skill_md.read_text(encoding='utf-8')
        info = parse_frontmatter(content)
        info['path'] = str(skill_dir)
        info['lines'] = content.count('\n') + 1
        
        # Count resources
        scripts = list((skill_dir / 'scripts').glob('*.py')) if (skill_dir / 'scripts').exists() else []
        refs = list((skill_dir / 'references').glob('*.md')) if (skill_dir / 'references').exists() else []
        assets = list((skill_dir / 'assets').iterdir()) if (skill_dir / 'assets').exists() else []
        
        info['scripts'] = len(scripts)
        info['references'] = len(refs)
        info['assets'] = len(assets)
        
        return info
    except Exception as e:
        return {'name': skill_dir.name, 'error': str(e)}


def find_skills_dir() -> Path | None:
    """Find skills directory"""
    # Try common locations
    candidates = [
        Path('.agent/skills'),
        Path('.claude/skills'),
        Path('skills'),
    ]
    
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    
    return None


def list_skills(skills_dir: Path) -> list[dict]:
    """List all skills in directory"""
    skills = []
    
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and not item.name.startswith('.'):
            info = get_skill_info(item)
            if info:
                skills.append(info)
    
    return skills


def main():
    parser = argparse.ArgumentParser(
        description='List all Skills',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--path', '-p', help='Skills directory path')
    parser.add_argument('--validate', '-v', action='store_true', help='Validate each skill')
    parser.add_argument('--json', '-j', action='store_true', help='Output JSON format')
    
    args = parser.parse_args()
    
    # Determine skills directory
    if args.path:
        skills_dir = Path(args.path).resolve()
    else:
        skills_dir = find_skills_dir()
    
    if not skills_dir or not skills_dir.exists():
        print("❌ Skills directory not found", file=sys.stderr)
        print("   Try: python list_skills.py --path <skills-dir>", file=sys.stderr)
        return 1
    
    skills = list_skills(skills_dir)
    
    if args.json:
        import json
        print(json.dumps(skills, indent=2, ensure_ascii=False))
        return 0
    
    # Table output
    print(f"📁 Skills directory: {skills_dir}")
    print("=" * 70)
    
    if not skills:
        print("   (No skills found)")
        return 0
    
    print(f"{'Name':<20} {'Lines':>6} {'Scripts':>7} {'Refs':>5} {'Description'}")
    print("-" * 70)
    
    for skill in skills:
        if 'error' in skill:
            print(f"❌ {skill['name']:<18} Error: {skill['error']}")
        else:
            name = skill.get('name', '?')
            lines = skill.get('lines', 0)
            scripts = skill.get('scripts', 0)
            refs = skill.get('references', 0)
            desc = skill.get('description', '')[:30]
            
            status = '✅' if lines < 500 else '⚠️'
            print(f"{status} {name:<18} {lines:>6} {scripts:>7} {refs:>5}  {desc}")
    
    print("=" * 70)
    print(f"Total: {len(skills)} skills")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
