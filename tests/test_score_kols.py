import copy
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('score_kols', ROOT / 'scripts/score_kols.py')
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / '01-kol-profile-and-scoring/scoring-config.json').read_text())
        with (ROOT / '02-sourcing/candidates.csv').open(encoding='utf-8', newline='') as stream:
            self.rows = list(csv.DictReader(stream))

    def rated(self, rating):
        row = dict(self.rows[0])
        for key in self.config['dimensions']:
            row[key] = str(rating)
        return row

    def test_tier_boundaries_and_endpoints(self):
        for rating, tier in [(5, 'A'), (4.25, 'A'), (4.249, 'B'), (3.5, 'B'),
                             (3.499, 'C'), (2.5, 'C'), (2.499, 'D'), (0, 'D')]:
            with self.subTest(rating=rating):
                result = score.rank_rows(self.config, [self.rated(rating)])[0]
                self.assertEqual(result['tier'], tier)
                self.assertAlmostEqual(float(result['score']), rating * 20, places=2)

    def test_weighting_and_custom_configuration(self):
        self.config['dimensions'] = {'audience_fit': 3, 'content_relevance': 1}
        row = self.rated(0)
        row['audience_fit'] = '5'
        result = score.rank_rows(self.config, [row])[0]
        self.assertEqual(result['score'], '75.00')
        self.config['tiers'][1].update(min_score=74, priority='Review next', recommendation='Custom action')
        self.config['scale_max'] = 10
        row['audience_fit'] = '10'
        result = score.rank_rows(self.config, [row])[0]
        self.assertEqual((result['tier'], result['priority'], result['recommendation']),
                         ('B', 'Review next', 'Custom action'))

    def test_deterministic_ties_and_empty_input(self):
        a, b = dict(self.rows[0]), dict(self.rows[1])
        for key in self.config['dimensions']:
            b[key] = a[key]
        self.assertEqual([r['candidate_id'] for r in score.rank_rows(self.config, [b, a])],
                         [a['candidate_id'], b['candidate_id']])
        self.assertEqual(score.rank_rows(self.config, []), [])

    def test_invalid_ratings_and_required_fields(self):
        for value in ['', 'NaN', 'Infinity', '-1', '6', 'unknown']:
            row = self.rated(4)
            row['audience_fit'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                score.rank_rows(self.config, [row])
        row = self.rated(4)
        row['assessed_on'] = 'yesterday'
        with self.assertRaises(ValueError):
            score.rank_rows(self.config, [row])

    def test_duplicate_ids_handles_and_path_traversal(self):
        for field, value in [('candidate_id', self.rows[0]['candidate_id'].lower()),
                             ('candidate_id', '../escape')]:
            rows = copy.deepcopy(self.rows[:2])
            rows[1][field] = value
            with self.assertRaises(ValueError):
                score.rank_rows(self.config, rows)
        rows = copy.deepcopy(self.rows[:2])
        rows[1]['platform'] = rows[0]['platform'].upper()
        rows[1]['handle'] = rows[0]['handle'].upper()
        with self.assertRaises(ValueError):
            score.rank_rows(self.config, rows)

    def test_invalid_config(self):
        for field, value in [('scale_max', 0), ('scale_max', float('nan')),
                             ('dimensions', {}), ('dimensions', {'fit': -1}),
                             ('dimensions', {'fit': 0}), ('dimensions', {'fit': float('inf')})]:
            config = copy.deepcopy(self.config)
            config[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                score.validate_config(config)
        for index, threshold in [(1, 90), (3, 1), (0, 101)]:
            config = copy.deepcopy(self.config)
            config['tiers'][index]['min_score'] = threshold
            with self.assertRaises(ValueError):
                score.validate_config(config)

    def test_html_escaping_and_single_pass_placeholders(self):
        row = score.rank_rows(self.config, [self.rows[0]])[0]
        row['name'] = '<script>alert(1)</script>{{YOUR_PRODUCT}}'
        page = score.render_dashboard([row])
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
        rendered = score.render_email('Hi {{name}}: {{YOUR_PRODUCT}}', row)
        self.assertEqual(rendered, 'Hi ' + row['name'] + ': {{YOUR_PRODUCT}}')

    def test_cli_end_to_end_from_other_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = [sys.executable, str(ROOT / 'scripts/score_kols.py'),
                       '--output-root', tmp, '--generate-emails']
            result = subprocess.run(command, cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            out = Path(tmp)
            with (out / '03-scoring-and-ranking/ranked-kols.csv').open(encoding='utf-8') as stream:
                ranked = list(csv.DictReader(stream))
            self.assertEqual([r['tier'] for r in ranked], list('ABCD'))
            self.assertEqual(len(list((out / '05-first-email-templates/drafts').glob('*.md'))), 4)
            draft = (out / '05-first-email-templates/drafts/SAMPLE-001.md').read_text()
            self.assertIn('Sample Creator A', draft)
            self.assertIn('{{YOUR_PRODUCT}}', draft)
            before = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
            subprocess.run(command, cwd=tmp, check=True, capture_output=True)
            after = {p.relative_to(out): p.read_bytes() for p in out.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            invalid = out / 'invalid.csv'
            invalid.write_text('candidate_id\nBROKEN\n')
            result = subprocess.run(command + ['--input', str(invalid)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((out / '00-console/dashboard.html').read_bytes(),
                             before[Path('00-console/dashboard.html')])


if __name__ == '__main__':
    unittest.main()
