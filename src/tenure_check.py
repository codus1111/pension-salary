"""연차별 연봉(신입 → 10년 차)을 업종별로: 정부 통계 곡선과 상장사 공시 분석을 나란히 본다.

국민연금 공개 자료에는 사람별 근속·연봉이 없어서 '한 사람의 연차별 연봉'을 직접 계산할 수 없다. 그래서
1) 정부 통계: 고용노동부 고용형태별노동실태조사(2025)의 업종 × 근속 구간별 월임금 → 업종별 곡선(전체 평균 대비 비율)
2) 상장사 분석: DART 공시의 평균 근속연수와 1인 평균 급여로 '평균 근속이 1년 긴 회사는 연봉이 몇 % 높은가'(직원 규모 통제)
를 업종 묶음마다 구해 비교한다. 2)는 회사끼리 비교한 값이라 한 사람의 상승률과 다르다(보통 더 작게 나온다).
결과: reports/tenure_check.md
사용법 (WSL): ~/venvs/pension/bin/python src/tenure_check.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import mcp_server as m  # noqa: E402

GOV = json.loads((Path("data/app") / "tenure_wage_2025.json").read_text(encoding="utf-8"))
MID = [0.5, 2, 4, 7.5, 15]  # 근속 구간의 가운데 값 (10년 이상은 15년으로 본다)


def gov_slope(industry):
    """정부 통계: 근속 1년당 임금 상승률 (구간 가운데 값에 대한 로그 임금 기울기)."""
    w = GOV["wage_thousand_won"][industry][1:]
    return float(np.exp(np.polyfit(MID, np.log(w), 1)[0]) - 1)


def dart_slope(g):
    """상장사: 평균 근속연수 1년당 평균 급여 차이 (직원 수 로그를 함께 넣어 규모 차이를 뺀다)."""
    X = np.column_stack([np.ones(len(g)), g["tenure_years"], np.log(g["members"])])
    b = np.linalg.lstsq(X, np.log(g["dart_avg_salary"]), rcond=None)[0]
    return float(np.exp(b[1]) - 1)


def main():
    d = m.DATA[(m.DATA["dart_avg_salary"] > 0) & (m.DATA["tenure_years"] > 0)]
    rows = []
    for group, industry in GOV["group_to_industry"].items():
        w = GOV["wage_thousand_won"][industry]
        g = d[d["group"] == group]
        rows.append({"업종 묶음": group, "정부 통계 업종": industry.split(".")[-1],
                     "신입 ÷ 평균": w[1] / w[0], "10년 이상 ÷ 신입": w[5] / w[1],
                     "정부 1년당": gov_slope(industry),
                     "상장사 수": len(g), "상장사 1년당": dart_slope(g) if len(g) >= 30 else None})
    t = pd.DataFrame(rows)
    lines = [
        "# 연차별 연봉: 정부 통계 곡선 vs 상장사 공시 분석 (업종별)", "",
        f"- 정부 통계: {GOV['source']}",
        "- 상장사 분석: DART 2025 사업보고서의 평균 근속연수·1인 평균 급여, 직원 수 로그를 함께 넣은 회귀 (30곳 이상인 업종만)",
        "- '정부 1년당' = 근속 구간 가운데 값(0.5·2·4·7.5·15년)에 대한 로그 임금 기울기", "",
        "| 업종 묶음 | 정부 통계 업종 | 신입 ÷ 업종 평균 | 10년 이상 ÷ 신입 | 정부 통계 근속 1년당 | 상장사 수 | 상장사 근속 1년당 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in t.itertuples():
        dart = "-" if r[7] is None or pd.isna(r[7]) else f"{r[7]:+.1%}"
        lines.append(f"| {r[1]} | {r[2]} | {r[3]:.0%} | {r[4]:.2f}배 | {r[5]:+.1%} | {r[6]:,} | {dart} |")
    ok = t.dropna(subset=["상장사 1년당"])
    lines += ["",
              f"- 정부 통계의 근속 1년당 상승률 중간값 **{t['정부 1년당'].median():+.1%}**, "
              f"상장사 비교 중간값 **{ok['상장사 1년당'].median():+.1%}**",
              f"- 두 값의 업종 간 상관: {ok['정부 1년당'].corr(ok['상장사 1년당']):.2f}",
              "- 해석: 정부 통계는 같은 업종 안에서 근속이 다른 '사람들'을 비교해 한 사람의 경력 곡선에 가깝다. "
              "상장사 분석은 평균 근속이 다른 '회사들'을 비교해서, 근속이 짧아도 연봉이 높은 회사(IT 등)가 섞이면 기울기가 작아진다. "
              "그래서 웹 화면의 연차별 연봉은 정부 통계 곡선을 쓰고, 상장사 분석은 그 업종에서 근속과 연봉이 얼마나 같이 움직이는지 "
              "참고로만 보여준다."]
    Path("reports/tenure_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
