"""회사 합치기 결과를 잘 알려진 이름 몇 개로 눈으로 확인한다.

사용법 (WSL): ~/venvs/pension/bin/python src/spot_check.py 삼성전자 한국전력공사 율촌
"""
import sys

import pandas as pd

sites = pd.read_parquet("data/processed/sites.parquet")
print("이름이 비어 있는 사업장:", (sites["base_nm"] == "").sum())
for q in sys.argv[1:]:
    m = sites[sites["base_nm"] == q]
    print(f"{q}: 사업장 {len(m)}곳, 일용 {int(m['is_daily'].sum())}곳, "
          f"사업자번호 6자리 {m['bzowr_no6'].nunique()}종, 가입자 {m['jnngp_cnt'].sum():,}명")
