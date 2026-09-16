"""Measure and validate template-derived municipal/county chronicle lengths.

The DOCX measurement is read-only. It counts Unicode letters and numbers in
accepted narrative paragraphs; tables, headings, captions and front matter are
excluded. The result is a planning baseline, never evidence of content quality.
"""
import argparse
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
VERSION = 'narrative-effective-characters-v1'
CHAPTERS = ('1', '2', '3', '4', '5', '6')
ADAPTATION_KINDS = {'3':'soil_narrative_units', '4':'property_indicators', '5':'evaluation_modules', '6':'recommendation_topics'}
EXCLUDED_STYLE = re.compile(r'^(heading\s*\d+|标题\s*\d+|toc\s*\d*|目录\s*\d*|caption|题注|table of figures|图表目录|表格标题)', re.I)
CAPTION_TEXT = re.compile(r'^\s*[图表]\s*[一二三四五六七八九十百零〇\d]+(?:\s*[.．—-]\s*\d+)?\s+')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def visible_text(element):
    if element.tag in {W + 'del', W + 'moveFrom'}:
        return ''
    if element.tag in {W + 't', W + 'tab', W + 'br'}:
        return element.text or (' ' if element.tag != W + 't' else '')
    if element.tag in {W + 'instrText', W + 'txbxContent'}:
        return ''
    return ''.join(visible_text(child) for child in element)


def effective_characters(text):
    return sum(unicodedata_category(char)[0] in {'L', 'N'} for char in text)


def unicodedata_category(char):
    # Local import keeps module startup cheap for plan-only validation.
    import unicodedata
    return unicodedata.category(char)


def body_paragraphs(container):
    for child in container:
        if child.tag == W + 'tbl':
            continue
        if child.tag == W + 'p':
            yield child
        else:
            yield from body_paragraphs(child)


def measure_docx(path):
    path = Path(path)
    with ZipFile(path) as archive:
        if not {'word/document.xml', 'word/styles.xml'} <= set(archive.namelist()):
            raise ValueError('DOCX缺document.xml或styles.xml')
        document = ET.fromstring(archive.read('word/document.xml'))
        styles_root = ET.fromstring(archive.read('word/styles.xml'))
    body = document.find(W + 'body')
    if body is None:
        raise ValueError('DOCX正文结构缺失')
    style_names = {}
    for style in styles_root.findall(W + 'style'):
        name = style.find(W + 'name')
        if name is not None:
            style_names[style.get(W + 'styleId', '')] = name.get(W + 'val', '')
    chapters, current = [], None
    before_first_chapter = 0
    for p in body_paragraphs(body):
        text = visible_text(p).strip()
        pstyle = p.find(W + 'pPr/' + W + 'pStyle')
        style_id = pstyle.get(W + 'val', '') if pstyle is not None else ''
        style_name = style_names.get(style_id, style_id)
        if re.fullmatch(r'(heading\s*1|标题\s*1)', style_name.strip(), re.I):
            current = {'id': str(len(chapters) + 1), 'title': text, 'effective_characters': 0,
                       'narrative_paragraphs': 0, 'excluded_paragraphs': 1}
            chapters.append(current)
            continue
        if current is None:
            if text:
                before_first_chapter += 1
            continue
        if not text or EXCLUDED_STYLE.match(style_name.strip()) or CAPTION_TEXT.match(text):
            current['excluded_paragraphs'] += 1
            continue
        units = effective_characters(text)
        if units:
            current['effective_characters'] += units
            current['narrative_paragraphs'] += 1
        else:
            current['excluded_paragraphs'] += 1
    warnings = []
    if len(chapters) != 6:
        warnings.append(f'检测到{len(chapters)}个标题1章，不是市县级土壤志默认六章；须按适用导引人工映射后才能锁定篇幅')
    if any(not row['title'] for row in chapters):
        warnings.append('存在空章标题')
    total = sum(row['effective_characters'] for row in chapters)
    return {
        'kind': 'docx_length_profile_only', 'measurement_version': VERSION,
        'source': {'path': str(path.resolve()), 'sha256': digest(path), 'bytes': path.stat().st_size},
        'exclusions': ['封面及首章前置内容', '标题段', '表格内文字', '图表题注', '页眉页脚', '附件/脚注尾注', '删除和移出修订文字'],
        'chapters': chapters, 'total_effective_characters': total,
        'front_matter_nonempty_paragraphs_excluded': before_first_chapter,
        'warnings': warnings,
        'limitation': '按DOCX结构计量有效字符，不判断事实质量；异常样式、正文表格化或文本框正文须人工复核。'
    }


