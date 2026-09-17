import json
import math
import sys

from maths import (
    EXCLUDED_FUND_IDS,
    compute_mean_vector,
    compute_std_vector,
    compute_covariance_matrix,
    compute_correlation_matrix,
)
from overlap import get_overlap_window


def jacobi_eigen(A, tol=1e-10, max_sweeps=200):
    """
    Cyclic Jacobi eigenvalue algorithm for a symmetric matrix A (list of
    lists). Repeatedly sweeps through every off-diagonal pair (p, q) and
    applies a rotation that zeroes a[p][q]; a later rotation for a
    different pair can slightly un-zero it, but the sum of squared
    off-diagonal elements strictly decreases every sweep, so this
    converges to a diagonal matrix.

    Returns (eigenvalues, eigenvectors):
    - eigenvalues: list of n floats (the converged diagonal of A)
    - eigenvectors: n x n list of lists; eigenvectors[i][k] is the i-th
      component of the k-th eigenvector (i.e. eigenvectors' COLUMNS are
      the eigenvectors, matching standard convention).
    """
    n = len(A)
    a = [row[:] for row in A]  # work on a copy, don't mutate the input
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

    for sweep in range(max_sweeps):
        off_diag_sq = 0.0
        for i in range(n):
            for j in range(n):
                if i != j:
                    off_diag_sq += a[i][j] ** 2

        if off_diag_sq < tol:
            break

        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) < 1e-15:
                    continue

                app = a[p][p]
                aqq = a[q][q]

                theta = (aqq - app) / (2 * apq)
                sign = 1.0 if theta >= 0 else -1.0
                t = sign / (abs(theta) + math.sqrt(theta ** 2 + 1))
                c = 1.0 / math.sqrt(t ** 2 + 1)
                s = t * c

                a[p][p] = c * c * app - 2 * s * c * apq + s * s * aqq
                a[q][q] = s * s * app + 2 * s * c * apq + c * c * aqq
                a[p][q] = 0.0
                a[q][p] = 0.0

                for i in range(n):
                    if i != p and i != q:
                        aip = a[i][p]
                        aiq = a[i][q]
                        a[i][p] = c * aip - s * aiq
                        a[p][i] = a[i][p]
                        a[i][q] = s * aip + c * aiq
                        a[q][i] = a[i][q]

                for i in range(n):
                    vip = v[i][p]
                    viq = v[i][q]
                    v[i][p] = c * vip - s * viq
                    v[i][q] = s * vip + c * viq

    eigenvalues = [a[i][i] for i in range(n)]
    return eigenvalues, v


def compute_effective_n(eigenvalues):
    """
    Entropy-based (Meucci-style) effective number of independent bets.
    Normalizes eigenvalues into a probability distribution, computes
    Shannon entropy, exponentiates. Ranges from 1 (all variance in one
    factor) to N (all factors equally weighted / fully independent).
    """
    total = sum(eigenvalues)

    probs = []
    for ev in eigenvalues:
        p = ev / total
        # Clamp tiny negative values from floating-point noise (an
        # eigenvalue that should be ~0 can come out as -1e-16).
        if p < 0:
            p = 0.0
        probs.append(p)

    entropy = 0.0
    for p in probs:
        if p > 1e-15:  # skip zero-probability terms, log(0) is undefined
            entropy += -p * math.log(p)

    return math.exp(entropy)


def correlation_dict_to_matrix(corr, fund_ids):
    """
    Converts the nested-dict correlation matrix (corr[fid_a][fid_b]) from
    maths.py into a plain n x n list of lists, in the order given by
    fund_ids — jacobi_eigen needs a fixed, ordered structure.
    """
    n = len(fund_ids)
    return [[corr[fund_ids[i]][fund_ids[j]] for j in range(n)] for i in range(n)]


def sanity_check_eigenvalues_sum_to_n(eigenvalues, n, tol=1e-6):
    """
    Trace invariant: for any correlation matrix, the diagonal is all 1s,
    so the trace is N — and trace is preserved by eigen-decomposition, so
    the eigenvalues must sum to N. If they don't, the Jacobi
    implementation has a bug (or hasn't converged — see max_sweeps/tol).
    """
    total = sum(eigenvalues)
    assert abs(total - n) < tol, (
        f"Eigenvalues sum to {total:.6f}, expected {n} — Jacobi didn't "
        f"converge or there's a bug in jacobi_eigen."
    )
    return total


if __name__ == "__main__":
    # --- Toy validation first: the 3-fund worked example ---
    # A and B nearly identical (0.9), C nearly independent (0.1).
    # Expected: eigenvalues ~[1.9, 1.0, 0.1], effective N ~2.16.
    toy_corr = [
        [1.0, 0.9, 0.1],
        [0.9, 1.0, 0.1],
        [0.1, 0.1, 1.0],
    ]
    toy_eigenvalues, _ = jacobi_eigen(toy_corr)
    toy_sorted = sorted(toy_eigenvalues, reverse=True)
    toy_sum = sanity_check_eigenvalues_sum_to_n(toy_eigenvalues, n=3)
    toy_eff_n = compute_effective_n(toy_eigenvalues)

    print("Toy 3-fund validation (A~B correlated 0.9, C independent):")
    print(f"  eigenvalues: {[round(e, 4) for e in toy_sorted]}")
    print(f"  sum: {toy_sum:.6f} (expected 3.0) — PASSED")
    print(f"  effective N: {toy_eff_n:.4f} (expected ~2.16)")
    print()

    # --- Real dataset ---
    path = sys.argv[1] if len(sys.argv) > 1 else "funds_aligned.json"
    with open(path, "r") as f:
        data = json.load(f)

    fund_ids = [f["id"] for f in data["funds"] if f["id"] not in EXCLUDED_FUND_IDS]
    window = get_overlap_window(fund_ids, data)

    means = compute_mean_vector(fund_ids, window, data)
    stds = compute_std_vector(fund_ids, window, data, means=means)
    cov = compute_covariance_matrix(fund_ids, window, data, means=means)
    corr = compute_correlation_matrix(fund_ids, window, data, means=means, stds=stds, cov=cov)

    matrix = correlation_dict_to_matrix(corr, fund_ids)
    eigenvalues, eigenvectors = jacobi_eigen(matrix)

    n = len(fund_ids)
    total = sanity_check_eigenvalues_sum_to_n(eigenvalues, n)
    print(f"Full {n}-fund universe:")
    print(f"  eigenvalue sum check passed: {total:.6f} ≈ {n}")

    eff_n = compute_effective_n(eigenvalues)
    eigenvalues_sorted = sorted(eigenvalues, reverse=True)
    print(f"  effective N: {eff_n:.4f}")
    print(f"  top 5 eigenvalues: {[round(e, 4) for e in eigenvalues_sorted[:5]]}")