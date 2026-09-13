"""
Step 2 of 2 — run this whenever you want fresh NAV data (e.g. weekly).
Reads verified_funds.json (from resolve_scheme_codes.py) and builds the
compact JSON the website ships. Output is minified, not pretty-printed —
this file is consumed by JS, not read by humans.
"""

import json
import time
import requests
from datetime import datetime

SCHEME_URL = "https://api.mfapi.in/mf/{}"

# One-time, scheme-specific patch — NOT a general outlier filter. See
# GOTCHAS.md for the full writeup. HDFC Liquid Fund (scheme 119091) has a
# genuine ~100x NAV level shift in mfapi's raw data between 2015-07-31
# (NAV ~28.39) and 2015-08-31 (NAV ~2857.83) — a real face-value
# consolidation event, not a spurious/reverting data-entry error. NAV stays
# at the new ~100x scale permanently afterward (confirmed against the
# scheme's current NAV, ~5578 as of Sep 2026), so deleting a raw NAV row
# before month-end bucketing can't fix this: whichever single row you drop,
# the 100x step just gets absorbed by a different month's return instead of
# disappearing. The only way to get a single clean exclusion is to drop the
# one resulting corrupted monthly return itself (the "2015-08" entry, i.e.
# the Jul-2015 -> Aug-2015 transition) after to_monthly_returns() computes
# it. If another fund in FUND_UNIVERSE turns out to have a similar
# face-value/consolidation jump, it will NOT be caught by this — add a new
# entry here (keyed by scheme code) after confirming it the same way: check
# whether the raw NAV level shift persists forward (real consolidation) vs.
# reverts (data glitch) before treating it the same way.
KNOWN_BAD_RETURNS = {
    119091: {"2015-08"},  # HDFC Liquid Fund face-value consolidation, see above
}


def drop_known_bad_returns(scheme_code, months, returns):
    bad = KNOWN_BAD_RETURNS.get(scheme_code)
    if not bad:
        return months, returns
    kept = [(m, r) for m, r in zip(months, returns) if m not in bad]
    return [m for m, _ in kept], [r for _, r in kept]


def fetch_nav_history(scheme_code):
    resp = requests.get(SCHEME_URL.format(scheme_code), timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", [])


def to_monthly_returns(nav_rows):
    parsed = []
    for row in nav_rows:
        try:
            d = datetime.strptime(row["date"], "%d-%m-%Y")
            parsed.append((d, float(row["nav"])))
        except (ValueError, KeyError):
            continue
    parsed.sort(key=lambda x: x[0])

    month_end = {}
    for d, nav in parsed:
        month_end[(d.year, d.month)] = nav

    keys = sorted(month_end.keys())
    navs = [month_end[k] for k in keys]

    returns = [
        round((navs[i] / navs[i - 1]) - 1, 6)
        for i in range(1, len(navs)) if navs[i - 1] > 0
    ]
    months = [f"{y}-{m:02d}" for (y, m) in keys[1:]]
    return months, returns


def build():
    with open("verified_funds.json") as f:
        verified = json.load(f)

    dataset = []
    for query, info in verified.items():
        code = info["schemeCode"]
        try:
            rows = fetch_nav_history(code)
        except requests.RequestException as e:
            print(f"[skip] {info['schemeName']} ({e})")
            continue

        if len(rows) < 24:
            print(f"[skip] {info['schemeName']} (insufficient history)")
            continue

        months, returns = to_monthly_returns(rows)
        months, returns = drop_known_bad_returns(code, months, returns)
        dataset.append({
            "id": code,
            "name": info["schemeName"],
            "category": info["category"],
            "months": months,
            "returns": returns,
        })
        print(f"[ok] {info['category']:<18} {info['schemeName']}")
        time.sleep(0.3)

    return dataset


if __name__ == "__main__":
    data = build()
    # compact, no indent -- this ships to the browser, not for human reading
    with open("funds_data.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"\nSaved {len(data)} funds to funds_data.json (compact)")