def number(value, name, integer=False, positive=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name}必须为有限数值')
    if integer and type(value) is not int:
        raise ValueError(f'{name}必须为整数')
    if positive and value <= 0:
        raise ValueError(f'{name}必须大于0')
    return value


def floor_percent(value, percent):
    return value * percent // 100


def ceil_percent(value, percent):
    return (value * percent + 99) // 100


def validate_plan(plan, final=False):
    if not isinstance(plan, dict) or plan.get('length_schema_version') not in {1, 2}:
        raise ValueError('不支持的length_schema_version')
    issues, notes = [], []
    def issue(code, identity, message):
        issues.append({'code': code, 'id': identity, 'message': message})
    schema_version = plan.get('length_schema_version')
    method = plan.get('measurement_version')
    if method != VERSION:
        issue('LENGTH_METHOD', 'measurement_version', '计量口径必须与模板及终稿一致')
    template = plan.get('template', {})
    if not isinstance(template, dict):
        raise ValueError('template必须为对象')
    template_chapters = template.get('chapters', {})
    if not isinstance(template_chapters, dict):
        raise ValueError('template.chapters必须为对象')
    level_profile = plan.get('level_profile', {})
    if schema_version == 1:
        if final:
            issue('LENGTH_LEVEL', 'level_profile', '终稿篇幅计划须迁移到schema 2并记录项目与模板层级')
        else:
            notes.append('旧篇幅计划未记录市县级模板匹配；终稿前须迁移')
    elif not isinstance(level_profile, dict):
        raise ValueError('level_profile必须为对象')
    else:
        project_level = level_profile.get('project')
        template_level = level_profile.get('template')
        allowed_levels = {'municipal', 'county', 'unknown'}
        if project_level not in allowed_levels or template_level not in allowed_levels:
            raise ValueError('level_profile.project/template无效')
        if project_level != 'unknown' and template_level != 'unknown' and project_level != template_level:
            issue('LENGTH_LEVEL_MISMATCH', 'level_profile', '项目与篇幅模板层级不一致，禁止混用市级和县级基线')
        if final and (project_level == 'unknown' or template_level == 'unknown' or not str(level_profile.get('basis', '')).strip()):
            issue('LENGTH_LEVEL', 'level_profile', '终稿须确认项目与模板同层级并记录依据')
    project = plan.get('project_structure', {})
    if not isinstance(project, dict):
        raise ValueError('project_structure必须为对象')
    for key in ('soil_narrative_units', 'soil_classes', 'soil_subgroups', 'soil_genera', 'soil_species', 'property_indicators', 'evaluation_modules', 'recommendation_topics'):
        value = project.get(key)
        if value is not None and (type(value) is not int or value < 0):
            issue('LENGTH_STRUCTURE', key, '结构数量须为非负整数；尚未核定用null')
    formal = plan.get('formal_override', {})
    if not isinstance(formal, dict) or not isinstance(formal.get('active'), bool):
        raise ValueError('formal_override必须为含active布尔值的对象')
    formal_active = formal.get('active') is True
    if formal_active and not all(isinstance(formal.get(k), str) and formal[k].strip() for k in ('basis', 'locator', 'confirmed_by', 'counting_method')):
        issue('LENGTH_FORMAL_OVERRIDE', 'formal_override', '正式篇幅例外缺来源、定位、确认人或计数口径')
        formal_active = False
    elif formal_active and formal.get('counting_method') != VERSION:
        issue('LENGTH_FORMAL_OVERRIDE', 'formal_override.counting_method', '正式例外仍须换算为本计划统一计量口径')
        formal_active = False
    rows = plan.get('chapters', {})
    if not isinstance(rows, dict):
        raise ValueError('chapters必须为对象')
    if set(rows) != set(CHAPTERS):
        issue('LENGTH_CHAPTERS', 'chapters', '须且仅须登记六个基本章')
    targets, actuals = [], []
    for cid in CHAPTERS:
        row = rows.get(cid, {})
        if not isinstance(row, dict):
            issue('LENGTH_ROW', cid, '章篇幅记录必须为对象')
            continue
        try:
            template_value = number(template_chapters.get(cid), f'template.chapters.{cid}', integer=True)
            target = number(row.get('target'), f'chapters.{cid}.target', integer=True)
            lower = number(row.get('lower'), f'chapters.{cid}.lower', integer=True)
            upper = number(row.get('upper'), f'chapters.{cid}.upper', integer=True)
        except ValueError as exc:
            if final or any(row.get(k) is not None for k in ('target', 'lower', 'upper')):
                issue('LENGTH_VALUE', cid, str(exc))
            continue
        if not (lower <= target <= upper):
            issue('LENGTH_RANGE', cid, '下限、目标、上限顺序错误')
        if lower != floor_percent(target, 85) or upper != ceil_percent(target, 115):
            issue('LENGTH_TOLERANCE', cid, '各章允许区间固定为目标值-15%至+15%（整数下取整/上取整）')
        basis = row.get('adaptation_basis')
        if not isinstance(basis, str) or not basis.strip():
            issue('LENGTH_BASIS', cid, '缺模板值到本项目目标值的适配依据')
        if cid in {'1', '2'} and not formal_active and not 0.85 * template_value <= target <= 1.15 * template_value:
            issue('LENGTH_TEMPLATE_DISTANCE', cid, '第一、二章目标原则上不得偏离模板±15%；正式例外须登记')
        if cid in {'3', '4', '5', '6'}:
            if row.get('adaptation_kind') != ADAPTATION_KINDS[cid]:
                issue('LENGTH_ADAPTATION', cid, '可变章未绑定规定的结构计数')
            ref_count = row.get('template_structure_count')
            project_count = project.get(row.get('adaptation_kind'))
            fixed_characters = row.get('template_fixed_characters')
            try:
                ref_count = number(ref_count, f'chapters.{cid}.template_structure_count', integer=True)
                project_count = number(project_count, f'project_structure.{row.get("adaptation_kind")}', integer=True)
                fixed_characters = number(fixed_characters, f'chapters.{cid}.template_fixed_characters', integer=True, positive=False)
                if not 0 <= fixed_characters < template_value:
                    raise ValueError(f'chapters.{cid}.template_fixed_characters必须在[0,模板章字符数)')
                if not isinstance(row.get('template_structure_evidence'), str) or not row['template_structure_evidence'].strip():
                    raise ValueError(f'chapters.{cid}.template_structure_evidence不能为空')
            except ValueError as exc:
                if final:
                    issue('LENGTH_STRUCTURE', cid, str(exc))
            else:
                raw_expected = fixed_characters + (template_value - fixed_characters) * project_count / ref_count
                expected = min(max(raw_expected, template_value * 0.70), template_value * 1.30)
                if not formal_active and not 0.90 * expected <= target <= 1.10 * expected:
                    issue('LENGTH_DENSITY', cid, '按结构单元折算并限制到模板±30%后的目标须在折算值±10%内')
                if not formal_active and not 0.70 * template_value <= target <= 1.30 * template_value:
                    issue('LENGTH_TEMPLATE_DISTANCE', cid, '可变章目标不得偏离可比模板±30%；超出应更换模板或登记书面例外')
        actual = row.get('actual')
        if actual is not None:
            try:
                actual = number(actual, f'chapters.{cid}.actual', integer=True)
                actuals.append(actual)
                if actual < lower or actual > upper:
                    issue('LENGTH_ACTUAL', cid, '实际有效字符数超出已锁定章区间')
            except ValueError as exc:
                issue('LENGTH_ACTUAL', cid, str(exc))
        elif final:
            issue('LENGTH_ACTUAL', cid, '终稿缺本章实际有效字符数')
        targets.append(target)
    if len(targets) == 6:
        total = plan.get('total', {})
        if not isinstance(total, dict):
            raise ValueError('total必须为对象')
        target_total = sum(targets)
        template_total = sum(template_chapters.get(cid, 0) for cid in CHAPTERS)
        if total.get('target') != target_total or total.get('lower') != floor_percent(target_total, 90) or total.get('upper') != ceil_percent(target_total, 110):
            issue('LENGTH_TOTAL_PLAN', 'total', '全志目标须等于六章目标之和，允许区间固定为目标±10%')
        if not formal_active and not 0.80 * template_total <= target_total <= 1.20 * template_total:
            issue('LENGTH_TOTAL_TEMPLATE', 'total', '六章目标合计不得偏离可比模板合计±20%')
        if final and len(actuals) == 6:
            actual_total = sum(actuals)
            if total.get('actual') != actual_total:
                issue('LENGTH_TOTAL_ACTUAL', 'total', '全志实际数不等于六章实际数之和')
            elif not total['lower'] <= actual_total <= total['upper']:
                issue('LENGTH_TOTAL_RANGE', 'total', '全志实际有效字符数超出目标±10%')
            if not formal_active and not 0.75 * template_total <= actual_total <= 1.25 * template_total:
                issue('LENGTH_TOTAL_TEMPLATE', 'total', '终稿六章实际合计不得偏离可比模板合计±25%')
    if final:
        if not all(isinstance(template.get(k), str) and template[k].strip() for k in ('path', 'sha256', 'identity', 'measurement_evidence')):
            issue('LENGTH_TEMPLATE', 'template', '终稿缺模板身份、路径、哈希或计量证据')
        elif not re.fullmatch(r'[0-9a-fA-F]{64}', template['sha256']):
            issue('LENGTH_TEMPLATE', 'template.sha256', '模板SHA-256格式无效')
        if not isinstance(project.get('basis'), str) or not project['basis'].strip():
            issue('LENGTH_STRUCTURE', 'project_structure.basis', '终稿缺模板与本项目结构计数清单定位')
        if plan.get('status') != 'locked':
            issue('LENGTH_STATUS', 'status', '终稿前篇幅契约须锁定')
    else:
        notes.append('篇幅检查只核计量记录；不以达到字数替代资料、土种覆盖和专业质量')
    return issues, notes


