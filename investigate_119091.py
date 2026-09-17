import json
import sys

from maths import EXCLUDED_FUND_IDS, compute_mean_vector, compute_std_vector
from overlap import get_overlap_window


def investigate_pair(fund_a, fund_b, fund_ids, window, data):
    """
    Prints the paired monthly return series for two funds over a shared
    window, ranks months by their contribution to the covariance sum,
    and recomputes correlation with the single biggest-contributing
    month excluded — to test whether a handful of months are driving
    an otherwise-unexpected correlation (gotcha #12's hypothesis).
    """
    funds_by_id = {f['id']: f for f in data['funds']}
    dates = data['dates']
    start_idx = window['start_idx']
    end_idx = window['end_idx']
    n_months = window['n_months']

    means = compute_mean_vector(fund_ids, window, data)
    stds = compute_std_vector(fund_ids, window, data, means=means)

    returns_a = funds_by_id[fund_a]['returns']
    returns_b = funds_by_id[fund_b]['returns']
    mean_a, mean_b = means[fund_a], means[fund_b]
    std_a, std_b = stds[fund_a], stds[fund_b]

    rows = []
    i = start_idx
    while i <= end_idx:
        ra, rb = returns_a[i], returns_b[i]
        dev_a, dev_b = ra - mean_a, rb - mean_b
        contribution = dev_a * dev_b
        rows.append({
            "date": dates[i],
            "ra": ra,
            "rb": rb,
            "dev_a": dev_a,
            "dev_b": dev_b,
            "contribution": contribution,
        })
        i += 1

    print(f"Paired returns: {fund_a} vs {fund_b}, window {window['start_date']}–{window['end_date']} ({n_months} months)")
    print(f"{'date':<10}{'r_a':>10}{'r_b':>10}{'contribution':>16}")
    for row in rows:
        print(f"{row['date']:<10}{row['ra']:>10.4%}{row['rb']:>10.4%}{row['contribution']:>16.8f}")

    total_contribution = sum(r["contribution"] for r in rows)
    cov = total_contribution / (n_months - 1)
    corr_full = cov / (std_a * std_b)
    print(f"\nFull-window correlation: {corr_full:.4f}")

    # Rank months by absolute contribution to see if 1-2 months dominate.
    ranked = sorted(rows, key=lambda r: abs(r["contribution"]), reverse=True)
    print("\nTop 5 months by |contribution| to covariance:")
    for row in ranked[:5]:
        pct_of_total = row["contribution"] / total_contribution * 100 if total_contribution != 0 else float("nan")
        print(f"  {row['date']}: contribution={row['contribution']:.8f} ({pct_of_total:.1f}% of total)")

    # Recompute correlation excluding the single biggest-contributing month,
    # using the ORIGINAL means/std (not recentered) — this isolates that
    # month's effect on the correlation coefficient specifically, which is
    # what we actually want to test (not a fully re-fit statistic).
    biggest = ranked[0]
    remaining = [r for r in rows if r["date"] != biggest["date"]]
    cov_excl = sum(r["contribution"] for r in remaining) / (len(remaining) - 1)
    corr_excl = cov_excl / (std_a * std_b)
    print(f"\nCorrelation excluding {biggest['date']} (biggest contributor): {corr_excl:.4f}")
    print(f"Shift from full-window correlation: {corr_excl - corr_full:+.4f}")

    if abs(corr_excl - corr_full) > 0.15:
        print("\n=> Correlation is highly sensitive to a single month — consistent with")
        print("   noise from near-zero variance + short window, per gotcha #12's hypothesis.")
    else:
        print("\n=> Correlation is NOT dominated by a single month — the 0.48 figure looks")
        print("   more structural than a one-off outlier. Worth digging further before")
        print("   dismissing it as noise.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "funds_aligned.json"
    with open(path, "r") as f:
        data = json.load(f)

    fund_ids = [f["id"] for f in data["funds"] if f["id"] not in EXCLUDED_FUND_IDS]
    window = get_overlap_window(fund_ids, data)

    investigate_pair(119091, 118632, fund_ids, window, data)