"""MCP 서버가 조회할 회사별 추정 데이터를 만든다 (모든 국민연금 회사 대상).

- 보정 규칙은 E(혼합): cap_ratio 0.8 이상이면 C(선형 + 업종) 모델, 아니면 1차 추정 그대로.
  학습 데이터(상장사)보다 실제 조회 대상(비상장·중소기업)이 저연봉 쪽에 많아서 E를 쓴다.
- C 모델은 검증에 쓴 상장사 2,392곳 전체로 다시 학습한다.
- 오차 범위: 교차검증 예측(E)의 오차를 (cap_ratio 구간 × 회사 규모 300명 기준)별로 모아 분위수를 쓴다.
  80% 범위(10~90%): "비슷한 회사 10곳 중 8곳은 실제 연봉이 이 범위 안에 있었다"
  50% 범위(25~75%): "2곳 중 1곳은 이 범위 안에 있었다" — 가장 가능성 높은 범위

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
MIN_CELL = 50
SIZE_CUT = 300


def size_band(members):
    return np.where(members >= SIZE_CUT, f"{SIZE_CUT}명 이상", f"{SIZE_CUT}명 미만")


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

    # 오차 범위: 교차검증 예측의 오차를 (cap_ratio 구간 × 회사 규모)별로 모아 분위수를 쓴다.
    # 규모를 넣은 이유: 같은 cap 구간이어도 300명 이상 회사는 80% 범위 폭이 22~38%, 미만은 32~63%로 달랐다.
    # 한 칸에 회사가 MIN_CELL보다 적으면 cap 구간만으로 계산한 값을 쓴다.
    oof = pd.read_parquet(PROC / f"model_oof_{year}.parquet")
    members = pd.read_parquet(PROC / f"compare_{year}.parquet", columns=["corp_code", "nps_members"])
    oof = oof.merge(members, on="corp_code", how="left")
    oof["err"] = oof["E 혼합(천장 근처만 C)"] / oof["dart_avg_salary"] - 1
    oof["cap_band"] = pd.cut(oof["cap_ratio"], CAP_BANDS, labels=CAP_LABELS, right=False).astype(str)
    oof["size_band"] = size_band(oof["nps_members"])

    def summary(e):
        return {"q10": float(e.quantile(0.1)), "q90": float(e.quantile(0.9)),
                "q25": float(e.quantile(0.25)), "q75": float(e.quantile(0.75)),
                "mape": float(e.abs().mean()), "n": int(len(e))}

    intervals = {b: summary(g["err"]) for b, g in oof.groupby("cap_band")}
    for (b, s), g in oof.groupby(["cap_band", "size_band"]):
        if len(g) >= MIN_CELL:
            intervals[f"{b}|{s}"] = summary(g["err"])

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
    comp["size_band"] = size_band(comp["members"])
    # 실제 = 추정 ÷ (1 + 오차) 이므로, 오차 분위수가 클수록 범위의 아래쪽이 된다
    cell = [f"{b}|{s}" if f"{b}|{s}" in intervals else b for b, s in zip(comp["cap_band"], comp["size_band"])]
    comp["interval_key"] = cell
    for col, q in [("range_low", "q90"), ("range_high", "q10"), ("range50_low", "q75"), ("range50_high", "q25")]:
        comp[col] = [p / (1 + intervals[c][q]) if c in intervals else np.nan
                     for p, c in zip(comp["est_corrected"], cell)]

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
            "cap_ratio", "cap_band", "size_band", "interval_key", "est_corrected", "range_low", "range_high",
            "range50_low", "range50_high", "industry_pct", "industry_n",
            "corp_name", "dart_avg_salary", "dart_employees", "tenure_years"]
    comp[keep].to_parquet(PROC / "serving.parquet", index=False)

    meta = {"data_month": "2026-09", "dart_year": year, "rate": RATE, "cap_monthly": CAP,
            "near_cap": NEAR_CAP, "train_companies": len(train), "intervals": intervals}
    (PROC / "serving_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"조회용 회사 {len(comp):,}곳 저장. 상장사 실제 값 붙은 곳 {comp['dart_avg_salary'].notna().sum():,}곳")
    for b, v in intervals.items():
        w80 = (1 / (1 + v["q10"]) - 1 / (1 + v["q90"])) * 100
        w50 = (1 / (1 + v["q25"]) - 1 / (1 + v["q75"])) * 100
        print(f"  {b}: 80% 범위 폭 추정값의 {w80:.0f}%, 50% 범위 폭 {w50:.0f}%, MAPE {v['mape']:.1%} ({v['n']}곳)")


if __name__ == "__main__":
    main(sys.argv[1])
