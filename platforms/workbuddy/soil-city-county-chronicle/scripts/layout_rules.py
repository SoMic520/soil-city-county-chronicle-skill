"""Validate a declared layout plan against the shipped profile, not a DOCX.

Project-specific departures require exact, confirmed field-level records.
No files are modified and no visual or factual certification is performed.
"""
import math

LOCKED_GROUPS = ('styles', 'execution', 'acceptance_requirements')


def leaves(value, prefix=''):
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(leaves(child, f'{prefix}.{key}' if prefix else key))
        return result
    return {prefix: value}


def finite_number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))


def same_value(a, b):
    # JSON true must not pass as 1, or 0 as false.
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return finite_number(a) and finite_number(b) and a == b
    return type(a) is type(b) and a == b


def text_present(value):
    return isinstance(value, str) and bool(value.strip())


def validate_layout(layout, baseline, final=False):
    if not isinstance(layout, dict):
        raise ValueError('layout.json must be an object')
    issues, notes = [], []
    def issue(code, identity, message):
        issues.append(dict(code=code, id=identity, message=message))
    if layout.get('layout_schema_version') is None:
        message = '旧版/未知排版配置需按三普对齐模板升级，先备份并保留项目约定；资料整理可继续'
        if final:
            issue('LAYOUT_UPGRADE', 'layout_schema_version', message)
        else:
            notes.append(message)
        return issues, notes
    if type(layout['layout_schema_version']) is not int or layout['layout_schema_version'] != baseline['layout_schema_version']:
        raise ValueError('unsupported layout_schema_version')
    if layout.get('format_profile') != baseline['format_profile']:
        issue('LAYOUT_PROFILE', 'format_profile', '未采用声明的三普对齐配置标识')
    level = layout.get('level_profile')
    if not isinstance(level, dict):
        raise ValueError('level_profile must be an object')
    project_level = level.get('project')
    guide_profile = level.get('guide_profile')
    if project_level not in {'municipal', 'county', 'unknown'} or guide_profile not in {'N2-municipal', 'N1-county', 'unknown'}:
        raise ValueError('level_profile values are invalid')
    expected_guide = {'municipal': 'N2-municipal', 'county': 'N1-county'}.get(project_level)
    if expected_guide and guide_profile != expected_guide:
        issue('LAYOUT_LEVEL_MISMATCH', 'level_profile', '成果层级与验收导引配置不一致')
    if final and (not expected_guide or not text_present(level.get('basis'))):
        issue('LAYOUT_LEVEL', 'level_profile', '终稿前须确认市级或县级及适用导引依据')
    if final and project_level == 'municipal' and level.get('municipal_guide_confirmed') is not True:
        issue('LAYOUT_MUNICIPAL_GUIDE', 'level_profile.municipal_guide_confirmed', '市级终稿须以完整N2-municipal或正式项目副本逐项复核排版值')
    expected = leaves({key: baseline[key] for key in LOCKED_GROUPS})
    actual = leaves({key: layout.get(key) for key in LOCKED_GROUPS})
    overrides = layout.get('project_overrides_with_basis', [])
    if not isinstance(overrides, list):
        raise ValueError('project_overrides_with_basis must be a list')
    allowed, seen = {}, set()
    for index, record in enumerate(overrides, 1):
        if not isinstance(record, dict):
            issue('LAYOUT_OVERRIDE', str(index), '例外必须为逐字段记录对象')
            continue
        path = record.get('path')
        if not isinstance(path, str) or path not in expected or path in seen:
            issue('LAYOUT_OVERRIDE', str(index), '例外路径不存在、不是叶字段或重复；不支持通配符')
            continue
        seen.add(path)
        if record.get('confirmed') is not True or record.get('scope') != 'global' or not all(text_present(record.get(k)) for k in ('basis', 'confirmed_by')) or 'value' not in record:
            issue('LAYOUT_OVERRIDE', path, '全局变更缺明确范围、依据或责任方确认；局部对象另登记')
        elif path not in actual or not same_value(record['value'], actual[path]):
            issue('LAYOUT_OVERRIDE', path, '例外值与实际采用配置不一致')
        elif not same_value(record['value'], expected[path]) and type(record['value']) is not type(expected[path]) and not (isinstance(record['value'], (int, float)) and not isinstance(record['value'], bool) and isinstance(expected[path], (int, float)) and not isinstance(expected[path], bool)):
            issue('LAYOUT_OVERRIDE', path, '例外值类型与字段不一致')
        elif isinstance(record['value'], str) and not record['value'].strip():
            issue('LAYOUT_OVERRIDE', path, '例外不能把非空格式字段清空')
        elif not isinstance(record['value'], bool) and isinstance(record['value'], (int, float)) and (not finite_number(record['value']) or record['value'] < 0 or (path.endswith('.pt') and record['value'] == 0) or (path.endswith('.width_percent_of_text_area') and not 0 < record['value'] <= 100)):
            issue('LAYOUT_OVERRIDE', path, '例外数值无效：字号须为正数，宽度须在(0,100]，距离/间隔不能为负')
        else:
            allowed[path] = record
    for path, wanted in expected.items():
        if path not in actual:
            issue('LAYOUT_PROFILE_MISSING', path, '基准字段缺失，不能靠删除绕过要求')
        elif not same_value(actual[path], wanted):
            if path not in allowed:
                issue('LAYOUT_PROFILE_DRIFT', path, f'偏离基准且无有效例外；基准值: {wanted!r}')
            else:
                notes.append(f'{path}: 已登记项目例外；仍须在实际文档复核，依据 {allowed[path]["basis"]}')
    for path in sorted(set(actual) - set(expected)):
        issue('LAYOUT_PROFILE_UNKNOWN', path, '锁定配置出现未知路径；项目补充请写project_details')
    toc_roles = ['chapter', 'level_1', 'level_2', 'level_3', 'level_4']
    toc_max = actual.get('acceptance_requirements.toc_max_depth')
    if type(toc_max) is not int or not 1 <= toc_max <= len(toc_roles):
        issue('LAYOUT_TOC', 'acceptance_requirements.toc_max_depth', '目录最大深度应为1至5的整数；偏离已采纳导引值还须有效逐字段例外')
        toc_max = baseline['acceptance_requirements']['toc_max_depth']
    toc = layout.get('toc_semantic_levels')
    if not isinstance(toc, list) or toc != toc_roles[:len(toc)] or len(toc) > toc_max:
        issue('LAYOUT_TOC', 'toc_semantic_levels', '目录须以章为起点连续选择有序角色数组，默认仅["chapter"]或["chapter","level_1"]，不能用自由文字掩盖五层目录')
    elif final and not toc:
        issue('LAYOUT_TOC_PENDING', 'toc_semantic_levels', '终稿目录实际收录层级尚未选择')
    records = layout.get('preserved_sections_and_objects', [])
    if not isinstance(records, list):
        raise ValueError('preserved_sections_and_objects must be a list')
    ids = set()
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            issue('LAYOUT_PRESERVED', str(index), '保护记录必须为对象')
            continue
        identity = record.get('id')
        if not text_present(identity) or identity in ids or record.get('kind') not in {'section', 'figure', 'table', 'cover'} or not all(text_present(record.get(k)) for k in ('basis', 'geometry_locator')):
            issue('LAYOUT_PRESERVED', str(index), '保护对象缺唯一ID、类型、依据或原几何参数定位')
        else:
            ids.add(identity)
        if final and not text_present(record.get('review_evidence')):
            issue('LAYOUT_PRESERVED_REVIEW', str(index), '保护对象缺实际保全复核证据')
    checks = layout.get('format_checks', {})
    if not isinstance(checks, dict):
        raise ValueError('format_checks must be an object')
    for key in baseline['format_checks']:
        record = checks.get(key, {})
        if not isinstance(record, dict):
            raise ValueError(f'invalid format check: {key}')
        status = record.get('status', 'pending')
        if status not in {'pending', 'passed', 'not_applicable'}:
            issue('LAYOUT_CHECK_STATUS', key, '格式检查状态应为pending/passed/not_applicable')
        if status == 'not_applicable' and (key != 'protected_objects' or records):
            issue('LAYOUT_CHECK_WAIVER', key, '该项不能省略；只有无保护对象时可豁免protected_objects')
        if status in {'passed', 'not_applicable'} and not text_present(record.get('evidence')):
            issue('LAYOUT_CHECK_EVIDENCE', key, '实际检查或不适用处置缺记录')
        if final and status == 'pending':
            issue('LAYOUT_CHECK_PENDING', key, '该排版检查尚未完成')
    details = layout.get('project_details', {})
    if not isinstance(details, dict):
        raise ValueError('project_details must be an object')
    for key in ('header_distance_mm', 'footer_distance_mm'):
        value = details.get(key)
        if value is not None and (not finite_number(value) or value < 0):
            issue('LAYOUT_DETAIL', key, '页眉/页脚距边界应为非负毫米数，不与上下页边距混用')
    if final:
        if layout.get('adoption_confirmed') is not True or not all(text_present(layout.get(k)) for k in ('basis', 'target_application')):
            issue('LAYOUT', 'layout', '采纳依据或目标软件未锁定')
        if not text_present(details.get('table_chinese_font')) or any(details.get(k) is None for k in ('header_distance_mm', 'footer_distance_mm')):
            issue('LAYOUT_DETAILS_PENDING', 'project_details', '终稿需登记实际表格中文字体和独立页眉/页脚距离')
    return issues, notes
