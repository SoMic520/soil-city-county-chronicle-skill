"""Synthetic layout-plan regressions; do not certify actual Word rendering."""
import copy
import json
import unittest
from pathlib import Path

from layout_rules import validate_layout

ROOT = Path(__file__).resolve().parents[1]


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((ROOT / 'templates/project/layout.json').read_text(encoding='utf-8'))
        self.plan = copy.deepcopy(self.base)

    def codes(self, final=False):
        return {i['code'] for i in validate_layout(self.plan, self.base, final)[0]}

    def complete(self):
        self.plan.update(adoption_confirmed=True, target_application='合成目标软件及版本', toc_semantic_levels=['chapter', 'level_1'])
        self.plan['project_details'].update(table_chinese_font='宋体', header_distance_mm=15, footer_distance_mm=17.5)
        for row in self.plan['format_checks'].values():
            row.update(status='passed', evidence='合成检查证据，非真实文档验收')

    def override(self, path, value, **kw):
        row = dict(path=path, value=value, scope='global', basis='合成项目模板第1条', confirmed_by='合成责任方', confirmed=True)
        row.update(kw)
        self.plan['project_overrides_with_basis'].append(row)

    def test_default_plan_is_not_completed_document(self):
        self.assertEqual(self.codes(), set())
        self.assertIn('LAYOUT_CHECK_PENDING', self.codes(True))
        self.assertIn('LAYOUT_DETAILS_PENDING', self.codes(True))

    def test_guide_heading_roles_sizes_and_explicit_bold(self):
        # Exact official heading mappings are an intentional invariant, not prose matching.
        wanted = [('chapter','宋体',18,True), ('level_1','黑体',16,False), ('level_2','宋体',14,True), ('level_3','黑体',12,False), ('level_4','宋体',12,True)]
        for level, (key, font, pt, bold) in enumerate(wanted):
            row = self.plan['styles'][key]
            self.assertEqual((row['style'],row['outline_level'],row['font'],row['pt'],row['bold']), (f'Heading {level+1}',level,font,pt,bold))
            self.assertEqual(row['first_line_chars'], 0 if level == 0 else 2)
        self.assertTrue(self.plan['execution']['headings']['use_chapter_titles'])
        self.assertEqual(self.plan['execution']['headings']['before_lines'], 0.5)

    def test_wrong_heading_font_or_boolean_integer_rejected(self):
        self.plan['styles']['chapter']['font'] = '黑体'
        self.plan['styles']['level_1']['bold'] = 0
        self.assertIn('LAYOUT_PROFILE_DRIFT', self.codes())

    def test_changed_margins_blanks_table_width_need_explicit_basis(self):
        self.plan['execution']['pages']['margins_mm']['left'] = 30
        self.plan['execution']['blocks']['blank_paragraphs_after_explanation'] = 0
        self.plan['execution']['tables']['width_percent_of_text_area'] = 90
        issues, _ = validate_layout(self.plan, self.base)
        self.assertEqual(sum(x['code']=='LAYOUT_PROFILE_DRIFT' for x in issues), 3)

    def test_exact_confirmed_project_exception_allowed(self):
        self.plan['execution']['pages']['margins_mm']['left'] = 30
        self.override('execution.pages.margins_mm.left', 30)
        issues, notes = validate_layout(self.plan, self.base)
        self.assertEqual(issues, [])
        self.assertTrue(notes)

    def test_exception_mismatch_unconfirmed_and_local_scope_rejected(self):
        self.plan['execution']['pages']['margins_mm']['left'] = 30
        self.override('execution.pages.margins_mm.left', 29)
        self.assertIn('LAYOUT_OVERRIDE', self.codes())
        self.plan['project_overrides_with_basis'][0].update(value=30, confirmed=False)
        self.assertIn('LAYOUT_OVERRIDE', self.codes())
        self.plan['project_overrides_with_basis'][0].update(confirmed=True, scope='section:S1')
        self.assertIn('LAYOUT_OVERRIDE', self.codes())

    def test_unknown_duplicate_and_deleted_profile_field_rejected(self):
        self.override('execution.pages.*', 30)
        self.override('styles.chapter.pt', 18)
        self.override('styles.chapter.pt', 18)
        del self.plan['styles']['level_3']['bold']
        self.assertTrue({'LAYOUT_OVERRIDE','LAYOUT_PROFILE_MISSING'} <= self.codes())

    def test_complete_plan_still_only_checks_declared_records(self):
        self.complete()
        self.assertEqual(self.codes(True), set())
        del self.plan['format_checks']['headings']
        self.assertIn('LAYOUT_CHECK_PENDING', self.codes(True))

    def test_passed_without_evidence_and_core_waiver_rejected(self):
        self.complete()
        self.plan['format_checks']['headings']['evidence'] = ''
        self.plan['format_checks']['toc_and_page_numbers']['status'] = 'not_applicable'
        self.assertTrue({'LAYOUT_CHECK_EVIDENCE','LAYOUT_CHECK_WAIVER'} <= self.codes(True))

    def test_no_protected_objects_can_be_not_applicable(self):
        self.complete()
        self.plan['format_checks']['protected_objects'].update(status='not_applicable', evidence='合成任务未指定保护对象')
        self.assertEqual(self.codes(True), set())

    def test_protected_landscape_does_not_change_normal_margins(self):
        self.complete()
        self.plan['preserved_sections_and_objects'] = [dict(id='S_landscape',kind='section',basis='合成模板保留横向节',geometry_locator='合成原pgSz/pgMar记录',review_evidence='合成保存前后比对')]
        self.assertEqual(self.codes(True), set())
        self.assertEqual(self.plan['execution']['pages']['margins_mm']['left'],31.8)
        self.plan['format_checks']['protected_objects']['status']='not_applicable'
        self.assertIn('LAYOUT_CHECK_WAIVER', self.codes(True))

    def test_header_footer_parameters_separate_from_page_margins(self):
        self.complete()
        self.assertEqual(self.plan['execution']['pages']['margins_mm']['top'],25.4)
        self.plan['project_details']['header_distance_mm']=-1
        self.assertIn('LAYOUT_DETAIL', self.codes(True))

    def test_legacy_plan_allows_intake_but_blocks_final(self):
        self.plan={'adoption_confirmed':True, 'target_application':'Word', 'toc_semantic_levels':'全层级'}
        self.assertEqual(self.codes(), set())
        self.assertIn('LAYOUT_UPGRADE', self.codes(True))

    def test_structurally_invalid_plan_rejected(self):
        self.plan['project_overrides_with_basis'] = 'not a list'
        with self.assertRaises(ValueError):
            validate_layout(self.plan,self.base)

    def test_unknown_schema_not_silently_treated_as_legacy(self):
        for value in [999, '2', True, 2.0]:
            self.plan['layout_schema_version'] = value
            with self.assertRaises(ValueError):
                validate_layout(self.plan,self.base)

    def test_confirmed_exception_cannot_create_nonsense_format_value(self):
        self.plan['styles']['chapter']['pt'] = 0
        self.override('styles.chapter.pt', 0)
        self.assertIn('LAYOUT_OVERRIDE', self.codes())
        self.plan = copy.deepcopy(self.base)
        self.plan['styles']['chapter']['font'] = ''
        self.override('styles.chapter.font', '')
        self.assertIn('LAYOUT_OVERRIDE', self.codes())

    def test_toc_accepts_one_or_two_contiguous_semantic_levels(self):
        self.complete()
        for value in [['chapter'], ['chapter', 'level_1']]:
            self.plan['toc_semantic_levels'] = value
            self.assertEqual(self.codes(True), set())

    def test_toc_rejects_free_text_excessive_depth_gaps_and_duplicates(self):
        self.complete()
        for value in ['五级目录，Heading 1至5全收录，不采用N1一级或二级', ['chapter','level_1','level_2'], ['chapter','level_2'], ['chapter','chapter'], ['level_1'], None, 2]:
            self.plan['toc_semantic_levels'] = value
            self.assertIn('LAYOUT_TOC', self.codes())
            self.assertIn('LAYOUT_TOC', self.codes(True))

    def test_toc_empty_can_plan_but_not_finish(self):
        self.complete()
        self.plan['toc_semantic_levels'] = []
        self.assertEqual(self.codes(), set())
        self.assertIn('LAYOUT_TOC_PENDING', self.codes(True))

    def test_toc_depth_exception_requires_basis_and_valid_integer(self):
        self.complete()
        self.plan['toc_semantic_levels'] = ['chapter','level_1','level_2']
        self.plan['county_requirements']['toc_max_depth'] = 3
        self.assertIn('LAYOUT_PROFILE_DRIFT', self.codes())
        self.override('county_requirements.toc_max_depth', 3)
        self.assertEqual(self.codes(True), set())
        for value in [0,6,True,2.5]:
            self.plan['county_requirements']['toc_max_depth'] = value
            self.plan['project_overrides_with_basis'][0]['value'] = value
            self.assertIn('LAYOUT_TOC', self.codes(True))


if __name__ == '__main__':
    unittest.main()
