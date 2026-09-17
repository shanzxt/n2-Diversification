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

**Last updated:** 2026-09-17

**Phase: 2 — Interactive fund-picker tool, built and live in the Shan
website repo (`github.com/shanzxt/Shan`, `D:\Shan\Shan\Website`).**

- **Two bug fixes this session:**
  - **Single-fund selection stats bug (`FundPickerTool.jsx`)**: selecting
    exactly one fund was unconditionally reusing the precomputed
    44-fund-universe window/stats (the deliberately short ~22-month
    window from gotcha #10), rather than that fund's own full history —
    causing wrong return/std/Sharpe and a spurious "shared window is
    shorter than usual" note (structurally meaningless for n=1). Fixed
    by special-casing `weights.size === 1` to compute a fresh
    `getOverlapWindow([singleId], fundsData)` and call
    `computePortfolioStats` against just that fund, leaving all n≥2
    selections (including both presets, whose `expectedEffectiveN`
    values depend on the universe-wide window) untouched. Verified via
    UTI Nifty 50 Index Fund (id 120716): before 0.73% return / 14.03%
    std / -0.25 Sharpe / spurious note; after 11.72% return / 15.73%
    std / 0.46 Sharpe / no note — matching its real 163-month history.
    Committed/pushed (`ef30400`).
  - **Correlation heatmap color scale (`CorrelationHeatmap.jsx`)**: the
    old `colorForCorrelation` faded both branches from the dark
    background color, so any positive correlation (nearly all real fund
    pairs, since the dataset's ~85%-single-factor structure means even
    the "diversifying" HDFC Liquid Fund lands at a noisy +0.46 per
    gotcha #12) only ever mixed toward amber — cells varied in
    lightness, never crossed hue, so low-positive correlations read as
    dim/muddy amber rather than a genuinely distinct color. Fixed with a
    direct RGB lerp between teal and amber across the full `[-1, 1]`
    range (checked against an HSL lerp, which swings through an
    off-palette green/lime midtone — rejected), and unified the legend
    gradient onto the same two-stop scale. Verified live: HDFC Liquid
    Fund's row/column now renders as clearly olive/teal-shifted against
    the all-amber equity funds under the "Add the debt fund" preset.
    Committed/pushed (`7f075e7`).
- **Heatmap color scale made dynamic, plus a new perceived-vs-actual
  diversification visual** (same session, follow-up to the color-hue
  fix above; full writeup in GOTCHAS.md gotchas #22-23): the hue-blend
  fix alone still used a fixed [-1, 1] domain, which compresses this
  dataset's real correlations (roughly 0.3-0.98) into a narrow band —
  `colorForCorrelation` now anchors teal/amber to the min/max
  off-diagonal correlation actually present in the current selection,
  so the same raw correlation value can render differently depending
  on what else is selected (intentional — relative contrast within
  what's on screen, not an absolute scale). Correlation numbers now
  render directly inside each cell (dropped above 10 funds to avoid
  illegible overlap), and the legend shows the live min/max alongside
  the endpoint labels. Added `DiversificationBars.jsx`: two
  directly-comparable bars below the heatmap — one sliced evenly by
  nominal fund weight ("what it looks like you own"), one sliced by
  the selection's own correlation-matrix eigenvalues, long tail grouped
  into "the rest" ("what you actually own") — making the effective-N
  thesis legible as a shape. Required exposing raw `eigenvalues` from
  `computePortfolioStats` (additive field, all 14 tests still pass
  unmodified). Verified live across the all-equity preset (effective N
  1.24, one dominant amber factor) and +debt-fund preset (effective N
  1.66, visibly smaller dominant factor + real teal "rest" segment),
  and confirmed n=1 selections correctly render neither the heatmap nor
  the bars. Committed/pushed (`eadb09e`).
- **Self-explanatory pass**: the tool now teaches its own numbers rather
  than assuming the reader knows what they mean — a start-here
  instruction above the fund list, weight sliders relabeled as live
  normalized percentages (reusing the engine's own `normalizeWeights`,
  no second normalization path), a correlation-heatmap caption plus a
  real inline color-scale legend using the heatmap's own color tokens, a
  dynamic "You're holding N funds but making about M genuinely different
  bets" payoff sentence with a one-time dismissible tooltip bridging back
  to the intro animation's eigenvalue math, a "try it" framing line above
  the presets plus a transient dynamically-computed "that's a real jump —
  from ~X to ~Y" note after a preset click (explicitly ordered never to
  overlap the one-time tooltip), a "worth knowing" heading above the
  confidence notes, and a caption under the stats row. All copy/visual
  only — math engine, heatmap computation, and stats calculations
  untouched. Verified live across manual (non-preset) selections at 1, 2,
  and 3 funds (correct singular/plural grammar each time) and the
  debt-fund-clicked-first edge case (tooltip fires, jump note correctly
  suppressed). Committed and pushed to `main` (`5a5949d`).
- The math engine (`js/overlap.js`, `maths.js`, `eigen.js`,
  `confidence.js`, `portfolioMath.js`) was ported as-is (ESM conversion
  only, no reimplemented math) into `src/lib/portfolioEngine/` in the
  Shan repo, bundled with `funds_aligned.json` as a native Vite JSON
  import — all computation (correlation, covariance, eigenvalues,
  effective N) runs live in the browser, no backend. Full 14/14 test
  parity confirmed with `node --test` in the new location.
  `funds_aligned.json`, not `funds_data.json`, is the shape actually
  bundled — see GOTCHAS.md gotcha #19 for why.
- Live at `/portfolio`, continuing directly below the existing intro
  animation (not a separate page): pick funds from the 45-fund universe
  with a searchable/filterable list, adjust weights via debounced
  sliders, two preset buttons reproducing the exact thesis numbers
  (all-equity effective N ≈ 1.243, +debt fund effective N ≈ 1.661), a
  custom SVG correlation heatmap (amber/teal/dark-bg, single-hover-
  listener design after fixing an early freeze — GOTCHAS.md gotcha #20),
  a stats panel (annualized return/std dev/Sharpe, effective-N headline),
  and confidence-flag tooltips surfaced from the engine's existing
  output. Verified live: manual add/remove, weight-slider drag +
  debounce, search filtering, both presets producing exact expected
  effective-N values, confidence flags rendering correctly.
- **Not yet visually confirmed: narrow-viewport responsiveness** — code
  looks correct (Tailwind responsive classes throughout) but couldn't be
  verified visually due to a Chrome browser-automation `resize_window`
  tooling limitation; flagged as an open caution, not a known bug.
- Committed and pushed to `main` in the Shan repo (`0c3046a`).

**Phase: 1 — Client-side math engine, complete in both Python and JS.**

- Built and validated (Python): input conventions (aligned fund JSON,
  shared overlap window per gotcha #10), core statistical primitives
  (mean, std dev, covariance matrix, correlation matrix), portfolio-level
  formulas for arbitrary weighted subsets of funds (return, std dev,
  Sharpe ratio — `portfolio.py`), Jacobi eigen-decomposition of the
  correlation matrix (`eigen.py`), entropy-based effective-N
  (diversification measured as "effective number of independent bets,"
  not just fund count), and a confidence-flagging system
  (`confidence.py`) that distinguishes portfolio-level facts (e.g. a
  short shared window) from genuinely fund-specific concerns (short
  own-history, low-variance-driven correlation noise). Full writeup of
  that session's work, including a bug found and fixed in the
  confidence-flagging logic, in GOTCHAS.md (gotchas #15–17).
- **Built and validated (JS): all five modules ported to plain JS/Node**
  (`js/overlap.js`, `js/maths.js`, `js/eigen.js`, `js/confidence.js`,
  `js/portfolioMath.js`), tested against golden values dumped from the
  Python reference implementation (`generate_fixtures.py` →
  `js/fixtures.json`, regeneratable, never hand-edited) using Node's
  built-in test runner (`node --test`, no new dependencies). All
  fund-id-keyed structures use `Map` rather than plain objects, to avoid
  JS's silent numeric-key reordering corrupting row/column order
  downstream. The full pipeline — raw weights in, normalized, universe
  stats computed, portfolio stats out — is exercised end-to-end by
  `js/integration.test.js`, matching the shape Phase 2's UI will
  actually call. Full writeup of this session's design decisions
  (Map-vs-object, tolerance-vs-exact-equality, fixture discipline) in
  GOTCHAS.md (gotcha #18).
- **Headline number, now numerically confirmed in both languages:**
  across the current 44-fund universe, effective N ≈ **2.04** — despite
  ~45 nominally distinct funds spanning 13 categories, the *effective*
  number of independent bets is closer to 2 than 44 (top eigenvalue
  ≈37.49 of 44, i.e. ~85% of total variance loads onto a single common
  factor). This is the newsletter's core claim, and it's now backed by a
  real computation on real fund data, cross-validated Python-vs-JS,
  rather than an assertion.
- **Phase 2 now built** — see the Phase 2 status block above.

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
