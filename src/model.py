"""1차 추정 연봉을 보정하는 모델을 만들고, 교차검증으로 오차가 얼마나 줄었는지 잰다.

원칙: 비상장 회사에도 써야 하므로 국민연금 데이터에 있는 정보만 변수로 쓴다.
      (DART의 근속연수처럼 상장사에만 있는 정보는 쓰지 않는다)

변수
- log_est     : 1차 추정 연봉의 로그
- cap_ratio   : 평균 기준소득월액 ÷ 상한 (1에 가까울수록 천장에 막혔을 가능성)
- log_members : 가입자 수의 로그
- exit_rate   : 월 퇴사율(상실 ÷ 가입자)
- ind2        : 업종코드 앞 2자리 (대분류에 가까운 묶음)

모델
- A 1차 추정 그대로
- B 선형 보정: 천장 근처에서 기울기가 꺾이는 구간 선형회귀 (변수: log_est, cap_ratio 꺾임, log_members)
- C B + 업종 (릿지 회귀)
- D 그래디언트 부스팅 (모든 변수)
- E 혼합: cap_ratio 0.8 이상(천장 근처)만 C로 보정하고, 나머지는 A를 그대로 쓴다
  (B~D를 돌려본 뒤, 보정이 오히려 저연봉 회사를 망치는 것을 보고 추가한 규칙. 기준 0.8은 결과를 보고 정했다)

평가: 5겹 교차검증의 예측값(학습에 안 쓴 회사)으로 평균 절대 오차율(MAPE)과 부트스트랩 95% CI.
결과: reports/model.md, data/processed/model_oof_2025.parquet
사용법 (WSL): ~/venvs/pension/bin/python src/model.py 2025
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

PROC = Path("data/processed")
RNG = np.random.default_rng(42)
NUM = ["log_est", "cap_ratio", "log_members", "exit_rate"]


def load(year):
    m = pd.read_parquet(PROC / f"compare_{year}.parquet")
    sites = pd.read_parquet(PROC / "sites.parquet", columns=["intp_nm", "intp_cd"])
    code = sites.dropna().groupby("intp_nm")["intp_cd"].agg(lambda s: s.mode().iloc[0])
    m["ind2"] = m["intp_nm"].map(code).fillna("00").str[:2]
    m["log_est"] = np.log(m["nps_est_annual"])
    m["log_members"] = np.log(m["nps_members"])
    m["exit_rate"] = m["monthly_exit_rate"].clip(0, 0.5)
    m["log_y"] = np.log(m["dart_avg_salary"])
    # 구간 선형: 천장 근처(0.8, 0.9 이후)에서 기울기가 바뀔 수 있게
    m["cap_over80"] = (m["cap_ratio"] - 0.8).clip(lower=0)
    m["cap_over90"] = (m["cap_ratio"] - 0.9).clip(lower=0)
    return m.reset_index(drop=True)


def models():
    lin_cols = ["log_est", "cap_ratio", "cap_over80", "cap_over90", "log_members"]
    return {
        "B 선형 보정": (lin_cols, LinearRegression()),
        "C 선형 + 업종": (lin_cols + ["ind2"], make_pipeline(
            ColumnTransformer([("ind", OneHotEncoder(handle_unknown="ignore", min_frequency=10), ["ind2"])],
                              remainder="passthrough"),
            Ridge(alpha=1.0))),
        "D 그래디언트 부스팅": (NUM + ["ind2"], HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
            categorical_features=["ind2"], random_state=42)),
    }


def oof_predict(df, cols, model):
    """5겹 교차검증: 각 회사는 자기가 빠진 4겹으로 학습한 모델로 예측한다."""
    pred = np.zeros(len(df))
    X = df[cols].copy()
    if "ind2" in cols:
        X["ind2"] = X["ind2"].astype("category")
    for tr, te in KFold(5, shuffle=True, random_state=42).split(X):
        model.fit(X.iloc[tr], df["log_y"].iloc[tr])
        pred[te] = model.predict(X.iloc[te])
    return np.exp(pred)


def boot_ci(v, n=2000):
    v = np.asarray(v)
    means = RNG.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    return np.percentile(means, 2.5), np.percentile(means, 97.5)


def main(year):
    df = load(year)
    preds = {"A 1차 추정": df["nps_est_annual"].to_numpy()}
    for name, (cols, model) in models().items():
        preds[name] = oof_predict(df, cols, model)
    near_cap = df["cap_ratio"].to_numpy() >= 0.8
    preds["E 혼합(천장 근처만 C)"] = np.where(near_cap, preds["C 선형 + 업종"], preds["A 1차 추정"])

    out = [f"# 보정 모델 비교 (5겹 교차검증, {len(df):,}곳)\n",
           "국민연금 데이터에 있는 정보만 사용. 모든 숫자는 학습에 쓰지 않은 회사에 대한 예측으로 계산했다.\n",
           "| 모델 | 평균 절대 오차율 (95% CI) | 중간값 | 평균 오차 | 오차 10% 이내 회사 비율 |",
           "|---|---|---|---|---|"]
    ape = {}
    for name, p in preds.items():
        err = p / df["dart_avg_salary"] - 1
        ape[name] = err.abs()
        lo, hi = boot_ci(ape[name])
        out.append(f"| {name} | {ape[name].mean():.1%} ({lo:.1%}~{hi:.1%}) | {ape[name].median():.1%} | "
                   f"{err.mean():+.1%} | {(ape[name] <= 0.10).mean():.0%} |")

    best = min(ape, key=lambda k: ape[k].mean())
    # 짝지은 부트스트랩: 같은 회사 표본에서 A와 best의 MAPE 차이
    diff = (ape["A 1차 추정"] - ape[best]).to_numpy()
    dlo, dhi = boot_ci(diff)
    out.append(f"\n가장 좋은 모델 **{best}**: 1차 추정보다 평균 절대 오차율이 **{diff.mean():.1%}p** 줄었다 "
               f"(짝지은 부트스트랩 95% CI {dlo:.1%}p~{dhi:.1%}p, 0을 포함하지 않으면 우연이 아니라고 볼 수 있다).\n")

    for col, bins, labels, title in [
        ("cap_ratio", [0, 0.6, 0.8, 0.9, 1.01], ["0.6 미만", "0.6~0.8", "0.8~0.9", "0.9 이상"], "상한 근접도별"),
        ("dart_avg_salary", [0, 5e7, 7e7, 9e7, 1e12], ["5천 미만", "5천~7천", "7천~9천", "9천 이상"], "실제 연봉 수준별"),
    ]:
        band = pd.cut(df[col], bins=bins, labels=labels, right=False)
        out.append(f"## {title} 평균 절대 오차율\n")
        out.append("| 구간 | 회사 수 | " + " | ".join(preds) + " |")
        out.append("|---|---|" + "---|" * len(preds))
        for b in labels:
            idx = band == b
            out.append(f"| {b} | {idx.sum():,} | " + " | ".join(f"{ape[n][idx].mean():.1%}" for n in preds) + " |")
        out.append("")

    # 변수 중요도는 학습하는 모델 중 가장 좋은 것으로 본다 (E는 C를 쓰는 규칙이라 C로 본다)
    best = min((k for k in models()), key=lambda k: ape[k].mean()) if best not in models() else best
    cols, model = models()[best]
    X = df[cols].copy()
    if "ind2" in cols:
        X["ind2"] = X["ind2"].astype("category")
    model.fit(X, df["log_y"])
    imp = permutation_importance(model, X, df["log_y"], n_repeats=10, random_state=42,
                                 scoring="neg_mean_absolute_error")
    out.append(f"## {best}의 변수 중요도 (값을 섞었을 때 로그 오차 증가량)\n")
    out.append("| 변수 | 중요도 |")
    out.append("|---|---|")
    for c, v in sorted(zip(cols, imp.importances_mean), key=lambda x: -x[1]):
        out.append(f"| {c} | {v:.4f} |")

    out.append("\n## 많이 틀렸던 회사는 얼마나 나아졌나 (직원 1,000명 이상, 1차 추정 오차 큰 순)\n")
    out.append(f"| 회사 | 실제(만 원) | 1차 추정 | {best} |")
    out.append("|---|---|---|---|")
    big = df[df["dart_employees"] >= 1000].copy()
    big["a"] = ape["A 1차 추정"][big.index]
    for i in big.sort_values("a", ascending=False).head(10).index:
        r = df.loc[i]
        out.append(f"| {r.corp_name} | {r.dart_avg_salary / 1e4:,.0f} | "
                   f"{preds['A 1차 추정'][i] / 1e4:,.0f} ({preds['A 1차 추정'][i] / r.dart_avg_salary - 1:+.0%}) | "
                   f"{preds[best][i] / 1e4:,.0f} ({preds[best][i] / r.dart_avg_salary - 1:+.0%}) |")

    oof = df[["corp_code", "corp_name", "dart_avg_salary", "nps_est_annual", "cap_ratio", "ind2"]].copy()
    for name, p in preds.items():
        oof[name] = p
    oof.to_parquet(PROC / f"model_oof_{year}.parquet", index=False)
    Path("reports/model.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
