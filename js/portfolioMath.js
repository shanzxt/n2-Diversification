const {
  computeMeanVector,
  computeStdVector,
  computeCovarianceMatrix,
  computeCorrelationMatrix,
} = require("./maths.js");
const {
  jacobiEigen,
  computeEffectiveN,
  correlationDictToMatrix,
  sanityCheckEigenvaluesSumToN,
} = require("./eigen.js");
const { computeConfidenceFlags, computePortfolioWindowNote } = require("./confidence.js");

// 91-day T-bill yield, per the earlier risk-free-rate decision. Hardcoded
// for now — update periodically, don't wire up a live API for this.
// Source: RBI 91-day T-bill auction cut-off yield, 5.2089%, auction dated
// 2026-09-09 (most recent auction as of the date checked). Checked 2026-09-17.
const RISK_FREE_RATE_ANNUAL = 0.052089;

function normalizeWeights(rawWeights) {
  // This is the ONLY place normalization should happen — every formula
  // downstream assumes it's already receiving a normalized Map.
  const total = [...rawWeights.values()].reduce((sum, w) => sum + w, 0);
  if (total === 0) {
    throw new Error(
      "All weights are zero — select at least one fund with a " +
        "nonzero weight before computing portfolio stats."
    );
  }
  const normalized = new Map();
  for (const [fid, w] of rawWeights) {
    normalized.set(fid, w / total);
  }
  return normalized;
}

function computePortfolioReturn(weights, means) {
  // w^T mu — portfolio expected return as the weighted sum of each
  // fund's arithmetic mean return. `weights` must already be normalized
  // (see normalizeWeights); this function does not check or normalize.
  let total = 0;
  for (const [fid, w] of weights) {
    total += w * means.get(fid);
  }
  return total;
}

function computePortfolioVariance(weights, cov) {
  // w^T Sigma w — portfolio variance. Full double sum over all pairs,
  // since covariance captures both each fund's own variance (diagonal)
  // and every pairwise co-movement (off-diagonal) — dropping either half
  // would silently understate diversification effects.
  let total = 0.0;
  for (const [fidA, wA] of weights) {
    for (const [fidB, wB] of weights) {
      total += wA * wB * cov.get(fidA).get(fidB);
    }
  }
  return total;
}

function computePortfolioStd(variance) {
  if (variance < 0) {
    // Can only happen from floating-point noise on a near-zero
    // variance portfolio (e.g. a single-fund "portfolio"); a
    // genuinely negative variance would indicate a bug upstream.
    if (variance > -1e-12) {
      variance = 0.0;
    } else {
      throw new Error(`Negative portfolio variance (${variance}) — check covariance matrix / weights.`);
    }
  }
  return Math.sqrt(variance);
}

function computeSharpe(portfolioReturnAnnual, portfolioStdAnnual, riskFreeRateAnnual = RISK_FREE_RATE_ANNUAL) {
  // (portfolio return - risk-free) / portfolio std dev, all annualized
  // inputs — see annualizeReturn / annualizeStd below for how monthly
  // numbers get there.
  return (portfolioReturnAnnual - riskFreeRateAnnual) / portfolioStdAnnual;
}

function annualizeReturnArithmetic(monthlyReturn) {
  // Arithmetic annualization: monthly x 12. Used for the underlying
  // math (Sharpe, etc.) since it stays linear in the weights — see
  // annualizeReturnGeometric for the number to actually DISPLAY.
  return monthlyReturn * 12;
}

function annualizeStd(monthlyStd) {
  // Monthly std x sqrt(12) — the standard convention, no geometric
  // equivalent exists for volatility.
  return monthlyStd * Math.sqrt(12);
}

