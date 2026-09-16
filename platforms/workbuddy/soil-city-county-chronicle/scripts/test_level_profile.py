"""Synthetic level-detection regression tests; contains no real project facts."""
import json
import tempfile
import unittest
from pathlib import Path

import level_profile as lp


class LevelProfileTests(unittest.TestCase):
    def test_municipal_guide_and_aggregation(self):
        text = ('第三次全国土壤普查省市级成果清单及编制导引。'
                '本节为市级成果报告形成提纲，应核验所辖县级成果并开展县际接边检查。')
        scores, strong, _, decision = lp.analyze_text(text)
        self.assertEqual(decision, 'municipal')
        self.assertGreater(scores['municipal'], scores['county'])
        self.assertGreaterEqual(strong['municipal'], 2)

    def test_county_guide_and_species_detail(self):
        text = ('第三次全国土壤普查县级成果编制及验收导引。'
                '针对所有土属与土种逐个描述，并给出土种典型剖面。')
        _, _, _, decision = lp.analyze_text(text)
        self.assertEqual(decision, 'county')

    def test_city_suffix_is_not_level_evidence(self):
        _, _, _, decision = lp.analyze_text('邵东市土壤志编写模板')
        self.assertEqual(decision, 'unknown')

    def test_weak_prose_is_not_enough(self):
        _, _, _, decision = lp.analyze_text('本市土壤资源丰富，本市农业生产稳定。')
        self.assertEqual(decision, 'unknown')

    def test_conflicting_documents_return_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            municipal = Path(temp, 'municipal.txt')
            county = Path(temp, 'county.txt')
            municipal.write_text('市级成果报告形成提纲；核验所辖县级成果并开展县际接边检查。', encoding='utf-8')
            county.write_text('第三次全国土壤普查县级成果编制及验收导引；所有土属与土种逐个描述。', encoding='utf-8')
            result = lp.detect([municipal, county])
        self.assertEqual(result['decision'], 'unknown')
        self.assertTrue(any('分别出现明确市级和县级角色' in row for row in result['warnings']))

    def test_text_file_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp, 'guide.txt')
            source.write_text('市级成果报告形成提纲；市级成果汇总；市级制图综合。', encoding='utf-8')
            result = lp.detect([source])
        self.assertEqual(result['decision'], 'municipal')
        self.assertEqual(result['selected_profile']['chapter_3_narrative_unit'], 'soil_genus')
        json.dumps(result, ensure_ascii=False)

    def test_unsupported_file(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp, 'guide.pdf')
            source.write_bytes(b'%PDF')
            with self.assertRaisesRegex(ValueError, '没有可分析的文件'):
                lp.detect([source])


if __name__ == '__main__':
    unittest.main()
