"""2025년 1~12월 국민연금 파일을 회사 단위로 합쳐 '1년 평균' 추정을 만든다.

왜: 지금까지는 2026-09 한 달 자료로 추정해 (1) 달마다 흔들리고 (2) 정답인 DART 2025 연간 급여와
    시기가 달랐다. 2025년 12개월을 쓰면 둘 다 풀린다.

- 사업장 → 회사: companies.py와 같은 이름 정규화(normalize), 일용직 현장 제외
- 달마다 그 달의 보험료율·상한을 쓴다 (2025: 9%, 상한 1~6월 617만 원, 7~12월 637만 원)
- 결과: data/processed/monthly_companies.parquet  (회사 × 월: 가입자, 고지금액, 신규, 상실, 상한)

사용법 (WSL): ~/venvs/pension/bin/python src/monthly.py                 # 2025년 1~12월
             ~/venvs/pension/bin/python src/monthly.py 2026          # 2026년 파일 (7~9월)

주의: 기준소득월액은 매년 7월에 '전년도 소득'으로 다시 정해진다 (src/lag_check.py로 확인).
      그래서 DART 2025 연봉과 같은 해 소득은 2026년 7월 이후 자료다.
"""
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from companies import DAILY_RE, normalize  # noqa: E402

RAW = Path("data/raw/monthly")
# 연도별 보험료율과 기준소득월액 상한 (상한은 7월에 바뀐다)
RATE = {2025: 0.09, 2026: 0.095}
CAP = {2025: (6_170_000, 6_370_000), 2026: (6_370_000, 6_590_000)}


def rate_cap(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return RATE[y], CAP[y][0] if m <= 6 else CAP[y][1]
COLS = {0: "data_ym", 1: "wkpl_nm", 2: "bzowr_no6", 3: "join_stcd", 18: "members", 19: "ntc_amt", 20: "hires", 21: "exits"}


def read_month(path):
    for enc in ("cp949", "utf-8-sig"):
        try:
            df = pd.read_csv(path, encoding=enc, header=0, usecols=list(COLS), dtype={1: str, 2: str})
            break
        except UnicodeDecodeError:
            continue
    df.columns = [COLS[i] for i in sorted(COLS)]
    df = df[(df["join_stcd"] == 1) & (df["members"] > 0) & (df["ntc_amt"] > 0)]
    return df


def main(year="2025"):
    files = sorted(RAW.glob(f"nps_{year}-*.csv"))
    out_path = Path("data/processed/monthly_companies.parquet" if year == "2025"
                    else f"data/processed/monthly_companies_{year}.parquet")
    print(f"월별 파일 {len(files)}개", flush=True)
    cache = {}
    parts = []
    for f in files:
        t0 = time.time()
        ym = re.search(r"(\d{4}-\d{2})", f.name).group(1)
        df = read_month(f)
        actual = str(df["data_ym"].iloc[0])
        if actual != ym:  # 파일 이름의 달과 안에 든 자료의 달이 다르면 멈춘다
            sys.exit(f"{f.name}: 파일 안의 자료생성년월은 {actual}")
        names = df["wkpl_nm"].fillna("")
        new = [n for n in names.unique() if n not in cache]
        cache.update({n: normalize(n)[0] for n in new})
        df["base_nm"] = names.map(cache)
        df = df[~names.str.contains(DAILY_RE)]
        df["company_key"] = df["base_nm"] + "|" + df["bzowr_no6"].astype(str)
        g = df.groupby("company_key", as_index=False)[["members", "ntc_amt", "hires", "exits"]].sum()
        g["ym"] = ym
        g["rate"], g["cap"] = rate_cap(ym)
        parts.append(g)
        print(f"  {ym}: 사업장 {len(df):,}곳 → 회사 {len(g):,}곳 ({time.time() - t0:.0f}초)", flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(out_path, index=False)
    print(f"저장: {out_path} ({len(out):,}행)")


if __name__ == "__main__":
    main(*sys.argv[1:])
