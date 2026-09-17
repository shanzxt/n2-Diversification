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
from eigen import jacobi_eigen, compute_effective_n, correlation_dict_to_matrix, sanity_check_eigenvalues_sum_to_n
from confidence import compute_confidence_flags, compute_portfolio_window_note

# 91-day T-bill yield, per the earlier risk-free-rate decision. Hardcoded
# for now — update periodically, don't wire up a live API for this.
RISK_FREE_RATE_ANNUAL = 0.065  # placeholder — replace with current RBI 91-day T-bill cutoff yield


def normalize_weights(raw_weights):
    """
    Takes {fund_id: raw_weight} (need not sum to 1 — e.g. raw slider
    values) and returns {fund_id: normalized_weight} summing to exactly 1.

    This is the ONLY place normalization should happen — every formula
    downstream assumes it's already receiving a normalized vector.
    """
    total = sum(raw_weights.values())
    if total == 0:
        raise ValueError(
            "All weights are zero — select at least one fund with a "
            "nonzero weight before computing portfolio stats."
        )
    return {fid: w / total for fid, w in raw_weights.items()}


def compute_portfolio_return(weights, means):
    """
    w^T mu — portfolio expected return as the weighted sum of each
    fund's arithmetic mean return. `weights` must already be normalized
    (see normalize_weights); this function does not check or normalize.
    """
    return sum(weights[fid] * means[fid] for fid in weights)


def compute_portfolio_variance(weights, cov):
    """
    w^T Sigma w — portfolio variance. Full double sum over all pairs,
    since covariance captures both each fund's own variance (diagonal)
    and every pairwise co-movement (off-diagonal) — dropping either half
    would silently understate diversification effects.
    """
    total = 0.0
    for fid_a, w_a in weights.items():
        for fid_b, w_b in weights.items():
            total += w_a * w_b * cov[fid_a][fid_b]
    return total


def compute_portfolio_std(variance):
    if variance < 0:
        # Can only happen from floating-point noise on a near-zero
        # variance portfolio (e.g. a single-fund "portfolio"); a
        # genuinely negative variance would indicate a bug upstream.
        if variance > -1e-12:
            variance = 0.0
        else:
            raise ValueError(f"Negative portfolio variance ({variance}) — check covariance matrix / weights.")
    return math.sqrt(variance)


def compute_sharpe(portfolio_return_annual, portfolio_std_annual, risk_free_rate_annual=RISK_FREE_RATE_ANNUAL):
    """
    (portfolio return - risk-free) / portfolio std dev, all annualized
    inputs — see annualize_return / annualize_std below for how monthly
    numbers get there.
    """
    return (portfolio_return_annual - risk_free_rate_annual) / portfolio_std_annual


def annualize_return_arithmetic(monthly_return):
    """Arithmetic annualization: monthly x 12. Used for the underlying
    math (Sharpe, etc.) since it stays linear in the weights — see
    annualize_return_geometric for the number to actually DISPLAY."""
    return monthly_return * 12


def annualize_std(monthly_std):
    """Monthly std x sqrt(12) — the standard convention, no geometric
    equivalent exists for volatility."""
    return monthly_std * math.sqrt(12)


def annualize_return_geometric(weights, fund_ids, window, data):
    """
    The number to DISPLAY as "annualized return" — NOT used in any
    downstream math (Sharpe, variance, etc. all use the arithmetic
    mean, since only arithmetic means combine linearly across weights).

    Builds the portfolio's own monthly return series first (each month
    = w^T r_t using that month's actual returns), then geometrically
    compounds THAT series. Do not combine individual funds' own CAGRs
    with weights — that produces a wrong number, since geometric means
    don't combine linearly the way arithmetic means do.
    """
    funds_by_id = {f['id']: f for f in data['funds']}
    start_idx = window['start_idx']
    end_idx = window['end_idx']
    n_months = window['n_months']

    portfolio_monthly_returns = []
    i = start_idx
    while i <= end_idx:
        month_return = sum(
            weights[fid] * funds_by_id[fid]['returns'][i]
            for fid in weights
        )
        portfolio_monthly_returns.append(month_return)
        i += 1

    compounded = 1.0
    for r in portfolio_monthly_returns:
        compounded *= (1 + r)

    monthly_geometric_mean = compounded ** (1 / n_months) - 1
    annualized_geometric = (1 + monthly_geometric_mean) ** 12 - 1
    return annualized_geometric


