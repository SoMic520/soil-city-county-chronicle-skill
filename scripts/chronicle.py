"""Read-only record/OOXML checks and non-overwriting project initialization.

Standard library only. Success never certifies soil science or rendered layout.
"""
import argparse
import csv
import json
import posixpath
import re
import shutil
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile, BadZipFile
import xml.etree.ElementTree as ET
from layout_rules import validate_layout
from length_profile import validate_plan as validate_length_plan

ROOT = Path(__file__).resolve().parents[1]
TOOL_VERSION = '2026-09-07-r4'
TOPIC_STATES = {'applicable_available', 'applicable_missing', 'not_applicable', 'unknown'}
SECTION_STATES = {'materials', 'drafting', 'review_ready', 'final'}
DIMENSIONS = ('scope', 'land_use', 'depth', 'indicator', 'method', 'unit', 'sampling_statistic', 'classification')
REVIEWS = ('coverage', 'data_and_sources', 'professional_review', 'target_app_reopened', 'fields_updated', 'all_pages_rendered_reviewed', 'baseline_and_regression')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
OPTIONAL_COLUMNS = {'evidence.csv': {'depends_on'}, 'figures.csv': {'kind'}, 'requirements.csv': {'reuse_basis'}}
CT = '{http://schemas.openxmlformats.org/package/2006/content-types}'
PR = '{http://schemas.openxmlformats.org/package/2006/relationships}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
DOCX_TYPE = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'


def split_ids(value):
    return [v.strip() for v in value.split('|') if v.strip()]


def number(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not a number')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'invalid decimal: {value}') from exc
    if not result.is_finite():
        raise ValueError('non-finite number')
    return result


def table(folder, name, key):
    template = ROOT / 'assets' / 'project' / name
    with template.open(encoding='utf-8-sig', newline='') as f:
        expected = next(csv.reader(f))
    with (folder / name).open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        required = set(expected) - OPTIONAL_COLUMNS.get(name, set())
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not required <= set(reader.fieldnames):
            raise ValueError(f'{name}: missing or duplicate header')
        rows = {}
        for line, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'{name}:{line}: malformed row')
            row = {k: v.strip() for k, v in row.items()}
            for col in OPTIONAL_COLUMNS.get(name, set()):
                row.setdefault(col, '')
            if not any(row.values()):
                continue
            identity = row[key]
            if not identity or identity in rows:
                raise ValueError(f'{name}:{line}: empty/duplicate {key}')
            rows[identity] = row
        return rows


