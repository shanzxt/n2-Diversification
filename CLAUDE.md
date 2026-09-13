# n2-Diversification Newsletter — Project Notes

## What this is

A mutual fund newsletter issue about portfolio diversification. The
centerpiece is an interactive, in-browser animation/visualization that
starts from a small toy dataset (e.g. 5 numbers), walks through computing
mean and standard deviation, then builds up to the portfolio risk formula
(variance of a portfolio as a function of asset weights, individual
variances, and pairwise correlations) — using real fund return data instead
of made-up numbers, so readers can see the concept apply to actual mutual
funds.

## Architecture decision: offline pipeline → static JSON → client-side math

No backend, no server-side computation at request time. Everything that
needs live network calls or is likely to change (fund NAV history) is
resolved **offline, ahead of time**, in this `Code/` directory, and baked
into a single static JSON file the website ships as a static asset. All the
actual math (returns, mean, std dev, correlation, covariance, portfolio
variance) runs in the reader's browser in JS, against that static JSON —
not recomputed per request, not fetched live from mfapi.in at page-load
time.

Why: mfapi.in is a free, rate-limit-prone, occasionally unreliable
third-party API (see [GOTCHAS.md](GOTCHAS.md)) — not something to depend on
at serve time for a newsletter page real people load. Resolving fund
identities and pulling NAV history is a one-time (or "rerun occasionally")
offline job; the website itself only needs to read a small trusted JSON
blob and do arithmetic.

Pipeline:

```
schemecodes.py  →  verified_funds.json  →  fetchfunddata.py  →  funds_data.json  →  (ships to browser, JS does the math)
   (Step 1)      (fund name → scheme code,   (Step 2)         (compact NAV-derived
                  verified against mfapi.in)                   monthly returns per fund)
```

- **`schemecodes.py`** — Run once, and again only when funds are added/changed.
  Takes a hand-maintained `FUND_UNIVERSE` of ~47 fund search queries across
  13 categories (Large Cap, Flexi Cap, Large & Mid Cap, Mid Cap, Small Cap,
  Multi Cap, ELSS, Value/Contra, Focused, Index, Hybrid, Debt,
  International), searches mfapi.in for each, and scores/picks the correct
  Direct Growth scheme code non-interactively. Ambiguous cases are left out
  and flagged for manual review rather than guessed. Some funds mfapi's
  search can't reliably resolve are hardcoded directly into
  `verified_funds.json` instead (see GOTCHAS.md) — **note: rerunning this
  script regenerates `verified_funds.json` from scratch and will silently
  wipe those hardcoded entries; always re-add them after a full rerun.**
- **`verified_funds.json`** — query → `{schemeCode, schemeName, category}`.
  The trusted, human-reviewed mapping. Source of truth for Step 2.
- **`fetchfunddata.py`** — Run whenever fresh NAV data is wanted (e.g.
  weekly). Reads `verified_funds.json`, pulls full NAV history per scheme
  code from mfapi.in, converts to month-end NAV → monthly returns, and
  writes a compact (non-pretty-printed) `funds_data.json` for the browser.
- **`funds_data.json`** — the only file the live website actually consumes.
  List of `{id, name, category, months[], returns[]}` per fund.

## Roadmap

- **Phase 0 — Data pipeline** *(current phase, see status below)*: get a
  clean, verified, ~45-fund dataset with reliable monthly return history
  across categories, resolved via `schemecodes.py`/`fetchfunddata.py`, with
  known data-quality issues (bad NAV points, wrong scheme codes, dead
  schemes) found and fixed rather than silently baked in.
- **Phase 1 — Client-side math engine**: JS that reads `funds_data.json`
  and computes mean, standard deviation, pairwise correlation/covariance,
  and portfolio variance/risk for arbitrary weighted combinations of funds,
  entirely in the browser.
- **Phase 2 — Interactive animation/visualization**: the toy-dataset →
  mean/stdev → portfolio-risk-formula animation described in
  `../Ideas.txt`, wired up to the real fund data via the Phase 1 math
  engine.
- **Phase 3 — Newsletter integration & ship**: embed the finished
  visualization into the actual newsletter issue, polish/cross-browser
  check, publish.

## Status (update this section every work session)

**Last updated:** 2026-09-12

**Phase: 0 — Data pipeline.**

- `verified_funds.json`: **45 of 47** target funds resolved and verified.
- `funds_data.json` rebuilt from the current 45 with 0 skips; passed 3
  sanity checks (date-range coverage, debt-vs-equity volatility spread,
  correlation between adjacent index/active funds).
- **Still pending (2 funds, both ICICI Prudential, deliberately deferred
  pending more digging — do not guess):**
  - **ICICI Prudential Multicap** — no live Direct/Growth plan found;
    looks like a dead/institutional-only scheme under this query. Needs
    manual research into whether it was renamed or discontinued.
  - **ICICI Prudential Equity & Debt Fund** — mfapi search only returns
    unrelated FOF candidates for this query; needs manual research for the
    correct scheme code, same as the renames already fixed for other funds.
- Data-quality issues found and fixed this phase (full detail in
  [GOTCHAS.md](GOTCHAS.md), gotchas #6–8): wrong scheme code for "ICICI
  Prudential Short Term Fund" (was pointing at a discontinued Gilt fund,
  code 120608; corrected to 120754); a genuine ~100x face-value
  consolidation event in HDFC Liquid Fund's raw NAV history (30-08-2015)
  that was corrupting its mean/std dev and correlation figures — fixed via
  a one-time, scheme-specific `KNOWN_BAD_RETURNS` exclusion in
  `fetchfunddata.py` (corrected stats: mean 0.547%, std dev 0.150%,
  ~34x less volatile than the equity average, as expected for a debt fund;
  correlation with UTI Nifty 50 Index now a sane 0.001, was -0.131).
- Ran a systematic scan of all 45 funds' raw NAV histories for other
  single-day ratio jumps >20x — found only one more class of issue (a
  same-day zero-NAV glitch in Axis Midcap and Axis ELSS Tax Saver Fund,
  2013-04-07), which currently causes no wrong output since it doesn't land
  on a month-end date; left unpatched and flagged as a landmine (gotcha #8)
  rather than fixed pre-emptively.
- Not yet started: Phase 1 (client-side math engine) itself.
