"""웹 배포용 조회 데이터를 작게 만든다 (GitHub에 올릴 수 있게, 파일 하나 100MB 제한).

serving.parquet에서 도구가 쓰는 열만 남기고, 숫자는 float32로, zstd로 압축한다.
결과: data/app/serving.parquet, data/app/serving_meta.json  (이 폴더만 저장소에 올린다)
사용법 (WSL): ~/venvs/pension/bin/python src/make_app_data.py
"""
import shutil
from pathlib import Path

import pandas as pd

SRC = Path("data/processed")
OUT = Path("data/app")
KEEP = ["company_key", "key_nm", "sample_nm", "intp_nm", "sido", "members", "n_sites", "hires", "exits",
        "monthly_exit_rate", "est_annual", "cap_ratio", "cap_band", "interval_key", "est_corrected",
        "range_low", "range_high", "range50_low", "range50_high", "industry_pct", "industry_n",
        "dart_avg_salary", "tenure_years"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(SRC / "serving.parquet", columns=KEEP)
    for c in df.select_dtypes("float64").columns:
        df[c] = df[c].astype("float32")
    for c in ["intp_nm", "sido", "cap_band", "interval_key"]:
        df[c] = df[c].astype("category")
    df.to_parquet(OUT / "serving.parquet", index=False, compression="zstd")
    shutil.copy(SRC / "serving_meta.json", OUT / "serving_meta.json")
    size = (OUT / "serving.parquet").stat().st_size / 1e6
    print(f"저장: {OUT / 'serving.parquet'} ({len(df):,}행, {size:.1f}MB)")


if __name__ == "__main__":
    main()
