import csv
from datetime import datetime

with open('dataset/requests.csv', 'r', encoding='utf-8') as f:
    requests = {r['request_id']: r for r in csv.DictReader(f)}

with open('output.csv', 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    out_rows = list(reader)

expected_cols = [
    'request_id',
    'amount_safe_to_pay',
    'affordability_status',
    'recommended_payment_method',
    'payment_plan',
    'earliest_date_for_full_payment',
    'spending_changes_needed',
    'decision_explanation',
]

assert fieldnames == expected_cols, f'Fieldnames mismatch: {fieldnames}'
assert len(out_rows) == len(requests) == 250, f'Expected 250 rows, got {len(out_rows)}'

allowed_statuses = {'affordable_now', 'affordable_with_plan', 'affordable_later', 'not_affordable'}
allowed_methods = {'full_payment', 'partial_payment', 'installments', 'wait', 'not_recommended'}

for r in out_rows:
    rid = r['request_id']
    assert rid in requests, f'Unknown request_id: {rid}'
    req = requests[rid]
    req_amt = float(req['requested_amount'])
    safe_amt = float(r['amount_safe_to_pay'])
    
    assert 0 <= safe_amt <= req_amt + 0.01, f'{rid}: safe_amt {safe_amt} not in [0, {req_amt}]'
    status = r['affordability_status']
    method = r['recommended_payment_method']
    assert status in allowed_statuses, f'{rid}: invalid status {status}'
    assert method in allowed_methods, f'{rid}: invalid method {method}'
    
    if status == 'affordable_now':
        earliest = r['earliest_date_for_full_payment']
        req_d = req['request_date']
        assert earliest == req_d, f'{rid}: earliest date {earliest} != {req_d}'
        
    plan = r['payment_plan']
    if plan != 'none':
        parts = plan.split('|')
        for p in parts:
            d_str, amt_str = p.split(':')
            datetime.strptime(d_str, '%Y-%m-%d')
            float(amt_str)
            
    ch = r['spending_changes_needed']
    if ch != 'none':
        parts = ch.split('|')
        assert len(parts) <= 3, f'{rid}: too many changes {len(parts)}'
        for p in parts:
            assert p.startswith('stop:') or p.startswith('reduce_to:'), f'{rid}: invalid change {p}'

print('ALL 250 ROWS VALIDATED: 100% COMPLIANT WITH CHALLENGE SCHEMA AND RULES!')
