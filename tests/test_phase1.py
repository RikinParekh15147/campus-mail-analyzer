import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from campusmail.nlp import analyze
from campusmail.documents import read_document
from campusmail.training import train_models


class NLPTests(unittest.TestCase):
    def test_two_dates_with_distinct_roles_and_evidence(self):
        text = 'Registration closes on 25 October 2026. The Python workshop will be held on 28 October 2026. Students must register through the portal.'
        result = analyze(text)
        self.assertEqual([(x['normalized'],x['role']) for x in result['dates']], [('2026-10-25','registration_deadline'),('2026-10-28','event_start')])
        for evidence in result['dates'] + result['actions']:
            self.assertEqual(text[evidence['start']:evidence['end']], evidence['text'])

    def test_missing_year_and_ambiguous_numeric_date_abstain(self):
        result = analyze('Submit by 04/05/2026. Meet on 25 October.')
        self.assertTrue(all(d['needs_review'] for d in result['dates']))
        self.assertTrue(all(d['normalized'] is None for d in result['dates']))

    def test_negated_and_completed_actions_are_not_obligations(self):
        self.assertEqual(analyze('Do not submit the old form. Registration has closed.')['actions'], [])

    def test_readable_and_unsupported_files(self):
        self.assertEqual(read_document(b'Course,Marks\nNLP,80', 'marks.csv')['status'], 'readable')
        self.assertEqual(read_document(b'not an image', 'poster.png')['status'], 'unsupported')

    def test_training_split_has_no_duplicate_group_leakage(self):
        rows = [{'text':f'{label} topic example {i}', 'label':label, 'group':f'{label}-{i}'} for label in ('exam','event') for i in range(10)]
        rows.append(dict(rows[0]))
        with TemporaryDirectory() as d:
            report = train_models(rows, Path(d))
            self.assertFalse(set(report['train_groups']) & set(report['test_groups']))
            self.assertEqual(set(report['models']), {'naive_bayes','linear_svm','majority'})
            self.assertTrue((Path(d)/'classifier.joblib').is_file())
