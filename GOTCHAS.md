# Gotchas & bugs we've already hit

Append to this file every time we hit a new one — the point is that nobody
(including future-us) has to rediscover these the hard way twice. See also
`test_scoring.py` (scoring/resolution bugs in `schemecodes.py`) and
`test_fetchdata.py` (NAV-cleaning bugs in `fetchfunddata.py`), which encode
the ones below as regression tests so a future edit fails loudly instead of
silently reintroducing a bad match or a bad return.

## `schemecodes.py` (fund name → scheme code resolution)

### 1. False-positive word penalty list was initially too broad for "International" category funds

`FALSE_POSITIVE_WORDS` (US, Overseas, Global, FOF, Multi, Asset,
Institutional, Focused, Vision — words that usually signal "this candidate
is actually a different fund") originally penalized every category equally.
That's wrong for the **International** category: Indian AMCs legitimately
offer US/global index exposure via fund-of-funds, so "US", "Overseas",
"Global", and "FOF" are the *expected, correct* structure for an
International-category fund, not a false-positive signal. Penalizing them
there caused legitimate matches (e.g. "ICICI Prudential US Bluechip
Equity") to lose points they shouldn't have lost.

**Fix:** `FALSE_POSITIVE_EXEMPTIONS_BY_CATEGORY` — per-category exemption
set, currently `{"International": {"us", "overseas", "global", "fof"}}` —
subtracted from the penalty word list before scoring. Only penalize those
words for categories where they really do indicate a wrong match.

### 2. Bonus-option NAV history distorts return calculations — never match a Bonus plan

Bonus plans issue extra units instead of NAV appreciation, so their NAV
history is not comparable to Growth plan returns and will silently corrupt
downstream monthly-return math if one sneaks into `verified_funds.json`.
Growth is the only valid option for this dataset.

**Fix:** candidate filter in `resolve_all()` excludes any scheme name
containing "bonus" (also "idcw"/"dividend" for the same reason — non-Growth
plans don't produce comparable return series), in addition to requiring
"direct" and "growth" in the name.

### 3. Token overlap alone isn't enough — extra unrelated words must be penalized

Several real fund names share most of their words with a *different* fund
entirely:
- "ICICI Prudential Bluechip" vs "ICICI Prudential **US** Bluechip Equity
  Fund" — completely different fund (domestic large cap vs US equity FOF),
  one extra token away from looking like a match.
- "Motilal Oswal Midcap Fund" vs "Motilal Oswal **Large and** Midcap Fund"
  — different category (Mid Cap vs Large & Mid Cap) despite huge word
  overlap.
- Plain "Large Cap" queries vs "**Focused** Large Cap Fund" style
  candidates — a different strategy despite the shared "Large Cap" words.

Naive token-overlap scoring (just counting shared words) ranks these as
strong or perfect matches, because it never penalizes tokens the candidate
has that the query didn't ask for.

**Fix:** `compute_score()` scores `2*overlap - 3*missing - 1*extra`
(with an additional `-4` for extra false-positive-category words on top of
the base extra penalty) — extra words always cost something, and
false-positive-category extra words cost more. Combined with the "exact
match" tier (missing=0 **and** extra=0) in `select_winner()` outranking any
same-scoring near-match, this is what actually separates e.g. "ICICI
Prudential Bluechip" from "ICICI Prudential US Bluechip Equity Fund".

### 4. Rerunning `schemecodes.py` regenerates `verified_funds.json` from scratch — no merge

`resolve_all()` only ever writes entries for queries in the current
`FUND_UNIVERSE`. It does not read the existing `verified_funds.json` first,
so any manually hardcoded entry that isn't (and can't be, because mfapi's
search can't reliably find it) in `FUND_UNIVERSE` gets silently deleted the
next time the script is run in full.

This has already bitten us twice — hardcoded entries for Motilal Oswal
Midcap, Quant Active, Motilal Oswal Nasdaq 100 FOF, and (going forward)
ICICI Prudential Short Term Fund all had to be manually re-added after a
full rerun wiped them.

**Fix (process, not code):** after every full `schemecodes.py` rerun,
check `verified_funds.json` against the list of hardcoded entries below and
re-add any that got dropped:
- `Motilal Oswal Midcap` → 127042
- `Quant Active` → 120823
- `Motilal Oswal Nasdaq 100 FOF` → 145552
- `ICICI Prudential Short Term Fund` → 120754

(A proper fix — e.g. having `resolve_all()` load and merge over the
existing file instead of overwriting it — would remove the need for this
manual step; not done yet, noted here as a possible future improvement.)

### 5. Some funds have both Direct and Regular plans sharing an identical bare scheme name in mfapi's data, with no plan tag at all

Normally mfapi scheme names include "Direct"/"Regular" in the string
itself, which is what the candidate filter relies on. A few funds instead
list multiple scheme codes under the exact same bare name (no Direct/
Regular/Growth tag at all in the string), making it impossible to pick the
right one by text matching. Hit this for "Motilal Oswal Midcap Fund" (4
untagged codes) and "Motilal Oswal Nasdaq 100 Fund of Fund" (2 untagged
codes).

**Fix:** resolved these by checking the AMC's own scheme metadata (the
official plan code/plan name from the fund house, not mfapi's free-text
name) to confirm which code is actually the Direct plan, then hardcoding
that confirmed code directly into `verified_funds.json` (see gotcha #4 for
the ones currently hardcoded this way). Do **not** try to infer this from
NAV level alone as a first resort — it happens to correlate (Direct plans
compound to a higher NAV than Regular given identical inception NAV/date,
since they have lower expense ratios) and was used once as a cross-check,
but it's inference, not confirmation; verify against the AMC's own metadata
directly when possible.

## `fetchfunddata.py` / NAV data quality (not scoring bugs, but real data issues found downstream)

### 6. mfapi.in's raw NAV history can contain genuine data corruption / discontinuities — HDFC Liquid Fund face-value consolidation (FIXED)

Found a ~100x NAV level shift in HDFC Liquid Fund's raw data (scheme
119091): NAV ~28.39 on 2015-07-31, ~2857.83 by 2015-08-31, and it **stays**
at that new ~100x scale permanently afterward (confirmed against its
current NAV, ~5578 as of Sep 2026). This is a real face-value/unit
consolidation corporate action, not a spurious data-entry error that
reverts. It produces one wildly wrong derived monthly return: July 2015 →
August 2015 shows as +9966%, which dominates any mean/std-dev computed over
the full series (raw: mean 60.9%, std dev 773%, backwards for a debt fund).

**Important nuance:** because the level shift is *permanent*, dropping a
single raw NAV row before month-end bucketing does **not** fix this — it
only relocates which month's return absorbs the 100x step (e.g. dropping
the 30-08/31-08 rows just pushes the same jump onto the August→September
transition instead). The only way to get one clean exclusion is to drop
the single resulting **corrupted monthly return itself**, after
`to_monthly_returns()` computes it — not the raw NAV row.

