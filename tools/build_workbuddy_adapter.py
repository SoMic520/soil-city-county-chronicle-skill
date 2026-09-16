"""Build a source-only WorkBuddy skill mirror from the canonical repository root.

The generated folder intentionally contains no ZIP and no local project data.
"""
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'platforms' / 'workbuddy' / 'soil-city-county-chronicle'
SOURCE_SKILL = ROOT / 'SKILL.md'


WORKBUDDY_FRONTMATTER = '''---
name: soil-city-county-chronicle
display_name: 三普市县级土壤志撰写与排版
display_name_en: Municipal and County Soil Chronicle Writing
description: 依据已有三普成果报告和地方资料，自动识别市县级并完成土壤志资料核验、证据编纂、篇幅控制、专业审查与规范排版
description_zh: 自动识别市县级，从已有报告形成证据可追溯、篇幅受控、格式规范的土壤志
description_en: Detect municipal or county scope and build evidence-traceable, length-controlled, standards-aligned soil chronicles
category: writing
version: 5.0.0
author: Soil City-County Chronicle Maintainers
user-invocable: true
disable-model-invocation: false
---
'''


def skill_body(text):
    match = re.match(r'^---\r?\n.*?\r?\n---\r?\n', text, re.DOTALL)
    if not match:
        raise ValueError('canonical SKILL.md frontmatter is invalid')
    body = text[match.end():]
    body = re.sub(r'\[([^\]]+)\]\(references/([^)]+)\)', r'\1（@references/\2）', body)
    body = body.replace('[assets/project](assets/project)', '`templates/project`')
    body = body.replace('assets/project', 'templates/project')
    return body


def main():
    if OUTPUT.exists():
        raise ValueError(f'output exists; refusing overwrite: {OUTPUT}')
    OUTPUT.mkdir(parents=True)
    (OUTPUT / 'SKILL.md').write_text(
        WORKBUDDY_FRONTMATTER + '\n' + skill_body(SOURCE_SKILL.read_text(encoding='utf-8')),
        encoding='utf-8',
    )
    shutil.copytree(ROOT / 'references', OUTPUT / 'references')
    shutil.copytree(ROOT / 'scripts', OUTPUT / 'scripts', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'assets' / 'project', OUTPUT / 'templates' / 'project')
    for script in (OUTPUT / 'scripts').glob('*.py'):
        text = script.read_text(encoding='utf-8')
        text = text.replace("ROOT / 'assets' / 'project'", "ROOT / 'templates' / 'project'")
        text = text.replace("ROOT / 'assets/project/", "ROOT / 'templates/project/")
        script.write_text(text, encoding='utf-8')
    metadata = {
        'adapter': 'workbuddy-open-platform',
        'adapter_version': 1,
        'canonical_skill_version': '2026-09-16-r5',
        'workbuddy_skill_version': '5.0.0',
        'source': '../../../SKILL.md',
        'contains_archive': False,
        'contains_local_project_data': False,
    }
    (OUTPUT / 'BUILD-METADATA.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps({'output': str(OUTPUT), 'files': sum(1 for p in OUTPUT.rglob('*') if p.is_file())},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