def check_project(folder, final=False):
    folder = Path(folder)
    data = json.loads((folder / 'project.json').read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != 1:
        raise ValueError('unsupported schema_version')
    issues, notes = [], []
    def issue(code, identity, message):
        issues.append({'code': code, 'id': identity, 'message': message})
    p = data['project']
    for key in ('county', 'scope', 'period'):
        if not p.get(key):
            issue('PROJECT', key, '项目范围字段未填写')
    topics = data['topics']
    for identity, topic in topics.items():
        status = topic['status']
        if status not in TOPIC_STATES:
            raise ValueError(f'unknown topic status: {identity}')
        if status != 'unknown' and not topic.get('basis'):
            issue('TOPIC_BASIS', identity, '专题处置缺依据')
        if status == 'applicable_missing':
            issue('TOPIC_GAP', identity, '适用专题资料缺失；仅限制受影响内容')
        elif status == 'unknown':
            if final:
                issue('TOPIC_UNKNOWN', identity, '终稿前应确认专题适用性')
            else:
                notes.append(f'{identity}: 是否开展未明，其他有据章节可推进')
    sections = {}
    for s in data['sections']:
        identity = s['id']
        if not isinstance(identity, str) or not identity or identity in sections:
            raise ValueError('empty/duplicate/non-string section id')
        if s['status'] not in SECTION_STATES or not isinstance(s['required_claim_ids'], list):
            raise ValueError(f'invalid section: {identity}')
        if any(not isinstance(e, str) or not e.strip() for e in s['required_claim_ids']):
            raise ValueError(f'invalid required_claim_ids: {identity}')
        sections[identity] = s
        topic_id = s.get('topic_id')
        if topic_id and topic_id not in topics:
            issue('TOPIC_REF', identity, '章节引用的专题不存在')
        if identity in {'1', '2', '3', '4', '5', '6'} and topic_id:
            issue('CORE_TOPIC', identity, '六个基本章不能整体设为可选专题')
    sources = table(folder, 'sources.csv', 'source_id')
    evidence = table(folder, 'evidence.csv', 'evidence_id')
    metrics = table(folder, 'metrics.csv', 'metric_id')
    comparisons = table(folder, 'comparisons.csv', 'comparison_id')
    conflicts = table(folder, 'conflicts.csv', 'conflict_id')
    figures = table(folder, 'figures.csv', 'figure_id')
    calculations = json.loads((folder / 'checks.json').read_text(encoding='utf-8-sig'))
    if not isinstance(calculations, list):
        raise ValueError('checks.json must be a list')
    length_path = folder / 'length-plan.json'
    if length_path.exists():
        length_plan = json.loads(length_path.read_text(encoding='utf-8-sig'))
        length_issues, length_notes = validate_length_plan(length_plan, final=final)
        issues.extend(length_issues)
        notes.extend(length_notes)
    elif final:
        issue('LENGTH_FILE', 'length-plan.json', '终稿缺模板驱动的篇幅契约')
    else:
        notes.append('旧项目暂缺length-plan.json；局部资料工作可继续，终稿前须补建并锁定篇幅契约')
    calculation_graph = {}
    for i, calc in enumerate(calculations, 1):
        try:
            result_id, inputs = calculation_ids(calc)
            if result_id in calculation_graph:
                issue('CALCULATION_DUPLICATE', result_id, '同一结果指标有多个计算定义')
            else:
                calculation_graph[result_id] = inputs
        except (KeyError, ValueError, TypeError) as exc:
            issue('ARITHMETIC_SCHEMA', str(i), str(exc))
    used_sources = {sid for e in evidence.values() if e['status'] == 'verified' for sid in split_ids(e['source_ids'])}
    used_metrics = {mid for e in evidence.values() if e['status'] == 'verified' for mid in split_ids(e['metric_ids'])}
    pending = list(used_metrics)
    while pending:
        for mid in calculation_graph.get(pending.pop(), []):
            if mid not in used_metrics:
                used_metrics.add(mid)
                pending.append(mid)
    dependency_checks({mid: {'depends_on': '|'.join(inputs), 'status': 'verified'} for mid, inputs in calculation_graph.items()} |
                      {mid: {'depends_on': '', 'status': 'verified'} for mid in metrics if mid not in calculation_graph},
                      lambda code, identity, message: issue('CALCULATION_' + code, identity, message))
    used_sources.update(m['source_id'] for mid, m in metrics.items() if mid in used_metrics)
    used_sources.update(f['source_id'] for f in figures.values() if f['status'] == 'verified')

    for identity, s in sources.items():
        if s['status'] not in {'catalogued', 'extracted', 'verified', 'rejected'} or s['qc'] not in {'confirmed', 'unknown', 'not_applicable'}:
            raise ValueError(f'invalid source status: {identity}')
        if s['status'] == 'verified':
            if not all(s[k] for k in ('title', 'path', 'version', 'coverage')):
                issue('SOURCE_FIELDS', identity, '已核对来源缺名称、路径、版本或可用范围')
            if s['qc'] in {'confirmed', 'not_applicable'} and not s['qc_basis']:
                issue('QC_BASIS', identity, '质量状态/不适用缺依据')
            if final and identity in used_sources and s['qc'] == 'unknown':
                issue('QC_UNKNOWN', identity, '在用来源的质量/验收状态未确认')

    for identity, c in comparisons.items():
        if c['status'] not in {'verified', 'incomparable', 'unknown'}:
            raise ValueError(f'invalid comparison status: {identity}')
        if any(c[k] not in {'same', 'harmonized', 'incomparable', 'unknown'} for k in DIMENSIONS):
            raise ValueError(f'invalid comparison dimension: {identity}')
        if c['status'] == 'verified' and (any(c[k] not in {'same', 'harmonized'} for k in DIMENSIONS) or not c['basis']):
            issue('COMPARABILITY', identity, '可比状态与逐项证据不一致')

    for identity, m in metrics.items():
        if not all(m[k] for k in ('definition', 'unit', 'scope', 'population', 'period', 'depth', 'method', 'statistic', 'n_valid', 'denominator', 'source_id', 'locator')):
            issue('METRIC_FIELDS', identity, '指标口径或定位缺字段；不适用填NA并解释')
        if m['source_id'] not in sources:
            issue('SOURCE_REF', identity, '指标来源ID不存在')
        elif identity in used_metrics and sources[m['source_id']]['status'] != 'verified':
            issue('METRIC_SOURCE', identity, '在用指标或计算输入的来源未核对/已拒绝')
        if m['value']:
            number(m['value'])
        elif identity in used_metrics:
            issue('METRIC_VALUE', identity, '在用数值指标没有原值；不能当作0')
        if m['display_decimals'] and (not m['display_decimals'].isdigit() or int(m['display_decimals']) > 12):
            raise ValueError(f'invalid display precision: {identity}')
        if m['n_valid'] not in {'', 'NA'} and (not m['n_valid'].isdigit()):
            raise ValueError(f'invalid n_valid: {identity}')

    for identity, e in evidence.items():
        if e['status'] not in {'draft', 'verified', 'withheld'} or e['kind'] not in {'observed', 'derived', 'historical', 'inference', 'recommendation'}:
            raise ValueError(f'invalid evidence status/kind: {identity}')
        if e['quantitative_comparison'] not in {'yes', 'no'}:
            raise ValueError(f'quantitative_comparison must be yes/no: {identity}')
        if e['section_id'] not in sections:
            issue('SECTION_REF', identity, '主张章节不存在')
        if final and e['status'] == 'draft':
            issue('DRAFT_CLAIM', identity, '终稿仍有待核主张；核定或明确暂不用')
        if e['status'] != 'verified':
            continue
        if not all(e[k] for k in ('claim', 'locator')) or not split_ids(e['source_ids']):
            issue('EVIDENCE_FIELDS', identity, '已核对主张缺来源/位置/内容')
        if e['kind'] == 'derived' and not split_ids(e['metric_ids']):
            issue('DERIVED_METRICS', identity, '计算主张缺指标/计算记录')
        elif e['kind'] == 'derived' and not any(mid in calculation_graph for mid in split_ids(e['metric_ids'])):
            issue('DERIVED_CALCULATION', identity, '本次计算主张缺checks中的结果公式；既有报告统计量应按报告记载登记')
        for source_id in split_ids(e['source_ids']):
            if source_id not in sources or sources[source_id]['status'] != 'verified':
                issue('SOURCE_REF', identity, f'来源未核对或不存在: {source_id}')
        for metric_id in split_ids(e['metric_ids']):
            if metric_id not in metrics:
                issue('METRIC_REF', identity, f'指标不存在: {metric_id}')
            elif sources.get(metrics[metric_id]['source_id'], {}).get('status') != 'verified':
                issue('METRIC_SOURCE', identity, f'指标来源未核对: {metric_id}')
        if e['quantitative_comparison'] == 'yes':
            comparison_metrics = set(split_ids(e['metric_ids']))
            if len(comparison_metrics) < 2:
                issue('HISTORY_METRICS', identity, '定量历史比较至少登记基期与现期两个指标ID，不能仅勾选可比')
            elif comparison_metrics <= set(metrics) and len({metrics[mid]['period'] for mid in comparison_metrics}) < 2:
                issue('HISTORY_PERIOD', identity, '历史比较未区分两期指标；在可比性依据中定位基期、现期及比较关系')
            h = comparisons.get(e['comparison_id'])
            if not h or h['status'] != 'verified' or any(h[k] not in {'same', 'harmonized'} for k in DIMENSIONS) or not h['basis']:
                issue('HISTORY', identity, '定量历史比较缺有效可比性证据')
        elif e['comparison_id'] and e['comparison_id'] not in comparisons:
            issue('COMPARISON_REF', identity, '可比性ID不存在')

    for identity, c in conflicts.items():
        if c['status'] not in {'open', 'resolved'}:
            raise ValueError(f'invalid conflict status: {identity}')
        if not c['issue'] or not split_ids(c['section_ids']) or not split_ids(c['source_ids']):
            issue('CONFLICT_FIELDS', identity, '冲突缺具体问题、受影响章节或来源')
        for sid in split_ids(c['source_ids']):
            if sid not in sources:
                issue('SOURCE_REF', identity, f'冲突来源不存在: {sid}')
        for sid in split_ids(c['section_ids']):
            if sid not in sections:
                issue('SECTION_REF', identity, f'冲突章节不存在: {sid}')
        if c['status'] == 'open':
            issue('CONFLICT', identity, f'未裁决冲突，影响章节: {c["section_ids"]}')
        elif not c['resolution'] or not c['basis']:
            issue('CONFLICT_BASIS', identity, '已解决冲突缺裁决和依据')

    for identity, s in sections.items():
        topic = topics.get(s.get('topic_id'), {})
        unused = topic.get('status') == 'not_applicable'
        claims = [e for e in evidence.values() if e['section_id'] == identity and e['status'] == 'verified']
        if unused and claims:
            issue('OMITTED_CLAIM', identity, '不适用专题仍有在用主张，须核对范围')
        if unused:
            continue
        if s['status'] in {'review_ready', 'final'}:
            if topic.get('status') in {'unknown', 'applicable_missing'}:
                issue('SECTION_TOPIC', identity, '专题依据不足却标为可送审')
            if not claims or not s['required_claim_ids']:
                issue('SECTION_EVIDENCE', identity, '可送审章节没有明确必需主张及已核对证据')
            for eid in s['required_claim_ids']:
                e = evidence.get(eid)
                if not e or e['section_id'] != identity or e['status'] != 'verified':
                    issue('CLAIM_REF', identity, f'必需主张缺失、跨章或未核对: {eid}')
        if final and s['status'] != 'final':
            issue('SECTION_PENDING', identity, '章节尚未完成')
    if final:
        if not {'1', '2', '3', '4', '5', '6'} <= set(sections):
            issue('CORE_COVERAGE', 'sections', '缺基本章；重组大纲仍须保留六章内容映射')
        if p.get('standards_confirmed') is not True or not p.get('standards_basis'):
            issue('STANDARDS', 'project', '规范采纳未确认或缺依据')
        reviews = data['final_reviews']
        for key in REVIEWS:
            if reviews.get(key, {}).get('done') is not True or not reviews[key].get('evidence'):
                issue('REVIEW', key, '人工检查未完成或无检查记录')
        layout = json.loads((folder / 'layout.json').read_text(encoding='utf-8-sig'))
        baseline = json.loads((ROOT / 'assets' / 'project' / 'layout.json').read_text(encoding='utf-8'))
        layout_issues, layout_notes = validate_layout(layout, baseline, final=True)
        issues.extend(layout_issues)
        notes.extend(layout_notes)
    for identity, f in figures.items():
        if f['status'] not in {'draft', 'verified', 'withheld'}:
            raise ValueError(f'invalid figure status: {identity}')
        if f['kind'] not in {'', 'map', 'table', 'profile_photo', 'landscape_photo', 'other'}:
            raise ValueError(f'invalid figure kind: {identity}')
        if f['status'] == 'withheld':
            continue
        if f['section_id'] not in sections or f['source_id'] not in sources:
            issue('FIGURE_REF', identity, '图表章节或来源不存在')
        if f['status'] == 'verified' or final:
            if sources.get(f['source_id'], {}).get('status') != 'verified':
                issue('FIGURE_SOURCE', identity, '图表来源未核对')
            if f['status'] != 'verified' or not all(f[k] for k in ('title', 'locator', 'path', 'period', 'scope', 'quality_check', 'permission')) or not split_ids(f['evidence_ids']):
                issue('FIGURE_FIELDS', identity, '图表核对/来源/权限/清晰度记录不完整')
            for eid in split_ids(f['evidence_ids']):
                if eid not in evidence or evidence[eid]['status'] != 'verified':
                    issue('FIGURE_EVIDENCE', identity, f'图表对应主张未核对: {eid}')

    for i, calc in enumerate(calculations, 1):
        try:
            calculation_ids(calc)
            arithmetic(calc, metrics)
            if calc['type'] == 'manual':
                notes.append(f'{calc["result"]}: 仅核对外部计算的依赖和复核记录；本脚本没有重算该公式')
        except (KeyError, ValueError, TypeError, InvalidOperation, ZeroDivisionError) as exc:
            issue('ARITHMETIC', str(i), str(exc))
    dependency_checks(evidence, issue)
    coverage_counts = coverage_checks(folder, data, sections, topics, sources, evidence, figures, issue, notes, final)
    return {'kind': 'record_check_only', 'tool_version': TOOL_VERSION, 'final_gate_requested': final, 'issues': issues, 'notes': notes,
            'counts': {'sources': len(sources), 'evidence': len(evidence), 'sections': len(sections), **coverage_counts},
            'limitation': '未自动判断事实真实性、章节充分性或实际版面；须结合人工记录审查。'}


def dependency_checks(evidence, issue):
    graph = {}
    for eid, e in evidence.items():
        deps = split_ids(e.get('depends_on', ''))
        graph[eid] = deps
        for parent in deps:
            if parent not in evidence:
                issue('DEPENDENCY_REF', eid, f'上游主张不存在: {parent}')
            elif e['status'] == 'verified' and evidence[parent]['status'] != 'verified':
                issue('DEPENDENCY_STATE', eid, f'上游主张未核对或已撤回: {parent}')
    # Iterative DFS avoids recursion failure on long editorial dependency chains.
    states = {}
    for start in graph:
        if states.get(start):
            continue
        states[start] = 1
        stack = [(start, iter(graph[start]))]
        while stack:
            node, edges = stack[-1]
            parent = next(edges, None)
            if parent is None:
                states[node] = 2
                stack.pop()
            elif states.get(parent) == 1:
                issue('DEPENDENCY_CYCLE', node, f'主张依赖形成循环: {parent}')
            elif parent in graph and not states.get(parent):
                states[parent] = 1
                stack.append((parent, iter(graph[parent])))


def coverage_checks(folder, data, sections, topics, sources, evidence, figures, issue, notes, final):
    rows = {}
    for filename, key in [('requirements.csv', 'requirement_id'), ('soil_types.csv', 'type_id'), ('gaps.csv', 'gap_id')]:
        if (folder / filename).exists():
            rows[filename] = table(folder, filename, key)
        else:
            rows[filename] = {}
            if final:
                issue('COVERAGE_FILE', filename, '旧项目需从新模板补建该台账，不覆盖已有记录')
            else:
                notes.append(f'{filename}: 尚未建台账；正式交付前补齐')
    requirements, soil_types, gaps = (rows[k] for k in ('requirements.csv', 'soil_types.csv', 'gaps.csv'))
    expected_requirements = table(ROOT / 'assets' / 'project', 'requirements.csv', 'requirement_id')
    if final:
        for rid in sorted(set(expected_requirements) - set(requirements)):
            issue('REQUIREMENT_MISSING', rid, '缺基本内容映射；重排不应删除覆盖项')
    def active_section(sid):
        return final or sections.get(sid, {}).get('status') in {'review_ready', 'final'}
    def source_ok(sid, identity):
        s = sources.get(sid, {})
        if s.get('status') != 'verified':
            issue('COVERAGE_SOURCE', identity, f'来源未核对或不存在: {sid}')
        elif final and s.get('qc') == 'unknown':
            issue('QC_UNKNOWN', identity, f'在用来源质量状态未确认: {sid}')
    def claim_refs(value, identity):
        ids = split_ids(value)
        if not ids:
            issue('COVERAGE_EVIDENCE', identity, '覆盖记录没有支撑主张')
        for eid in ids:
            if evidence.get(eid, {}).get('status') != 'verified':
                issue('COVERAGE_EVIDENCE', identity, f'支撑主张未核对或不存在: {eid}')
    def figure_refs(value, identity):
        for fid in split_ids(value):
            if figures.get(fid, {}).get('status') != 'verified':
                issue('COVERAGE_FIGURE', identity, f'图表未核对或不存在: {fid}')
    for rid, r in requirements.items():
        if r['status'] not in {'open', 'covered', 'not_applicable'} or r['category'] not in {'content', 'figure', 'editorial'}:
            raise ValueError(f'invalid requirement: {rid}')
        if r['section_id'] != 'all' and r['section_id'] not in sections:
            issue('REQUIREMENT_SECTION', rid, '要求映射的章节不存在')
        if r['topic_id'] and r['topic_id'] not in topics:
            issue('REQUIREMENT_TOPIC', rid, '条件专题不存在')
        topic = topics.get(r['topic_id'], {})
        if r['status'] == 'not_applicable':
            if not r['disposition_basis'] or not r['basis']:
                issue('REQUIREMENT_WAIVER', rid, '不适用处置缺依据；没有资料不等于不适用')
            if r['topic_id'] and topic.get('status') != 'not_applicable':
                issue('REQUIREMENT_WAIVER', rid, '专题状态不支持省略')
            continue
        if r['status'] == 'open':
            if active_section(r['section_id']):
                issue('REQUIREMENT_OPEN', rid, f'必需内容仍未覆盖，影响章节 {r["section_id"]}')
            continue
        if not all(r[k] for k in ('requirement', 'basis', 'locator')):
            issue('REQUIREMENT_FIELDS', rid, '已覆盖记录缺要求/依据/成稿定位')
        if r['topic_id'] and topic.get('status') != 'applicable_available':
            issue('REQUIREMENT_TOPIC', rid, '专题尚无可用材料或不适用，却登记已覆盖')
        if r['category'] == 'content':
            claim_refs(r['evidence_ids'], rid)
            if r['section_id'] != 'all' and any(evidence.get(eid, {}).get('section_id') not in {None, r['section_id']} for eid in split_ids(r['evidence_ids'])) and not r['reuse_basis']:
                issue('COVERAGE_SECTION', rid, '跨章复用主张须说明reuse_basis，避免把无关主张误作覆盖依据')
        if r['category'] == 'figure' and not split_ids(r['figure_ids']):
            issue('COVERAGE_FIGURE', rid, '附图要求没有对应图件')
        figure_refs(r['figure_ids'], rid)
    inventory = data.get('soil_inventory', {})
    ids = inventory.get('expected_ids', [])
    if not isinstance(ids, list) or any(not isinstance(i, str) or not i.strip() for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('invalid soil_inventory.expected_ids')
    inventory_required = active_section('3')
    if inventory_required or inventory.get('confirmed') is True:
        if inventory.get('confirmed') is not True or not ids or not inventory.get('locator'):
            issue('SOIL_INVENTORY', '3', '缺经核对的完整土种清单和原表定位')
        else:
            source_ok(inventory.get('source_id', ''), 'soil_inventory')
        for tid in sorted(set(ids) - set(soil_types)):
            issue('SOIL_TYPE_MISSING', tid, '审定清单中的土种没有记述覆盖记录')
        for tid in sorted(set(soil_types) - set(ids)):
            issue('SOIL_TYPE_EXTRA', tid, '覆盖记录不在确认的土种清单中')
    for tid, t in soil_types.items():
        if t['status'] not in {'draft', 'verified', 'withheld'} or t['profile_kind'] not in {'third_survey', 'historical_profile', 'historical_description', 'missing'}:
            raise ValueError(f'invalid soil type status/profile_kind: {tid}')
        if t['section_id'] not in sections:
            issue('SOIL_SECTION', tid, '土种记述章节不存在')
        if inventory_required and t['status'] != 'verified':
            issue('SOIL_TYPE_PENDING', tid, '该土种记述尚未完成；不能省略')
        if t['status'] != 'verified':
            continue
        if not all(t[k] for k in ('soil_class', 'subclass', 'genus', 'name', 'source_id', 'locator', 'record_locator')):
            issue('SOIL_TYPE_FIELDS', tid, '已核对土种缺分类/来源/正文条目定位')
        source_ok(t['source_id'], tid)
        claim_refs(t['evidence_ids'], tid)
        if t['profile_kind'] == 'missing' or not t['profile_locator']:
            issue('SOIL_PROFILE', tid, '不能在缺剖面/历史记述依据时标为已核对')
        else:
            source_ok(t['profile_source_id'], tid)
        photo_ids = split_ids(t['profile_figure_ids'])
        if t['profile_kind'] == 'third_survey' and len(set(photo_ids)) < 2:
            issue('SOIL_PHOTOS', tid, '三普剖面需分别对应标准剖面照和景观照')
        if t['profile_kind'] == 'third_survey':
            roles = {figures.get(fid, {}).get('kind') for fid in photo_ids}
            if not {'profile_photo', 'landscape_photo'} <= roles:
                issue('SOIL_PHOTO_ROLE', tid, '三普照片须明确profile_photo和landscape_photo角色，地图/表格不替代')
            for fid in photo_ids:
                photo = figures.get(fid, {})
                if photo and (photo.get('kind') not in {'profile_photo', 'landscape_photo'} or not set(split_ids(photo.get('evidence_ids', ''))) & set(split_ids(t['evidence_ids']))):
                    issue('SOIL_PHOTO_LINK', tid, f'照片角色或关联主张与本土种不匹配: {fid}')
        figure_refs(t['profile_figure_ids'], tid)
    for gid, g in gaps.items():
        if g['status'] not in {'open', 'resolved'}:
            raise ValueError(f'invalid gap status: {gid}')
        if g['requirement_id'] and g['requirement_id'] not in requirements:
            issue('GAP_REQUIREMENT', gid, '缺口对应要求不存在')
        section_ids = split_ids(g['section_ids'])
        if not section_ids or any(s not in sections and s != 'all' for s in section_ids):
            issue('GAP_SECTION', gid, '缺口影响章节未指定或不存在')
        if not all(g[k] for k in ('description', 'impact', 'first_existing_report', 'minimal_request', 'owner')):
            issue('GAP_FIELDS', gid, '缺口缺具体影响、先查报告、最小补件或责任方')
        if g['status'] == 'resolved':
            if not g['resolution'] or not g['basis']:
                issue('GAP_RESOLUTION', gid, '关闭缺口缺处理结果和依据')
        elif any(active_section(s) for s in section_ids):
            issue('GAP_OPEN', gid, '送审/终稿范围仍有未解决的具体缺口')
        else:
            notes.append(f'{gid}: 仅影响 {g["section_ids"]}，其他有据部分可继续')
    return {'requirements': len(requirements), 'soil_types': len(soil_types), 'gaps': len(gaps)}


def calculation_ids(calc):
    if not isinstance(calc, dict):
        raise ValueError('calculation must be an object')
    kind, result = calc['type'], calc['result']
    if not isinstance(result, str) or not result.strip():
        raise ValueError('invalid result id')
    if kind == 'sum':
        values = calc['parts']
    elif kind == 'ratio':
        values = [calc['numerator'], calc['denominator']]
    elif kind == 'weighted_mean':
        if not isinstance(calc['pairs'], list) or not calc['pairs']:
            raise ValueError('empty/invalid weighted pairs')
        values = [v for pair in calc['pairs'] for v in (pair['value'], pair['weight'])]
        value_ids = [pair['value'] for pair in calc['pairs']]
        if len(value_ids) != len(set(value_ids)):
            raise ValueError('duplicate weighted value id')
    elif kind == 'manual':
        values = calc['inputs']
    else:
        raise ValueError(f'unknown calculation: {kind}')
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError('empty/invalid input ids')
    if kind == 'sum' and len(values) != len(set(values)):
        raise ValueError('duplicate sum input id')
    if result in values:
        raise ValueError('result cannot be its own input')
    return result, values


def arithmetic(calc, metrics):
    calculation_ids(calc)
    kind = calc['type']
    result = metrics[calc['result']]
    if kind == 'manual':
        if not all(isinstance(calc.get(k), str) and calc[k].strip() for k in ('formula', 'method_basis', 'review_locator')):
            raise ValueError('manual calculation requires formula, method_basis and actual review_locator')
        for mid in calc['inputs'] + [calc['result']]:
            number(metrics[mid]['value'])
        return
    tolerance = number(calc['tolerance'])
    if tolerance < 0:
        raise ValueError('negative tolerance')
    def compatible(rows, unit=True):
        if not rows or any(not r['scope'] for r in rows) or len({r['scope'] for r in rows}) != 1:
            raise ValueError('scope mismatch')
        if unit and len({r['unit'] for r in rows}) != 1:
            raise ValueError('unit mismatch')
        dimensions = ('period', 'depth', 'method') if unit else ('period', 'depth')
        for dimension in dimensions:
            explicit = {r.get(dimension) for r in rows} - {None, '', 'NA'}
            if len(explicit) > 1:
                harmonized = calc.get('harmonized_dimensions', [])
                if not isinstance(harmonized, list) or dimension not in harmonized or not str(calc.get('harmonization_basis', '')).strip():
                    raise ValueError(f'{dimension} mismatch: explicit harmonization evidence required')
    if kind == 'sum':
        parts = [metrics[mid] for mid in calc['parts']]
        compatible(parts + [result])
        if not parts:
            raise ValueError('empty sum')
        expected = sum((number(r['value']) for r in parts), Decimal(0))
    elif kind == 'ratio':
        a, b = metrics[calc['numerator']], metrics[calc['denominator']]
        compatible([a, b])
        compatible([a, b, result], unit=False)
        av, bv = number(a['value']), number(b['value'])
        if bv <= 0 or av < 0 or av > bv:
            raise ValueError('ratio requires 0 <= numerator <= positive denominator')
        if result['unit'] != '%':
            raise ValueError('ratio result must use %')
        expected = av / bv * 100
    elif kind == 'weighted_mean':
        pairs = [(metrics[x['value']], metrics[x['weight']]) for x in calc['pairs']]
        compatible([v for v, _ in pairs] + [result])
        compatible([w for _, w in pairs])
        compatible([item for pair in pairs for item in pair] + [result], unit=False)
        weights = [number(w['value']) for _, w in pairs]
        if not weights or any(w < 0 for w in weights) or sum(weights) <= 0:
            raise ValueError('invalid weights')
        expected = sum(number(v['value']) * w for (v, _), w in zip(pairs, weights)) / sum(weights)
    else:
        raise ValueError(f'unknown calculation: {kind}')
    if abs(expected - number(result['value'])) > tolerance:
        raise ValueError(f'{kind}: expected {expected}, recorded {result["value"]}, tolerance {tolerance}')


def visible_text(element):
    if element.tag in {W+'del', W+'moveFrom'}:
        return ''
    if element.tag == W+'t':
        return element.text or ''
    return ''.join(visible_text(child) for child in element)


def relationship_target(part, target):
    base = '' if part == '_rels/.rels' else posixpath.dirname(part.split('/_rels/')[0] + '/' + posixpath.basename(part)[:-5])
    target = unquote(urlsplit(target).path).replace('\\', '/')
    return posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(base, target))


def check_docx(path):
    issues, external, counts = [], [], Counter()
    def issue(code, part, message):
        issues.append({'code': code, 'id': part, 'message': message})
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            issue('DUPLICATE_ZIP_PART', 'package', 'duplicate ZIP names')
        if not {'word/document.xml', '[Content_Types].xml', '_rels/.rels'} <= set(names):
            raise ValueError('not a Word DOCX package')
        xml_parts = [i for i in archive.infolist() if i.filename.endswith(('.xml', '.rels'))]
        if sum(i.file_size for i in xml_parts) > 256 * 1024 * 1024:
            raise ValueError('XML exceeds 256 MiB safety bound; inspect selectively')
        parsed = {i.filename: ET.fromstring(archive.read(i)) for i in xml_parts}
        types = parsed['[Content_Types].xml']
        if types.tag != CT+'Types':
            raise ValueError('invalid OPC Content Types root/namespace')
        main_types = [el.get('ContentType') for el in types if el.tag == CT+'Override' and el.get('PartName') == '/word/document.xml']
        if main_types != [DOCX_TYPE]:
            raise ValueError('missing/invalid DOCX main document content type')
        package_rels = parsed['_rels/.rels']
        office_rels = [el for el in package_rels if el.get('Type') == R[1:-1]+'/officeDocument']
        if package_rels.tag != PR+'Relationships' or len(office_rels) != 1 or office_rels[0].get('TargetMode') == 'External' or relationship_target('_rels/.rels', office_rels[0].get('Target', '')) != 'word/document.xml':
            raise ValueError('invalid package officeDocument entry relationship')
        if parsed['word/document.xml'].tag != W+'document' or parsed['word/document.xml'].find(W+'body') is None:
            raise ValueError('document.xml lacks Word document/body structure')
        counts['media_parts'] = sum(n.startswith('word/media/') and not n.endswith('/') for n in names)
        all_bookmarks, refs = Counter(), []
        for part, root in parsed.items():
            if part.endswith('.rels'):
                ids = Counter()
                if root.tag != PR+'Relationships':
                    issue('RELATIONSHIP_SCHEMA', part, 'invalid relationships root/namespace')
                for rel in root:
                    if rel.tag != PR+'Relationship' or not all(rel.get(k) for k in ('Id', 'Type', 'Target')):
                        issue('RELATIONSHIP_SCHEMA', part, 'relationship lacks valid element/Id/Type/Target')
                    ids[rel.get('Id')] += 1
                    target = rel.get('Target', '')
                    if rel.get('TargetMode') == 'External':
                        external.append({'part': part, 'target': target})
                        continue
                    resolved = relationship_target(part, target)
                    if resolved not in names:
                        issue('MISSING_REL_TARGET', part, resolved)
                if any(v > 1 for v in ids.values()):
                    issue('DUPLICATE_REL_ID', part, 'relationship ID repeated')
            if not part.startswith('word/') or part.endswith('.rels'):
                continue
            starts, ends, stack = Counter(), Counter(), []
            active_bookmarks = set()
            rel_part = posixpath.dirname(part) + '/_rels/' + posixpath.basename(part) + '.rels'
            rel_ids = {el.get('Id') for el in parsed.get(rel_part, [])}
            instructions = []
            for el in root.iter():
                for attr in (R+'id', R+'embed', R+'link'):
                    if el.get(attr) is not None and el.get(attr) not in rel_ids:
                        issue('REL_ID_REF', part, f'undefined relationship ID: {el.get(attr)}')
                if el.tag in {W+'tbl', W+'sectPr', W+'drawing', W+'pict', W+'ins', W+'del'}:
                    counts[el.tag.split('}')[-1]] += 1
                if el.tag == W+'bookmarkStart':
                    bid = el.get(W+'id')
                    starts[bid] += 1
                    active_bookmarks.add(bid)
                    all_bookmarks[el.get(W+'name')] += 1
                elif el.tag == W+'bookmarkEnd':
                    bid = el.get(W+'id')
                    ends[bid] += 1
                    if bid not in active_bookmarks:
                        issue('BOOKMARK_ORDER', part, 'bookmark end without earlier unmatched start')
                    active_bookmarks.discard(bid)
                elif el.tag == W+'fldSimple':
                    instructions.append(el.get(W+'instr', ''))
                elif el.tag == W+'fldChar':
                    kind = el.get(W+'fldCharType')
                    if kind == 'begin':
                        stack.append({'instruction': '', 'separated': False})
                    elif kind == 'end':
                        if not stack:
                            issue('FIELD_PAIR', part, 'field end without begin')
                        else:
                            instructions.append(stack.pop()['instruction'])
                    elif kind == 'separate':
                        if not stack or stack[-1]['separated']:
                            issue('FIELD_PAIR', part, 'field separator without begin or repeated separator')
                        else:
                            stack[-1]['separated'] = True
                elif el.tag == W+'instrText' and stack:
                    if not stack[-1]['separated']:
                        stack[-1]['instruction'] += el.text or ''
            if stack:
                issue('FIELD_PAIR', part, 'unclosed field')
            if starts != ends or any(v > 1 for v in starts.values()) or None in starts or None in ends:
                issue('BOOKMARK_PAIR', part, 'bookmark IDs unpaired or repeated')
            for instr in instructions:
                m = re.match(r'\s*(?:REF|PAGEREF)\s+(?:"([^"]+)"|(\S+))', instr, re.I)
                if m:
                    refs.append((part, m.group(1) or m.group(2)))
            content = visible_text(root)
            if re.search(r'错误[！!：:].{0,20}(引用|书签)|Error!\s*(Reference source not found|Bookmark not defined)', content, re.I):
                issue('FIELD_ERROR_TEXT', part, 'visible text contains possible field error; inspect context')
        for name, n in all_bookmarks.items():
            if not name or n > 1:
                issue('DUPLICATE_BOOKMARK_NAME', 'word', str(name))
        for part, target in refs:
            if target not in all_bookmarks:
                issue('REF_TARGET', part, target)
    return {'kind': 'static_docx_check_only', 'tool_version': TOOL_VERSION, 'issues': issues, 'counts': dict(counts), 'external_relationships': external,
            'limitation': '不更新域，不运行外链，不等于完整OOXML验证、实际打开或逐页排版检查。'}


def initialize(destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('destination exists; choose a new directory (nothing overwritten)')
    shutil.copytree(ROOT / 'assets' / 'project', destination)
    return {'created': str(destination.resolve()), 'note': '模板待填写，不是已验证县域数据'}


def check_layout_file(path, final=False):
    layout = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    baseline = json.loads((ROOT / 'assets' / 'project' / 'layout.json').read_text(encoding='utf-8'))
    issues, notes = validate_layout(layout, baseline, final)
    return {'kind': 'layout_plan_check_only', 'tool_version': TOOL_VERSION, 'issues': issues, 'notes': notes,
            'limitation': '只核排版配置和检查记录；未读取DOCX样式、更新域、打开或渲染页面。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init').add_argument('path')
    p = sub.add_parser('check')
    p.add_argument('path')
    p.add_argument('--final', action='store_true')
    sub.add_parser('docx-check').add_argument('path')
    p = sub.add_parser('layout-check')
    p.add_argument('path')
    p.add_argument('--final', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = initialize(args.path)
        elif args.command == 'check':
            result = check_project(args.path, args.final)
        elif args.command == 'layout-check':
            result = check_layout_file(args.path, args.final)
        else:
            result = check_docx(args.path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('issues') else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError, RuntimeError, BadZipFile) as exc:
        print(json.dumps({'error': str(exc), 'status': 'input_or_read_error'}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
