"""Build a source-only WorkBuddy skill mirror from the canonical repository root.

The generated folder intentionally contains no ZIP and no county project data.
"""
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'platforms' / 'workbuddy' / 'soil-county-chronicle'
SOURCE_SKILL = ROOT / 'SKILL.md'


WORKBUDDY_FRONTMATTER = '''---
name: soil-county-chronicle
display_name: 三普县级土壤志撰写与排版
display_name_en: County Soil Chronicle Writing and Layout
description: 依据已有三普成果报告和地方资料，完成县级土壤志资料核验、证据编纂、篇幅控制、专业审查与规范排版
description_zh: 从已有报告出发，形成证据可追溯、篇幅受控、格式规范的县级土壤志
description_en: Build evidence-traceable, length-controlled and standards-aligned county soil chronicles from existing survey reports
category: writing
version: 4.0.0
author: Soil County Chronicle Maintainers
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
        'canonical_skill_version': '2026-09-07-r4',
        'workbuddy_skill_version': '4.0.0',
        'source': '../../../SKILL.md',
        'contains_archive': False,
        'contains_county_data': False,
    }
    (OUTPUT / 'BUILD-METADATA.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps({'output': str(OUTPUT), 'files': sum(1 for p in OUTPUT.rglob('*') if p.is_file())},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
