"""매칭이 이상한 회사를 국민연금 쪽에서 이름으로 찾아본다.

사용법 (WSL): ~/venvs/pension/bin/python src/match_debug.py 기아 대신정보통신 한화생명
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from match import key_name  # noqa: E402

comp = pd.DataFrame([json.loads(l) for l in Path("data/raw/dart_company.jsonl").open(encoding="utf-8")])
nps = pd.read_parquet("data/processed/companies.parquet")

for q in sys.argv[1:]:
    d = comp[comp["corp_name"] == q]
    if len(d):
        r = d.iloc[0]
        print(f"\n== {q}  DART 사업자번호 {r.bizr_no}  주소 {r.adres}  비교용 이름 {key_name(q)}")
    hits = nps[nps["base_nm"].str.contains(key_name(q), regex=False)].nlargest(8, "members")
    print(hits[["base_nm", "bzowr_no6", "n_sites", "members", "intp_nm"]].to_string(index=False))
