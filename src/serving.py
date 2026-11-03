"""MCP 서버가 조회할 회사별 추정 데이터를 만든다 (모든 국민연금 회사 대상).

- 보정 규칙은 E(혼합): cap_ratio 0.8 이상이면 C(선형 + 업종) 모델, 아니면 1차 추정 그대로.
  학습 데이터(상장사)보다 실제 조회 대상(비상장·중소기업)이 저연봉 쪽에 많아서 E를 쓴다.
- C 모델은 검증에 쓴 상장사 2,392곳 전체로 다시 학습한다.
- 오차 범위: 교차검증 예측(E)의 오차를 cap_ratio 구간별로 모아 10~90% 구간을 쓴다.
  "비슷한 회사 10곳 중 8곳은 실제 연봉이 이 범위 안에 있었다"는 뜻.

결과: data/processed/serving.parquet, data/processed/serving_meta.json
사용법 (WSL): ~/venvs/pension/bin/python src/serving.py 2025
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from match import to_hangul  # noqa: E402
from model import load, models  # noqa: E402

PROC = Path("data/processed")
RATE = 0.095
CAP = 6_590_000
NEAR_CAP = 0.8
CAP_BANDS = [0, 0.6, 0.8, 0.9, 1.01]
CAP_LABELS = ["0.6 미만", "0.6~0.8", "0.8~0.9", "0.9 이상"]
SIDO = {"11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전", "31": "울산",
        "36": "세종", "41": "경기", "42": "강원", "51": "강원", "43": "충북", "44": "충남", "45": "전북",
        "52": "전북", "46": "전남", "47": "경북", "48": "경남", "50": "제주"}


def features(df, code):
    df = df.copy()
    df["ind2"] = df["intp_nm"].map(code).fillna("00").str[:2]
    df["log_est"] = np.log(df["est_annual"])
    df["log_members"] = np.log(df["members"])
    df["cap_over80"] = (df["cap_ratio"] - 0.8).clip(lower=0)
    df["cap_over90"] = (df["cap_ratio"] - 0.9).clip(lower=0)
    return df


def main(year):
    train = load(year)
    cols, model_c = models()["C 선형 + 업종"]
    model_c.fit(train[cols], train["log_y"])

    # 오차 범위: 교차검증 예측으로 구간별 분위수
    oof = pd.read_parquet(PROC / f"model_oof_{year}.parquet")
    err = oof["E 혼합(천장 근처만 C)"] / oof["dart_avg_salary"] - 1
    band = pd.cut(oof["cap_ratio"], CAP_BANDS, labels=CAP_LABELS, right=False)
    intervals = {b: {"q10": float(err[band == b].quantile(0.1)), "q90": float(err[band == b].quantile(0.9)),
                     "mape": float(err[band == b].abs().mean()), "n": int((band == b).sum())}
                 for b in CAP_LABELS}

    sites = pd.read_parquet(PROC / "sites.parquet", columns=["company_key", "intp_nm", "intp_cd", "sido_cd"])
    code = sites.dropna(subset=["intp_cd"]).groupby("intp_nm")["intp_cd"].agg(lambda s: s.mode().iloc[0])
    sido = sites.groupby("company_key")["sido_cd"].agg(lambda s: s.mode().iloc[0] if len(s.mode()) else None)

    comp = pd.read_parquet(PROC / "companies.parquet")
    comp = comp[(comp["members"] > 0) & (comp["ntc_amt"] > 0)]
    comp = features(comp, code)
    comp["sido"] = comp["company_key"].map(sido).map(SIDO)
    comp["key_nm"] = comp["base_nm"].map(lambda s: "".join(ch for ch in to_hangul(s) if ch.isalnum()))

    pred_c = np.exp(model_c.predict(comp[cols]))
    comp["est_corrected"] = np.where(comp["cap_ratio"] >= NEAR_CAP, pred_c, comp["est_annual"])
    comp["cap_band"] = pd.cut(comp["cap_ratio"], CAP_BANDS, labels=CAP_LABELS, right=False).astype(str)
    comp["range_low"] = [p / (1 + intervals[b]["q90"]) if b in intervals else np.nan
                         for p, b in zip(comp["est_corrected"], comp["cap_band"])]
    comp["range_high"] = [p / (1 + intervals[b]["q10"]) if b in intervals else np.nan
                          for p, b in zip(comp["est_corrected"], comp["cap_band"])]

    # 같은 업종(가입자 10명 이상) 안에서 몇 % 위치인지
    big = comp["members"] >= 10
    comp["industry_pct"] = np.nan
    comp.loc[big, "industry_pct"] = comp[big].groupby("intp_nm")["est_corrected"].rank(pct=True)
    comp["industry_n"] = comp["intp_nm"].map(comp[big]["intp_nm"].value_counts())

    # 상장사는 DART 실제 값도 붙인다 (직원 수가 맞는 믿을 만한 매칭만)
    matched = pd.read_parquet(PROC / f"matched_{year}.parquet")
    matched = matched[matched["size_ok"]][["nps_key", "corp_name", "dart_avg_salary", "dart_employees",
                                           "tenure_years"]]
    comp = comp.merge(matched.rename(columns={"nps_key": "company_key"}), on="company_key", how="left")

    keep = ["company_key", "key_nm", "base_nm", "sample_nm", "bzowr_no6",
            "intp_nm", "sido", "n_sites", "members", "hires", "exits", "monthly_exit_rate", "est_annual",
            "cap_ratio", "cap_band", "est_corrected", "range_low", "range_high", "industry_pct", "industry_n",
            "corp_name", "dart_avg_salary", "dart_employees", "tenure_years"]
    comp[keep].to_parquet(PROC / "serving.parquet", index=False)

    meta = {"data_month": "2026-09", "dart_year": year, "rate": RATE, "cap_monthly": CAP,
            "near_cap": NEAR_CAP, "train_companies": len(train), "intervals": intervals}
    (PROC / "serving_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"조회용 회사 {len(comp):,}곳 저장. 상장사 실제 값 붙은 곳 {comp['dart_avg_salary'].notna().sum():,}곳")
    for b, v in intervals.items():
        print(f"  {b}: 오차 10~90% 구간 {v['q10']:+.0%} ~ {v['q90']:+.0%}, MAPE {v['mape']:.1%} ({v['n']}곳)")


if __name__ == "__main__":
    main(sys.argv[1])
