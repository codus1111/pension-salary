"""남은 질문: 실제 연봉 5천만 원 미만 회사는 왜 높게 추정될까?

가설 1: DART 평균 급여는 계약직·단시간 근로자까지 포함해 낮게 나오고,
        국민연금은 소득이 낮은 단시간 근로자 일부가 가입 대상에서 빠져 평균이 높게 잡힌다.
        → 회사별 계약직·단시간 비율과 추정 오차의 관계를 본다.
가설 2: 통계적 착시(평균으로의 회귀). '실제 값'으로 구간을 나누면, 추정이 치우치지 않아도
        실제 값이 우연히 낮게 나온 회사가 낮은 구간에 몰려 추정이 높아 보인다.
        → '추정값'으로 구간을 나눠 보면 이 현상이 사라지는지 본다.

결과: reports/low_salary_check.md
사용법 (WSL): ~/venvs/pension/bin/python src/low_salary_check.py 2025
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from dart_parse import num, pick_rows  # noqa: E402

RAW = Path("data/raw")
PROC = Path("data/processed")


def worker_mix(year):
    rows = []
    for line in (RAW / f"dart_emp_{year}.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        for r in rec["list"]:
            rows.append({"corp_code": rec["corp_code"], "fo_bbm": r.get("fo_bbm"),
                         "sm": num(r.get("sm")), "salary_total": num(r.get("fyer_salary_totamt")),
                         "contract": num(r.get("cnttk_co")),
                         "short": (num(r.get("rgllbr_abacpt_labrr_co")) or 0) + (num(r.get("cnttk_abacpt_labrr_co")) or 0)})
    df = pick_rows(pd.DataFrame(rows))  # 급여 계산과 같은 줄만 쓴다 (합계 줄 중복 방지)
    g = df.groupby("corp_code").agg(sm=("sm", "sum"), contract=("contract", "sum"), short=("short", "sum"))
    g["contract_share"] = g["contract"] / g["sm"]
    g["short_share"] = g["short"] / g["sm"]
    return g.reset_index()


def main(year):
    cmp = pd.read_parquet(PROC / f"compare_{year}.parquet")
    m = cmp.merge(worker_mix(year), on="corp_code", how="left")
    low = m[m["dart_avg_salary"] < 5e7]
    rest = m[m["dart_avg_salary"] >= 5e7]

    out = ["# 남은 질문: 저연봉 회사는 왜 높게 추정될까?\n",
           "| 구분 | 회사 수 | 평균 오차 | 계약직 비율(중간값) | 단시간 근로자 비율(평균) |", "|---|---|---|---|---|"]
    for name, g in [("실제 연봉 5천만 원 미만", low), ("5천만 원 이상", rest)]:
        out.append(f"| {name} | {len(g):,} | {g['err'].mean():+.1%} | {g['contract_share'].median():.1%} | "
                   f"{g['short_share'].mean():.2%} |")

    corr_c = low[["contract_share", "err"]].corr(method="spearman").iloc[0, 1]
    corr_s = low[["short_share", "err"]].corr(method="spearman").iloc[0, 1]
    out.append(f"\n저연봉 회사({len(low):,}곳) 안에서 오차와의 순위 상관: 계약직 비율 {corr_c:+.2f}, 단시간 비율 {corr_s:+.2f}\n")

    low = low.assign(band=pd.qcut(low["contract_share"].rank(method="first"), 3, labels=["낮음", "중간", "높음"]))
    out.append("| 계약직 비율 3분위 (저연봉 회사) | 회사 수 | 계약직 비율 범위 | 평균 오차 |")
    out.append("|---|---|---|---|")
    for b, g in low.groupby("band", observed=True):
        out.append(f"| {b} | {len(g):,} | {g['contract_share'].min():.0%}~{g['contract_share'].max():.0%} | "
                   f"{g['err'].mean():+.1%} |")

    out.append("\n## 가설 2: 구간을 무엇으로 나누느냐에 따라 달라지나\n")
    out.append("| 구간 | 실제 연봉으로 나눴을 때 평균 오차 | 추정 연봉으로 나눴을 때 평균 오차 |")
    out.append("|---|---|---|")
    bins, labels = [0, 5e7, 7e7, 1e12], ["5천만 원 미만", "5천~7천", "7천 이상"]
    by_actual = m.groupby(pd.cut(m["dart_avg_salary"], bins, labels=labels, right=False), observed=True)["err"].mean()
    by_est = m.groupby(pd.cut(m["nps_est_annual"], bins, labels=labels, right=False), observed=True)["err"].mean()
    for b in labels:
        out.append(f"| {b} | {by_actual.get(b, float('nan')):+.1%} | {by_est.get(b, float('nan')):+.1%} |")

    Path("reports/low_salary_check.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
