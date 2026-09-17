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

const TOL = 1e-9;

const fixtures = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf8")
);
const data = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "funds_aligned.json"), "utf8")
);

function assertClose(actual, expected, tol = TOL, msg = "") {
  assert.ok(
    Math.abs(actual - expected) < tol,
    `${msg} expected ${expected}, got ${actual} (diff ${Math.abs(actual - expected)})`
  );
}

function mapFromObj(obj) {
  return new Map(Object.entries(obj).map(([k, v]) => [Number(k), v]));
}

// Shared setup, reused across test cases below rather than recomputed
// per test -- mirrors portfolio.py's own __main__.
const fundIds = fixtures.overlap_window.all_44_funds.fund_ids.filter(
  (fid) => !EXCLUDED_FUND_IDS.includes(fid)
);
const window = getOverlapWindow(fundIds, data);
const means = computeMeanVector(fundIds, window, data);
const stds = computeStdVector(fundIds, window, data, means);
const cov = computeCovarianceMatrix(fundIds, window, data, means);
const corr = computeCorrelationMatrix(fundIds, window, data, means, stds, cov);

test("computePortfolioStats — single-fund portfolio matches standalone stats", () => {
  const fixture = fixtures.portfolio_single_fund_validation;
  const stats = computePortfolioStats(
    mapFromObj({ [fixture.test_fid]: 1.0 }),
    fundIds,
    window,
    data,
    means,
    stds,
    cov,
    corr
  );

  assertClose(stats.monthly_return, fixture.expected_mean, TOL, "monthly_return");
  assertClose(stats.monthly_std, fixture.expected_std, TOL, "monthly_std");
  assertClose(stats.monthly_return, fixture.portfolio_monthly_return, TOL, "monthly_return vs fixture");
  assertClose(stats.monthly_std, fixture.portfolio_monthly_std, TOL, "monthly_std vs fixture");
});

test("computePortfolioStats — unnormalized weights match pre-normalized weights", () => {
  const fixture = fixtures.portfolio_normalization_validation;
  const statsRaw = computePortfolioStats(mapFromObj(fixture.raw_weights), fundIds, window, data, means, stds, cov, corr);
  const statsPre = computePortfolioStats(mapFromObj(fixture.pre_normalized_weights), fundIds, window, data, means, stds, cov, corr);

  assertClose(statsRaw.monthly_return, statsPre.monthly_return, TOL, "raw vs pre-normalized");
  assertClose(statsRaw.monthly_return, fixture.raw_weights_return, TOL, "raw vs fixture");
  assertClose(statsPre.monthly_return, fixture.normalized_return, TOL, "pre-normalized vs fixture");
});

test("computePortfolioStats — 7/8-fund thesis test (all-equity vs. equity+debt effective N)", () => {
  const fixture = fixtures.thesis_test;
  const allEquity = mapFromObj({
    118632: 1, 118955: 1, 120166: 1, 118834: 1, 120158: 1, 118989: 1, 119775: 1,
  });
  const withDebt = new Map(allEquity);
  withDebt.set(119091, 1);

  const equityStats = computePortfolioStats(allEquity, fundIds, window, data, means, stds, cov, corr);
  const mixedStats = computePortfolioStats(withDebt, fundIds, window, data, means, stds, cov, corr);

  // Jacobi-eigen-derived, so use the same wider tolerance as eigen.test.js.
  assertClose(equityStats.effective_n, fixture.all_equity_effective_n, 1e-3, "all-equity effective N");
  assertClose(mixedStats.effective_n, fixture.equity_plus_debt_effective_n, 1e-3, "equity+debt effective N");
  assert.ok(mixedStats.effective_n > equityStats.effective_n, "adding the debt fund should raise effective N");
});
