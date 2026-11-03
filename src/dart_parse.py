"""DART 직원 현황 원본(jsonl)을 회사별 1인 평균 급여 표로 정리한다.

사업보고서의 직원 현황은 사업부문 × 성별로 여러 줄이라, 회사 단위로 합친다.
- 직원 수        = 줄별 합계(sm)의 합
- 1인 평균 급여  = 연간 급여 총액의 합 ÷ 직원 수
  (회사마다 금액 단위가 다를 수 있어, 줄에 적힌 1인 평균 급여와 비교해 단위를 맞춘다)

사용법 (WSL): ~/venvs/pension/bin/python src/dart_parse.py 2025
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")


def num(v):
    if v is None:
        return np.nan
    s = str(v).replace(",", "").strip()
    if s in ("", "-"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse(year):
    rows = []
    status = {}
    for line in (RAW / f"dart_emp_{year}.jsonl").open(encoding="utf-8"):
        rec = json.loads(line)
        status[rec["corp_code"]] = rec["status"]
        for r in rec["list"]:
            rows.append({
                "corp_code": rec["corp_code"], "corp_name": rec["corp_name"],
                "fo_bbm": r.get("fo_bbm"), "sexdstn": r.get("sexdstn"),
                "sm": num(r.get("sm")), "salary_total": num(r.get("fyer_salary_totamt")),
                "salary_avg_row": num(r.get("jan_salary_am")), "tenure": num(r.get("avrg_cnwk_sdytrn")),
            })
    df = pd.DataFrame(rows)
    return df, pd.Series(status, name="status")


# 삼성전자처럼 사업부문별 줄과 "성별합계" 줄을 함께 적는 회사가 있다. 다 더하면 직원 수가 2배가 된다.
TOTAL_RE = r"합계|총계|소계|^계$|^전체$|^전사$"


def pick_rows(df):
    """회사마다 중복 없이 더할 줄만 고른다.

    - 급여 총액이 있는 줄만 쓴다 (사업부문별 줄에는 인원만 있고 급여는 합계 줄에만 있는 경우가 있다)
    - 합계 줄과 일반 줄이 함께 있으면 합계 줄만 쓴다
    """
    df = df[df["salary_total"].notna() & df["sm"].notna()].copy()
    df["is_total"] = df["fo_bbm"].fillna("").str.strip().str.contains(TOTAL_RE)
    has_both = df.groupby("corp_code")["is_total"].transform(lambda s: s.any() and not s.all())
    return df[~has_both | df["is_total"]]


def summarize(df):
    df = pick_rows(df)
    # 줄마다 적힌 1인 평균 급여를 인원으로 가중 평균한 값: 총액 ÷ 인원 계산이 맞는지 대조용
    df = df.assign(w_avg=df["salary_avg_row"] * df["sm"])
    g = df.groupby(["corp_code", "corp_name"])
    out = g.agg(employees=("sm", "sum"), salary_total=("salary_total", "sum"),
                w_avg=("w_avg", "sum"), rows_used=("sm", "size")).reset_index()
    out["row_avg_weighted"] = out["w_avg"] / out["employees"]
    out = out.drop(columns="w_avg")
    tenure = df.dropna(subset=["tenure", "sm"]).assign(w=lambda d: d["tenure"] * d["sm"])
    t = tenure.groupby("corp_code").agg(w=("w", "sum"), n=("sm", "sum"))
    out = out.merge((t["w"] / t["n"]).rename("tenure_years"), on="corp_code", how="left")

    raw_avg = out["salary_total"] / out["employees"]
    # 단위 추정: 원 단위면 1인 평균이 수천만~억 원대. 백만 원·천 원 단위로 적힌 회사를 원 단위로 맞춘다.
    unit = pd.Series(1.0, index=out.index)
    unit[raw_avg.between(10, 1_000)] = 1e6      # 백만 원 단위로 보임
    unit[raw_avg.between(10_000, 1_000_000)] = 1e3  # 천 원 단위로 보임
    out["salary_unit_guess"] = unit
    out["dart_avg_salary"] = raw_avg * unit
    # 대조: 총액÷인원과 줄별 평균의 가중평균(같은 단위로 맞춘 값)이 20% 넘게 다르면 의심
    row_avg = out["row_avg_weighted"] * unit
    out["consistency"] = out["dart_avg_salary"] / row_avg
    out["dart_avg_salary_ok"] = (out["dart_avg_salary"].between(15_000_000, 300_000_000)
                                 & (row_avg.isna() | out["consistency"].between(0.8, 1.25)))
    return out


def main(year):
    df, status = parse(year)
    out = summarize(df)
    out.to_parquet(OUT / f"dart_salary_{year}.parquet", index=False)

    print(f"응답 받은 회사 {len(status):,}곳: " + ", ".join(f"{k} {v:,}" for k, v in status.value_counts().items()))
    print(f"급여 총액이 있는 회사 {len(out):,}곳, 그중 검증을 통과한 회사 {out['dart_avg_salary_ok'].sum():,}곳")
    bad = out[~out["dart_avg_salary_ok"]]
    print(f"  제외: 범위 밖 {(~out['dart_avg_salary'].between(15_000_000, 300_000_000)).sum():,}곳, "
          f"줄별 평균과 20% 넘게 불일치 {(~out['consistency'].between(0.8, 1.25) & out['consistency'].notna()).sum():,}곳")
    print("단위 추정:", out["salary_unit_guess"].value_counts().to_dict())
    ok = out[out["dart_avg_salary_ok"]]
    print(f"1인 평균 급여 중간값 {ok['dart_avg_salary'].median() / 1e4:,.0f}만 원")
    print(ok.nlargest(5, "employees")[["corp_name", "employees", "dart_avg_salary", "tenure_years"]]
          .assign(dart_avg_salary=lambda d: (d["dart_avg_salary"] / 1e4).round()).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