**Fix:** `fetchfunddata.py` has a `KNOWN_BAD_RETURNS` dict keyed by scheme
code, applied via `drop_known_bad_returns()` right after
`to_monthly_returns()` and before the fund is added to the dataset.
Currently: `{119091: {"2015-08"}}`. Corrected stats: mean 0.547%, std dev
0.150% (was 773%) — ~34x less volatile than the 42-fund equity average
(5.10%), which is the expected debt-vs-equity relationship. Its correlation
with UTI Nifty 50 Index also moved from a nonsensical -0.131 (dominated by
the one outlier) to 0.001, i.e. genuinely uncorrelated, as expected for a
liquid fund vs. an equity index.

**This is explicitly a one-time, scheme-specific patch, not a general
outlier filter.** If another fund in `FUND_UNIVERSE` has a similar
level-shift, `KNOWN_BAD_RETURNS` will **not** catch it automatically — see
gotcha #8 for the systematic scan done to check for this, and how to add a
new entry if one turns up later.

### 8. Systematic scan for other single-day NAV ratio jumps (>20x or <1/20x) across all 45 funds

After fixing #6, scanned every fund's full raw NAV history for any
single-day NAV ratio jump beyond a 20x bound (well above any plausible
normal daily move for a debt or equity fund) to check whether the ICICI
Short Term Fund (#7) and HDFC Liquid Fund (#6) issues were one-offs or part
of a wider pattern in mfapi's data. Found exactly 3 hits:

- HDFC Liquid Fund (119091), 2015-08-28 → 2015-08-30, ~100x — already
  covered by #6.
- **Axis Midcap Fund (120505)** and **Axis ELSS Tax Saver Fund (120503)**,
  both on **2013-04-07**, NAV recorded as **0.00000** (same date, both
  funds — likely a shared mfapi feed glitch on that specific day, not a
  corporate action; NAV recovers to a normal value the very next trading
  day in both cases).

**Impact assessment: currently none.** 2013-04-07 is a mid-month date, not
a month-end, and `to_monthly_returns()` only ever uses the last NAV row of
each calendar month (`month_end` dict overwrite-by-date-order). The zero
row is silently skipped over and doesn't reach the derived monthly
returns used in `funds_data.json` today.

**Status: left as-is, flagged as a landmine.** Not patched, because it
currently causes no wrong output — patching data that isn't affecting
anything risks introducing a bug instead of fixing one. But it means the
raw NAV history for these two funds cannot be trusted at daily granularity
without a zero-check; if any future work computes daily (not monthly)
returns, or if a scheme's month-end happens to land on a bad-data date like
this for some other fund, it will need handling. If that happens, add a
`(scheme_code, date)` skip-list check into the raw-row parsing step in
`to_monthly_returns()`, distinct from `KNOWN_BAD_RETURNS` (which operates
on already-computed monthly returns, not raw rows) — genuinely different
failure mode (isolated zero-value glitch vs. permanent level shift), so
don't conflate the two fixes.

### 7. A `verified_funds.json` entry can silently point at the wrong (discontinued) scheme code

"ICICI Prudential Short Term Fund" was mapped to code 120608, which turned
out to be a *different*, likely-discontinued fund — "ICICI Prudential Short
Term **Gilt** Fund" — with corrupted `meta.scheme_type` (literally
containing another fund's identifier, "...BARODA PIONEER GILT FUND - Plan
B") and NAV history dead since 25-05-2018. The correct, currently-active
fund is code 120754 (exact name match, clean metadata, live NAV history).

Root cause: mfapi's `/mf/search` endpoint is unreliable for this query —
repeated calls with identical query text returned different, sometimes
incomplete result sets, at one point returning 15 results containing
*neither* code. This isn't fixable by wording the query differently.

**Fix:** hardcoded the confirmed-correct code (120754) directly into
`verified_funds.json`, moved it out of `schemecodes.py`'s search-driven
`FUND_UNIVERSE` into a documented exception (see gotcha #4's hardcoded
list), same pattern as gotcha #5.

**Takeaway:** an oddly short date range or suspiciously old "last NAV date"
for a fund that should still be active is worth investigating — it can mean
the resolved scheme code is simply wrong, not just that the fund itself is
young or was recently renamed.

### 9. HDFC Liquid Fund (119091) was missing 2015-08 entirely — interpolated (FIXED)

`gap_check.py` (checks every fund's aligned returns for a null landing
*between* its first and last non-null month — see `find_internal_gaps()`)
flagged fund 119091 (HDFC Liquid Fund - Direct Plan - Growth Option) as the
only mid-series gap across all 45 funds: 2015-08 was genuinely absent from
the source data (confirmed absent, not `null` — the month just doesn't
appear in `funds_data.json`'s `months`/`returns` for this fund).

**Fix:** `data_cleaner.py` interpolates this single month as the average of
its 2015-07 and 2015-09 returns, before alignment. Rationale: liquid fund
returns are low-volatility and highly stable month to month, so a linear
interpolation between adjacent months is a safe approximation for this
fund specifically. **This is explicitly a one-off, manually reviewed fix
for fund 119091 / 2015-08 — not a general "auto-interpolate any gap" rule.**
It is not applied to any other fund or month, and no other fund had a
mid-series gap in this scan.

The interpolated month is recorded on the fund's entry as
`interpolated_dates: ["2015-08"]` in `funds_aligned.json`, so it's traceable
downstream if anyone inspects the aligned data. After this fix,
`gap_check.py` reports 0 funds with a mid-series gap across all 45 funds.

## `maths.py` (mean/std/covariance/correlation, steps 1–6) — session of 2026-09-13

### 10. Shared overlap window across all 44 funds is currently short (~22 months), driven by one recent fund

`get_overlap_window` intersects the valid date range across *every* fund in
the selection, so the single most-recently-launched fund sets the window
for the whole set. Right now that fund is `152881` (Nippon India Nifty 500
Momentum 50 Index Fund), which only launched in `2024-11` — its inception
truncates the shared window for all 44 funds down to Nov 2024–Aug 2026 (22
months), even though most of the other 43 funds have much longer individual
histories going back years.

**Decision: keep the fund in and use the shared 22-month window, rather
than excluding it** — it's a genuine category (momentum index) we want
represented in the dataset, and dropping it just to get a longer window
would mean not covering that category at all.

**Consequence:** any report/writeup built on these stats must explicitly
state the window length (22 months) and explain that it's driven by
`152881`'s recent inception — otherwise a reader could easily mistake these
for full-history stats, when for 43 of the 44 funds they're actually a
short recent slice.

### 11. `n_months < 2` guard added to `compute_std_vector` and `compute_covariance_matrix`

Sample std dev and sample covariance both divide by `n_months - 1`, so
`n_months == 1` is a division-by-zero crash — but even conceptually,
`n_months == 1` can't estimate volatility at all (a single data point has
zero squared deviation from itself by construction, which would otherwise
silently produce a misleading std of 0 rather than a real error).

**Fix:** both functions now raise `ValueError` up front if `n_months < 2`,
with the window's dates included in the message, so a too-short overlap
window fails loudly instead of returning a silently-wrong 0.

### 12. `119091` (HDFC Liquid Fund) shows an unexpectedly high correlation (~0.48) with equity fund `118632` over the current 22-month window — not yet root-caused

Liquid/debt funds should show near-zero correlation with equity funds under
normal circumstances, so 0.48 stands out. Likely explanation: `119091`'s
std dev over this window is extremely small (~0.00068, vs. 0.03–0.07 for
the equity funds in this set), and with only 22 data points (see #10),
correlation against a near-zero-variance series is highly noisy — a couple
of coincidental co-movements can swing the coefficient a lot with no real
economic relationship behind it.

**Status: not fully root-caused.** We haven't yet eyeballed the paired
monthly returns side by side to confirm it's noise vs. a data artifact vs.
a real short-window effect. **Flag:** treat any correlation involving
`119091` (and potentially other low-volatility/debt funds) as
lower-confidence until this is investigated further — e.g. by printing the
paired return series for `119091` vs `118632` over the window and checking
whether the correlation is driven by one or two outlier months.

Note: this is a separate, unrelated quirk from gotcha #9 above (the
2015-08 interpolation) — same fund (`119091`), two different data
peculiarities to keep in mind when working with it.

### 13. Validation checks now built into `maths.py`'s `__main__`

- `sanity_check_covariance_matrix`: confirms `cov[i][i] == stds[i]**2` for
  every fund. Passed — max diff ~8.67e-19, floating point noise only.
- `sanity_check_correlation_matrix`: confirms the diagonal is 1.0 and the
  matrix is symmetric. Passed.
- Two "real-world" eyeball checks: `152881` vs `151739` (two Nifty
  500-based index funds) came out to 0.75, correctly showing strong
  positive correlation — this validates the mechanism works as expected
  when the underlying data behaves normally. Contrast this with #12 above,
  where the mechanism produces a number that doesn't match intuition and
  needs more digging.

### 14. Design decisions worth remembering (not bugs, but easy to relitigate by accident)

- Returns are null-padded to a common date axis (one `dates` array + a
  per-fund aligned `returns` array, same index = same month) rather than
  using per-fund start indices — chosen for simplicity of downstream
  indexing.
- `get_overlap_window` computes the *intersection* of valid indices across
  the selected funds and raises if the result isn't contiguous (which
  would indicate an unexpected mid-series gap slipping through) — this is
  stricter than just taking the min/max of individual start/end dates.
- The covariance matrix is computed independently from the correlation
  matrix (not derived from it), specifically so the two can cross-validate
  each other via the diagonal check in #13.
- `EXCLUDED_FUND_IDS = [145552]` (Motilal Oswal Nasdaq 100 FOF — see
  gotcha #4/#5 for its scheme-code history) is excluded from
  `maths.py`'s computations, but the *reason* for the exclusion isn't
  documented anywhere yet. **TODO: find/record why before relying on
  this list being complete or correct** — don't assume it's still valid
  without checking.
