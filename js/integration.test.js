// Chains the full pipeline the way the browser eventually will: raw
// weights in -> normalized -> means/stds/cov/corr computed -> portfolio
// stats out. This is the shape Phase 2's UI will actually call (a user
// drags sliders -> raw weights -> full stats dict), so it's kept as its
// own clearly-named test rather than buried inside a portfolioMath unit
// test for one function.

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { getOverlapWindow } = require("./overlap.js");
const {
  computeMeanVector,
  computeStdVector,
  computeCovarianceMatrix,
  computeCorrelationMatrix,
  EXCLUDED_FUND_IDS,
} = require("./maths.js");
const { computePortfolioStats } = require("./portfolioMath.js");

const TOL = 1e-3; // effective N is Jacobi-eigen-derived, same tolerance as eigen.test.js

const fixtures = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf8")
);
const data = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "funds_aligned.json"), "utf8")
);

function assertClose(actual, expected, tol, msg) {
  assert.ok(
    Math.abs(actual - expected) < tol,
    `${msg} expected ${expected}, got ${actual} (diff ${Math.abs(actual - expected)})`
  );
}

test("full pipeline: raw weights -> normalized -> stats, all-equity vs. equity+debt", () => {
  const fixture = fixtures.thesis_test;

  // 1. Universe setup -- reads the shipped data, builds the shared window.
  const fundIds = data.funds
    .map((f) => f.id)
    .filter((fid) => !EXCLUDED_FUND_IDS.includes(fid));
  const window = getOverlapWindow(fundIds, data);

  // 2. Compute the universe-level primitives once (as the app would on load).
  const means = computeMeanVector(fundIds, window, data);
  const stds = computeStdVector(fundIds, window, data, means);
  const cov = computeCovarianceMatrix(fundIds, window, data, means);
  const corr = computeCorrelationMatrix(fundIds, window, data, means, stds, cov);

  // 3. Raw (unnormalized) weights, as sliders would produce -- equal
  // weight per fund, expressed as raw "1" values rather than 1/7 or 1/8.
  const rawAllEquity = new Map([
    [118632, 1], [118955, 1], [120166, 1], [118834, 1],
    [120158, 1], [118989, 1], [119775, 1],
  ]);
  const rawWithDebt = new Map(rawAllEquity);
  rawWithDebt.set(119091, 1);

  // 4. The actual entry point a UI slider-drag would call.
  const equityStats = computePortfolioStats(rawAllEquity, fundIds, window, data, means, stds, cov, corr);
  const mixedStats = computePortfolioStats(rawWithDebt, fundIds, window, data, means, stds, cov, corr);

  // Weights actually got normalized (7 equal raw weights of 1 -> 1/7 each).
  assertClose(equityStats.weights.get(118632), 1 / 7, TOL, "normalized weight");
  assertClose(mixedStats.weights.get(118632), 1 / 8, TOL, "normalized weight (with debt fund)");

  // The diversification effect the newsletter's UI needs to demonstrate:
  // adding a low-correlation debt fund raises effective N.
  assertClose(equityStats.effective_n, fixture.all_equity_effective_n, TOL, "all-equity effective N");
  assertClose(mixedStats.effective_n, fixture.equity_plus_debt_effective_n, TOL, "equity+debt effective N");
  assert.ok(
    mixedStats.effective_n > equityStats.effective_n,
    "adding the debt fund should raise effective N"
  );

  // 119091's low-variance confidence flag should surface for the mixed
  // portfolio (it's in the selection) but not the all-equity one (it isn't).
  assert.ok(mixedStats.confidence_flags.has(119091));
  assert.ok(!equityStats.confidence_flags.has(119091));
});
