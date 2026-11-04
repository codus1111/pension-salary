"""1년(2025년 12개월) 평균 추정이 한 달(2026-09) 추정보다 나은지 DART 2025로 비교한다.

- 비교 대상: 지금까지와 같은 상장사 (매칭되고 직원 수가 맞는 회사)
- 회사 묶음: match.py와 같은 규칙 (이름·업종이 같은 공장·지점을 합친다)
- 보정 모델도 1년 평균 변수로 다시 학습해, 5겹 교차검증으로 한 달 버전과 비교한다

결과: reports/monthly.md, data/processed/annual_2025.parquet
사용법 (WSL): ~/venvs/pension/bin/python src/compare_monthly.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from model import boot_ci, models, oof_predict  # noqa: E402

PROC = Path("data/processed")
BANDS = [0, 0.6, 0.8, 0.9, 1.01]
LABELS = ["0.6 미만", "0.6~0.8", "0.8~0.9", "0.9 이상"]


def annual_by_corp(monthly_file="monthly_companies.parquet", out_file="annual_2025.parquet"):
    cmp = pd.read_parquet(PROC / "compare_2025.parquet")      # 한 달 버전 비교 결과 (DART 정답 포함)
    comp = pd.read_parquet(PROC / "companies.parquet", columns=["company_key", "base_nm", "intp_nm"])
    monthly = pd.read_parquet(PROC / monthly_file)

    # 회사 키 → DART 회사: 매칭된 회사와 이름·업종이 같은 회사(공장·지점)를 한 묶음으로
    by_name = {k: g for k, g in comp.groupby("base_nm")}
    key_to_corp = {}
    for r in cmp.itertuples():
        base = r.nps_key.split("|")[0]
        same = by_name.get(base)
        keys = {r.nps_key}
        if same is not None:
            keys |= set(same.loc[same["intp_nm"] == r.intp_nm, "company_key"])
        for k in keys:
            key_to_corp.setdefault(k, r.corp_code)

    m = monthly[monthly["company_key"].isin(key_to_corp)].copy()
    m["corp_code"] = m["company_key"].map(key_to_corp)
    g = m.groupby(["corp_code", "ym"], as_index=False).agg(
        members=("members", "sum"), ntc=("ntc_amt", "sum"), hires=("hires", "sum"), exits=("exits", "sum"),
        rate=("rate", "first"), cap=("cap", "first"))
    g["income"] = g["ntc"] / g["members"] / g["rate"]          # 그 달의 1인 평균 기준소득월액
    g["cap_ratio"] = g["income"] / g["cap"]
    a = g.groupby("corp_code").agg(
        months=("ym", "nunique"), income=("income", "mean"), income_sd=("income", "std"),
        cap_ratio12=("cap_ratio", "mean"), members12=("members", "mean"), exits12=("exits", "sum"))
    a["est12"] = a["income"] * 12
    a["exit_rate12"] = a["exits12"] / a["members12"] / 12      # 월평균으로 맞춰 한 달 버전과 비교
    a["month_cv"] = a["income_sd"] / a["income"]               # 달마다 얼마나 흔들리나
    out = cmp.merge(a.reset_index(), on="corp_code", how="left")
    out.to_parquet(PROC / out_file, index=False)
    return out


def mape_table(df, cols, band_col):
    band = pd.cut(df[band_col], BANDS, labels=LABELS, right=False)
    lines = ["| 구간 | 회사 수 | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for b in LABELS:
        idx = band == b
        lines.append(f"| {b} | {idx.sum():,} | " + " | ".join(
            f"{(df.loc[idx, c] / df.loc[idx, 'dart_avg_salary'] - 1).abs().mean():.1%}" for c in cols) + " |")
    return lines


SETTINGS = {
    "2025": dict(monthly="monthly_companies.parquet", annual="annual_2025.parquet", oof="annual_2025_oof.parquet",
                 report="reports/monthly.md", min_months=10, label="1년 평균 (2025)",
                 title="1년 평균(2025년 12개월) vs 한 달(2026-09) 추정"),
    # 기준소득월액이 2025년 소득으로 정해진 달들 (2026년 7월~): DART 2025와 같은 해 소득
    "2026": dict(monthly="monthly_companies_2026.parquet", annual="aligned_2026.parquet",
                 oof="aligned_2026_oof.parquet", report="reports/monthly_aligned.md", min_months=3,
                 label="3개월 평균 (2026년 7~9월)", title="같은 소득 연도 3개월 평균(2026년 7~9월) vs 한 달(2026-09)"),
}


def main(year="2025"):
    s = SETTINGS[year]
    df = annual_by_corp(s["monthly"], s["annual"])
    full = df[df["months"] >= s["min_months"]].copy()
    out = [f"# {s['title']}\n",
           f"- 비교 대상: 상장사 {len(df):,}곳 중 자료가 {s['min_months']}개월 이상 있는 **{len(full):,}곳**",
           f"- 달마다 1인 평균 소득이 흔들린 정도(변동계수) 중간값 {full['month_cv'].median():.1%}\n",
           "| 추정 | 평균 절대 오차율 (95% CI) | 중간값 | 평균 오차 | 오차 10% 이내 |", "|---|---|---|---|---|"]
    ape = {}
    for name, col in [("한 달 (2026-09)", "nps_est_annual"), (s["label"], "est12")]:
        err = full[col] / full["dart_avg_salary"] - 1
        ape[name] = err.abs()
        lo, hi = boot_ci(ape[name])
        out.append(f"| {name} | {ape[name].mean():.1%} ({lo:.1%}~{hi:.1%}) | {ape[name].median():.1%} | "
                   f"{err.mean():+.1%} | {(ape[name] <= 0.1).mean():.0%} |")
    diff = (ape["한 달 (2026-09)"] - ape[s["label"]]).to_numpy()
    dlo, dhi = boot_ci(diff)
    out.append(f"\n{s['label']}이 한 달보다 평균 절대 오차율을 **{diff.mean():+.1%}p** 줄였다 "
               f"(음수면 오히려 늘었다; 짝지은 부트스트랩 95% CI {dlo:+.1%}p~{dhi:+.1%}p).\n")
    out.append("## 상한 근접도별\n")
    out += mape_table(full, ["nps_est_annual", "est12"], "cap_ratio12")

    # 보정 모델: 1년 평균 변수로 다시 학습 (model.py와 같은 모델, 같은 교차검증)
    sites = pd.read_parquet(PROC / "sites.parquet", columns=["intp_nm", "intp_cd"])
    code = sites.dropna().groupby("intp_nm")["intp_cd"].agg(lambda s: s.mode().iloc[0])
    t = full.reset_index(drop=True).copy()
    t["ind2"] = t["intp_nm"].map(code).fillna("00").str[:2]
    t["log_est"] = np.log(t["est12"])
    t["cap_ratio"] = t["cap_ratio12"]
    t["cap_over80"] = (t["cap_ratio"] - 0.8).clip(lower=0)
    t["cap_over90"] = (t["cap_ratio"] - 0.9).clip(lower=0)
    t["log_members"] = np.log(t["members12"])
    t["exit_rate"] = t["exit_rate12"].clip(0, 0.5)
    t["log_y"] = np.log(t["dart_avg_salary"])
    cols, model_c = models()["C 선형 + 업종"]
    pred_c = oof_predict(t, cols, model_c)
    pred_e = np.where(t["cap_ratio"] >= 0.8, pred_c, t["est12"])
    out.append("\n## 보정 모델 (5겹 교차검증)\n")
    out.append("| 모델 | 평균 절대 오차율 (95% CI) | 오차 10% 이내 |")
    out.append("|---|---|---|")
    for name, p in [(f"{s['label']} 그대로", t["est12"].to_numpy()), ("+ 선형·업종 보정 (C)", pred_c),
                    ("+ 상한 근처만 보정 (E)", pred_e)]:
        a = np.abs(p / t["dart_avg_salary"].to_numpy() - 1)
        lo, hi = boot_ci(a)
        out.append(f"| {name} | {a.mean():.1%} ({lo:.1%}~{hi:.1%}) | {(a <= 0.1).mean():.0%} |")
    t["pred_c12"], t["pred_e12"] = pred_c, pred_e
    t.to_parquet(PROC / s["oof"], index=False)

    Path(s["report"]).write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main(*sys.argv[1:])
