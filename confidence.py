import json
import sys

from maths import EXCLUDED_FUND_IDS, compute_std_vector, compute_mean_vector
from overlap import get_overlap_window

SHORT_HISTORY_MONTHS_THRESHOLD = 36  # fund's own full history under 3 years
LOW_STD_RATIO_THRESHOLD = 0.1        # fund's std < 10% of the group's median std
PORTFOLIO_WINDOW_NOTE_THRESHOLD = 36  # flag the window itself if under 3 years


def own_history_length(fund_id, data):
    """Count of non-null months in a fund's FULL returns array (its own
    entire history), independent of any shared overlap window."""
    funds_by_id = {f['id']: f for f in data['funds']}
    returns = funds_by_id[fund_id]['returns']
    return sum(1 for r in returns if r is not None)


def find_window_bottleneck_fund(fund_ids, window, data):
    """
    Identifies which fund's own history is shortest among the selection —
    that's the fund forcing the shared overlap window to be as short as
    it is (see gotcha #10). Used for the portfolio-level note, not a
    per-fund flag, since this is a fact about the selection as a whole.
    """
    shortest_fid = None
    shortest_len = None
    for fid in fund_ids:
        own_len = own_history_length(fid, data)
        if shortest_len is None or own_len < shortest_len:
            shortest_len = own_len
            shortest_fid = fid
    return shortest_fid, shortest_len


def compute_portfolio_window_note(fund_ids, window, data):
    """
    ONE note about the shared window itself, when it's short — not
    repeated per fund. Returns None if the window is long enough not
    to need flagging.
    """
    n_months = window['n_months']
    if n_months >= PORTFOLIO_WINDOW_NOTE_THRESHOLD:
        return None

    bottleneck_fid, bottleneck_len = find_window_bottleneck_fund(fund_ids, window, data)
    return {
        "reason": "short_shared_window",
        "detail": (
            f"All stats in this selection are computed over a shared window of "
            f"only {n_months} months ({window['start_date']} to {window['end_date']}), "
            f"even though most funds here have far longer individual histories. "
            f"This is driven by fund {bottleneck_fid}, which only has {bottleneck_len} "
            f"months of its own history and sets the floor for the whole selection."
        ),
    }


def compute_confidence_flags(fund_ids, window, data, stds=None):
    """
    Returns {fund_id: [flag_dict, ...]} for funds with a FUND-SPECIFIC
    confidence concern (not caused merely by another fund in the
    selection forcing a short shared window — that's a portfolio-level
    fact, see compute_portfolio_window_note). A fund with no concerns is
    absent from the dict.
    """
    if stds is None:
        means = compute_mean_vector(fund_ids, window, data)
        stds = compute_std_vector(fund_ids, window, data, means=means)

    std_values = list(stds.values())
    median_std = sorted(std_values)[len(std_values) // 2]

    flags = {}

    for fid in fund_ids:
        fund_flags = []

        own_len = own_history_length(fid, data)
        if own_len > 0 and own_len < SHORT_HISTORY_MONTHS_THRESHOLD:
            fund_flags.append({
                "reason": "intrinsically_short_history",
                "detail": (
                    f"This fund only has {own_len} months of history in total "
                    f"(under {SHORT_HISTORY_MONTHS_THRESHOLD} months) — likely a "
                    f"recently-launched fund. Its own stats, not just the shared "
                    f"window, are based on limited data."
                ),
            })

        std = stds[fid]
        if median_std > 0 and std / median_std < LOW_STD_RATIO_THRESHOLD:
            fund_flags.append({
                "reason": "low_variance_relative_to_group",
                "detail": (
                    f"Std dev ({std:.4%}) is under {LOW_STD_RATIO_THRESHOLD:.0%} of "
                    f"the group's median ({median_std:.4%}). Correlations involving "
                    f"this fund can be noisy — a handful of months can swing the "
                    f"coefficient with limited underlying signal."
                ),
            })

        if fund_flags:
            flags[fid] = fund_flags

    return flags


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "funds_aligned.json"
    with open(path, "r") as f:
        data = json.load(f)

    fund_ids = [f["id"] for f in data["funds"] if f["id"] not in EXCLUDED_FUND_IDS]
    window = get_overlap_window(fund_ids, data)

    portfolio_note = compute_portfolio_window_note(fund_ids, window, data)
    if portfolio_note:
        print(f"[{portfolio_note['reason']}] {portfolio_note['detail']}\n")

    flags = compute_confidence_flags(fund_ids, window, data)
    print(f"Fund-specific confidence flags for {len(flags)} of {len(fund_ids)} funds:\n")
    for fid, fund_flags in flags.items():
        print(f"Fund {fid}:")
        for flag in fund_flags:
            print(f"  [{flag['reason']}] {flag['detail']}")
        print()