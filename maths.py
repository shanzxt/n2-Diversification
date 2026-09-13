import json
import sys

EXCLUDED_FUND_IDS = [145552]


def compute_mean_vector(fund_ids, window, data):
    """
    Arithmetic mean of each fund's returns, restricted to the overlap
    window (window comes from get_overlap_window — same window must be
    reused for covariance/Sharpe so everything agrees on the same period).
    """
    funds_by_id = {f['id']: f for f in data['funds']}
    start_idx = window['start_idx']
    end_idx = window['end_idx']
    n_months = window['n_months']  # == end_idx - start_idx + 1

    means = {}
    for fid in fund_ids:
        returns = funds_by_id[fid]['returns']

        total = 0
        i = start_idx
        while i <= end_idx:          # inclusive of end_idx
            r = returns[i]
            assert r is not None, f"Unexpected None at idx {i} for fund {fid}"
            total = total + r
            i += 1

        means[fid] = total / n_months  # divide after the loop, not inside it

    return means


def compute_std_vector(fund_ids, window, data, means=None):
    """
    Sample standard deviation (n-1 denominator) of each fund's returns,
    restricted to the overlap window. Reuses the same means dict as
    compute_mean_vector so mean/std/covariance all agree.
    """
    funds_by_id = {f['id']: f for f in data['funds']}
    start_idx = window['start_idx']
    end_idx = window['end_idx']
    n_months = window['n_months']

    if n_months < 2:
        raise ValueError(
            f"Cannot compute sample std dev with n_months={n_months} "
            f"(window {window['start_date']} to {window['end_date']}). "
            f"Need at least 2 overlapping months."
        )

    if means is None:
        means = compute_mean_vector(fund_ids, window, data)

    stds = {}
    for fid in fund_ids:
        returns = funds_by_id[fid]['returns']
        mean = means[fid]

        sum_sq_dev = 0
        i = start_idx
        while i <= end_idx:          # inclusive of end_idx, same range as mean
            r = returns[i]
            assert r is not None, f"Unexpected None at idx {i} for fund {fid}"
            sum_sq_dev = sum_sq_dev + (r - mean) ** 2
            i += 1

        variance = sum_sq_dev / (n_months - 1)  # divide after the loop
        stds[fid] = variance ** 0.5             # sqrt as the very last step

    return stds


def compute_covariance_matrix(fund_ids, window, data, means=None):
    """
    Sample covariance matrix (n-1 denominator), built directly from the
    aligned windowed return series — NOT derived from correlation — so
    the two can be cross-checked against each other independently.

    Only the upper triangle (including diagonal) is computed; the rest
    is mirrored, which guarantees symmetry by construction and halves
    the work.

    Returns a nested dict: cov[fid_a][fid_b].
    """
    funds_by_id = {f['id']: f for f in data['funds']}
    start_idx = window['start_idx']
    end_idx = window['end_idx']
    n_months = window['n_months']

    if n_months < 2:
        raise ValueError(
            f"Cannot compute sample covariance with n_months={n_months} "
            f"(window {window['start_date']} to {window['end_date']}). "
            f"Need at least 2 overlapping months."
        )

    if means is None:
        means = compute_mean_vector(fund_ids, window, data)

    # Pre-slice each fund's windowed returns once, rather than re-slicing
    # inside the double loop.
    windowed = {}
    for fid in fund_ids:
        returns = funds_by_id[fid]['returns']
        series = []
        i = start_idx
        while i <= end_idx:
            r = returns[i]
            assert r is not None, f"Unexpected None at idx {i} for fund {fid}"
            series.append(r)
            i += 1
        windowed[fid] = series

    cov = {fid: {} for fid in fund_ids}

    for a_idx, fid_a in enumerate(fund_ids):
        series_a = windowed[fid_a]
        mean_a = means[fid_a]

        for fid_b in fund_ids[a_idx:]:   # upper triangle including diagonal
            series_b = windowed[fid_b]
            mean_b = means[fid_b]

            total = 0
            for t in range(n_months):
                total += (series_a[t] - mean_a) * (series_b[t] - mean_b)

            c = total / (n_months - 1)
            cov[fid_a][fid_b] = c
            cov[fid_b][fid_a] = c   # mirror — symmetry by construction

    return cov


