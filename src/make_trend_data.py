"""연봉 상승 추이: 해마다 가을(9월) 국민연금 자료로 회사별 1차 추정 연봉과 직원 수를 만든다 (웹 배포용).

왜 9월끼리: 기준소득월액은 매년 7월에 '전년도 소득'으로 다시 정해진다. 그래서 2026-09 자료 = 2025년 소득,
2020-09 자료 = 2019년 소득이다. 같은 달끼리 비교해야 해마다 기준이 같다 (src/lag_check.py에서 확인한 내용).
2021년은 9월분 파일이 없어 10월분을 쓴다 (같은 7월~다음 6월 구간이라 소득 연도가 같다).

- 1차 추정 = 고지금액 ÷ 가입자 ÷ 보험료율 × 12. 해마다 그해의 보험료율·상한을 쓴다
- 보정 모델은 2025년 소득으로만 검증했으므로 추이는 1차 추정으로 본다. 상한에 가까운 고연봉 회사는
  해마다 오르는 상한(503만 → 659만 원)만큼 같이 오르는 것처럼 보일 수 있어서, 그해 평균 소득이 상한의 몇 %인지도 남긴다
- 최근 자료에 직원 10명 이상이고 3개 연도 이상 있는 회사만 남긴다
입력: data/raw/monthly/nps_2020-09.csv … nps_2026-09.csv (src/download_years.sh, src/download_months.sh)
결과: data/app/trend.parquet (+ data/processed)
사용법 (WSL): ~/venvs/pension/bin/python src/make_trend_data.py
"""
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from companies import DAILY_RE, normalize  # noqa: E402
from monthly import read_month  # noqa: E402

RAW, PROC, OUT = Path("data/raw/monthly"), Path("data/processed"), Path("data/app")
# 자료 달 → (소득 연도, 보험료율, 그달의 기준소득월액 상한)
FILES = {
    "2020-09": (2019, 0.09, 5_030_000),
    "2021-10": (2020, 0.09, 5_240_000),
    "2022-09": (2021, 0.09, 5_530_000),
    "2023-09": (2022, 0.09, 5_900_000),
    "2024-09": (2023, 0.09, 6_170_000),
    "2025-09": (2024, 0.09, 6_370_000),
    "2026-09": (2025, 0.095, 6_590_000),
}


def company_year(ym, cache):
    df = read_month(RAW / f"nps_{ym}.csv")
    names = df["wkpl_nm"].fillna("")
    new = [n for n in names.unique() if n not in cache]
    cache.update({n: normalize(n)[0] for n in new})
    df["base_nm"] = names.map(cache)
    df = df[~names.str.contains(DAILY_RE)]
    df["company_key"] = df["base_nm"] + "|" + df["bzowr_no6"].astype(str)
    g = df.groupby("company_key")[["members", "ntc_amt"]].sum()
    year, rate, cap = FILES[ym]
    g["est"] = g["ntc_amt"] / g["members"] / rate * 12
    g["cap_ratio"] = g["ntc_amt"] / g["members"] / rate / cap
    return year, g


def main():
    cache, est, mem, capr = {}, {}, {}, {}
    for ym in FILES:
        path = RAW / f"nps_{ym}.csv"
        if not path.exists():
            print(f"없음: {path} (src/download_years.sh로 받는다)")
            continue
        t0 = time.time()
        year, g = company_year(ym, cache)
        est[year], mem[year], capr[year] = g["est"], g["members"], g["cap_ratio"]
        print(f"  {ym} → {year}년 소득: 회사 {len(g):,}곳 ({time.time() - t0:.0f}초)", flush=True)
    years = sorted(est)
    e, m, c = pd.DataFrame(est)[years], pd.DataFrame(mem)[years], pd.DataFrame(capr)[years]
    keep = (m[years[-1]] >= 10) & (e.notna().sum(axis=1) >= 3)
    out = pd.concat([(e[keep] / 1e4).round().add_prefix("est_"), m[keep].add_prefix("members_"),
                     c[keep].round(3).add_prefix("cap_")], axis=1)
    for col in out.columns:
        out[col] = out[col].astype("float32")
    out = out.reset_index().rename(columns={"index": "company_key"})
    for d in (OUT, PROC):
        out.to_parquet(d / "trend.parquet", index=False, compression="zstd")
    size = (OUT / "trend.parquet").stat().st_size / 1e6
    print(f"저장: 회사 {len(out):,}곳 × {len(years)}개 연도({years[0]}~{years[-1]}년 소득), {size:.1f}MB")


if __name__ == "__main__":
    main()
