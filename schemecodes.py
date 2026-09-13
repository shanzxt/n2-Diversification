"""
Step 1 of 2 — run this once (and again only when you add/change funds).

For each fund query, fetches candidates from mfapi.in and scores them by how
closely the scheme name matches the query, auto-picking the best Direct
Growth plan. Ambiguous cases (no confident winner) are left out of
verified_funds.json and flagged for manual review instead of guessing.
"""

import json
import re
import requests

SEARCH_URL = "https://api.mfapi.in/mf/search?q={}"

# Words that often appear in schemes sharing a word with the query but that
# are actually a different fund (international/FOF/multi-asset/etc. variants).
# Penalized when they show up in a candidate but weren't asked for in the query.
FALSE_POSITIVE_WORDS = {
    "us", "overseas", "global", "fof", "multi", "asset",
    "institutional", "focused", "vision",
}

# Some of those words are exactly what defines a legitimate fund in certain
# categories — e.g. Indian AMCs offer US/global index exposure via
# fund-of-funds, so "US"/"Overseas"/"Global"/"FOF" are the expected structure
# for an International-category query, not a false-positive signal. Only
# penalize them for categories where they really do indicate a wrong match.
FALSE_POSITIVE_EXEMPTIONS_BY_CATEGORY = {
    "International": {"us", "overseas", "global", "fof"},
}

# Note: "growth" and "direct" are deliberately NOT stopwords — they're
# stripped off as boilerplate via PLAN_SUFFIX_RE below instead, so that the
# rare fund whose actual (non-boilerplate) name contains "Growth" — e.g.
# "Nippon India Growth Mid Cap Fund" — isn't quietly treated as a match for
# every Direct Growth candidate regardless of what it actually is.
STOPWORDS = {"fund", "plan", "scheme", "the", "of", "and"}

ERSTWHILE_RE = re.compile(r"\(erstwhile\s+([^)]*?)\)", re.IGNORECASE)
PAREN_RE = re.compile(r"\([^)]*\)")
# Strips the "- Direct Plan - Growth Option" style boilerplate suffix that
# every candidate has (we already filtered on it), so it doesn't get counted
# as a meaningful word of the scheme's actual name.
PLAN_SUFFIX_RE = re.compile(r"[-–]\s*(direct|regular)\b.*$", re.IGNORECASE)


def tokenize(text):
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {t for t in text.split() if t and t not in STOPWORDS}


def compute_score(cand_tokens, query_tokens, category=None):
    overlap = cand_tokens & query_tokens
    missing = query_tokens - cand_tokens
    extra = cand_tokens - query_tokens
    fp_words = FALSE_POSITIVE_WORDS - FALSE_POSITIVE_EXEMPTIONS_BY_CATEGORY.get(category, set())
    fp_extra = extra & fp_words
    score = 2 * len(overlap) - 3 * len(missing) - 1 * len(extra) - 4 * len(fp_extra)
    return score, len(missing), len(extra)


def score_candidate(query_tokens, scheme_name, category=None):
    """Returns (score, missing_count, extra_count) for the best-scoring
    interpretation of scheme_name against query_tokens, accounting for
    SEBI-mandated renames ("... (erstwhile Old Fund)")."""
    lower = scheme_name.lower()
    core = PLAN_SUFFIX_RE.sub("", PAREN_RE.sub(" ", lower))
    base_tokens = tokenize(core)
    variants = [base_tokens]

    m = ERSTWHILE_RE.search(lower)
    if m:
        old_tokens = tokenize(m.group(1))
        # A renamed fund is still a match if its *erstwhile* name lines up
        # with the query, even though the current name has drifted away from
        # it (e.g. new category words replacing the old brand words).
        brand_tokens = base_tokens & query_tokens
        variants.append(brand_tokens | old_tokens)

    return max((compute_score(t, query_tokens, category) for t in variants), key=lambda s: s[0])

