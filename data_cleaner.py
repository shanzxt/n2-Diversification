import json
from datetime import date
from collections import Counter

with open('funds_data.json', 'r') as f:
    funds = json.load(f)

today = date.today()
current_month = f"{today.year}-{today.month:02d}"

for fund in funds:
    pairs = [(m, r) for m, r in zip(fund['months'], fund['returns']) if m < current_month]
    fund['months'] = [m for m, r in pairs]
    fund['returns'] = [r for m, r in pairs]

# One-off, manually reviewed fix: fund 119091 (HDFC Liquid Fund - Direct Plan
# - Growth Option) is missing 2015-08 entirely in the source data (confirmed
# absent, not null). Interpolated as the average of 2015-07 and 2015-09.
# NOT a general policy — do not extend this to other funds/gaps. See GOTCHAS.md.
for fund in funds:
    if fund['id'] == 119091 and '2015-08' not in fund['months']:
        lookup = dict(zip(fund['months'], fund['returns']))
        if '2015-07' in lookup and '2015-09' in lookup:
            interpolated = (lookup['2015-07'] + lookup['2015-09']) / 2
            insert_at = next(
                (i for i, m in enumerate(fund['months']) if m > '2015-08'),
                len(fund['months'])
            )
            fund['months'].insert(insert_at, '2015-08')
            fund['returns'].insert(insert_at, interpolated)
            fund['interpolated_dates'] = fund.get('interpolated_dates', []) + ['2015-08']

all_months=set()  #notes for self- set() is a data type that stores unique values, so it will automatically remove duplicates (basically a bucket to dump all the months)
for x in funds:
    all_months.update(x['months'])

master_dates = sorted(all_months)

for m in master_dates:
    year, month = m.split("-")
    assert len(year) == 4 and len(month) == 2, f"Unexpected format: {m}"

for fund in funds:
    fund['lookup'] = dict(zip(fund['months'], fund['returns']))

for fund in funds:
    fund['aligned_returns'] = [fund['lookup'].get(m, None) for m in master_dates]

for fund in funds:
    non_null = sum(1 for r in fund['aligned_returns'] if r is not None)
    assert non_null == len(fund['months']), f"Mismatch for {fund['name']}"

mismatches = []
for fund in funds:
    non_null = sum(1 for r in fund['aligned_returns'] if r is not None)
    if non_null != len(fund['months']):
        mismatches.append((fund['name'], non_null, len(fund['months'])))

output = {
    "dates": master_dates,
    "funds": [
        {
            "id": fund["id"],
            "name": fund["name"],
            "category": fund["category"],
            "returns": fund["aligned_returns"],
            **({"interpolated_dates": fund["interpolated_dates"]} if "interpolated_dates" in fund else {})
        }
        for fund in funds
    ]
}

with open('funds_aligned.json', 'w') as f:
    json.dump(output, f, indent=2)

