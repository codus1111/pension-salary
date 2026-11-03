"""국민연금 추정 연봉과 DART 실제 1인 평균 급여를 비교한다 (1차 추정의 오차 분석).

- 직원 수가 0.5~2배 안에 드는 매칭만 쓴다 (잘못 매칭됐을 가능성이 낮은 회사)
- 오차 = 추정 ÷ 실제 - 1 (음수면 낮게 추정)
- 구간별 평균 절대 오차율(MAPE)에 부트스트랩 95% 신뢰구간을 붙인다

결과: reports/compare.md
사용법 (WSL): ~/venvs/pension/bin/python src/compare.py 2025
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROC = Path("data/processed")
CAP_ANNUAL = 6_590_000 * 12
RNG = np.random.default_rng(42)


def boot_ci(values, n=2000):
    """평균의 부트스트랩 95% 신뢰구간."""
    v = np.asarray(values)
    if len(v) < 5:
        return np.nan, np.nan
    means = RNG.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    return np.percentile(means, 2.5), np.percentile(means, 97.5)


def band_table(df, col, bins, labels, title):
    df = df.assign(band=pd.cut(df[col], bins=bins, labels=labels, right=False))
    out = [f"## {title}\n", "| 구간 | 회사 수 | 평균 오차 | 평균 절대 오차율 (95% CI) | 중간값 절대 오차율 |",
           "|---|---|---|---|---|"]
    for b, g in df.groupby("band", observed=True):
        lo, hi = boot_ci(g["ape"])
        out.append(f"| {b} | {len(g):,} | {g['err'].mean():+.1%} | {g['ape'].mean():.1%} ({lo:.1%}~{hi:.1%}) | "
                   f"{g['ape'].median():.1%} |")
    return out


def main(year):
    m = pd.read_parquet(PROC / f"matched_{year}.parquet")
    total = len(m)
    m = m[m["method"].notna() & m["size_ok"]].copy()
    m["err"] = m["nps_est_annual"] / m["dart_avg_salary"] - 1
    m["ape"] = m["err"].abs()
    m.to_parquet(PROC / f"compare_{year}.parquet", index=False)

    lo, hi = boot_ci(m["ape"])
    corr = m[["nps_est_annual", "dart_avg_salary"]].corr(method="spearman").iloc[0, 1]
    under = (m["err"] < 0).mean()
    out = [
        "# 1차 추정 vs DART 실제 급여\n",
        f"- 비교 대상: DART 회사 {total:,}곳 중 매칭되고 직원 수가 맞는 **{len(m):,}곳**",
        f"- 평균 절대 오차율 **{m['ape'].mean():.1%}** (95% CI {lo:.1%}~{hi:.1%}), 중간값 {m['ape'].median():.1%}",
        f"- 평균 오차 {m['err'].mean():+.1%} — **{under:.0%}의 회사에서 실제보다 낮게 추정**",
        f"- 순위 상관(스피어만) {corr:.2f} — 금액은 틀려도 '어느 회사가 더 많이 주나'의 순서는 어느 정도 맞는지\n",
    ]
    out += band_table(m, "cap_ratio", [0, 0.6, 0.8, 0.9, 1.01], ["0.6 미만", "0.6~0.8", "0.8~0.9", "0.9 이상"],
                      "상한 근접도(cap_ratio)별 오차")
    out.append("")
    out += band_table(m, "dart_avg_salary", [0, 5e7, 7e7, 9e7, 1e12],
                      ["5천만 원 미만", "5천~7천", "7천~9천", "9천만 원 이상"], "실제 연봉 수준별 오차")
    out.append("")
    out += band_table(m, "dart_employees", [0, 100, 300, 1000, 1e9],
                      ["100명 미만", "100~299명", "300~999명", "1000명 이상"], "회사 규모별 오차")

    above = m[m["dart_avg_salary"] > CAP_ANNUAL]
    out.append(f"\n## 상한 천장 효과\n")
    out.append(f"- 실제 평균 급여가 천장({CAP_ANNUAL / 1e4:,.0f}만 원)을 넘는 회사: **{len(above):,}곳** ({len(above) / len(m):.0%})")
    out.append(f"- 이 회사들의 평균 오차 {above['err'].mean():+.1%}, 나머지 회사 {m.drop(above.index)['err'].mean():+.1%}")

    out.append("\n## 가장 많이 틀린 회사 10곳 (직원 300명 이상)\n")
    out.append("| 회사 | 업종 | 직원 | 추정(만 원) | 실제(만 원) | 오차 | cap_ratio |")
    out.append("|---|---|---|---|---|---|---|")
    big = m[m["dart_employees"] >= 300]
    for r in big.reindex(big["ape"].sort_values(ascending=False).index).head(10).itertuples():
        out.append(f"| {r.corp_name} | {r.intp_nm} | {r.dart_employees:,.0f} | {r.nps_est_annual / 1e4:,.0f} | "
                   f"{r.dart_avg_salary / 1e4:,.0f} | {r.err:+.0%} | {r.cap_ratio:.2f} |")

    Path("reports/compare.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
