"""
Regression tests for the fund-matching scoring/selection logic in
schemecodes.py — see GOTCHAS.md for the story behind each case.

These are hardcoded (query, category, candidate scheme names, expected
winner) fixtures, most pulled directly from real mfapi.in scheme names we
actually hit while building FUND_UNIVERSE. The point isn't coverage for its
own sake: it's that a future edit to compute_score()/score_candidate()/
select_winner() that reintroduces one of these specific bad matches fails
immediately here, instead of silently shipping a wrong fund in
verified_funds.json again.

Run with: python -m pytest test_scoring.py -v
     or:  python test_scoring.py   (plain assert runner, no pytest needed)
"""

from schemecodes import tokenize, score_candidate, select_winner, is_valid_candidate


def resolve(query, category, candidate_names):
    """Mini version of the resolve_all() inner loop, minus the network
    call — filters candidates through is_valid_candidate(), scores the
    survivors, and runs them through the real select_winner() used in
    production. Returns the winning scheme name, or None if it would be
    filtered out entirely or flagged for manual review."""
    query_tokens = tokenize(query)
    scored = []
    for name in candidate_names:
        if not is_valid_candidate(name):
            continue
        score, missing, extra = score_candidate(query_tokens, name, category)
        scored.append((score, missing, extra, {"schemeName": name, "schemeCode": 0}))
    scored.sort(key=lambda x: x[0], reverse=True)
    winner = select_winner(scored)
    return winner["schemeName"] if winner else None


CASES = [
    # --- Gotcha #1: FOF/US/Overseas/Global should NOT be penalized for
    # International-category funds — they're the expected structure there.
    (
        "ICICI Prudential US Bluechip Equity",
        "International",
        [
            "ICICI Prudential US Bluechip Equity Fund - Direct Plan - Growth",
            "ICICI Prudential Bluechip Fund - Direct Plan - Growth",
        ],
        "ICICI Prudential US Bluechip Equity Fund - Direct Plan - Growth",
    ),
    # Gotcha #5: when Direct/Regular plans share an identical bare name (no
    # plan tag at all in the string, just "- Direct Plan -"/"- Regular
    # Plan -" which PLAN_SUFFIX_RE strips as boilerplate before scoring),
    # scoring genuinely cannot tell them apart — both come out as tied exact
    # matches. This *should* come back None (manual review / hardcode via
    # AMC metadata), not a guess — this case exists to make sure nobody
    # "fixes" the tie-breaking to silently pick one at random.
    (
        "Motilal Oswal Nasdaq 100 FOF",
        "International",
        [
            "Motilal Oswal Nasdaq 100 Fund of Fund - Direct Plan - Growth",
            "Motilal Oswal Nasdaq 100 Fund of Fund - Regular Plan - Growth",
        ],
        None,
    ),

    # --- Gotcha #3: extra unrelated words must be penalized, even with
    # heavy token overlap — these are different funds despite sharing words.
    (
        "ICICI Prudential Bluechip",
        "Large Cap",
        [
            "ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund) - Direct Plan - Growth",
            "ICICI Prudential US Bluechip Equity Fund - Direct Plan - Growth",
        ],
        "ICICI Prudential Large Cap Fund (erstwhile Bluechip Fund) - Direct Plan - Growth",
    ),
    (
        "Motilal Oswal Midcap Fund",
        "Mid Cap",
        [
            "Motilal Oswal Midcap Fund - Direct Plan - Growth",
            "Motilal Oswal Large and Midcap Fund - Direct Plan - Growth",
        ],
        "Motilal Oswal Midcap Fund - Direct Plan - Growth",
    ),
    (
        "HDFC Large Cap",
        "Large Cap",
        [
            "HDFC Large Cap Fund - Direct Plan - Growth Option",
            "HDFC Focused Large Cap Fund - Direct Plan - Growth Option",
        ],
        "HDFC Large Cap Fund - Direct Plan - Growth Option",
    ),

    # --- Gotcha #2: Bonus/IDCW/Dividend plans must be filtered out before
    # scoring ever runs (is_valid_candidate) — their NAV history isn't
    # comparable to Growth plans and must never end up chosen.
    (
        "Nippon India Large Cap",
        "Large Cap",
        [
            "Nippon India Large Cap Fund - Direct Plan - Growth Option",
            "Nippon India Large Cap Fund - Direct Plan - Bonus",
        ],
        "Nippon India Large Cap Fund - Direct Plan - Growth Option",
    ),

    # --- Erstwhile-rename handling: query matches the fund's *old* name,
    # current name has drifted (category words replaced brand words).
    (
        "ICICI Prudential Value Discovery",
        "Value / Contra",
        [
            "ICICI Prudential Value Fund (erstwhile Value Discovery Fund) - Direct Plan - Growth",
            "ICICI Prudential Focused Value Fund - Direct Plan - Growth",
        ],
        "ICICI Prudential Value Fund (erstwhile Value Discovery Fund) - Direct Plan - Growth",
    ),

    # --- Ambiguous toss-up: no confident winner should be picked — this
    # must come back None (manual review), not a guess.
    (
        "Kotak Emerging Equity",
        "Mid Cap",
        [
            "Kotak Global Emerging Market Overseas Equity Active FOF - Direct Plan - Growth",
        ],
        None,
    ),
]


def run():
    failures = []
    for query, category, candidates, expected in CASES:
        got = resolve(query, category, candidates)
        status = "PASS" if got == expected else "FAIL"
        if status == "FAIL":
            failures.append((query, expected, got))
        print(f"[{status}] '{query}' ({category}) -> {got!r}")

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print("\nFAILURES:")
        for query, expected, got in failures:
            print(f"  '{query}': expected {expected!r}, got {got!r}")
        raise SystemExit(1)


# --- pytest-compatible wrapper, so `pytest test_scoring.py` also works if
# pytest happens to be installed. Not a hard dependency — `python
# test_scoring.py` below works standalone without it.
try:
    import pytest

    @pytest.mark.parametrize("query,category,candidates,expected", CASES)
    def test_case(query, category, candidates, expected):
        assert resolve(query, category, candidates) == expected
except ImportError:
    pass


if __name__ == "__main__":
    run()
