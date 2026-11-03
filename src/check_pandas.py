"""pandas로 원본 CSV를 읽어 SQLite 적재 결과와 같은지 확인한다.

사용법 (WSL): ~/venvs/pension/bin/python src/check_pandas.py data/raw/nps_2026-09.csv
"""
import sqlite3
import sys
import time

import pandas as pd

RATE = 0.095


def main(csv_path):
    start = time.time()
    df = pd.read_csv(csv_path, encoding="cp949", dtype={"사업자등록번호": str, "사업장업종코드": str, "우편번호": str})
    print(f"pandas 읽기: {len(df):,}행 × {df.shape[1]}열, {time.time() - start:.1f}초")

    con = sqlite3.connect("data/processed/nps.db")
    sqlite_rows = con.execute("SELECT COUNT(*) FROM nps_raw").fetchone()[0]
    con.close()
    print(f"SQLite 행 수와 일치: {len(df) == sqlite_rows} ({sqlite_rows:,})")

    active = df[(df["사업장가입상태코드 1 등록 2 탈퇴"] == 1) & (df["가입자수"] >= 10)].copy()
    active["추정연봉_만원"] = active["당월고지금액"] / active["가입자수"] / RATE * 12 / 1e4
    print(f"\n가입자 10명 이상 등록 사업장: {len(active):,}곳")
    print(active["추정연봉_만원"].describe().round(0).to_string())

    top = active.nlargest(5, "가입자수")[["사업장명", "가입자수", "추정연봉_만원"]]
    print("\n가입자 수 상위 5곳:")
    print(top.round(0).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