function annualizeReturnGeometric(weights, fundIds, window, data) {
  // The number to DISPLAY as "annualized return" — NOT used in any
  // downstream math (Sharpe, variance, etc. all use the arithmetic
  // mean, since only arithmetic means combine linearly across weights).
  //
  // Builds the portfolio's own monthly return series first (each month
  // = w^T r_t using that month's actual returns), then geometrically
  // compounds THAT series. Do not combine individual funds' own CAGRs
  // with weights — that produces a wrong number, since geometric means
  // don't combine linearly the way arithmetic means do.
  const fundsById = new Map(data.funds.map((f) => [f.id, f]));
  const startIdx = window.start_idx;
  const endIdx = window.end_idx;
  const nMonths = window.n_months;

  const portfolioMonthlyReturns = [];
  for (let i = startIdx; i <= endIdx; i++) {
    let monthReturn = 0;
    for (const [fid, w] of weights) {
      monthReturn += w * fundsById.get(fid).returns[i];
    }
    portfolioMonthlyReturns.push(monthReturn);
  }

  let compounded = 1.0;
  for (const r of portfolioMonthlyReturns) {
    compounded *= 1 + r;
  }

  const monthlyGeometricMean = compounded ** (1 / nMonths) - 1;
  const annualizedGeometric = (1 + monthlyGeometricMean) ** 12 - 1;
  return annualizedGeometric;
}

function computePortfolioStats(rawWeights, fundIds, window, data, means = null, stds = null, cov = null, corr = null) {
  // The main entry point: takes raw (possibly unnormalized) weights (a
  // Map) for a SUBSET of fundIds, and returns a full stats dict —
  // return, variance, std, Sharpe (all annualized), effective N for
  // just this subset, and any confidence flags relevant to the selected
  // funds.
  //
  // means/stds/cov/corr, if not passed in, are computed fresh from the
  // FULL fundIds universe (so they reuse the same shared window) — pass
  // them in when calling this repeatedly (e.g. per slider drag) to
  // avoid recomputing the whole universe's stats every time.
  const selectedIds = [...rawWeights.keys()];
  const unknown = selectedIds.filter((fid) => !fundIds.includes(fid));
  if (unknown.length > 0) {
    throw new Error(`Fund id(s) not in universe: ${unknown}`);
  }

  const weights = normalizeWeights(rawWeights);

  if (means === null) {
    means = computeMeanVector(fundIds, window, data);
  }
  if (stds === null) {
    stds = computeStdVector(fundIds, window, data, means);
  }
  if (cov === null) {
    cov = computeCovarianceMatrix(fundIds, window, data, means);
  }
  if (corr === null) {
    corr = computeCorrelationMatrix(fundIds, window, data, means, stds, cov);
  }

  const monthlyReturn = computePortfolioReturn(weights, means);
  const variance = computePortfolioVariance(weights, cov);
  const monthlyStd = computePortfolioStd(variance);

  const annualReturnArith = annualizeReturnArithmetic(monthlyReturn);
  const annualStd = annualizeStd(monthlyStd);
  const annualReturnDisplay = annualizeReturnGeometric(weights, fundIds, window, data);

  const sharpe = annualStd > 0 ? computeSharpe(annualReturnArith, annualStd) : null;

  // Effective N for just this subset — decompose the subset's OWN
  // correlation matrix, not the full 44-fund one.
  const subsetCorrMatrix = correlationDictToMatrix(corr, selectedIds);
  const [eigenvalues] = jacobiEigen(subsetCorrMatrix);
  sanityCheckEigenvaluesSumToN(eigenvalues, selectedIds.length);
  const effectiveN = computeEffectiveN(eigenvalues);

  const confidenceFlags = computeConfidenceFlags(fundIds, window, data, stds);
  const relevantFlags = new Map();
  for (const fid of selectedIds) {
    if (confidenceFlags.has(fid)) {
      relevantFlags.set(fid, confidenceFlags.get(fid));
    }
  }
  const portfolioNote = computePortfolioWindowNote(fundIds, window, data);

  return {
    weights,
    monthly_return: monthlyReturn,
    annual_return_arithmetic: annualReturnArith, // used internally (Sharpe etc.)
    annual_return_display: annualReturnDisplay, // geometric — show THIS to the user
    monthly_std: monthlyStd,
    annual_std: annualStd,
    sharpe_ratio: sharpe,
    effective_n: effectiveN,
    n_funds_selected: selectedIds.length,
    confidence_flags: relevantFlags,
    portfolio_window_note: portfolioNote,
  };
}

module.exports = {
  RISK_FREE_RATE_ANNUAL,
  normalizeWeights,
  computePortfolioReturn,
  computePortfolioVariance,
  computePortfolioStd,
  computeSharpe,
  annualizeReturnArithmetic,
  annualizeStd,
  annualizeReturnGeometric,
  computePortfolioStats,
};
