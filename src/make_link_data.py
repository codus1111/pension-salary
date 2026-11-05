"""상장사 공식 홈페이지 주소 표: company_key → 홈페이지 (웹 화면의 '공식 홈페이지' 버튼용).

입력: data/raw/dart_homepage.jsonl (src/dart.py homepage), data/processed/matched_2025.parquet (DART ↔ 국민연금 매칭)
결과: data/app/homepage.parquet (+ data/processed에 같은 파일)
사용법 (WSL): ~/venvs/pension/bin/python src/make_link_data.py
"""
import json
from pathlib import Path

import pandas as pd

RAW, PROC, OUT = Path("data/raw"), Path("data/processed"), Path("data/app")


def clean_url(u):
    """'www.samsung.com' 처럼 http가 빠진 주소도 열리게, 빈 값·이상한 값은 버린다."""
    u = (u or "").strip()
    if not u or "." not in u or " " in u:
        return None
    return u if u.lower().startswith(("http://", "https://")) else "https://" + u


def main():
    hp = pd.DataFrame([json.loads(line) for line in (RAW / "dart_homepage.jsonl").open(encoding="utf-8")])
    hp["hm_url"] = hp["hm_url"].map(clean_url)
    m = pd.read_parquet(PROC / "matched_2025.parquet", columns=["corp_code", "nps_key"]).dropna()
    out = (m.merge(hp.dropna(), on="corp_code")[["nps_key", "hm_url"]]
           .drop_duplicates("nps_key").rename(columns={"nps_key": "company_key"}))
    for d in (OUT, PROC):
        out.to_parquet(d / "homepage.parquet", index=False, compression="zstd")
    print(f"홈페이지 주소: {len(out):,}곳 (DART {len(hp):,}곳 중 주소가 있는 곳 {hp['hm_url'].notna().sum():,})")
    print(out.head().to_string())


if __name__ == "__main__":
    main()