def calculate_targets(plan):
    """Return a planning copy with deterministic default targets; never lock it."""
    if not isinstance(plan, dict) or plan.get('length_schema_version') not in {1, 2} or plan.get('measurement_version') != VERSION:
        raise ValueError('篇幅计划版本或计量口径无效')
    result = copy.deepcopy(plan)
    template = result.get('template', {})
    template_chapters = template.get('chapters', {})
    project = result.get('project_structure', {})
    rows = result.get('chapters', {})
    if set(rows) != set(CHAPTERS):
        raise ValueError('须且仅须登记六个基本章')
    targets = []
    for cid in CHAPTERS:
        template_value = number(template_chapters.get(cid), f'template.chapters.{cid}', integer=True)
        row = rows[cid]
        if cid in {'1', '2'}:
            target = template_value
        else:
            if row.get('adaptation_kind') != ADAPTATION_KINDS[cid]:
                raise ValueError(f'chapters.{cid}.adaptation_kind无效')
            ref_count = number(row.get('template_structure_count'), f'chapters.{cid}.template_structure_count', integer=True)
            project_count = number(project.get(row['adaptation_kind']), f'project_structure.{row["adaptation_kind"]}', integer=True)
            fixed = number(row.get('template_fixed_characters'), f'chapters.{cid}.template_fixed_characters', integer=True, positive=False)
            if not 0 <= fixed < template_value:
                raise ValueError(f'chapters.{cid}.template_fixed_characters必须在[0,模板章字符数)')
            if not isinstance(row.get('template_structure_evidence'), str) or not row['template_structure_evidence'].strip():
                raise ValueError(f'chapters.{cid}.template_structure_evidence不能为空')
            raw = fixed + (template_value - fixed) * project_count / ref_count
            bounded = min(max(raw, template_value * 0.70), template_value * 1.30)
            target = math.floor(bounded + 0.5)
        row.update(target=target, lower=floor_percent(target, 85), upper=ceil_percent(target, 115))
        targets.append(target)
    total = sum(targets)
    result['total'] = {'target': total, 'lower': floor_percent(total, 90), 'upper': ceil_percent(total, 110),
                       'actual': result.get('total', {}).get('actual')}
    result['status'] = 'planning'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('measure-docx')
    p.add_argument('path')
    p.add_argument('--output')
    p = sub.add_parser('check-plan')
    p.add_argument('path')
    p.add_argument('--final', action='store_true')
    p = sub.add_parser('calculate-plan')
    p.add_argument('path')
    p.add_argument('--output')
    args = parser.parse_args(argv)
    try:
        if args.command == 'measure-docx':
            result = measure_docx(args.path)
            if args.output:
                output = Path(args.output)
                if output.exists():
                    raise ValueError('输出已存在，拒绝覆盖')
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        elif args.command == 'check-plan':
            plan = json.loads(Path(args.path).read_text(encoding='utf-8-sig'))
            issues, notes = validate_plan(plan, args.final)
            result = {'kind': 'length_plan_check_only', 'measurement_version': VERSION,
                      'issues': issues, 'notes': notes,
                      'limitation': '只核模板、目标和实际计量记录；不判断正文是否真实、完整或高质量。'}
        else:
            plan = json.loads(Path(args.path).read_text(encoding='utf-8-sig'))
            result = calculate_targets(plan)
            if args.output:
                output = Path(args.output)
                if output.exists():
                    raise ValueError('输出已存在，拒绝覆盖')
                output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('issues') else 0
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError, BadZipFile) as exc:
        print(json.dumps({'error': str(exc), 'status': 'input_or_read_error'}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
