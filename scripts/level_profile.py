"""Detect municipal or county soil-chronicle evidence in DOCX/text sources.

The result is a preflight profile, not an administrative or acceptance ruling.
Standard library only; source files are read without modification.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

VERSION = 'city-county-evidence-v1'
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_DOCUMENT_XML_BYTES = 50 * 1024 * 1024
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'

RULES = {
    'municipal': (
        ('N2省市级导引', r'第三次全国土壤普查省市级成果(?:清单及)?编制导引', 12, True),
        ('市级提纲', r'市级成果报告形成提纲', 12, True),
        ('市级成果对象', r'市级成果(?:汇总|编制|验收|报告|清单)', 7, True),
        ('所辖县级成果', r'(?:所辖|下辖).{0,10}(?:县|区|旗).{0,20}(?:成果|数据|图件)', 7, True),
        ('县级成果上收', r'县级成果.{0,20}(?:核验|汇总|接边|综合)', 7, True),
        ('县际一致性', r'(?:县际|区县间|跨县).{0,20}(?:接边|一致|汇总|比较)', 6, True),
        ('市级制图综合', r'市级.{0,10}制图综合', 7, True),
        ('市域叙述', r'市域', 2, False),
        ('本市叙述', r'本市', 1, False),
    ),
    'county': (
        ('N1县级导引', r'第三次全国土壤普查县级成果编制及验收导引', 12, True),
        ('县级提纲', r'县级成果报告(?:编制|形成)提纲', 10, True),
        ('县级成果对象', r'县级成果(?:编制|自验|验收|报告|清单)', 7, True),
        ('县市区旗对象', r'(?:本)?县\s*[（(]\s*市[、,，]\s*区[、,，]\s*旗\s*[）)]', 6, True),
        ('逐土种记述', r'(?:所有土属与土种|逐(?:个|一)土种|土种记述示例)', 6, True),
        ('土种典型剖面', r'土种.{0,24}典型剖面', 5, True),
        ('本县叙述', r'本县', 1, False),
        ('全县叙述', r'全县', 1, False),
    ),
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _docx_text(path):
    try:
        with ZipFile(path) as archive:
            try:
                info = archive.getinfo('word/document.xml')
            except KeyError as exc:
                raise ValueError('DOCX缺少word/document.xml') from exc
            if info.file_size > MAX_DOCUMENT_XML_BYTES:
                raise ValueError('DOCX正文XML超过50 MB安全上限')
            root = ET.fromstring(archive.read(info))
    except BadZipFile as exc:
        raise ValueError('文件不是有效DOCX') from exc
    paragraphs = []
    for paragraph in root.iter(W + 'p'):
        parts = []
        for node in paragraph.iter():
            if node.tag == W + 't' and node.text:
                parts.append(node.text)
            elif node.tag in {W + 'tab', W + 'br'}:
                parts.append(' ')
        if parts:
            paragraphs.append(''.join(parts))
    return '\n'.join(paragraphs)


def _plain_text(path):
    raw = Path(path).read_bytes()
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('文本编码无法识别；请转换为UTF-8、GB18030或DOCX')


def read_source(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError('文件不存在或不是普通文件')
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('文件超过100 MB安全上限')
    suffix = path.suffix.lower()
    if suffix == '.docx':
        return _docx_text(path)
    if suffix in {'.txt', '.md', '.json', '.csv'}:
        return _plain_text(path)
    raise ValueError('仅支持DOCX、TXT、MD、JSON和CSV；PDF请先提取文字或提供DOCX版本')


def _excerpt(text, match, radius=42):
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return re.sub(r'\s+', ' ', text[start:end]).strip()


def analyze_text(text):
    scores = {'municipal': 0, 'county': 0}
    evidence = {'municipal': [], 'county': []}
    strong = {'municipal': 0, 'county': 0}
    for level, rules in RULES.items():
        for label, pattern, weight, is_strong in rules:
            match = re.search(pattern, text, re.I | re.S)
            if not match:
                continue
            scores[level] += weight
            strong[level] += int(is_strong)
            evidence[level].append({
                'rule': label,
                'weight': weight,
                'strong': is_strong,
                'excerpt': _excerpt(text, match),
            })
    decision = decide(scores, strong)
    return scores, strong, evidence, decision


def decide(scores, strong):
    ordered = sorted(scores, key=scores.get, reverse=True)
    winner, other = ordered
    margin = scores[winner] - scores[other]
    if strong[winner] == 0 or scores[winner] < 7 or margin < 4:
        return 'unknown'
    if strong['municipal'] and strong['county'] and margin < 8:
        return 'unknown'
    return winner


def detect(paths):
    files, aggregate_scores = [], {'municipal': 0, 'county': 0}
    aggregate_strong = {'municipal': 0, 'county': 0}
    aggregate_evidence = {'municipal': [], 'county': []}
    errors = []
    for item in paths:
        path = Path(item)
        try:
            text = read_source(path)
            scores, strong, evidence, decision = analyze_text(text)
            files.append({
                'path': str(path.resolve()),
                'sha256': digest(path),
                'characters_read': len(text),
                'scores': scores,
                'strong_hits': strong,
                'decision': decision,
                'evidence': evidence,
            })
            for level in aggregate_scores:
                aggregate_scores[level] += scores[level]
                aggregate_strong[level] += strong[level]
                for row in evidence[level]:
                    aggregate_evidence[level].append({'source': str(path.resolve()), **row})
        except (OSError, ValueError, ET.ParseError) as exc:
            errors.append({'path': str(path), 'error': str(exc)})
    if not files:
        raise ValueError('没有可分析的文件')
    decision = decide(aggregate_scores, aggregate_strong)
    file_decisions = {row['decision'] for row in files} - {'unknown'}
    warnings = []
    if len(file_decisions) > 1:
        decision = 'unknown'
        warnings.append('输入文件分别出现明确市级和县级角色；请先区分任务/模板与下级来源材料')
    if decision == 'unknown':
        confidence = 'insufficient'
        warnings.append('证据不足或冲突，不能锁定层级专属章节、模板和验收规则')
    else:
        other = 'county' if decision == 'municipal' else 'municipal'
        margin = aggregate_scores[decision] - aggregate_scores[other]
        confidence = 'high' if aggregate_scores[decision] >= 12 and margin >= 8 else 'medium'
    profiles = {
        'municipal': {'guide_profile': 'N2-municipal', 'chapter_3_narrative_unit': 'soil_genus'},
        'county': {'guide_profile': 'N1-county', 'chapter_3_narrative_unit': 'soil_species'},
        'unknown': {'guide_profile': None, 'chapter_3_narrative_unit': None},
    }
    return {
        'kind': 'city_county_level_profile',
        'version': VERSION,
        'decision': decision,
        'confidence': confidence,
        'scores': aggregate_scores,
        'strong_hits': aggregate_strong,
        'selected_profile': profiles[decision],
        'evidence': aggregate_evidence,
        'warnings': warnings,
        'errors': errors,
        'sources': files,
        'limitation': '基于文件正文信号预判；县级市名称中的“市”不构成市级证据，最终层级须由项目依据确认。',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest='command', required=True)
    detect_parser = subparsers.add_parser('detect', help='识别市级、县级或待确认')
    detect_parser.add_argument('sources', nargs='+', help='任务书、适用导引或模板（DOCX/文本）')
    detect_parser.add_argument('--output', help='可选JSON输出路径；拒绝覆盖已有文件')
    args = parser.parse_args(argv)
    try:
        result = detect(args.sources)
        payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            target = Path(args.output)
            if target.exists():
                raise ValueError(f'拒绝覆盖已有文件: {target}')
            target.write_text(payload, encoding='utf-8')
        sys.stdout.write(payload)
        return 0
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
