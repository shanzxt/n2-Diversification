function getOverlapWindow(fundIds, data) {
  const dates = data.dates;
  const fundsById = new Map(data.funds.map((f) => [f.id, f]));

  const missing = fundIds.filter((fid) => !fundsById.has(fid));
  if (missing.length > 0) {
    throw new Error(`Unknown fund id(s): ${missing}`);
  }

  const selected = fundIds.map((fid) => fundsById.get(fid));

  const validIndices = [];
  for (let i = 0; i < dates.length; i++) {
    if (selected.every((f) => f.returns[i] !== null)) {
      validIndices.push(i);
    }
  }

  if (validIndices.length === 0) {
    return null;
  }

  const startIdx = validIndices[0];
  const endIdx = validIndices[validIndices.length - 1];
  const expectedCount = endIdx - startIdx + 1;

  if (validIndices.length !== expectedCount) {
    const validSet = new Set(validIndices);
    const gapIndices = [];
    for (let i = startIdx; i <= endIdx; i++) {
      if (!validSet.has(i)) gapIndices.push(i);
    }
    throw new Error(
      `Overlap window for ${fundIds} is not contiguous — ` +
        `gaps at dates: ${gapIndices.map((i) => dates[i])}. ` +
        `This is unexpected post-cleanup; investigate before proceeding.`
    );
  }

  return {
    fund_ids: fundIds,
    start_idx: startIdx,
    end_idx: endIdx,
    start_date: dates[startIdx],
    end_date: dates[endIdx],
    n_months: expectedCount,
  };
}

module.exports = { getOverlapWindow };
