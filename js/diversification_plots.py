"""
Diversification analysis: everything behind "44 funds, 2 bets" in one file.

Needs funds_aligned.json in the same folder.

    python analysis.py factor    # the one shared factor, step by step
    python analysis.py nifty     # how closely that factor tracks the Nifty 50
    python analysis.py charts    # rebuild all seven newsletter charts into ./charts
    python analysis.py           # all three

Needs numpy; charts also needs matplotlib.
"""
import json, os, sys
import numpy as np

DATA_FILE = "funds_aligned.json"
EXCLUDED_ID = 145552          # Motilal Oswal Nasdaq 100 FOF, same exclusion as the repo


# ============================ shared: returns table ============================
def load_returns():
    data = json.load(open(DATA_FILE))
    funds = [f for f in data["funds"] if f["id"] != EXCLUDED_ID]
    first = max(next(i for i, r in enumerate(f["returns"]) if r is not None) for f in funds)
    last = min(max(i for i, r in enumerate(f["returns"]) if r is not None) for f in funds)
    R = np.array([f["returns"][first:last + 1] for f in funds], float)   # 44 funds x 22 months
    return funds, R, data["dates"][first:last + 1]


def build_factor(R):
    # standardise each fund (subtract its own average, divide by its own spread)
    Z = (R - R.mean(axis=1, keepdims=True)) / R.std(axis=1, ddof=1, keepdims=True)
    # correlation matrix: how every fund moves with every other fund (the heatmap)
    C = np.corrcoef(R)
    # break the matrix into its patterns (eigenvalues = size, eigenvectors = recipe)
    eigenvalues, eigenvectors = np.linalg.eigh(C)
    order = np.argsort(-eigenvalues)                                     # biggest first
    eigenvalues, eigenvectors = eigenvalues[order], eigenvectors[:, order]
    # factor 1's recipe = the biggest pattern's weights (one weight per fund)
    weights = eigenvectors[:, 0]
    if weights.sum() < 0:
        weights = -weights                                               # so "up" means up
    factor = weights @ Z                                                 # one number per month
    return eigenvalues, factor


# ============================ 1. the factor ============================
def run_factor():
    funds, R, dates = load_returns()
    eigenvalues, factor = build_factor(R)
    share = eigenvalues / eigenvalues.sum()                              # eigenvalues add up to 44
    print(f"factor 1 explains {share[0]:.1%}  ({eigenvalues[0]:.2f} of {len(funds)})")
    print("next shares:", [f"{s:.1%}" for s in share[1:4]])
    print("factor by month (first 5):", np.round(factor[:5], 2))


# ============================ 2. Nifty check ============================
NIFTY_FUND_ID = 120716        # UTI Nifty 50 Index Fund, Direct Plan, Growth (tracks the Nifty 50)


def run_nifty():
    funds, R, dates = load_returns()
    _, factor = build_factor(R)
    k = [f["id"] for f in funds].index(NIFTY_FUND_ID)
    nifty = R[k]                                        # the index fund's monthly returns
    print(f"window: {dates[0]} to {dates[-1]}  ({len(dates)} months)")
    print(f"factor vs UTI Nifty 50 Index Fund: {np.corrcoef(factor, nifty)[0, 1]:.3f}")
    # the index fund is one of the 44, so also rebuild the factor without it (43 funds)
    R43 = np.delete(R, k, axis=0)
    _, factor43 = build_factor(R43)
    print(f"factor built from the other 43 funds vs the index fund: "
          f"{np.corrcoef(factor43, nifty)[0, 1]:.3f}")