def compute_portfolio_stats(raw_weights, fund_ids, window, data, means=None, stds=None, cov=None, corr=None):
    """
    The main entry point: takes raw (possibly unnormalized) weights for
    a SUBSET of fund_ids, and returns a full stats dict — return,
    variance, std, Sharpe (all annualized), effective N for just this
    subset, and any confidence flags relevant to the selected funds.

    means/stds/cov/corr, if not passed in, are computed fresh from the
    FULL fund_ids universe (so they reuse the same shared window) —
    pass them in when calling this repeatedly (e.g. per slider drag) to
    avoid recomputing the whole universe's stats every time.
    """
    selected_ids = list(raw_weights.keys())
    unknown = [fid for fid in selected_ids if fid not in fund_ids]
    if unknown:
        raise KeyError(f"Fund id(s) not in universe: {unknown}")

    weights = normalize_weights(raw_weights)

    if means is None:
        means = compute_mean_vector(fund_ids, window, data)
    if stds is None:
        stds = compute_std_vector(fund_ids, window, data, means=means)
    if cov is None:
        cov = compute_covariance_matrix(fund_ids, window, data, means=means)
    if corr is None:
        corr = compute_correlation_matrix(fund_ids, window, data, means=means, stds=stds, cov=cov)

    monthly_return = compute_portfolio_return(weights, means)
    variance = compute_portfolio_variance(weights, cov)
    monthly_std = compute_portfolio_std(variance)

    annual_return_arith = annualize_return_arithmetic(monthly_return)
    annual_std = annualize_std(monthly_std)
    annual_return_display = annualize_return_geometric(weights, fund_ids, window, data)

    sharpe = compute_sharpe(annual_return_arith, annual_std) if annual_std > 0 else None

    # Effective N for just this subset — decompose the subset's OWN
    # correlation matrix, not the full 44-fund one.
    subset_corr_matrix = correlation_dict_to_matrix(corr, selected_ids)
    eigenvalues, eigenvectors = jacobi_eigen(subset_corr_matrix)
    sanity_check_eigenvalues_sum_to_n(eigenvalues, len(selected_ids))
    effective_n = compute_effective_n(eigenvalues)

    confidence_flags = compute_confidence_flags(fund_ids, window, data, stds=stds)
    relevant_flags = {fid: confidence_flags[fid] for fid in selected_ids if fid in confidence_flags}
    portfolio_note = compute_portfolio_window_note(fund_ids, window, data)

    return {
        "weights": weights,
        "monthly_return": monthly_return,
        "annual_return_arithmetic": annual_return_arith,   # used internally (Sharpe etc.)
        "annual_return_display": annual_return_display,     # geometric — show THIS to the user
        "monthly_std": monthly_std,
        "annual_std": annual_std,
        "sharpe_ratio": sharpe,
        "effective_n": effective_n,
        "n_funds_selected": len(selected_ids),
        "confidence_flags": relevant_flags,
        "portfolio_window_note": portfolio_note,
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "funds_aligned.json"
    with open(path, "r") as f:
        data = json.load(f)

    fund_ids = [f["id"] for f in data["funds"] if f["id"] not in EXCLUDED_FUND_IDS]
    window = get_overlap_window(fund_ids, data)

    # Shared computations, reused across the test cases below rather
    # than recomputed per call.
    means = compute_mean_vector(fund_ids, window, data)
    stds = compute_std_vector(fund_ids, window, data, means=means)
    cov = compute_covariance_matrix(fund_ids, window, data, means=means)
    corr = compute_correlation_matrix(fund_ids, window, data, means=means, stds=stds, cov=cov)

    # --- Validation 1: single-fund "portfolio" should exactly match
    # that fund's own standalone mean/std. ---
    test_fid = 118632
    single_fund_stats = compute_portfolio_stats(
        {test_fid: 1.0}, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr
    )
    expected_mean = means[test_fid]
    expected_std = stds[test_fid]
    print("Validation: single-fund portfolio vs. standalone stats")
    print(f"  portfolio monthly return: {single_fund_stats['monthly_return']:.8f} (expected {expected_mean:.8f})")
    print(f"  portfolio monthly std:    {single_fund_stats['monthly_std']:.8f} (expected {expected_std:.8f})")
    assert abs(single_fund_stats['monthly_return'] - expected_mean) < 1e-9, "Mean mismatch!"
    assert abs(single_fund_stats['monthly_std'] - expected_std) < 1e-9, "Std mismatch!"
    print("  PASSED\n")

    # --- Validation 2: unnormalized weights should behave identically
    # to pre-normalized weights (tests normalize_weights is actually
    # being applied). ---
    raw = {118632: 3.0, 118955: 1.0}   # will normalize to 0.75 / 0.25
    pre_normalized = {118632: 0.75, 118955: 0.25}
    stats_raw = compute_portfolio_stats(raw, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)
    stats_pre = compute_portfolio_stats(pre_normalized, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)
    print("Validation: unnormalized weights vs. pre-normalized weights")
    print(f"  raw-weights return:  {stats_raw['monthly_return']:.8f}")
    print(f"  normalized return:   {stats_pre['monthly_return']:.8f}")
    assert abs(stats_raw['monthly_return'] - stats_pre['monthly_return']) < 1e-9, "Normalization mismatch!"
    print("  PASSED\n")

    # --- The actual thesis test: all-equity vs. equity+debt-fund ---
    all_equity = {118632: 1, 118955: 1, 120166: 1, 118834: 1, 120158: 1, 118989: 1, 119775: 1}
    with_debt = {**all_equity, 119091: 1}  # add the liquid/debt fund

    equity_stats = compute_portfolio_stats(all_equity, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)
    mixed_stats = compute_portfolio_stats(with_debt, fund_ids, window, data, means=means, stds=stds, cov=cov, corr=corr)

    print("Thesis test: 7 equity funds vs. same 7 + 1 debt fund")
    print(f"  All-equity (7 funds)  — effective N: {equity_stats['effective_n']:.4f}")
    print(f"  Equity + debt (8 funds) — effective N: {mixed_stats['effective_n']:.4f}")
    print(f"  (Note: fund 119091 carries a low-variance confidence flag — "
          f"see 'confidence_flags' in the returned stats dict.)\n")

    print("Full stats dict for the equity+debt portfolio:")
    for k, v in mixed_stats.items():
        print(f"  {k}: {v}")