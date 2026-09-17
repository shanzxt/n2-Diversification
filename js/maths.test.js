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
  sanityCheckCovarianceMatrix,
  sanityCheckCorrelationMatrix,
} = require("./maths.js");

const TOL = 1e-9; // mirrors the Python side's tol=1e-9

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

test("computeMeanVector / computeStdVector — fund 118632 within the 44-fund shared window", () => {
  // Matches how the fixture was generated (generate_fixtures.py mirrors
  // maths.py's own __main__): 118632's mean/std computed alongside the
  // full 44-fund universe under its shared overlap window, not truly
  // standalone with its own full history — those differ (see the
  // separate small-multi-fund case below for a true standalone window).
  const fixture = fixtures.fund_118632_within_44_fund_window;
  const fundIds = fixtures.overlap_window.all_44_funds.fund_ids.filter(
    (fid) => fid !== 145552 // EXCLUDED_FUND_IDS, mirrors maths.py's own __main__
  );
  const window = getOverlapWindow(fundIds, data);
  const means = computeMeanVector(fundIds, window, data);
  const stds = computeStdVector(fundIds, window, data, means);

  assertClose(means.get(118632), fixture.mean, TOL, "mean");
  assertClose(stds.get(118632), fixture.std, TOL, "std");
});

test("computeCorrelationMatrix — spot cells against fixtures", () => {
  const fundIds = fixtures.overlap_window.all_44_funds.fund_ids.filter(
    (fid) => fid !== 145552 // EXCLUDED_FUND_IDS, mirrors maths.py's own __main__
  );
  const window = getOverlapWindow(fundIds, data);
  const means = computeMeanVector(fundIds, window, data);
  const stds = computeStdVector(fundIds, window, data, means);
  const cov = computeCovarianceMatrix(fundIds, window, data, means);
  const corr = computeCorrelationMatrix(fundIds, window, data, means, stds, cov);

  assertClose(
    corr.get(152881).get(151739),
    fixtures.correlation_cells.corr_152881_151739,
    TOL,
    "corr[152881][151739]"
  );
  assertClose(
    corr.get(119091).get(118632),
    fixtures.correlation_cells.corr_119091_118632,
    TOL,
    "corr[119091][118632]"
  );

  // Cross-check invariants, same as maths.py's __main__.
  sanityCheckCovarianceMatrix(cov, stds, fundIds);
  sanityCheckCorrelationMatrix(corr, fundIds);
});

test("maths.js small multi-fund case — full mean/std/covariance/correlation matrices, fixed fund_ids order", () => {
  const fixture = fixtures.maths_small_multi_fund;
  const fundIds = fixture.fund_ids;
  const window = getOverlapWindow(fundIds, data);

  assert.deepEqual(window, fixture.window);

  const means = computeMeanVector(fundIds, window, data);
  const stds = computeStdVector(fundIds, window, data, means);
  const cov = computeCovarianceMatrix(fundIds, window, data, means);
  const corr = computeCorrelationMatrix(fundIds, window, data, means, stds, cov);

  for (const fid of fundIds) {
    assertClose(means.get(fid), fixture.means[String(fid)], TOL, `mean[${fid}]`);
    assertClose(stds.get(fid), fixture.stds[String(fid)], TOL, `std[${fid}]`);
  }

  for (const a of fundIds) {
    for (const b of fundIds) {
      assertClose(
        cov.get(a).get(b),
        fixture.covariance_matrix[String(a)][String(b)],
        TOL,
        `cov[${a}][${b}]`
      );
      assertClose(
        corr.get(a).get(b),
        fixture.correlation_matrix[String(a)][String(b)],
        TOL,
        `corr[${a}][${b}]`
      );
    }
  }

  // Same invariants maths.py checks in its own __main__.
  sanityCheckCovarianceMatrix(cov, stds, fundIds);
  sanityCheckCorrelationMatrix(corr, fundIds);

  // Confirms fund_ids row/column order is preserved through Map iteration
  // (this is the failure mode a plain-object implementation with
  // numeric-looking string keys could silently get wrong).
  assert.deepEqual([...means.keys()], fundIds);
  assert.deepEqual([...stds.keys()], fundIds);
  assert.deepEqual([...cov.keys()], fundIds);
  assert.deepEqual([...corr.keys()], fundIds);
});