def compute_correlation_matrix(fund_ids, window, data, means=None, stds=None, cov=None):
    """
    Normalizes covariance by the outer product of std devs:
    corr[a][b] = cov[a][b] / (std[a] * std[b]).
    Diagonal must come out to exactly 1.0 (up to floating point) —
    that's the first free sanity check.
    """
    if means is None:
        means = compute_mean_vector(fund_ids, window, data)
    if stds is None:
        stds = compute_std_vector(fund_ids, window, data, means=means)
    if cov is None:
        cov = compute_covariance_matrix(fund_ids, window, data, means=means)

    corr = {}
    for fid_a in fund_ids:
        corr[fid_a] = {}
        for fid_b in fund_ids:
            corr[fid_a][fid_b] = cov[fid_a][fid_b] / (stds[fid_a] * stds[fid_b])

    return corr


def sanity_check_covariance_matrix(cov, stds, fund_ids, tol=1e-9):
    """
    Formula-level invariant: cov[i][i] must equal std[i]**2, since
    variance IS covariance-with-itself. This cross-checks the
    independently-computed std and covariance functions against each
    other — if they disagree, one of the two has a bug.
    """
    max_diff = 0
    for fid in fund_ids:
        diag = cov[fid][fid]
        var = stds[fid] ** 2
        diff = abs(diag - var)
        max_diff = max(max_diff, diff)
        assert diff < tol, (
            f"Covariance diagonal mismatch for fund {fid}: "
            f"cov[i][i]={diag}, std[i]**2={var}, diff={diff}"
        )
    return max_diff


def sanity_check_correlation_matrix(corr, fund_ids, tol=1e-9):
    """
    Two invariants that must hold for any valid correlation matrix,
    regardless of the underlying data — catches bugs in the math itself,
    not the data.
    """
    for fid in fund_ids:
        diag = corr[fid][fid]
        assert abs(diag - 1.0) < tol, f"Diagonal for fund {fid} = {diag}, expected 1.0"

    for fid_a in fund_ids:
        for fid_b in fund_ids:
            a_b = corr[fid_a][fid_b]
            b_a = corr[fid_b][fid_a]
            assert abs(a_b - b_a) < tol, (
                f"Asymmetry: corr[{fid_a}][{fid_b}]={a_b} vs corr[{fid_b}][{fid_a}]={b_a}"
            )


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "funds_aligned.json"
    with open(path, 'r') as f:
        data = json.load(f)

    from overlap import get_overlap_window  # or wherever you kept it

    fund_ids = [f['id'] for f in data['funds'] if f['id'] not in EXCLUDED_FUND_IDS]
    window = get_overlap_window(fund_ids, data)

    means = compute_mean_vector(fund_ids, window, data)
    stds = compute_std_vector(fund_ids, window, data, means=means)
    cov = compute_covariance_matrix(fund_ids, window, data, means=means)
    corr = compute_correlation_matrix(fund_ids, window, data, means=means, stds=stds, cov=cov)

    print(window)
    print()

    # --- Formula-level sanity checks ---
    max_diag_diff = sanity_check_covariance_matrix(cov, stds, fund_ids)
    print(f"Covariance diagonal check passed (max diff vs std**2: {max_diag_diff:.2e})")

    sanity_check_correlation_matrix(corr, fund_ids)
    print("Correlation diagonal (==1.0) + symmetry checks passed")

    # --- Real-world eyeball checks ---
    # Two Nifty 500-based index funds — expect strongly positive correlation.
    if 152881 in fund_ids and 151739 in fund_ids:
        print(f"\ncorr[152881][151739] (Momentum 50 vs Value 50, both Nifty 500-based): "
              f"{corr[152881][151739]:.4f}")

    # Liquid/debt fund vs. an equity fund — expect near-zero / weak correlation.
    if 119091 in fund_ids and 118632 in fund_ids:
        print(f"corr[119091][118632] (liquid fund vs equity fund): "
              f"{corr[119091][118632]:.4f}")

    print("\nmeans:", means)
    print("stds:", stds)