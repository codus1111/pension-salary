"""DART 직원 현황 원본에서 특정 회사의 줄을 그대로 보여준다.

사용법 (WSL): ~/venvs/pension/bin/python src/dart_inspect.py 삼성전자 현대자동차
"""
import json
import sys
from collections import Counter
from pathlib import Path

recs = [json.loads(line) for line in Path("data/raw/dart_emp_2025.jsonl").open(encoding="utf-8")]

fo, sex = Counter(), Counter()
for rec in recs:
    for r in rec["list"]:
        fo[(r.get("fo_bbm") or "").strip()] += 1
        sex[(r.get("sexdstn") or "").strip()] += 1
print("자주 나오는 사업부문 값:", fo.most_common(12))
print("성별 값:", sex.most_common(8))

for name in sys.argv[1:]:
    for rec in recs:
        if rec["corp_name"] == name:
            print(f"\n== {name}")
            for r in rec["list"]:
                print({k: (r.get(k) or "").strip() for k in
                       ("fo_bbm", "sexdstn", "rgllbr_co", "cnttk_co", "sm", "fyer_salary_totamt", "jan_salary_am")})
