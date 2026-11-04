"""2025년 1~12월 국민연금 자료로 회사별 '1년 퇴사율'과 직원 수 추이를 만든다 (웹 배포용).

한 달치 퇴사율은 개편·계열사 이동 한 번에 크게 흔들려서(토스 2026-09: 한 달 13.7%), 12개월을 합쳐 본다.
- 1년 퇴사율 = 12개월 상실자 합 ÷ 12개월 평균 가입자 (국민연금 자격 상실 기준이라 계열사 이동도 들어간다)
- 1년 입사율도 같은 방식. 직원 수 변화 = 12월 가입자 - 1월 가입자
- 10개월 이상 자료가 있는 회사만 (중간에 생기거나 없어진 회사는 1년 값이 왜곡된다)
- 월별 직원 수(추이 그래프용)는 평균 가입자 30명 이상만 남겨 파일을 작게 한다
입력: data/processed/monthly_companies.parquet (src/monthly.py)
결과: data/app/turnover_2025.parquet, data/app/headcount_2025.parquet (+ data/processed에 같은 파일)
사용법 (WSL): ~/venvs/pension/bin/python src/make_turnover_data.py
"""
from pathlib import Path

import pandas as pd

PROC, OUT = Path("data/processed"), Path("data/app")


def main():
    m = pd.read_parquet(PROC / "monthly_companies.parquet", columns=["company_key", "ym", "members", "hires", "exits"])
    keys = pd.read_parquet(OUT / "serving.parquet", columns=["company_key"])["company_key"]
    m = m[m["company_key"].isin(keys)]
    g = m.groupby("company_key")
    t = pd.DataFrame({"months": g["ym"].nunique(), "avg_members": g["members"].mean(),
                      "hires_12m": g["hires"].sum(), "exits_12m": g["exits"].sum()})
    first, last = m[m["ym"] == m["ym"].min()], m[m["ym"] == m["ym"].max()]
    t["members_jan"] = first.set_index("company_key")["members"]
    t["members_dec"] = last.set_index("company_key")["members"]
    t = t[(t["months"] >= 10) & (t["avg_members"] >= 1)].copy()
    t["annual_exit_rate"] = (t["exits_12m"] / t["avg_members"]).astype("float32")
    t["annual_hire_rate"] = (t["hires_12m"] / t["avg_members"]).astype("float32")
    for c in ["avg_members"]:
        t[c] = t[c].astype("float32")
    for c in ["months", "hires_12m", "exits_12m", "members_jan", "members_dec"]:
        t[c] = t[c].fillna(-1).astype("int32")
    t = t.reset_index()

    big = t.loc[t["avg_members"] >= 30, "company_key"]
    hc = m[m["company_key"].isin(big)].pivot_table(index="company_key", columns="ym", values="members", aggfunc="sum")
    hc.columns = [c.replace("-", "_") for c in hc.columns]
    hc = hc.astype("float32").reset_index()

    for d in (OUT, PROC):
        t.to_parquet(d / "turnover_2025.parquet", index=False, compression="zstd")
        hc.to_parquet(d / "headcount_2025.parquet", index=False, compression="zstd")
    print(f"1년 퇴사율: {len(t):,}곳 ({(OUT / 'turnover_2025.parquet').stat().st_size / 1e6:.1f}MB), "
          f"월별 직원 수: {len(hc):,}곳 ({(OUT / 'headcount_2025.parquet').stat().st_size / 1e6:.1f}MB)")
    print(t[t["avg_members"] >= 30]["annual_exit_rate"].describe(percentiles=[.25, .5, .75, .9]).round(3).to_string())


if __name__ == "__main__":
    main()