# ============================ 3. charts ============================
def run_charts(DATA=DATA_FILE, OUT="charts"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    os.makedirs(OUT, exist_ok=True)
    # ---------- style (blue / orange / warm greys, white page for Substack) ----------
    BLUE, ORANGE = "#2a78d6", "#eb6834"
    INK, INK2, MUTED, GRID, GREYBAR = "#0b0b0b", "#52514e", "#8a8983", "#e8e7e3", "#c9c8c2"
    SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
    plt.rcParams.update({
        "font.family": ["Liberation Sans", "Arial", "Helvetica", "DejaVu Sans"], "font.size": 10, "axes.edgecolor": GRID,
        "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 200,
        "savefig.facecolor": "white", "figure.facecolor": "white",
    })
    W, H = 7.28, 4.3  # inches -> 1456 x 860 px at 200 dpi
    WINDOW_NOTE = "22-month window (Nov 2024 – Aug 2026), set by the newest fund in the set"
    SRC = "Source: mfapi.in NAVs (Direct–Growth plans), author's calculations. "


    import textwrap
    def frame(fig, title, sub, src):
        h = fig.get_figheight()
        fig.text(0.045, 1 - 0.16 / h, title, fontsize=15, fontweight="bold", color=INK, va="top", ha="left")
        fig.text(0.045, 1 - 0.56 / h, sub, fontsize=9.5, color=INK2, va="top", ha="left")
        fig.text(0.045, 0.10 / h, textwrap.fill(src, 105), fontsize=7.5, color=MUTED, va="bottom", ha="left", linespacing=1.3)


    def save(fig, name):
        fig.savefig(os.path.join(OUT, name), dpi=200)
        plt.close(fig)
        print("wrote", name)


    # ---------- data ----------
    d = json.load(open(DATA))
    by = {f["id"]: f for f in d["funds"]}
    EXCLUDED = {EXCLUDED_ID}
    CAT_ORDER = ["Large Cap", "Flexi Cap", "Large & Mid Cap", "Mid Cap", "Small Cap", "Multi Cap", "ELSS",
                 "Value / Contra", "Focused", "Index", "Hybrid", "Debt", "International"]
    funds = [f for f in d["funds"] if f["id"] not in EXCLUDED]
    funds.sort(key=lambda f: CAT_ORDER.index(f["category"]))
    ids = [f["id"] for f in funds]
    cats = [f["category"] for f in funds]
    n = len(ids)


    def valid_range(i):
        r = by[i]["returns"]
        v = [k for k, x in enumerate(r) if x is not None]
        return v[0], v[-1]


    def returns(ids_, s, e):
        return np.array([by[i]["returns"][s:e + 1] for i in ids_], float)


    def effn(C):
        ev = np.clip(np.linalg.eigvalsh(C), 0, None)
        p = ev / ev.sum()
        p = p[p > 1e-15]
        return float(np.exp(-(p * np.log(p)).sum()))


    s0 = max(valid_range(i)[0] for i in ids)
    e0 = min(valid_range(i)[1] for i in ids)
    X = returns(ids, s0, e0)
    C = np.corrcoef(X)
    ev = np.sort(np.linalg.eigvalsh(C))[::-1]
    share = ev / ev.sum()
    iu = np.triu_indices(n, 1)
    pair = C[iu]
    print(f"window {d['dates'][s0]}..{d['dates'][e0]}  n_months={e0 - s0 + 1}  funds={n}")
    print(f"top eigenvalue {ev[0]:.2f} of {n} ({share[0]*100:.1f}%), effective N {effn(C):.3f}")
    print(f"pairs {len(pair)}  median corr {np.median(pair):.3f}  min {pair.min():.3f}  max {pair.max():.3f}")

    # ====================== 1. correlation heatmap ======================
    fig = plt.figure(figsize=(W, 6.6))
    ax = fig.add_axes([0.20, 0.13, 0.75, 0.70])
    off = C[~np.eye(n, dtype=bool)]
    vmin = np.floor(off.min() * 10) / 10
    cmap = LinearSegmentedColormap.from_list("seq", SEQ)
    im = ax.imshow(C, cmap=cmap, vmin=vmin, vmax=1, aspect="equal", interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    # category blocks
    start = 0
    for cat in CAT_ORDER:
        idx = [k for k, c in enumerate(cats) if c == cat]
        a, b = idx[0], idx[-1]
        ax.text(-1.2, (a + b) / 2, cat, ha="right", va="center", fontsize=8, color=INK2)
        if b + 1 < n:
            ax.axhline(b + 0.5, color="white", lw=1.2)
            ax.axvline(b + 0.5, color="white", lw=1.2)
    cax = fig.add_axes([0.40, 0.075, 0.35, 0.014])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal")
    cb.outline.set_visible(False)
    cb.set_ticks([vmin, 0, 0.5, 1.0])
    cb.ax.tick_params(labelsize=8, length=0)
    fig.text(0.39, 0.078, "correlation", fontsize=8, color=INK2, ha="right", va="center")
    frame(fig, "Nearly every fund moves with nearly every other",
          f"Correlation of monthly returns between {n} mutual funds in 13 categories. Darker = moves together.",
          SRC + WINDOW_NOTE + ".")
    save(fig, "1_correlation_heatmap.png")

    # ====================== 2. one factor explains most ======================
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.09, 0.17, 0.87, 0.60])
    top = 8
    x = np.arange(1, top + 1)
    cols = [ORANGE] + [GREYBAR] * (top - 1)
    ax.bar(x, share[:top] * 100, color=cols, width=0.68, edgecolor="white", linewidth=1.5)
    ax.text(1, share[0] * 100 + 2, f"{share[0]*100:.0f}%", ha="center", fontsize=15, fontweight="bold", color=INK)
    ax.text(1.55, share[0] * 100 - 4, linespacing=1.5, s= f"of all the ups and downs across {n} funds\nis one shared factor\n({ev[0]:.1f} out of a possible {n})",
            fontsize=9, color=INK2, va="top", ha="left")
    for k in range(1, top):
        ax.text(k + 1, share[k] * 100 + 1.5, f"{share[k]*100:.1f}%", ha="center", fontsize=8, color=INK2)
    ax.set_xticks(x); ax.set_xticklabels([f"#{k}" for k in x])
    ax.set_ylim(0, 100); ax.set_yticks([0, 25, 50, 75, 100]); ax.set_yticklabels(["0", "25", "50", "75", "100%"])
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.spines["bottom"].set_color(GRID); ax.tick_params(length=0)
    ax.set_xlabel("Hidden factors driving the funds, ranked by importance")
    frame(fig, f"One factor drives {share[0]*100:.0f}% of everything",
          "Share of total variation in fund returns explained by each hidden factor (principal components).",
          SRC + WINDOW_NOTE + ".")
    save(fig, "2_one_factor.png")

    # ====================== 3. funds held vs real bets ======================
    rng = np.random.default_rng(7)
    DEBT = {c for c in ("Debt",)}
    pool = [k for k, c in enumerate(cats) if c not in ("Debt", "Hybrid")]  # equity + international
    liquid_k = ids.index(119091)
    ks = list(range(1, len(pool) + 1))
    med, lo, hi = [], [], []
    for k in ks:
        draws = 1 if k == len(pool) else 600
        vals = []
        for _ in range(draws):
            sel = rng.choice(pool, size=k, replace=False)
            vals.append(effn(C[np.ix_(sel, sel)]) if k > 1 else 1.0)
        med.append(np.median(vals)); lo.append(np.percentile(vals, 10)); hi.append(np.percentile(vals, 90))
    med, lo, hi = map(np.array, (med, lo, hi))
    XMAX = 15
    kk = [k for k in ks if k <= XMAX]
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.09, 0.17, 0.87, 0.62])
    ax.plot(kk, kk, color=MUTED, lw=1.2, ls=(0, (4, 3)))
    ax.fill_between(kk, lo[:XMAX], hi[:XMAX], color=BLUE, alpha=0.15, lw=0)
    ax.plot(kk, med[:XMAX], color=BLUE, lw=2.4)
    ax.plot([XMAX], [med[XMAX - 1]], "o", color=BLUE, ms=6, mec="white", mew=1.5)
    ax.text(6.6, 11.6, "What it looks like:\none new bet per fund", color=MUTED, fontsize=9, ha="right", va="bottom", linespacing=1.4)
    ax.text(XMAX + 0.4, med[XMAX - 1] + 1.9, f"What it is: ≈{med[XMAX-1]:.1f} bets\nwith {XMAX} funds", color=BLUE, fontsize=9,
            fontweight="bold", va="bottom", ha="left")
    ax.text(XMAX + 0.4, med[XMAX - 1] + 0.3, f"(≈{med[-1]:.1f} even with all {len(pool)})", color=INK2, fontsize=8, va="bottom", ha="left")
    ax.set_xlim(0, XMAX + 6); ax.set_ylim(0, 16); ax.set_xticks(range(0, XMAX + 1, 3))
    ax.set_xlabel("Number of equity funds held (drawn at random from the 41)"); ax.set_ylabel("Effective number of independent bets")
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)
    frame(fig, "Ten funds is not ten bets",
          "Median of 600 random equity portfolios at each size; shaded band = 10th to 90th percentile.",
          SRC + WINDOW_NOTE + ". Effective bets = exp(entropy) of the correlation-matrix eigenvalues.")
    save(fig, "3_funds_vs_bets.png")
    print("effN medians k=1,3,5,7,10,20,41:", [round(float(med[k - 1]), 2) for k in (1, 3, 5, 7, 10, 20, 41)])

    # ====================== 4. what adding a debt fund does ======================
    groups = [3, 5, 7, 10]
    A, B, D = [], [], []
    for k in groups:
        a, b, dd = [], [], []
        for _ in range(1500):
            sel = rng.choice(pool, size=k + 1, replace=False)
            a.append(effn(C[np.ix_(sel[:k], sel[:k])]))
            b.append(effn(C[np.ix_(sel, sel)]))
            s2 = list(sel[:k]) + [liquid_k]
            dd.append(effn(C[np.ix_(s2, s2)]))
        A.append(np.median(a)); B.append(np.median(b)); D.append(np.median(dd))
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.09, 0.17, 0.87, 0.58])
    xx = np.arange(len(groups)); bw = 0.26
    for off_, vals, col in ((-bw, A, GREYBAR), (0, B, BLUE), (bw, D, ORANGE)):
        ax.bar(xx + off_, vals, width=bw - 0.02, color=col, edgecolor="white", linewidth=1.5)
        for xi, v in zip(xx, vals):
            ax.text(xi + off_, v + 0.04, f"{v:.2f}", ha="center", fontsize=8.5, color=INK, fontweight="bold" if col == ORANGE else "normal")
    ax.set_xticks(xx); ax.set_xticklabels([f"{k} equity funds" for k in groups])
    ax.set_ylim(0, max(D) + 0.6); ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)
    ax.set_ylabel("Effective independent bets")
    # legend (top, one row)
    for i_, (col, lab) in enumerate(((GREYBAR, "Start"), (BLUE, "Add one more equity fund"), (ORANGE, "Add one liquid (debt) fund instead"))):
        xpos = [0.09, 0.19, 0.44][i_]
        fig.patches.append(plt.Rectangle((xpos, 0.782), 0.014, 0.022, transform=fig.transFigure, color=col))
        fig.text(xpos + 0.02, 0.793, lab, fontsize=8.5, color=INK2, va="center")
    frame(fig, "One debt fund beats one more equity fund",
          "Median effective bets over 1,500 random equity portfolios, before and after a single addition.",
          SRC + WINDOW_NOTE + ". Debt fund = HDFC Liquid Fund.")
    save(fig, "4_debt_fund_effect.png")
    print("debt effect:", dict(zip(groups, zip(np.round(A, 2), np.round(B, 2), np.round(D, 2)))))

    # ====================== 5. two-fund risk vs correlation ======================
    rho = np.linspace(-1, 1, 401)
    risk = np.sqrt((1 + rho) / 2) * 100
    med_rho = float(np.median(pair))
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.09, 0.17, 0.87, 0.62])
    ax.plot(rho, risk, color=BLUE, lw=2.4)
    for r_, lab, dx, dy, ha in ((1.0, "ρ = +1: no help", 0.0, 6, "right"), (0.0, "ρ = 0: risk falls ~29%", 0.06, -13, "left")):
        v = np.sqrt((1 + r_) / 2) * 100
        ax.plot([r_], [v], "o", color=BLUE, ms=6, mec="white", mew=1.5)
        ax.text(r_ + dx, v + dy, lab, fontsize=9, color=INK2, ha=ha)
    vm = np.sqrt((1 + med_rho) / 2) * 100
    ax.plot([med_rho], [vm], "o", color=ORANGE, ms=8, mec="white", mew=1.5, zorder=5)
    ax.annotate(f"Typical pair in your data: ρ = {med_rho:.2f}\nrisk falls only {100 - vm:.0f}%", xy=(med_rho, vm), xytext=(0.12, 40),
                fontsize=9.5, color=INK, fontweight="bold", va="top", linespacing=1.4,
                arrowprops=dict(arrowstyle="-", color=ORANGE, lw=1.2, shrinkA=6))
    ax.set_xlim(-1.05, 1.05); ax.set_ylim(0, 113); ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("Correlation between the two funds (ρ)"); ax.set_ylabel("Portfolio risk, % of a single fund's")
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)
    frame(fig, "Risk only falls when funds behave differently",
          "50/50 portfolio of two funds with equal volatility. Portfolio risk = √((1+ρ)/2) × single-fund risk.",
          f"Formula: standard portfolio variance. Orange marker = median pairwise correlation across all {len(pair)} fund pairs, " + "Nov 2024 – Aug 2026.")
    save(fig, "5_risk_vs_correlation.png")

    # ====================== 6. distribution of pairwise correlations ======================
    def pid(fid):
        return ids.index(fid)
    mv = C[pid(152881), pid(151739)]  # Momentum 50 vs Value 50
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.09, 0.17, 0.87, 0.62])
    bins = np.arange(np.floor(pair.min() * 20) / 20, 1.0001, 0.05)
    cnt, edges = np.histogram(pair, bins=bins)
    ax.bar(edges[:-1], cnt, width=0.05 - 0.004, align="edge", color=BLUE, edgecolor="white", linewidth=0.5)
    ax.axvline(med_rho, color=ORANGE, lw=1.6)
    ax.text(med_rho - 0.015, cnt.max() * 0.98, f"median {med_rho:.2f}", color=ORANGE, fontsize=9.5, fontweight="bold", ha="right", va="top")
    share_hi = (pair >= 0.6).mean() * 100
    ax.text(0.02, 0.96, f"{share_hi:.0f}% of the {len(pair)} pairs\nhave correlation ≥ 0.6", transform=ax.transAxes, fontsize=9.5, color=INK, va="top", ha="left")
    ax.annotate(f"Momentum vs Value index funds\n(different styles): {mv:.2f}", xy=(mv, 0.3), xytext=(mv - 0.42, cnt.max() * 0.55),
                fontsize=8.5, color=INK2, ha="center", arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.set_xlim(edges[0] - 0.02, 1.02)
    ax.set_xlabel("Correlation of monthly returns"); ax.set_ylabel("Number of fund pairs")
    ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)
    frame(fig, "Most fund pairs are close cousins",
          f"Distribution of correlation across all {len(pair)} pairs of the {n} funds.",
          SRC + WINDOW_NOTE + ".")
    save(fig, "6_pair_distribution.png")
    print(f"median {med_rho:.3f}, share>=0.6 {share_hi:.1f}%, Momentum vs Value {mv:.3f}")

    # ====================== 7. does the window matter? ======================
    rows = [(f"{e0 - s0 + 1} months\n(all {n} funds)", effn(C), share[0])]
    for minm in (36, 60, 84, 120):
        keep = [i for i in ids if valid_range(i)[1] - valid_range(i)[0] + 1 >= minm]
        s = max(valid_range(i)[0] for i in keep); e = min(valid_range(i)[1] for i in keep)
        Ck = np.corrcoef(returns(keep, s, e)); evk = np.sort(np.linalg.eigvalsh(Ck))[::-1]
        rows.append((f"{e - s + 1} months\n({len(keep)} funds)", effn(Ck), evk[0] / len(keep)))
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0.09, 0.17, 0.87, 0.60])
    xx = np.arange(len(rows))
    ax.bar(xx, [r[1] for r in rows], width=0.6, color=[ORANGE] + [BLUE] * (len(rows) - 1), edgecolor="white", linewidth=1.5)
    for xi, r in zip(xx, rows):
        ax.text(xi, r[1] + 0.06, f"{r[1]:.2f}", ha="center", fontsize=10, fontweight="bold", color=INK)
        ax.text(xi, r[1] / 2, f"{r[2]*100:.0f}%\non one\nfactor", ha="center", va="center", fontsize=8, color=(INK if xi == 0 else "white"))
    ax.set_xticks(xx); ax.set_xticklabels([r[0] for r in rows], fontsize=8.5)
    ax.set_ylim(0, 3.0); ax.set_yticks([0, 1, 2, 3]); ax.yaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(length=0)
    ax.set_ylabel("Effective independent bets"); ax.set_xlabel("Length of the shared history used (funds with shorter history dropped)")
    frame(fig, "Longer history: still only 2–2.6 bets",
          "Same calculation on longer windows. Orange = the window used in the tool; blue = robustness checks.",
          SRC + "Each column keeps only funds with at least that much history.")
    save(fig, "7_window_robustness.png")
    print("robustness:", [(r[0].replace(chr(10), ' '), round(r[1], 2), round(r[2] * 100, 1)) for r in rows])


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("factor", "all"):
        run_factor()
    if mode in ("nifty", "all"):
        print(); run_nifty()
    if mode in ("charts", "all"):
        print(); run_charts()