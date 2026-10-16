"""Fixture matching and source-span checks; no inference or semantic guarantees."""
import argparse
import collections
import json
import math
import pathlib
import re

KEY_FIELDS = ('subject', 'location', 'year', 'outcome', 'value', 'unit', 'qualifier')

def normalized(value):
    if isinstance(value, str):
        return re.sub(r'\s+', ' ', value.strip().casefold())
    return value

def key(claim):
    return tuple(normalized(claim.get(field)) for field in KEY_FIELDS)

def validate(claim, text):
    if not isinstance(claim, dict):
        return 'claim_not_object'
    for field in ('subject', 'outcome', 'unit', 'qualifier'):
        if not isinstance(claim.get(field), str) or not claim[field].strip():
            return 'invalid_' + field
    if claim.get('location') is not None and not isinstance(claim['location'], str):
        return 'invalid_location'
    if claim.get('year') is not None and type(claim['year']) is not int:
        return 'invalid_year'
    if type(claim.get('value')) not in (int, float) or not math.isfinite(claim['value']):
        return 'invalid_value'
    if not isinstance(claim.get('evidence_text'), str) or not claim['evidence_text'].strip():
        return 'missing_evidence'
    if claim['evidence_text'] not in text:
        return 'evidence_not_verbatim'
    return None

def evaluate(inputs, gold, output):
    if not isinstance(output, dict) or not isinstance(output.get('cases'), list):
        raise ValueError('Output must contain a cases array.')
    source = {c['id']: c for c in inputs['cases']}
    expected = {c['id']: c['claims'] for c in gold['cases']}
    supplied = {}
    for case in output['cases']:
        if not isinstance(case, dict) or not isinstance(case.get('id'), str):
            raise ValueError('Malformed case.')
        if case['id'] not in source or case['id'] in supplied:
            raise ValueError('Unknown or duplicate case ID: ' + case['id'])
        supplied[case['id']] = case
    totals = collections.Counter()
    details = []
    for ident, passage in source.items():
        case = supplied.get(ident)
        if case is None or not isinstance(case.get('claims'), list):
            rows = []
            errors = ['missing_case_or_invalid_claims_collection']
        else:
            rows = case['claims']
            errors = []
        wanted = collections.Counter(key(c) for c in expected[ident])
        matched = 0
        seen = set()
        unmatched = []
        for index, row in enumerate(rows):
            reason = validate(row, passage['text'])
            if reason:
                errors.append({'index': index, 'reason': reason})
                continue
            k = key(row)
            if k in seen:
                errors.append({'index': index, 'reason': 'duplicate_claim'})
            elif wanted[k] > 0:
                wanted[k] -= 1
                matched += 1
            else:
                unmatched.append(row)
            seen.add(k)
        missing = sum(wanted.values())
        totals.update(matched=matched, expected=len(expected[ident]), emitted=len(rows))
        details.append({'id': ident, 'matched': matched, 'expected': len(expected[ident]),
                        'emitted': len(rows), 'missing': missing, 'errors': errors,
                        'unmatched_requires_review': unmatched,
                        'complete': not errors and not unmatched and missing == 0})
    return {'status': 'scored_model_output',
            'fixture_match_precision': totals['matched']/totals['emitted'] if totals['emitted'] else None,
            'fixture_recall': totals['matched']/totals['expected'] if totals['expected'] else None,
            'counts': dict(totals), 'cases': details,
            'all_cases_complete': all(c['complete'] for c in details),
            'limitations': ['Fixture matching is not corpus-wide factual accuracy.',
                           'Verbatim evidence does not itself establish semantic support.',
                           'Unmatched claims require review; they are not automatically hallucinations.',
                           'Order variants reuse source facts and are not independent observations.']}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', default='passages.json')
    parser.add_argument('--gold', default='evaluation_only/gold.json')
    parser.add_argument('--output', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    read = lambda p: json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
    result = evaluate(read(args.inputs), read(args.gold), read(args.output))
    pathlib.Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('counts', 'fixture_match_precision', 'fixture_recall', 'all_cases_complete')}))

if __name__ == '__main__':
    main()
