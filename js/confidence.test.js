const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { getOverlapWindow } = require("./overlap.js");
const { computeMeanVector, computeStdVector, EXCLUDED_FUND_IDS } = require("./maths.js");
const { computePortfolioWindowNote, computeConfidenceFlags } = require("./confidence.js");

const fixtures = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf8")
);
const data = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "funds_aligned.json"), "utf8")
);

test("computePortfolioWindowNote / computeConfidenceFlags — full 44-fund universe", () => {
  const fixture = fixtures.confidence_flags;
  const fundIds = fixtures.overlap_window.all_44_funds.fund_ids.filter(
    (fid) => !EXCLUDED_FUND_IDS.includes(fid)
  );
  const window = getOverlapWindow(fundIds, data);
  const means = computeMeanVector(fundIds, window, data);
  const stds = computeStdVector(fundIds, window, data, means);

  const note = computePortfolioWindowNote(fundIds, window, data);
  assert.deepEqual(note, fixture.portfolio_window_note);

  const flags = computeConfidenceFlags(fundIds, window, data, stds);
  assert.equal(flags.size, fixture.n_flagged_funds);
  assert.deepEqual(flags.get(152881), fixture.flags_152881);
  assert.deepEqual(flags.get(119091), fixture.flags_119091);
  assert.deepEqual(flags.get(120754), fixture.flags_120754);
});
