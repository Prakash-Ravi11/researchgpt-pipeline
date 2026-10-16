import copy
import json
import pathlib
import unittest
from evaluate import evaluate

ROOT = pathlib.Path(__file__).resolve().parent

class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.inputs = json.loads((ROOT/'passages.json').read_text(encoding='utf-8'))
        self.gold = json.loads((ROOT/'evaluation_only/gold.json').read_text(encoding='utf-8'))
        source = {c['id']: c['text'] for c in self.inputs['cases']}
        self.output = {'cases': [{'id': c['id'], 'claims': [dict(x, evidence_text=source[c['id']]) for x in c['claims']]} for c in self.gold['cases']]}

    def score(self):
        return evaluate(self.inputs, self.gold, self.output)

    def test_supported_fixture(self):
        self.assertTrue(self.score()['all_cases_complete'])

    def test_swapped_subject(self):
        self.output['cases'][1]['claims'][0]['subject'] = 'Netafim'
        self.assertFalse(self.score()['all_cases_complete'])

    def test_duplicate(self):
        self.output['cases'][0]['claims'].append(copy.deepcopy(self.output['cases'][0]['claims'][0]))
        self.assertFalse(self.score()['all_cases_complete'])

    def test_false_location_propagation(self):
        self.output['cases'][1]['claims'][1]['location'] = 'India'
        self.assertFalse(self.score()['all_cases_complete'])

    def test_wrong_value(self):
        self.output['cases'][0]['claims'][0]['value'] = 50
        self.assertFalse(self.score()['all_cases_complete'])

    def test_missing_evidence(self):
        self.output['cases'][0]['claims'][0]['evidence_text'] = 'invented'
        self.assertFalse(self.score()['all_cases_complete'])

    def test_malformed_collection(self):
        self.output['cases'][0]['claims'] = None
        self.assertFalse(self.score()['all_cases_complete'])

    def test_missing_case(self):
        self.output['cases'].pop(0)
        self.assertFalse(self.score()['all_cases_complete'])

    def test_boolean_value(self):
        self.output['cases'][0]['claims'][0]['value'] = True
        self.assertFalse(self.score()['all_cases_complete'])

    def test_duplicate_case(self):
        self.output['cases'].append(copy.deepcopy(self.output['cases'][0]))
        with self.assertRaises(ValueError): self.score()

if __name__ == '__main__':
    unittest.main()
