"""가설: 국민연금 기준소득월액은 매년 7월에 '전년도 소득'으로 다시 정해진다.
   그러면 DART 2025 연봉과 같은 해 소득을 쓰는 건 2026년 7월 이후 자료다.

확인: 같은 회사들로, 어느 기간 자료가 DART 2025와 가장 잘 맞는지 본다.
  - 2025년 1~6월 (2023년 소득 기준)
  - 2025년 7~12월 (2024년 소득 기준)
  - 2026년 9월 (2025년 소득 기준)
결과: reports/lag_check.md
사용법 (WSL): ~/venvs/pension/bin/python src/lag_check.py
"""
from pathlib import Path

import pandas as pd

PROC = Path("data/processed")


def main():
    a = pd.read_parquet(PROC / "annual_2025.parquet")
    a = a[a["months"] >= 10]
    monthly = pd.read_parquet(PROC / "monthly_companies.parquet")
    comp = pd.read_parquet(PROC / "companies.parquet", columns=["company_key", "base_nm", "intp_nm"])

    by_name = {k: g for k, g in comp.groupby("base_nm")}
    key_to_corp = {}
    for r in a.itertuples():
        same = by_name.get(r.nps_key.split("|")[0])
        keys = {r.nps_key} | (set(same.loc[same["intp_nm"] == r.intp_nm, "company_key"]) if same is not None else set())
        for k in keys:
            key_to_corp.setdefault(k, r.corp_code)
    m = monthly[monthly["company_key"].isin(key_to_corp)].copy()
    m["corp_code"] = m["company_key"].map(key_to_corp)
    m["half"] = m["ym"].str[5:].astype(int).map(lambda x: "H1" if x <= 6 else "H2")
    g = m.groupby(["corp_code", "ym", "half"], as_index=False).agg(members=("members", "sum"), ntc=("ntc_amt", "sum"),
                                                                    rate=("rate", "first"))
    g["income"] = g["ntc"] / g["members"] / g["rate"]
    h = g.groupby(["corp_code", "half"])["income"].mean().unstack() * 12
    d = a.set_index("corp_code").join(h, how="inner")

    out = ["# 국민연금 소득은 몇 년 전 소득일까\n",
           "| 자료 기간 | 기준이 되는 소득 연도 | DART 2025와 평균 절대 오차율 | 평균 오차 |", "|---|---|---|---|"]
    for name, col, year in [("2025년 1~6월", "H1", "2023년"), ("2025년 7~12월", "H2", "2024년"),
                            ("2026년 9월", "nps_est_annual", "2025년")]:
        err = d[col] / d["dart_avg_salary"] - 1
        out.append(f"| {name} | {year} | {err.abs().mean():.1%} | {err.mean():+.1%} |")
    grow = (d["H2"] / d["H1"] - 1).median()
    out.append(f"\n같은 회사의 추정 연봉이 1~6월 → 7~12월 사이에 중간값 **{grow:+.1%}** 바뀌었다 "
               f"(7월에 기준 소득이 다시 정해질 때 한 번에 오르는지 확인용). 비교 회사 {len(d):,}곳.")
    Path("reports/lag_check.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
