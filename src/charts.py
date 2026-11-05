"""포트폴리오용 결과 차트 3개를 reports/figures/에 PNG로 저장한다.

1. 추정 vs 실제 산점도: 천장(7,908만 원)에 막힌 회사가 한눈에 보이게
2. 실제 연봉 구간별 평균 절대 오차율: 보정 전(A) / 선형+업종(C) / 혼합(E)
3. 가장 많이 틀렸던 대기업 10곳: 실제 · 보정 전 · 보정 후

색은 데이터 시각화 가이드의 검증된 기본 팔레트 앞 3칸(파랑·주황·청록, 모든 쌍 구분 검증됨)을 쓴다.
한글은 Windows의 맑은 고딕을 WSL에서 불러온다.

사용법 (WSL): ~/venvs/pension/bin/python src/charts.py 2025
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

PROC = Path("data/processed")
FIG = Path("reports/figures")
CAP_ANNUAL_MANWON = 6_590_000 * 12 / 1e4

# 팔레트 (라이트 모드)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


# 한글 글꼴 후보: Windows · WSL · macOS · Linux(나눔고딕). 먼저 찾은 것을 쓴다
KOREAN_FONTS = [
    ("Malgun Gothic", ["C:/Windows/Fonts/malgun.ttf", "/mnt/c/Windows/Fonts/malgun.ttf"]),
    ("Apple SD Gothic Neo", ["/System/Library/Fonts/AppleSDGothicNeo.ttc"]),
    ("NanumGothic", ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]),
]


def setup_font():
    family = "sans-serif"
    for name, paths in KOREAN_FONTS:
        found = [p for p in paths if Path(p).exists()]
        if found:
            font_manager.fontManager.addfont(found[0])
            family = name
            break
    plt.rcParams.update({
        "font.family": family, "axes.unicode_minus": False,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "grid.linestyle": "-",
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
    })


def title(ax, main, sub):
    ax.set_title(main, loc="left", fontsize=15, color=INK, fontweight="bold", pad=28)
    ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=10.5, color=INK2, va="bottom")


def scatter(df):
    fig, ax = plt.subplots(figsize=(8.5, 7))
    near = df["cap_ratio"] >= 0.9
    x, y = df["dart_avg_salary"] / 1e4, df["nps_est_annual"] / 1e4
    ax.scatter(x[~near], y[~near], s=22, color=BLUE, alpha=0.55, edgecolor=SURFACE, linewidth=0.6,
               label=f"그 외 ({(~near).sum():,}곳)")
    ax.scatter(x[near], y[near], s=22, color=ORANGE, alpha=0.8, edgecolor=SURFACE, linewidth=0.6,
               label=f"천장 근처, cap_ratio ≥ 0.9 ({near.sum():,}곳)")
    lim = (2_000, 22_000)
    ax.plot(lim, lim, color=MUTED, linewidth=1.2)
    ax.text(8_700, 9_300, "추정 = 실제", color=MUTED, fontsize=10, rotation=48)
    ax.axhline(CAP_ANNUAL_MANWON, color=INK2, linewidth=1.2)
    ax.text(lim[1], CAP_ANNUAL_MANWON + 250, f"보험료 상한 천장 {CAP_ANNUAL_MANWON:,.0f}만 원",
            color=INK2, fontsize=10, ha="right", va="bottom")
    for name in ["메리츠증권", "SK하이닉스", "삼성전자"]:
        r = df[df["corp_name"] == name]
        if len(r):
            r = r.iloc[0]
            ax.annotate(name, (r.dart_avg_salary / 1e4, r.nps_est_annual / 1e4), xytext=(0, -16),
                        textcoords="offset points", ha="center", fontsize=9.5, color=INK)
    ax.set_xlim(lim)
    ax.set_ylim(lim[0], 12_000)
    ax.set_xlabel("DART 실제 1인 평균 급여 (만 원)")
    ax.set_ylabel("국민연금으로 추정한 연봉 (만 원)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    title(ax, "고연봉 회사일수록 추정이 천장에 막힌다",
          f"상장사 {len(df):,}곳. 천장 근처 회사는 실제 연봉과 상관없이 같은 높이에 모인다")
    fig.tight_layout()
    fig.savefig(FIG / "1_estimate_vs_actual.png", dpi=200)
    plt.close(fig)


def band_bars(oof):
    bins, labels = [0, 5e7, 7e7, 9e7, 1e12], ["5천만 원 미만", "5천~7천", "7천~9천", "9천만 원 이상"]
    band = pd.cut(oof["dart_avg_salary"], bins=bins, labels=labels, right=False)
    series = [("A 1차 추정", "보정 전", BLUE), ("C 선형 + 업종", "선형 + 업종 보정", ORANGE),
              ("E 혼합(천장 근처만 C)", "천장 근처만 보정", AQUA)]
    fig, ax = plt.subplots(figsize=(9, 5.6))
    w = 0.26
    xs = np.arange(len(labels))
    for i, (col, lab, color) in enumerate(series):
        ape = (oof[col] / oof["dart_avg_salary"] - 1).abs()
        vals = [ape[band == b].mean() * 100 for b in labels]
        bars = ax.bar(xs + (i - 1) * (w + 0.02), vals, width=w, color=color, label=lab, zorder=3)
        for b, v in zip(bars, vals):  # 막대가 짧아 값이 잘 안 읽히므로 막대 끝 위에만 작게 표시
            ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.0f}", ha="center", fontsize=8.5, color=INK2)
    counts = band.value_counts().reindex(labels)
    ax.set_xticks(xs, [f"{l}\n({n:,}곳)" for l, n in zip(labels, counts)])
    ax.set_ylabel("평균 절대 오차율 (%)")
    ax.set_ylim(0, 42)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", frameon=False, fontsize=10)
    title(ax, "보정은 고연봉 회사를 크게 고치지만, 저연봉 회사는 조금 망친다",
          "실제 연봉 구간별 평균 절대 오차율, 5겹 교차검증 (학습에 쓰지 않은 회사로 계산)")
    fig.tight_layout()
    fig.savefig(FIG / "2_error_by_salary_band.png", dpi=200)
    plt.close(fig)


def dumbbell(oof, cmp):
    big = cmp[cmp["dart_employees"] >= 1000][["corp_code", "ape"]]
    top = oof.merge(big, on="corp_code").sort_values("ape", ascending=False).head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ys = np.arange(len(top))
    for y, (_, r) in zip(ys, top.iterrows()):
        lo = min(r["A 1차 추정"], r["C 선형 + 업종"], r["dart_avg_salary"]) / 1e4
        hi = max(r["A 1차 추정"], r["C 선형 + 업종"], r["dart_avg_salary"]) / 1e4
        ax.plot([lo, hi], [y, y], color=GRID, linewidth=2, zorder=1)
    ax.scatter(top["A 1차 추정"] / 1e4, ys, s=70, color=BLUE, label="보정 전", zorder=3,
               edgecolor=SURFACE, linewidth=2)
    ax.scatter(top["C 선형 + 업종"] / 1e4, ys, s=70, color=ORANGE, label="선형 + 업종 보정", zorder=3,
               edgecolor=SURFACE, linewidth=2)
    ax.scatter(top["dart_avg_salary"] / 1e4, ys, s=80, color=INK, marker="D", label="DART 실제", zorder=4,
               edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(ys, top["corp_name"])
    ax.tick_params(axis="y", colors=INK, labelsize=10.5)
    ax.axvline(CAP_ANNUAL_MANWON, color=INK2, linewidth=1)
    ax.text(CAP_ANNUAL_MANWON, -0.75, " 천장", color=INK2, fontsize=9.5, va="center")
    ax.set_ylim(-1, len(top) - 0.5)
    ax.set_xlabel("연봉 (만 원)")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right", frameon=False, fontsize=10)
    title(ax, "가장 많이 틀렸던 대기업 10곳, 보정 후",
          "직원 1,000명 이상 중 보정 전 오차가 큰 순. 증권사는 실제에 가깝게 당겨지고, 반도체·통신은 아직 멀다")
    fig.tight_layout()
    fig.savefig(FIG / "3_top_misses.png", dpi=200)
    plt.close(fig)


def main(year):
    setup_font()
    FIG.mkdir(parents=True, exist_ok=True)
    cmp = pd.read_parquet(PROC / f"compare_{year}.parquet")
    oof = pd.read_parquet(PROC / f"model_oof_{year}.parquet")
    scatter(cmp)
    band_bars(oof)
    dumbbell(oof, cmp)
    print("저장:", *sorted(p.name for p in FIG.glob("*.png")))


if __name__ == "__main__":
    main(sys.argv[1])
