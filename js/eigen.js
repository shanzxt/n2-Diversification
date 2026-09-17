function jacobiEigen(A, tol = 1e-10, maxSweeps = 200) {
  const n = A.length;
  const a = A.map((row) => row.slice()); // work on a copy, don't mutate the input
  const v = Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => (i === j ? 1.0 : 0.0))
  );

  for (let sweep = 0; sweep < maxSweeps; sweep++) {
    let offDiagSq = 0.0;
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        if (i !== j) {
          offDiagSq += a[i][j] ** 2;
        }
      }
    }

    if (offDiagSq < tol) {
      break;
    }

    for (let p = 0; p < n - 1; p++) {
      for (let q = p + 1; q < n; q++) {
        const apq = a[p][q];
        if (Math.abs(apq) < 1e-15) {
          continue;
        }

        const app = a[p][p];
        const aqq = a[q][q];

        const theta = (aqq - app) / (2 * apq);
        const sign = theta >= 0 ? 1.0 : -1.0;
        const t = sign / (Math.abs(theta) + Math.sqrt(theta ** 2 + 1));
        const c = 1.0 / Math.sqrt(t ** 2 + 1);
        const s = t * c;

        a[p][p] = c * c * app - 2 * s * c * apq + s * s * aqq;
        a[q][q] = s * s * app + 2 * s * c * apq + c * c * aqq;
        a[p][q] = 0.0;
        a[q][p] = 0.0;

        for (let i = 0; i < n; i++) {
          if (i !== p && i !== q) {
            const aip = a[i][p];
            const aiq = a[i][q];
            a[i][p] = c * aip - s * aiq;
            a[p][i] = a[i][p];
            a[i][q] = s * aip + c * aiq;
            a[q][i] = a[i][q];
          }
        }

        for (let i = 0; i < n; i++) {
          const vip = v[i][p];
          const viq = v[i][q];
          v[i][p] = c * vip - s * viq;
          v[i][q] = s * vip + c * viq;
        }
      }
    }
  }

  const eigenvalues = Array.from({ length: n }, (_, i) => a[i][i]);
  return [eigenvalues, v];
}

function computeEffectiveN(eigenvalues) {
  const total = eigenvalues.reduce((sum, ev) => sum + ev, 0);

  const probs = eigenvalues.map((ev) => {
    let p = ev / total;
    // Clamp tiny negative values from floating-point noise (an
    // eigenvalue that should be ~0 can come out as -1e-16).
    if (p < 0) {
      p = 0.0;
    }
    return p;
  });

  let entropy = 0.0;
  for (const p of probs) {
    if (p > 1e-15) { // skip zero-probability terms, log(0) is undefined
      entropy += -p * Math.log(p);
    }
  }

  return Math.exp(entropy);
}

function correlationDictToMatrix(corr, fundIds) {
  // Takes a Map-based correlation structure (corr.get(fidA).get(fidB)),
  // matching maths.js's convention, and converts it into a plain n x n
  // array of arrays, in the order given by fundIds -- jacobiEigen needs
  // a fixed, ordered structure.
  const n = fundIds.length;
  return Array.from({ length: n }, (_, i) =>
    Array.from({ length: n }, (_, j) => corr.get(fundIds[i]).get(fundIds[j]))
  );
}

function sanityCheckEigenvaluesSumToN(eigenvalues, n, tol = 1e-6) {
  const total = eigenvalues.reduce((sum, ev) => sum + ev, 0);
  if (Math.abs(total - n) >= tol) {
    throw new Error(
      `Eigenvalues sum to ${total.toFixed(6)}, expected ${n} — Jacobi didn't ` +
        `converge or there's a bug in jacobiEigen.`
    );
  }
  return total;
}

module.exports = {
  jacobiEigen,
  computeEffectiveN,
  correlationDictToMatrix,
  sanityCheckEigenvaluesSumToN,
};
