"""
Regression tests for NAV-data-cleaning logic in fetchfunddata.py — see
GOTCHAS.md (gotchas #6, #8) for the story behind these.

Run with: python -m pytest test_fetchdata.py -v
     or:  python test_fetchdata.py   (plain assert runner, no pytest needed)
"""

from fetchfunddata import drop_known_bad_returns, KNOWN_BAD_RETURNS


CASES = [
    # Gotcha #6: HDFC Liquid Fund's one-time face-value-consolidation month
    # must be dropped for its known scheme code...
    (
        119091,
        ["2015-07", "2015-08", "2015-09"],
        [0.005, 99.66, 0.006],
        ["2015-07", "2015-09"],
        [0.005, 0.006],
    ),
    # ...but the exact same month label for any OTHER scheme code must be
    # left untouched — this is a scheme-specific patch, not a blanket
    # "drop everyone's August 2015" filter.
    (
        118632,
        ["2015-07", "2015-08", "2015-09"],
        [0.01, 0.02, -0.01],
        ["2015-07", "2015-08", "2015-09"],
        [0.01, 0.02, -0.01],
    ),
    # A scheme code with no entry in KNOWN_BAD_RETURNS at all must pass
    # through completely unmodified.
    (
        999999,
        ["2020-01", "2020-02"],
        [0.03, -0.02],
        ["2020-01", "2020-02"],
        [0.03, -0.02],
    ),
]


def run():
    failures = []
    for code, months, returns, expected_months, expected_returns in CASES:
        got_months, got_returns = drop_known_bad_returns(code, list(months), list(returns))
        ok = got_months == expected_months and got_returns == expected_returns
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures.append((code, (expected_months, expected_returns), (got_months, got_returns)))
        print(f"[{status}] scheme {code} -> months={got_months}")

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} passed")
    if failures:
        print("\nFAILURES:")
        for code, expected, got in failures:
            print(f"  scheme {code}: expected {expected}, got {got}")
        raise SystemExit(1)


try:
    import pytest

    @pytest.mark.parametrize("code,months,returns,expected_months,expected_returns", CASES)
    def test_case(code, months, returns, expected_months, expected_returns):
        got_months, got_returns = drop_known_bad_returns(code, list(months), list(returns))
        assert got_months == expected_months
        assert got_returns == expected_returns
except ImportError:
    pass


if __name__ == "__main__":
    run()
