const { computeMeanVector, computeStdVector } = require("./maths.js");

const SHORT_HISTORY_MONTHS_THRESHOLD = 36; // fund's own full history under 3 years
const LOW_STD_RATIO_THRESHOLD = 0.1; // fund's std < 10% of the group's median std
const PORTFOLIO_WINDOW_NOTE_THRESHOLD = 36; // flag the window itself if under 3 years

function formatPercent(x, decimals) {
  return `${(x * 100).toFixed(decimals)}%`;
}

function ownHistoryLength(fundId, data) {
  const fundsById = new Map(data.funds.map((f) => [f.id, f]));
  const returns = fundsById.get(fundId).returns;
  return returns.filter((r) => r !== null).length;
}

function findWindowBottleneckFund(fundIds, window, data) {
  let shortestFid = null;
  let shortestLen = null;
  for (const fid of fundIds) {
    const ownLen = ownHistoryLength(fid, data);
    if (shortestLen === null || ownLen < shortestLen) {
      shortestLen = ownLen;
      shortestFid = fid;
    }
  }
  return [shortestFid, shortestLen];
}

function computePortfolioWindowNote(fundIds, window, data) {
  const nMonths = window.n_months;
  if (nMonths >= PORTFOLIO_WINDOW_NOTE_THRESHOLD) {
    return null;
  }

  const [bottleneckFid, bottleneckLen] = findWindowBottleneckFund(fundIds, window, data);
  return {
    reason: "short_shared_window",
    detail:
      `All stats in this selection are computed over a shared window of ` +
      `only ${nMonths} months (${window.start_date} to ${window.end_date}), ` +
      `even though most funds here have far longer individual histories. ` +
      `This is driven by fund ${bottleneckFid}, which only has ${bottleneckLen} ` +
      `months of its own history and sets the floor for the whole selection.`,
  };
}

function computeConfidenceFlags(fundIds, window, data, stds = null) {
  if (stds === null) {
    const means = computeMeanVector(fundIds, window, data);
    stds = computeStdVector(fundIds, window, data, means);
  }

  const stdValues = [...stds.values()].sort((a, b) => a - b);
  const medianStd = stdValues[Math.floor(stdValues.length / 2)];

  const flags = new Map();

  for (const fid of fundIds) {
    const fundFlags = [];

    const ownLen = ownHistoryLength(fid, data);
    if (ownLen > 0 && ownLen < SHORT_HISTORY_MONTHS_THRESHOLD) {
      fundFlags.push({
        reason: "intrinsically_short_history",
        detail:
          `This fund only has ${ownLen} months of history in total ` +
          `(under ${SHORT_HISTORY_MONTHS_THRESHOLD} months) — likely a ` +
          `recently-launched fund. Its own stats, not just the shared ` +
          `window, are based on limited data.`,
      });
    }

    const std = stds.get(fid);
    if (medianStd > 0 && std / medianStd < LOW_STD_RATIO_THRESHOLD) {
      fundFlags.push({
        reason: "low_variance_relative_to_group",
        detail:
          `Std dev (${formatPercent(std, 4)}) is under ${formatPercent(LOW_STD_RATIO_THRESHOLD, 0)} of ` +
          `the group's median (${formatPercent(medianStd, 4)}). Correlations involving ` +
          `this fund can be noisy — a handful of months can swing the ` +
          `coefficient with limited underlying signal.`,
      });
    }

    if (fundFlags.length > 0) {
      flags.set(fid, fundFlags);
    }
  }

  return flags;
}

module.exports = {
  SHORT_HISTORY_MONTHS_THRESHOLD,
  LOW_STD_RATIO_THRESHOLD,
  PORTFOLIO_WINDOW_NOTE_THRESHOLD,
  ownHistoryLength,
  findWindowBottleneckFund,
  computePortfolioWindowNote,
  computeConfidenceFlags,
};
