const EXCLUDED_FUND_IDS = [145552];

function computeMeanVector(fundIds, window, data) {
  const fundsById = new Map(data.funds.map((f) => [f.id, f]));
  const startIdx = window.start_idx;
  const endIdx = window.end_idx;
  const nMonths = window.n_months;

  const means = new Map();
  for (const fid of fundIds) {
    const returns = fundsById.get(fid).returns;

    let total = 0;
    for (let i = startIdx; i <= endIdx; i++) {
      const r = returns[i];
      if (r === null) throw new Error(`Unexpected null at idx ${i} for fund ${fid}`);
      total = total + r;
    }

    means.set(fid, total / nMonths);
  }

  return means;
}

function computeStdVector(fundIds, window, data, means = null) {
  const fundsById = new Map(data.funds.map((f) => [f.id, f]));
  const startIdx = window.start_idx;
  const endIdx = window.end_idx;
  const nMonths = window.n_months;

  if (nMonths < 2) {
    throw new Error(
      `Cannot compute sample std dev with n_months=${nMonths} ` +
        `(window ${window.start_date} to ${window.end_date}). ` +
        `Need at least 2 overlapping months.`
    );
  }

  if (means === null) {
    means = computeMeanVector(fundIds, window, data);
  }

  const stds = new Map();
  for (const fid of fundIds) {
    const returns = fundsById.get(fid).returns;
    const mean = means.get(fid);

    let sumSqDev = 0;
    for (let i = startIdx; i <= endIdx; i++) {
      const r = returns[i];
      if (r === null) throw new Error(`Unexpected null at idx ${i} for fund ${fid}`);
      sumSqDev = sumSqDev + (r - mean) ** 2;
    }

    const variance = sumSqDev / (nMonths - 1);
    stds.set(fid, Math.sqrt(variance));
  }

  return stds;
}

function computeCovarianceMatrix(fundIds, window, data, means = null) {
  const fundsById = new Map(data.funds.map((f) => [f.id, f]));
  const startIdx = window.start_idx;
  const endIdx = window.end_idx;
  const nMonths = window.n_months;

  if (nMonths < 2) {
    throw new Error(
      `Cannot compute sample covariance with n_months=${nMonths} ` +
        `(window ${window.start_date} to ${window.end_date}). ` +
        `Need at least 2 overlapping months.`
    );
  }

  if (means === null) {
    means = computeMeanVector(fundIds, window, data);
  }

  const windowed = new Map();
  for (const fid of fundIds) {
    const returns = fundsById.get(fid).returns;
    const series = [];
    for (let i = startIdx; i <= endIdx; i++) {
      const r = returns[i];
      if (r === null) throw new Error(`Unexpected null at idx ${i} for fund ${fid}`);
      series.push(r);
    }
    windowed.set(fid, series);
  }

  const cov = new Map(fundIds.map((fid) => [fid, new Map()]));

  for (let aIdx = 0; aIdx < fundIds.length; aIdx++) {
    const fidA = fundIds[aIdx];
    const seriesA = windowed.get(fidA);
    const meanA = means.get(fidA);

    for (let bIdx = aIdx; bIdx < fundIds.length; bIdx++) {
      const fidB = fundIds[bIdx];
      const seriesB = windowed.get(fidB);
      const meanB = means.get(fidB);

      let total = 0;
      for (let t = 0; t < nMonths; t++) {
        total += (seriesA[t] - meanA) * (seriesB[t] - meanB);
      }

      const c = total / (nMonths - 1);
      cov.get(fidA).set(fidB, c);
      cov.get(fidB).set(fidA, c);
    }
  }

  return cov;
}

function computeCorrelationMatrix(fundIds, window, data, means = null, stds = null, cov = null) {
  if (means === null) {
    means = computeMeanVector(fundIds, window, data);
  }
  if (stds === null) {
    stds = computeStdVector(fundIds, window, data, means);
  }
  if (cov === null) {
    cov = computeCovarianceMatrix(fundIds, window, data, means);
  }

  const corr = new Map();
  for (const fidA of fundIds) {
    const row = new Map();
    for (const fidB of fundIds) {
      row.set(fidB, cov.get(fidA).get(fidB) / (stds.get(fidA) * stds.get(fidB)));
    }
    corr.set(fidA, row);
  }

  return corr;
}

function sanityCheckCovarianceMatrix(cov, stds, fundIds, tol = 1e-9) {
  let maxDiff = 0;
  for (const fid of fundIds) {
    const diag = cov.get(fid).get(fid);
    const variance = stds.get(fid) ** 2;
    const diff = Math.abs(diag - variance);
    maxDiff = Math.max(maxDiff, diff);
    if (diff >= tol) {
      throw new Error(
        `Covariance diagonal mismatch for fund ${fid}: ` +
          `cov[i][i]=${diag}, std[i]**2=${variance}, diff=${diff}`
      );
    }
  }
  return maxDiff;
}

function sanityCheckCorrelationMatrix(corr, fundIds, tol = 1e-9) {
  for (const fid of fundIds) {
    const diag = corr.get(fid).get(fid);
    if (Math.abs(diag - 1.0) >= tol) {
      throw new Error(`Diagonal for fund ${fid} = ${diag}, expected 1.0`);
    }
  }

  for (const fidA of fundIds) {
    for (const fidB of fundIds) {
      const aB = corr.get(fidA).get(fidB);
      const bA = corr.get(fidB).get(fidA);
      if (Math.abs(aB - bA) >= tol) {
        throw new Error(
          `Asymmetry: corr[${fidA}][${fidB}]=${aB} vs corr[${fidB}][${fidA}]=${bA}`
        );
      }
    }
  }
}

module.exports = {
  EXCLUDED_FUND_IDS,
  computeMeanVector,
  computeStdVector,
  computeCovarianceMatrix,
  computeCorrelationMatrix,
  sanityCheckCovarianceMatrix,
  sanityCheckCorrelationMatrix,
};
