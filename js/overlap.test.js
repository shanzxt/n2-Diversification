const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { getOverlapWindow } = require("./overlap.js");

const fixtures = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf8")
);
const data = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "funds_aligned.json"), "utf8")
);

function assertWindowEqual(actual, expected) {
  assert.deepEqual(actual.fund_ids, expected.fund_ids);
  assert.equal(actual.start_idx, expected.start_idx);
  assert.equal(actual.end_idx, expected.end_idx);
  assert.equal(actual.start_date, expected.start_date);
  assert.equal(actual.end_date, expected.end_date);
  assert.equal(actual.n_months, expected.n_months);
}

test("getOverlapWindow — all 44 funds together", () => {
  const fixture = fixtures.overlap_window.all_44_funds;
  const result = getOverlapWindow(fixture.fund_ids, data);
  assertWindowEqual(result, fixture.result);
});

test("getOverlapWindow — first two funds", () => {
  const fixture = fixtures.overlap_window.first_two_funds;
  const result = getOverlapWindow(fixture.fund_ids, data);
  assertWindowEqual(result, fixture.result);
});

test("getOverlapWindow — single fund (119091)", () => {
  const fixture = fixtures.overlap_window.single_fund_119091;
  const result = getOverlapWindow(fixture.fund_ids, data);
  assertWindowEqual(result, fixture.result);
});
