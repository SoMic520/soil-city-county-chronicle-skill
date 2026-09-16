"""Synthetic regression fixtures: no real county facts or online services."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

import chronicle as c
import length_profile as lp


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / '项目 with spaces'
        c.initialize(self.folder)
        self.project = json.loads((self.folder / 'project.json').read_text(encoding='utf-8'))
        self.project['project'].update(county='合成县', scope='合成评价范围', period='2023', standards_confirmed=True, standards_basis='合成任务确认记录')
        for topic in self.project['topics'].values():
            topic.update(status='not_applicable', basis='合成任务明确未开展专题')
        self.save()

    def save(self):
        (self.folder / 'project.json').write_text(json.dumps(self.project, ensure_ascii=False), encoding='utf-8')

    def rows(self, file, rows):
        path = self.folder / file
        header = path.read_text(encoding='utf-8-sig').splitlines()[0].split(',')
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)

    def source(self, status='verified'):
        self.rows('sources.csv', [dict(source_id='S1', title='合成数据报告', path='user:合成测试记录', version='v1', period='2023', status=status, qc='confirmed', qc_basis='合成质控声明', coverage='合成县样点')])

    def claim(self, section='4', **kw):
        e = dict(evidence_id='E1', section_id=section, claim='合成事实', kind='observed', source_ids='S1', locator='第4节表2', quantitative_comparison='no', status='verified')
        e.update(kw)
        self.rows('evidence.csv', [e])

    def codes(self, final=False):
        return {i['code'] for i in c.check_project(self.folder, final)['issues']}

    def test_init_refuses_existing_and_preserves(self):
        original = (self.folder / 'project.json').read_bytes()
        with self.assertRaises(ValueError):
            c.initialize(self.folder)
        self.assertEqual(original, (self.folder / 'project.json').read_bytes())

    def test_optional_not_contradictory_no_block_on_other_chapter(self):
        self.source()
        self.claim()
        self.project['sections'][3].update(status='drafting', required_claim_ids=['E1'])
        self.save()
        self.assertEqual(self.codes(), set())

    def test_missing_file_does_not_become_nonexistent(self):
        self.project['topics']['specialty'].update(status='unknown', basis='')
        self.save()
        r = c.check_project(self.folder)
        self.assertTrue(r['notes'])
        self.assertNotIn('TOPIC_GAP', self.codes())
        self.assertIn('TOPIC_UNKNOWN', self.codes(final=True))

    def test_required_missing_topic_and_false_omission(self):
        self.project['topics']['specialty'].update(status='applicable_missing', basis='合成任务要求')
        self.save()
        self.assertIn('TOPIC_GAP', self.codes())
        self.project['topics']['specialty'].update(status='not_applicable', basis='')
        self.save()
        self.assertIn('TOPIC_BASIS', self.codes())

    def test_filename_only_is_not_verified_evidence(self):
        self.source('catalogued')
        self.claim()
        self.assertIn('SOURCE_REF', self.codes())

    def test_conflict_cannot_silently_disappear(self):
        self.source()
        self.rows('conflicts.csv', [dict(conflict_id='C1', section_ids='4', source_ids='S1', issue='合成数值冲突', status='open')])
        self.assertIn('CONFLICT', self.codes())
        self.rows('conflicts.csv', [dict(conflict_id='C1', section_ids='4', source_ids='S1', issue='合成数值冲突', status='resolved')])
        self.assertIn('CONFLICT_BASIS', self.codes())

    def test_incomparable_history_not_verified_by_label(self):
        self.source()
        h = dict(comparison_id='H1', **{key:'same' for key in c.DIMENSIONS}, basis='合成对照记录', status='verified')
        h['depth'] = 'incomparable'
        self.rows('comparisons.csv', [h])
        self.claim(comparison_id='H1', quantitative_comparison='yes')
        self.assertTrue({'COMPARABILITY', 'HISTORY'} <= self.codes())
        self.claim(kind='historical', quantitative_comparison='no', comparison_id='H1')
        h['status'] = 'incomparable'
        self.rows('comparisons.csv', [h])
        self.assertNotIn('HISTORY', self.codes())

    def test_final_rejects_empty_project_and_all_required_evidence_missing(self):
        self.assertIn('SECTION_PENDING', self.codes(final=True))
        for s in self.project['sections']:
            s['status'] = 'final'
        self.save()
        self.assertIn('SECTION_EVIDENCE', self.codes(final=True))

    def test_old_project_without_length_plan_can_work_but_not_finalize(self):
        (self.folder / 'length-plan.json').unlink()
        result = c.check_project(self.folder)
        self.assertNotIn('LENGTH_FILE', {i['code'] for i in result['issues']})
        self.assertTrue(any('length-plan.json' in note for note in result['notes']))
        self.assertIn('LENGTH_FILE', self.codes(final=True))

    def complete_fixture(self):
        self.source()
        claims = []
        for s in self.project['sections']:
            eid = 'E' + s['id']
            s.update(status='final', required_claim_ids=[eid])
            claims.append(dict(evidence_id=eid, section_id=s['id'], claim='合成情景中已人工检查的条目', kind='observed', source_ids='S1', locator='合成材料节'+s['id'], quantitative_comparison='no', status='verified'))
        for r in self.project['final_reviews'].values():
            r.update(done=True, evidence='合成测试中的检查记录')
        self.save()
        self.rows('evidence.csv', claims)
        self.rows('figures.csv', [dict(figure_id=fid, section_id=sid, title='合成图件', source_id='S1', locator='合成图'+fid, path='user:合成图件', evidence_ids='E'+sid, period='2023', scope='合成县', quality_check='合成核验', permission='合成授权', status='verified') for fid, sid in [('F_type', '2'), ('F_property', '4')]])
        reqs = c.table(self.folder, 'requirements.csv', 'requirement_id')
        for row in reqs.values():
            row.update(status='covered', locator='合成成稿中的内容定位')
            if row['category'] == 'content':
                row['evidence_ids'] = 'E'+row['section_id']
            elif row['category'] == 'figure':
                row['figure_ids'] = 'F_type' if row['requirement_id'] == 'R-map-type' else 'F_property'
        self.rows('requirements.csv', reqs.values())
        self.project['soil_inventory'] = dict(confirmed=True, source_id='S1', locator='合成分类清单', expected_ids=['T1'])
        self.rows('soil_types.csv', [dict(type_id='T1', soil_class='合成土类', subclass='合成亚类', genus='合成土属', name='合成土种', source_id='S1', locator='合成分类表', section_id='3', evidence_ids='E3', profile_kind='historical_description', profile_source_id='S1', profile_locator='合成历史记述', record_locator='第三章合成土种', status='verified')])
        self.save()
        layout = json.loads((self.folder / 'layout.json').read_text(encoding='utf-8'))
        layout.update(adoption_confirmed=True, target_application='合成测试', toc_semantic_levels=['chapter','level_1'])
        layout['project_details'].update(table_chinese_font='宋体', header_distance_mm=15, footer_distance_mm=17.5)
        for check in layout['format_checks'].values():
            check.update(status='passed', evidence='合成测试中的实际检查定位，不代表真实文件验收')
        (self.folder / 'layout.json').write_text(json.dumps(layout), encoding='utf-8')
        length = json.loads((self.folder / 'length-plan.json').read_text(encoding='utf-8'))
        length['status'] = 'locked'
        length['template'].update(path='user:合成模板', identity='合成县级土壤志模板', measurement_evidence='合成测试计量记录')
        length['project_structure'].update(soil_types=10, property_indicators=10, evaluation_modules=10,
                                           recommendation_topics=10, basis='合成模板及本县结构清单')
        targets = []
        for cid, row in length['chapters'].items():
            target = length['template']['chapters'][cid]
            row.update(target=target, lower=lp.floor_percent(target, 85), upper=lp.ceil_percent(target, 115),
                       adaptation_basis='合成模板等结构密度', actual=target)
            if cid in lp.ADAPTATION_KINDS:
                row['template_structure_count'] = 10
                row['template_fixed_characters'] = 0
                row['template_structure_evidence'] = '合成模板结构标注'
            targets.append(target)
        target_total = sum(targets)
        length['total'].update(target=target_total, lower=lp.floor_percent(target_total, 90),
                               upper=lp.ceil_percent(target_total, 110), actual=target_total)
        (self.folder / 'length-plan.json').write_text(json.dumps(length, ensure_ascii=False), encoding='utf-8')

    def test_complete_record_fixture_passes_not_factual_certification(self):
        self.complete_fixture()
        result = c.check_project(self.folder, final=True)
        self.assertEqual(result['issues'], [])
        self.assertEqual(result['kind'], 'record_check_only')

    def test_empty_parsed_ids_rejected(self):
        self.source()
        self.claim(kind='derived', source_ids=' | | ', metric_ids=' | ')
        self.assertTrue({'EVIDENCE_FIELDS', 'DERIVED_METRICS'} <= self.codes())
        self.complete_fixture()
        rows = c.table(self.folder, 'figures.csv', 'figure_id')
        rows['F_type']['evidence_ids'] = ' | '
        self.rows('figures.csv', rows.values())
        self.assertIn('FIGURE_FIELDS', self.codes(True))

    def test_quantitative_history_requires_two_period_metrics(self):
        self.source()
        self.claim(kind='historical', quantitative_comparison='yes', comparison_id='H1')
        self.rows('comparisons.csv', [dict(comparison_id='H1', **{k:'same' for k in c.DIMENSIONS}, basis='合成可比说明', status='verified')])
        self.assertIn('HISTORY_METRICS', self.codes())
        self.rows('metrics.csv', [self.metric('M1','10'), self.metric('M2','20')])
        self.claim(kind='historical', quantitative_comparison='yes', comparison_id='H1', metric_ids='M1|M2')
        self.assertIn('HISTORY_PERIOD', self.codes())
        self.rows('metrics.csv', [self.metric('M1','10', period='1982'), self.metric('M2','20')])
        self.assertEqual(self.codes(), set())

    def metric(self, identity, value, **kw):
        row = dict(metric_id=identity, definition='合成数值；NA不适用', value=value, unit='个', scope='合成同口径', population='合成分类', period='2023', depth='NA', method='合成调查', statistic='数量', n_valid='NA', denominator='NA', source_id='S1', locator='合成表1')
        row.update(kw)
        return row

    def calculation_fixture(self):
        self.source()
        self.claim(kind='derived', metric_ids='M_result')
        sources = c.table(self.folder, 'sources.csv', 'source_id')
        sources['S_BAD'] = dict(sources['S1'], source_id='S_BAD', status='rejected')
        self.rows('sources.csv', sources.values())
        self.rows('metrics.csv', [self.metric('M_a','40', source_id='S_BAD'), self.metric('M_b','60'), self.metric('M_mid','100'), self.metric('M_result','160')])
        (self.folder / 'checks.json').write_text(json.dumps([
            dict(type='sum', parts=['M_a','M_b'], result='M_mid', tolerance='0'),
            dict(type='sum', parts=['M_mid','M_b'], result='M_result', tolerance='0')]), encoding='utf-8')

    def test_transitive_calculation_input_source_and_qc(self):
        self.calculation_fixture()
        self.assertIn('METRIC_SOURCE', self.codes())
        sources = c.table(self.folder, 'sources.csv', 'source_id')
        sources['S_BAD'].update(status='verified', qc='unknown', qc_basis='')
        self.rows('sources.csv', sources.values())
        self.assertIn('QC_UNKNOWN', self.codes(True))
        sources['S_BAD'].update(qc='confirmed', qc_basis='合成核对')
        self.rows('sources.csv', sources.values())
        self.assertEqual(self.codes(), set())

    def test_calculation_cycle_duplicate_and_missing_formula(self):
        self.calculation_fixture()
        (self.folder / 'checks.json').write_text(json.dumps([
            dict(type='sum', parts=['M_a','M_result'], result='M_mid', tolerance='0'),
            dict(type='sum', parts=['M_mid','M_b'], result='M_result', tolerance='0'),
            dict(type='sum', parts=['M_a','M_b'], result='M_result', tolerance='0')]), encoding='utf-8')
        self.assertTrue({'CALCULATION_DUPLICATE', 'CALCULATION_DEPENDENCY_CYCLE'} <= self.codes())
        (self.folder / 'checks.json').write_text('[]', encoding='utf-8')
        self.assertIn('DERIVED_CALCULATION', self.codes())

    def test_withdrawn_upstream_and_dependency_cycle(self):
        self.source()
        self.claim()
        rows = c.table(self.folder, 'evidence.csv', 'evidence_id')
        rows['E2'] = dict(rows['E1'], evidence_id='E2', kind='recommendation', depends_on='E1')
        rows['E1'].update(status='withheld')
        self.rows('evidence.csv', rows.values())
        self.assertIn('DEPENDENCY_STATE', self.codes())
        rows['E1'].update(status='verified', depends_on='E2')
        self.rows('evidence.csv', rows.values())
        self.assertIn('DEPENDENCY_CYCLE', self.codes())

    def test_empty_conflict_cannot_be_resolved(self):
        self.rows('conflicts.csv', [dict(conflict_id='C1', status='resolved', resolution='合成裁决', basis='合成依据')])
        self.assertIn('CONFLICT_FIELDS', self.codes())

    def test_required_content_and_missing_soil_type_block_final(self):
        self.complete_fixture()
        self.project['soil_inventory']['expected_ids'].append('T2')
        self.save()
        rows = c.table(self.folder, 'requirements.csv', 'requirement_id')
        rows['R4-history']['status'] = 'open'
        self.rows('requirements.csv', rows.values())
        self.assertTrue({'SOIL_TYPE_MISSING', 'REQUIREMENT_OPEN'} <= self.codes(True))
        del rows['R4-history']
        self.rows('requirements.csv', rows.values())
        self.assertIn('REQUIREMENT_MISSING', self.codes(True))

    def test_third_survey_photos_required_historical_description_allowed(self):
        self.complete_fixture()
        self.assertEqual(self.codes(True), set())
        rows = c.table(self.folder, 'soil_types.csv', 'type_id')
        rows['T1']['profile_kind'] = 'third_survey'
        self.rows('soil_types.csv', rows.values())
        self.assertIn('SOIL_PHOTOS', self.codes(True))

    def test_soil_photos_need_roles_and_same_type_evidence(self):
        self.complete_fixture()
        rows = c.table(self.folder, 'soil_types.csv', 'type_id')
        rows['T1'].update(profile_kind='third_survey', profile_figure_ids='F_type|F_property')
        self.rows('soil_types.csv', rows.values())
        self.assertTrue({'SOIL_PHOTO_ROLE', 'SOIL_PHOTO_LINK'} <= self.codes(True))
        figs = c.table(self.folder, 'figures.csv', 'figure_id')
        for fid, role in [('F_profile', 'profile_photo'), ('F_landscape', 'landscape_photo')]:
            figs[fid] = dict(figs['F_type'], figure_id=fid, section_id='3', evidence_ids='E3', kind=role)
        self.rows('figures.csv', figs.values())
        rows['T1']['profile_figure_ids'] = 'F_profile|F_landscape'
        self.rows('soil_types.csv', rows.values())
        self.assertEqual(self.codes(True), set())
        figs['F_profile']['evidence_ids'] = 'E1'
        self.rows('figures.csv', figs.values())
        self.assertIn('SOIL_PHOTO_LINK', self.codes(True))

    def test_cross_section_evidence_reuse_needs_explanation(self):
        self.complete_fixture()
        rows = c.table(self.folder, 'requirements.csv', 'requirement_id')
        rows['R4-history']['evidence_ids'] = 'E1'
        self.rows('requirements.csv', rows.values())
        self.assertIn('COVERAGE_SECTION', self.codes(True))
        rows['R4-history']['reuse_basis'] = '合成记录：复用第一章已经定位的两期原始表，本章另作属性讨论'
        self.rows('requirements.csv', rows.values())
        self.assertEqual(self.codes(True), set())

    def test_gaps_limit_affected_section_and_need_closure_evidence(self):
        self.rows('gaps.csv', [dict(gap_id='G1', requirement_id='R4-history', section_ids='4', description='合成历史材料缺失', impact='暂不能比较', first_existing_report='先查数据报告', minimal_request='补两期表', owner='合成负责人', status='open')])
        self.assertNotIn('GAP_OPEN', self.codes())
        self.project['sections'][3]['status'] = 'review_ready'
        self.save()
        self.assertIn('GAP_OPEN', self.codes())
        rows = c.table(self.folder, 'gaps.csv', 'gap_id')
        rows['G1']['status'] = 'resolved'
        self.rows('gaps.csv', rows.values())
        self.assertIn('GAP_RESOLUTION', self.codes())

    def test_legacy_project_draft_allowed_final_requests_new_coverage(self):
        # Remove only newly generated test fixture files, never user project files.
        for name in ('requirements.csv', 'soil_types.csv', 'gaps.csv'):
            (self.folder / name).unlink()
        self.assertEqual(self.codes(), set())
        self.assertIn('COVERAGE_FILE', self.codes(True))

    def test_core_chapter_cannot_be_optional(self):
        self.project['sections'][3]['topic_id'] = 'specialty'
        self.save()
        self.assertIn('CORE_TOPIC', self.codes())

    def test_duplicate_id_and_malformed_csv_fail_closed(self):
        self.rows('sources.csv', [dict(source_id='S1'), dict(source_id='S1')])
        with self.assertRaises(ValueError):
            c.check_project(self.folder)

    def test_bad_input_exit_code(self):
        (self.folder / 'project.json').write_text('{}', encoding='utf-8')
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(c.main(['check', str(self.folder)]), 2)


class ArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.m = {k: dict(value=v, unit=u, scope='same') for k,v,u in [('a','40','个'),('b','100','个'),('r','40','%'),('sum','140','个'),('x','10','g/kg'),('y','20','g/kg'),('mean','17.142857','g/kg')]}

    def test_ratio_sum_weighted_mean(self):
        c.arithmetic(dict(type='ratio', numerator='a', denominator='b', result='r', tolerance='0'), self.m)
        c.arithmetic(dict(type='sum', parts=['a','b'], result='sum', tolerance='0'), self.m)
        c.arithmetic(dict(type='weighted_mean', pairs=[dict(value='x',weight='a'),dict(value='y',weight='b')], result='mean', tolerance='0.000001'), self.m)

    def test_unit_scope_zero_denominator_and_incorrect_value(self):
        calc = dict(type='ratio', numerator='a', denominator='b', result='r', tolerance='0')
        for key, field, bad in [('b','unit','亩'),('b','scope','different'),('b','value','0'),('r','value','41')]:
            old = self.m[key][field]
            self.m[key][field] = bad
            with self.assertRaises(ValueError):
                c.arithmetic(calc, self.m)
            self.m[key][field] = old

    def test_nonfinite_rejected(self):
        for value in ['NaN','Infinity','-Infinity', True]:
            with self.assertRaises(ValueError):
                c.number(value)

    def test_explicit_depth_mismatch_and_duplicate_operand(self):
        self.m['a']['depth'], self.m['b']['depth'] = '0-20 cm', '20-40 cm'
        with self.assertRaises(ValueError):
            c.arithmetic(dict(type='sum', parts=['a','b'], result='sum', tolerance='0'), self.m)
        with self.assertRaises(ValueError):
            c.calculation_ids(dict(type='sum', parts=['a','a'], result='sum'))

    def test_external_manual_formula_requires_review_not_fake_recomputation(self):
        calc = dict(type='manual', inputs=['a','b'], result='r')
        with self.assertRaises(ValueError):
            c.arithmetic(calc, self.m)
        calc.update(formula='a/b*100', method_basis='合成方法说明', review_locator='合成外部复核记录第1项')
        c.arithmetic(calc, self.m)


class DocxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.docx'

    def make(self, body, rel=''):
        with ZipFile(self.path, 'w') as z:
            z.writestr('[Content_Types].xml', f'<Types xmlns="{c.CT[1:-1]}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="{c.DOCX_TYPE}"/></Types>')
            z.writestr('_rels/.rels', f'<Relationships xmlns="{c.PR[1:-1]}"><Relationship Id="rId1" Type="{c.R[1:-1]}/officeDocument" Target="word/document.xml"/></Relationships>')
            z.writestr('word/document.xml', f'<w:document xmlns:w="{c.W[1:-1]}" xmlns:r="{c.R[1:-1]}"><w:body>{body}</w:body></w:document>')
            if rel:
                z.writestr('word/_rels/document.xml.rels', f'<Relationships xmlns="{c.PR[1:-1]}">{rel}</Relationships>')

    def codes(self):
        return {i['code'] for i in c.check_docx(self.path)['issues']}

    def test_valid_and_missing_field_target(self):
        self.make('<w:bookmarkStart w:id="1" w:name="B"/><w:bookmarkEnd w:id="1"/><w:fldSimple w:instr="REF B"/>')
        self.assertEqual(self.codes(), set())
        self.make('<w:fldSimple w:instr="PAGEREF missing"/>')
        self.assertIn('REF_TARGET', self.codes())

    def test_split_complex_field_and_pair(self):
        self.make('<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText>RE</w:instrText></w:r><w:r><w:instrText>F missing</w:instrText></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>')
        self.assertIn('REF_TARGET', self.codes())
        self.make('<w:fldChar w:fldCharType="end"/>')
        self.assertIn('FIELD_PAIR', self.codes())

    def test_duplicate_bookmark_and_broken_media(self):
        self.make('<w:bookmarkStart w:id="1" w:name="B"/><w:bookmarkStart w:id="1" w:name="B"/>', f'<Relationship Id="r1" Type="{c.R[1:-1]}/image" Target="media/missing.png"/>')
        self.assertTrue({'BOOKMARK_PAIR','DUPLICATE_BOOKMARK_NAME','MISSING_REL_TARGET'} <= self.codes())

    def test_deleted_error_ignored_and_external_not_fetched(self):
        self.make('<w:del><w:r><w:t>Error! Reference source not found</w:t></w:r></w:del>', f'<Relationship Id="r1" Type="{c.R[1:-1]}/hyperlink" Target="https://example.invalid" TargetMode="External"/>')
        self.assertEqual(self.codes(), set())
        self.assertNotIn('FIELD_ERROR_TEXT', self.codes())
        self.assertEqual(len(c.check_docx(self.path)['external_relationships']), 1)
        self.make('<w:p><w:r><w:t>错误! 未找到引用源。</w:t></w:r></w:p>')
        self.assertIn('FIELD_ERROR_TEXT', self.codes())

    def test_bookmark_order_and_duplicate_field_separator(self):
        self.make('<w:bookmarkEnd w:id="1"/><w:bookmarkStart w:id="1" w:name="B"/>')
        self.assertIn('BOOKMARK_ORDER', self.codes())
        self.make('<w:fldChar w:fldCharType="begin"/><w:instrText>PAGE</w:instrText><w:fldChar w:fldCharType="separate"/><w:fldChar w:fldCharType="separate"/><w:fldChar w:fldCharType="end"/>')
        self.assertIn('FIELD_PAIR', self.codes())

    def test_overlap_bookmarks_and_nested_fields_are_valid(self):
        self.make('<w:bookmarkStart w:id="1" w:name="A"/><w:bookmarkStart w:id="2" w:name="B"/><w:bookmarkEnd w:id="1"/><w:bookmarkEnd w:id="2"/><w:fldChar w:fldCharType="begin"/><w:instrText>PAGE</w:instrText><w:fldChar w:fldCharType="begin"/><w:instrText>PAGE</w:instrText><w:fldChar w:fldCharType="end"/><w:fldChar w:fldCharType="separate"/><w:fldChar w:fldCharType="end"/>')
        self.assertEqual(self.codes(), set())

    def test_undefined_relationship_id(self):
        self.make('<w:hyperlink r:id="rMissing"/>')
        self.assertIn('REL_ID_REF', self.codes())

    def test_two_file_zip_is_not_docx(self):
        with ZipFile(self.path, 'w') as z:
            z.writestr('[Content_Types].xml', '<not_content_types/>')
            z.writestr('word/document.xml', f'<w:document xmlns:w="{c.W[1:-1]}"><w:body/></w:document>')
        with self.assertRaises(ValueError):
            c.check_docx(self.path)

    def test_not_zip_returns_input_error(self):
        self.path.write_text('not zip', encoding='utf-8')
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(c.main(['docx-check', str(self.path)]), 2)

    def test_wrong_document_root_rejected(self):
        with ZipFile(self.path, 'w') as z:
            z.writestr('[Content_Types].xml', '<Types/>')
            z.writestr('word/document.xml', '<not_a_document/>')
        with self.assertRaises(ValueError):
            c.check_docx(self.path)


if __name__ == '__main__':
    unittest.main()
