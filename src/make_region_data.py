"""회사 안의 지역별 사업장 표: 사업장이 여러 시·도에 있는 회사만, 시·도마다 한 줄.

웹의 지역 필터가 "회사 대표 지역"이 아니라 "그 지역 사업장"으로 거르게 하려고 만든다.
- 삼성전자·현대자동차처럼 전국 직원을 사업장 한 곳으로 신고한 회사는 나눌 수 없어서 여기 없다
- 지역별 추정 = 회사 보정 추정 × (그 지역 1차 추정 ÷ 회사 전체 1차 추정). 보정 모델은 회사 단위로만
  학습했으므로, 지역 사이의 차이는 보험료 비율 그대로 옮긴다. 범위도 같은 비율로 옮긴다
결과: data/app/region_sites.parquet (+ data/processed에 같은 파일)
사용법 (WSL): ~/venvs/pension/bin/python src/make_region_data.py
"""
import json
from pathlib import Path

import pandas as pd

from serving import SIDO

PROC, OUT = Path("data/processed"), Path("data/app")


def main():
    rate = json.loads((OUT / "serving_meta.json").read_text(encoding="utf-8"))["rate"]
    sites = pd.read_parquet(PROC / "sites.parquet",
                            columns=["company_key", "sido_cd", "jnngp_cnt", "ntc_amt", "nw_acqzr_cnt", "lss_jnngp_cnt",
                                     "is_daily"])
    sites = sites[~sites["is_daily"] & (sites["jnngp_cnt"] > 0)]  # 회사 집계와 같이 일용직 사업장은 뺀다
    sites["sido"] = sites["sido_cd"].map(SIDO)
    multi = sites.groupby("company_key")["sido"].transform("nunique") > 1
    reg = (sites[multi].groupby(["company_key", "sido"])
           .agg(members=("jnngp_cnt", "sum"), ntc_amt=("ntc_amt", "sum"),
                hires=("nw_acqzr_cnt", "sum"), exits=("lss_jnngp_cnt", "sum"), n_sites=("jnngp_cnt", "size"))
           .reset_index())
    comp = pd.read_parquet(OUT / "serving.parquet").set_index("company_key")
    reg = reg[reg["company_key"].isin(comp.index)]
    c = comp.loc[reg["company_key"]].reset_index()
    factor = (reg["ntc_amt"] / reg["members"] / rate * 12).values / c["est_annual"].values
    out = reg[["company_key", "sido", "members", "hires", "exits", "n_sites"]].copy()
    for col in ["sample_nm", "key_nm", "intp_nm"]:
        out[col] = c[col].values
    out["company_members"] = c["members"].values
    for col in ["est_corrected", "range_low", "range_high", "range50_low", "range50_high"]:
        out[col] = (c[col].values * factor).astype("float32")
    out["monthly_exit_rate"] = (out["exits"] / out["members"]).astype("float32")
    for d in (OUT, PROC):
        out.to_parquet(d / "region_sites.parquet", index=False, compression="zstd")
    size = (OUT / "region_sites.parquet").stat().st_size / 1e6
    print(f"저장: 회사 {out['company_key'].nunique():,}곳 × 지역 = {len(out):,}줄 ({size:.1f}MB)")
    print(out.nlargest(8, "members")[["sample_nm", "sido", "members", "company_members", "est_corrected"]].to_string())


if __name__ == "__main__":
    main()
