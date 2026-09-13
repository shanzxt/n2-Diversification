import json
import sys

def find_internal_gaps(fund, dates):
    """
    Checks a single fund's aligned returns for a gap in the MIDDLE of its
    history — i.e. a null that appears after the fund's first non-null
    value and before its last non-null value. Leading nulls (fund just
    hasn't started yet) and trailing nulls (fund hasn't reported the
    latest months yet) are normal and NOT flagged.
    """
    returns = fund['returns']
    non_null_idx = [i for i, r in enumerate(returns) if r is not None]

    if not non_null_idx:
        return {"fund_id": fund['id'], "name": fund.get('name'), "status": "no_data"}

    first, last = non_null_idx[0], non_null_idx[-1]
    gap_idx = [i for i in range(first, last + 1) if returns[i] is None]

    if gap_idx:
        return {
            "fund_id": fund['id'],
            "name": fund.get('name'),
            "status": "GAP",
            "gap_dates": [dates[i] for i in gap_idx],
            "history_range": (dates[first], dates[last]),
        }
    return {
        "fund_id": fund['id'],
        "name": fund.get('name'),
        "status": "clean",
        "history_range": (dates[first], dates[last]),
        "n_months": last - first + 1,
    }


def main(path):
    with open(path, 'r') as f:
        data = json.load(f)

    dates = data['dates']
    results = [find_internal_gaps(fund, dates) for fund in data['funds']]

    dated = [r for r in results if r['status'] in ('clean', 'GAP')]
    dated.sort(key=lambda r: r['history_range'][0], reverse=True)

    print(f"\nFunds sorted by LATEST start date (top 5 — these constrain any overlap window):")
    for r in dated[:5]:
        print(f"  - {r['fund_id']} ({r['name']}): starts {r['history_range'][0]}")

    gappy = [r for r in results if r['status'] == 'GAP']
    no_data = [r for r in results if r['status'] == 'no_data']
    clean = [r for r in results if r['status'] == 'clean']

    print(f"Checked {len(results)} funds.\n")

    if gappy:
        print(f"⚠️  {len(gappy)} fund(s) with a MID-SERIES GAP:")
        for r in gappy:
            print(f"  - {r['fund_id']} ({r['name']}): history {r['history_range'][0]} to "
                  f"{r['history_range'][1]}, missing {r['gap_dates']}")
    else:
        print("✅ No mid-series gaps found in any fund.")

    if no_data:
        print(f"\n⚠️  {len(no_data)} fund(s) with NO data at all:")
        for r in no_data:
            print(f"  - {r['fund_id']} ({r['name']})")

    print(f"\n{len(clean)} fund(s) clean (only leading/trailing nulls, if any).")

    return results


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "funds_aligned.json"
    main(path)