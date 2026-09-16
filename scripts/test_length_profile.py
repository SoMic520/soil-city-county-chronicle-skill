import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import length_profile as lp


class LengthProfileTests(unittest.TestCase):
    def make_docx(self, path):
        ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        parts = []
        for i in range(1, 7):
            parts.append(f'<w:p><w:pPr><w:pStyle w:val="H1"/></w:pPr><w:r><w:t>第{i}章</w:t></w:r></w:p>')
            parts.append('<w:p><w:r><w:t>有效正文A1。</w:t></w:r><w:del><w:r><w:delText>删除文字</w:delText></w:r></w:del></w:p>')
            parts.append('<w:p><w:pPr><w:pStyle w:val="CAP"/></w:pPr><w:r><w:t>图1.1 题注</w:t></w:r></w:p>')
            parts.append('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格不计</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
        document = f'<w:document xmlns:w="{ns}"><w:body>{"".join(parts)}</w:body></w:document>'
        styles = f'<w:styles xmlns:w="{ns}"><w:style w:type="paragraph" w:styleId="H1"><w:name w:val="heading 1"/></w:style><w:style w:type="paragraph" w:styleId="CAP"><w:name w:val="caption"/></w:style></w:styles>'
        with ZipFile(path, 'w') as z:
            z.writestr('word/document.xml', document)
            z.writestr('word/styles.xml', styles)

    def test_measure_excludes_titles_tables_captions_and_deletions(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'x.docx'
            self.make_docx(path)
            result = lp.measure_docx(path)
            self.assertEqual(len(result['chapters']), 6)
            self.assertEqual([x['effective_characters'] for x in result['chapters']], [6] * 6)
            self.assertEqual(result['total_effective_characters'], 36)

    def plan(self):
        t = {str(i): 1000 for i in range(1, 7)}
        rows = {}
        kinds = {'3':'soil_types','4':'property_indicators','5':'evaluation_modules','6':'recommendation_topics'}
        for cid in lp.CHAPTERS:
            rows[cid] = {'target':1000, 'lower':850, 'upper':1150, 'adaptation_kind':kinds.get(cid),
                         'template_structure_count':10 if cid in kinds else None,
                         'template_fixed_characters':0 if cid in kinds else None,
                         'template_structure_evidence':'合成模板结构标注' if cid in kinds else '',
                         'adaptation_basis':'合成模板和结构计数', 'actual':1000}
        return {'length_schema_version':1, 'measurement_version':lp.VERSION, 'status':'locked',
                'template':{'path':'x','sha256':'0'*64,'identity':'合成模板','measurement_evidence':'合成测试','chapters':t},
                'project_structure':{'soil_types':10,'property_indicators':10,'evaluation_modules':10,'recommendation_topics':10,'basis':'合成结构清单'},
                'chapters':rows, 'total':{'target':6000,'lower':5400,'upper':6600,'actual':6000},
                'formal_override':{'active':False,'basis':'','locator':'','confirmed_by':'','counting_method':''}}

    def codes(self, plan, final=True):
        return {x['code'] for x in lp.validate_plan(plan, final)[0]}

    def test_complete_contract_passes(self):
        self.assertEqual(self.codes(self.plan()), set())

    def test_calculate_targets_is_deterministic_and_never_locks(self):
        p = self.plan()
        p['project_structure']['soil_types'] = 20
        p['chapters']['3'].update(target=None, lower=None, upper=None, actual=None)
        out = lp.calculate_targets(p)
        self.assertEqual((out['chapters']['3']['target'], out['chapters']['3']['lower'], out['chapters']['3']['upper']),
                         (1300, 1105, 1495))
        self.assertEqual(out['status'], 'planning')
        self.assertEqual(out['total']['target'], 6300)
        self.assertEqual(p['chapters']['3']['target'], None)

    def test_chapter_and_total_tolerances_are_enforced(self):
        p = self.plan(); p['chapters']['1'].update(lower=800, upper=1200)
        self.assertIn('LENGTH_TOLERANCE', self.codes(p))
        p = self.plan(); p['total']['upper'] = 7000
        self.assertIn('LENGTH_TOTAL_PLAN', self.codes(p))

    def test_fixed_chapter_cannot_drift_from_template(self):
        p = self.plan(); p['chapters']['1'].update(target=1200, lower=1020, upper=1380)
        p['total'].update(target=6200, lower=5580, upper=6820, actual=6000)
        self.assertIn('LENGTH_TEMPLATE_DISTANCE', self.codes(p))

    def test_variable_chapter_uses_structure_density(self):
        p = self.plan(); p['project_structure']['soil_types'] = 20
        self.assertIn('LENGTH_DENSITY', self.codes(p))
        p['chapters']['3'].update(target=1300, lower=1105, upper=1495, actual=1300)
        p['total'].update(target=6300, lower=5670, upper=6931, actual=6300)
        self.assertIn('LENGTH_TOTAL_PLAN', self.codes(p))
        p['total']['upper'] = lp.ceil_percent(6300, 110)
        self.assertEqual(self.codes(p), set())

    def test_template_distance_caps_target_and_final_total(self):
        p = self.plan()
        p['chapters']['3'].update(target=1400, lower=1190, upper=1610, actual=1400)
        p['total'].update(target=6400, lower=5760, upper=7040, actual=6400)
        self.assertIn('LENGTH_TEMPLATE_DISTANCE', self.codes(p))
        p = self.plan()
        for cid in ('1','2'):
            p['chapters'][cid].update(target=1200, lower=1020, upper=1380, actual=1200)
        for cid in ('3','4','5','6'):
            p['project_structure'][lp.ADAPTATION_KINDS[cid]] = 20
            p['chapters'][cid].update(target=1300, lower=1105, upper=1495, actual=1300)
        p['total'].update(target=7600, lower=6840, upper=8360, actual=7600)
        self.assertIn('LENGTH_TOTAL_TEMPLATE', self.codes(p))

    def test_actual_and_pending_final_are_blocked(self):
        p = self.plan(); p['chapters']['4']['actual'] = 1200
        p['total']['actual'] = 6200
        self.assertIn('LENGTH_ACTUAL', self.codes(p))
        p = self.plan(); p['chapters']['2']['actual'] = None; p['status'] = 'planning'
        self.assertTrue({'LENGTH_ACTUAL','LENGTH_STATUS'} <= self.codes(p))

    def test_bad_types_fail_closed(self):
        p = self.plan(); p['chapters']['1']['target'] = True
        self.assertIn('LENGTH_VALUE', self.codes(p))
        p = self.plan(); p['project_structure']['soil_types'] = -1
        self.assertIn('LENGTH_STRUCTURE', self.codes(p))

    def test_template_fixed_characters_require_valid_tagging(self):
        p = self.plan(); p['chapters']['3']['template_fixed_characters'] = 1000
        self.assertIn('LENGTH_STRUCTURE', self.codes(p))
        p = self.plan(); p['chapters']['3']['template_structure_evidence'] = ''
        self.assertIn('LENGTH_STRUCTURE', self.codes(p))

    def test_confirmed_formal_requirement_can_set_different_targets(self):
        p = self.plan(); p['chapters']['1'].update(target=2000, lower=1700, upper=2300, actual=2000)
        p['total'].update(target=7000, lower=6300, upper=7700, actual=7000)
        self.assertIn('LENGTH_TEMPLATE_DISTANCE', self.codes(p))
        p['formal_override'].update(active=True, basis='合成合同', locator='合成第2条', confirmed_by='合成责任人', counting_method=lp.VERSION)
        self.assertEqual(self.codes(p), set())

    def test_formal_requirement_must_use_same_counting_method(self):
        p = self.plan()
        p['formal_override'].update(active=True, basis='合成合同', locator='合成第2条', confirmed_by='合成责任人', counting_method='页数')
        self.assertIn('LENGTH_FORMAL_OVERRIDE', self.codes(p))


if __name__ == '__main__':
    unittest.main()
