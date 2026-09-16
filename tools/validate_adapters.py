"""Validate platform adapters without third-party dependencies."""
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKBUDDY = ROOT / 'platforms' / 'workbuddy' / 'soil-county-chronicle'


def frontmatter(path):
    text = path.read_text(encoding='utf-8')
    match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if not match:
        raise ValueError(f'missing YAML frontmatter: {path}')
    fields = {}
    for line in match.group(1).splitlines():
        if ':' in line and not line.startswith((' ', '\t')):
            key, value = line.split(':', 1)
            fields[key.strip()] = value.strip()
    return fields, text[match.end():]


def main():
    fields, body = frontmatter(WORKBUDDY / 'SKILL.md')
    required = {'description', 'description_zh', 'description_en', 'version', 'author'}
    missing = sorted(key for key in required if not fields.get(key))
    if missing:
        raise ValueError(f'WorkBuddy frontmatter missing: {missing}')
    if not re.fullmatch(r'\d+\.\d+\.\d+', fields['version']):
        raise ValueError('WorkBuddy version must be semver')
    for folder in ('references', 'scripts', 'templates/project'):
        if not (WORKBUDDY / folder).is_dir():
            raise ValueError(f'WorkBuddy adapter missing directory: {folder}')
    if '@references/' not in body or 'assets/project' in body:
        raise ValueError('WorkBuddy body resource routing is incomplete')
    metadata = json.loads((WORKBUDDY / 'BUILD-METADATA.json').read_text(encoding='utf-8'))
    if metadata.get('contains_archive') or metadata.get('contains_county_data'):
        raise ValueError('adapter metadata violates repository data boundary')
    forbidden = {'.zip', '.7z', '.rar', '.doc', '.docx', '.pdf', '.xls', '.xlsx', '.shp', '.gpkg'}
    found = [str(path.relative_to(ROOT)) for path in ROOT.rglob('*') if path.is_file() and path.suffix.lower() in forbidden]
    if found:
        raise ValueError(f'forbidden repository artifacts: {found}')
    print('Platform adapters are valid.')


if __name__ == '__main__':
    main()

