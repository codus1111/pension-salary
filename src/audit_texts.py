"""화면·AI에 나가는 숫자와 문장이 서로 맞는지 여러 회사로 자동 점검한다 (예: '추정이 낮게 나와요'인데 실제로는 추정이 더 높음).

상장사 전부 + 직원 10명 이상 비상장사 3,000곳(무작위)을 get_salary_estimate로 뽑아 규칙을 확인하고,
규칙마다 걸린 회사 수와 예시를 보여준다. 결과: reports/audit_texts.md
사용법 (WSL): ~/venvs/pension/bin/python src/audit_texts.py
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mcp_server as m  # noqa: E402

MIN_WAGE_YEAR = 10_320 * 209 * 12 / 1e4 - 1  # 2026년 최저임금 1년치(만 원). 바닥값과 같으면 통과


def check(s):
    bad = []
    est = s["estimated_salary_manwon"]
    lo, hi = s["likely_range_manwon"]
    wlo, whi = s["range_manwon"]
    dart = s.get("dart_actual_salary_manwon")
    if est and lo and not (lo <= est <= hi):
        bad.append(("추정 연봉이 '가능성 높은 범위' 밖 (화면에 이유를 적음, 정상)", f"추정 {est} / 범위 {lo}~{hi}"))
    if est and wlo and not (wlo <= est <= whi):
        bad.append(("추정 연봉이 '넓은 범위' 밖", f"추정 {est} / 범위 {wlo}~{whi}"))
    if lo and wlo and not (wlo <= lo <= hi <= whi):
        bad.append(("가능성 높은 범위가 넓은 범위 안에 없음", f"{lo}~{hi} / {wlo}~{whi}"))
    tc = s.get("tenure_curve")
    if tc:
        v = tc["salary_manwon"]
        if any(b < a for a, b in zip(v, v[1:])):
            bad.append(("연차별 참고 연봉이 연차가 늘수록 줄어듦", str(v)))
        if v[0] < MIN_WAGE_YEAR:
            bad.append(("신입 참고 연봉이 최저임금 1년치보다 낮음", f"신입 {v[0]} (최저 약 {MIN_WAGE_YEAR:.0f})"))
        by = tc.get("by_year_manwon") or []
        if any(b < a for a, b in zip(by, by[1:])):
            bad.append(("내 연차 참고 연봉이 연차가 늘수록 줄어듦", str(by[:6])))
    if dart and s.get("industry_top_pct") and s.get("industry_top_pct_actual") is None:
        bad.append(("상장사인데 실제 공시 기준 순위가 없음", s["name"]))
    tr = s.get("salary_trend")
    if tr:
        g = tr.get("annual_growth_pct")
        if g is not None and ("+" in tr["change_text"]) != (g >= 0) and g != 0:
            bad.append(("연도별 변화 문장의 부호가 연평균 값과 다름", tr["change_text"]))
        for n in tr.get("notes", []):
            if "크게 늘었다" in n and tr["members"][-1] <= tr["members"][0]:
                bad.append(("직원이 늘지 않았는데 '크게 늘었다' 메모", str(tr["members"])))
    y = (s.get("turnover") or {}).get("year_2025")
    if y and y.get("change_text") and y["members_jan"] > 0:
        diff = y["members_dec"] - y["members_jan"]
        if (f"{diff:+,}명") not in y["change_text"]:
            bad.append(("직원 수 변화 문장과 숫자가 다름", y["change_text"]))
    sh = s.get("shrunk_estimate")
    if sh and s["members"] >= m.filters.SHRINK_UNDER:
        bad.append(("20명 이상인데 업종 평균 반영 값이 나옴", s["name"]))
    if s["members"] < 30 and s["confidence"]["level"] != "낮음" and not dart:
        bad.append(("직원 30명 미만인데 정확도가 낮음이 아님", s["confidence"]["level"]))
    return bad


def main():
    d = m.DATA
    listed = d[d["dart_avg_salary"].notna()]["company_key"].tolist()
    other = d[(d["dart_avg_salary"].isna()) & (d["members"] >= 10)].sample(3000, random_state=1)["company_key"].tolist()
    hits, total = defaultdict(list), 0
    for k in listed + other:
        try:
            s = m.get_salary_estimate(k)
        except Exception as e:  # noqa: BLE001
            hits["도구 오류"].append((k, str(e)[:80]))
            continue
        total += 1
        for rule, ex in check(s):
            hits[rule].append((s["name"], ex))
    lines = ["# 화면 숫자·문장 자동 점검", "", f"- 점검한 회사: {total:,}곳 (상장사 {len(listed):,} + 비상장 무작위 3,000)", "",
             "| 규칙 | 걸린 회사 | 예시 |", "|---|---|---|"]
    for rule, xs in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"| {rule} | {len(xs):,} | {xs[0][0]}: {xs[0][1]} |")
    if not hits:
        lines.append("| (걸린 규칙 없음) | 0 | - |")
    Path("reports/audit_texts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