FUND_UNIVERSE = {
    "Large Cap": [
        "Nippon India Large Cap", "ICICI Prudential Bluechip", "SBI Large Cap Fund",
        "Mirae Asset Large Cap", "HDFC Large Cap",
    ],
    "Flexi Cap": [
        "Parag Parikh Flexi Cap", "HDFC Flexi Cap", "Kotak Flexi Cap Fund",
        "UTI Flexi Cap", "Franklin India Flexi Cap",
    ],
    "Large & Mid Cap": [
        "Motilal Oswal Large and Midcap", "Mirae Asset Large and Midcap",
        "Kotak Large & Mid Cap Fund",
    ],
    "Mid Cap": [
        "Motilal Oswal Midcap Fund", "HDFC Mid Cap Fund",
        "Kotak Mid Cap Fund", "Nippon India Growth Mid Cap", "Axis Midcap",
    ],
    "Small Cap": [
        "Nippon India Small Cap", "SBI Small Cap", "HDFC Small Cap",
        "Axis Small Cap", "Bandhan Small Cap",
    ],
    "Multi Cap": [
        "Nippon India Multi Cap", "Quant Active", "ICICI Prudential Multicap",
    ],
    "ELSS": [
        "Axis ELSS Tax Saver Fund", "Mirae Asset Tax Saver", "Quant Tax Plan",
        "SBI ELSS Tax Saver Fund",
    ],
    "Value / Contra": [
        "ICICI Prudential Value Discovery", "UTI Value Fund",
    ],
    "Focused": [
        "SBI Focused Fund", "HDFC Focused",
    ],
    "Index": [
        "UTI Nifty 50 Index Fund", "HDFC Index Fund Sensex",
        "UTI Nifty Next 50 Index", "Motilal Oswal Nifty Midcap 150 Index",
        "Nippon India Nifty Smallcap 250 Index",
        "Nippon India Nifty 500 Momentum 50 Index",
        "UTI Nifty 500 Value 50 Index",
    ],
    "Hybrid": [
        "HDFC Balanced Advantage", "ICICI Prudential Equity & Debt Fund",
    ],
    "Debt": [
        "HDFC Liquid Fund",
        # ICICI Prudential Short Term Fund is hardcoded directly in
        # verified_funds.json instead — mfapi's /mf/search is unreliable for
        # this query (returns different/incomplete result sets across calls,
        # and has previously omitted the correct scheme entirely). The
        # earlier automated run picked code 120608, "ICICI Prudential Short
        # Term GILT Fund", a different, seemingly discontinued scheme with
        # corrupted meta.scheme_type data and NAV history stopping in 2018.
        # The correct fund is code 120754, "ICICI Prudential Short Term
        # Fund - Direct Plan - Growth" (exact name match, clean metadata,
        # current NAV history) — confirmed directly via /mf/120754.
    ],
    "International": [
        "ICICI Prudential US Bluechip Equity",
        # Motilal Oswal Nasdaq 100 FOF is hardcoded directly in
        # verified_funds.json — mfapi lists both Direct and Regular plans
        # under the identical bare name "Motilal Oswal Nasdaq 100 Fund of
        # Fund" with no plan tag, so search/scoring can't disambiguate it.
    ],
}


def search(query):
    resp = requests.get(SEARCH_URL.format(query), timeout=15)
    resp.raise_for_status()
    return resp.json()


# Minimum score margin between the best and second-best full match before we
# trust the top pick instead of calling it a toss-up.
CONFIDENCE_GAP = 3


def is_valid_candidate(scheme_name):
    """Direct Growth plans only — Bonus/IDCW/Dividend variants aren't valid
    for return calculations (see GOTCHAS.md #2), and Regular plans aren't
    what we want. Pulled out of resolve_all() so it's directly testable."""
    lower = scheme_name.lower()
    return (
        "direct" in lower
        and "growth" in lower
        and "bonus" not in lower
        and "idcw" not in lower
        and "dividend" not in lower
    )


