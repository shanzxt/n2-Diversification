"""
Generates js/fixtures.json — known-correct outputs from the current,
validated Python math engine, used as golden values for the JS port
(js/*.js + js/*.test.js) to check itself against.

Rerun this whenever the underlying data (funds_aligned.json) or the
Python reference implementation changes, so the JS tests are always
checked against up-to-date expected values rather than hand-copied,
stale numbers.
"""

import json

from overlap import get_overlap_window
from maths import (
    EXCLUDED_FUND_IDS,
    compute_mean_vector,
    compute_std_vector,
    compute_covariance_matrix,
    compute_correlation_matrix,
)
from eigen import jacobi_eigen, compute_effective_n, correlation_dict_to_matrix
from confidence import compute_portfolio_window_note, compute_confidence_flags
from portfolio import compute_portfolio_stats


def main():
    with open("funds_aligned.json", "r") as f:
        data = json.load(f)

    fixtures = {}

    # --- Toy 3-fund correlation matrix (same as eigen.py's __main__) ---
    toy_corr = [
        [1.0, 0.9, 0.1],
        [0.9, 1.0, 0.1],
        [0.1, 0.1, 1.0],
    ]
    toy_eigenvalues, _ = jacobi_eigen(toy_corr)
    toy_effective_n = compute_effective_n(toy_eigenvalues)
    fixtures["toy_3fund"] = {
        "correlation_matrix": toy_corr,
        "eigenvalues": sorted(toy_eigenvalues, reverse=True),
        "effective_n": toy_effective_n,
    }

    # --- get_overlap_window: three cases from overlap.py's own __main__ ---
    all_ids = [f["id"] for f in data["funds"]]
    fixtures["overlap_window"] = {
        "all_44_funds": {
            "fund_ids": all_ids,
            "result": get_overlap_window(all_ids, data),
        },
        "first_two_funds": {
            "fund_ids": all_ids[:2],
            "result": get_overlap_window(all_ids[:2], data),
        },
        "single_fund_119091": {
            "fund_ids": [119091],
            "result": get_overlap_window([119091], data),
        },
    }

    # --- Fund 118632's standalone mean/std over the current window ---
    fund_ids = [f["id"] for f in data["funds"] if f["id"] not in EXCLUDED_FUND_IDS]
    window = get_overlap_window(fund_ids, data)
    means = compute_mean_vector(fund_ids, window, data)
    stds = compute_std_vector(fund_ids, window, data, means=means)
    cov = compute_covariance_matrix(fund_ids, window, data, means=means)
    corr = compute_correlation_matrix(fund_ids, window, data, means=means, stds=stds, cov=cov)

    fixtures["fund_118632_within_44_fund_window"] = {
        "mean": means[118632],
        "std": stds[118632],
    }

    # --- Specific correlation matrix cells ---
    fixtures["correlation_cells"] = {
        "corr_152881_151739": corr[152881][151739],
        "corr_119091_118632": corr[119091][118632],
    }

    # --- Small multi-fund case (maths.js layer): exercises full mean/std/
    # covariance/correlation matrices and the sanity-check functions
    # together, in a fixed fund_ids order, so the JS test can catch a Map
    # (or object-key) ordering bug that single-cell fixtures above would
    # miss. Mix of equity funds + the low-variance debt fund (119091).
    small_ids = [118632, 118955, 119091]
    small_window = get_overlap_window(small_ids, data)
    small_means = compute_mean_vector(small_ids, small_window, data)
    small_stds = compute_std_vector(small_ids, small_window, data, means=small_means)
    small_cov = compute_covariance_matrix(small_ids, small_window, data, means=small_means)
    small_corr = compute_correlation_matrix(
        small_ids, small_window, data, means=small_means, stds=small_stds, cov=small_cov
    )
    fixtures["maths_small_multi_fund"] = {
        "fund_ids": small_ids,
        "window": small_window,
        "means": small_means,
        "stds": small_stds,
        "covariance_matrix": {str(a): {str(b): small_cov[a][b] for b in small_ids} for a in small_ids},
        "correlation_matrix": {str(a): {str(b): small_corr[a][b] for b in small_ids} for a in small_ids},
    }

    # --- Full 44-fund effective N and top eigenvalue ---
    matrix = correlation_dict_to_matrix(corr, fund_ids)
    eigenvalues, _ = jacobi_eigen(matrix)
    eigenvalues_sorted = sorted(eigenvalues, reverse=True)
    fixtures["full_universe_eigen"] = {
        "n_funds": len(fund_ids),
        "effective_n": compute_effective_n(eigenvalues),
        "top_eigenvalue": eigenvalues_sorted[0],
    }

    # --- portfolioMath.js fixtures: the two structural validations from
    # portfolio.py's own __main__, so the JS port checks itself the same
    # way the Python reference does. ---
    single_fund_stats = compute_portfolio_stats(
        {118632: 1.0}, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr
    )
    fixtures["portfolio_single_fund_validation"] = {
        "test_fid": 118632,
        "portfolio_monthly_return": single_fund_stats["monthly_return"],
        "portfolio_monthly_std": single_fund_stats["monthly_std"],
        "expected_mean": means[118632],
        "expected_std": stds[118632],
    }

    raw = {118632: 3.0, 118955: 1.0}
    pre_normalized = {118632: 0.75, 118955: 0.25}
    stats_raw = compute_portfolio_stats(raw, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)
    stats_pre = compute_portfolio_stats(pre_normalized, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)
    fixtures["portfolio_normalization_validation"] = {
        "raw_weights": raw,
        "pre_normalized_weights": pre_normalized,
        "raw_weights_return": stats_raw["monthly_return"],
        "normalized_return": stats_pre["monthly_return"],
    }

    # --- 7/8-fund thesis-test effective-N pair (portfolio.py's __main__) ---
    all_equity = {118632: 1, 118955: 1, 120166: 1, 118834: 1, 120158: 1, 118989: 1, 119775: 1}
    with_debt = {**all_equity, 119091: 1}
    equity_stats = compute_portfolio_stats(all_equity, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)
    mixed_stats = compute_portfolio_stats(with_debt, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)
    fixtures["thesis_test"] = {
        "all_equity_effective_n": equity_stats["effective_n"],
        "equity_plus_debt_effective_n": mixed_stats["effective_n"],
    }

    # --- confidence.js fixtures: portfolio window note + specific
    # per-fund flags, for the full 44-fund universe. ---
    portfolio_note = compute_portfolio_window_note(fund_ids, window, data)
    confidence_flags = compute_confidence_flags(fund_ids, window, data, stds=stds)
    fixtures["confidence_flags"] = {
        "portfolio_window_note": portfolio_note,
        "flags_152881": confidence_flags.get(152881),
        "flags_119091": confidence_flags.get(119091),
        "flags_120754": confidence_flags.get(120754),
        "n_flagged_funds": len(confidence_flags),
    }

    with open("js/fixtures.json", "w") as f:
        json.dump(fixtures, f, indent=2)

    print("Wrote js/fixtures.json")


if __name__ == "__main__":
    main()