def select_winner(scored):
    """Given a list of (score, missing, extra, candidate) sorted by score
    descending, returns the winning candidate dict if confident, else None.
    Pulled out of resolve_all() so test_scoring.py can exercise the exact
    same decision logic used in production instead of a re-implementation
    of it that could silently drift out of sync."""
    # Only candidates that contain every query token (in some interpretation,
    # including erstwhile names) are viable matches.
    full_matches = [s for s in scored if s[1] == 0]
    # An "exact" match has every query token and nothing extra — its name
    # (minus plan/growth boilerplate) *is* the query. This beats a
    # same-scoring near-match even when the score gap is small, since it's
    # the strongest signal fund names give us.
    exact_matches = [s for s in full_matches if s[2] == 0]

    if len(exact_matches) == 1:
        return exact_matches[0][3]
    if len(exact_matches) >= 2:
        if exact_matches[0][0] - exact_matches[1][0] >= CONFIDENCE_GAP:
            return exact_matches[0][3]
        return None
    if len(full_matches) == 1 and full_matches[0][0] > 0:
        return full_matches[0][3]
    if len(full_matches) >= 2 and full_matches[0][0] > 0:
        if full_matches[0][0] - full_matches[1][0] >= CONFIDENCE_GAP:
            return full_matches[0][3]
    return None


def resolve_all():
    verified = {}
    auto_selected = []   # (query, category, schemeName, schemeCode) for the summary table
    needs_review = []    # (query, category, [candidate dicts]) for the manual-review list
    total = sum(len(v) for v in FUND_UNIVERSE.values())
    n = 0

    for category, queries in FUND_UNIVERSE.items():
        for query in queries:
            n += 1
            results = search(query)
            candidates = [r for r in results if is_valid_candidate(r["schemeName"])]
            if not candidates:
                print(f"[{n}/{total}] '{query}' ({category}): NO Direct Growth matches found. Skipping.")
                continue

            query_tokens = tokenize(query)
            scored = []
            for c in candidates:
                score, missing, extra = score_candidate(query_tokens, c["schemeName"], category)
                scored.append((score, missing, extra, c))
            scored.sort(key=lambda x: x[0], reverse=True)

            chosen = select_winner(scored)

            if chosen is not None:
                verified[query] = {
                    "schemeCode": chosen["schemeCode"],
                    "schemeName": chosen["schemeName"],
                    "category": category,
                }
                auto_selected.append((query, category, chosen["schemeName"], chosen["schemeCode"]))
                print(f"[{n}/{total}] '{query}' ({category}): -> {chosen['schemeName']} [{chosen['schemeCode']}]")
            else:
                needs_review.append((query, category, scored))
                print(f"[{n}/{total}] '{query}' ({category}): NEEDS MANUAL REVIEW ({len(scored)} candidates)")

    return verified, auto_selected, needs_review


def print_summary(auto_selected, needs_review):
    print("\n" + "=" * 90)
    print("AUTO-SELECTED FUNDS")
    print("=" * 90)
    if not auto_selected:
        print("(none)")
    else:
        query_w = max(len(q) for q, *_ in auto_selected)
        for query, category, scheme_name, scheme_code in auto_selected:
            print(f"{query:<{query_w}}  [{category}]  {scheme_name}  (code {scheme_code})")

    print("\n" + "=" * 90)
    print("NEEDS MANUAL REVIEW")
    print("=" * 90)
    if not needs_review:
        print("(none)")
    else:
        for query, category, scored in needs_review:
            print(f"\n'{query}' ({category}):")
            for score, missing, _extra, c in scored:
                flag = "" if missing == 0 else "  [missing query terms]"
                print(f"  score={score:>3}  {c['schemeName']}  [code {c['schemeCode']}]{flag}")


if __name__ == "__main__":
    verified, auto_selected, needs_review = resolve_all()
    with open("verified_funds.json", "w") as f:
        json.dump(verified, f, indent=2)
    print(f"\nSaved {len(verified)} verified funds to verified_funds.json")
    print_summary(auto_selected, needs_review)