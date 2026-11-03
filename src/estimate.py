"""사업장별 추정 연봉·월 퇴사율을 계산해 est 테이블과 reports/estimate.md로 저장한다.

사용법: python src/estimate.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/processed/nps.db")
REPORT_PATH = Path("reports/estimate.md")

# 자료생성년월 2026-09 기준
RATE = 0.095          # 보험료율 (사업장 + 근로자 합산), 2026.1~
CAP = 6_590_000       # 기준소득월액 상한, 2026.7~2027.6
MIN_MEMBERS = 10      # 이보다 작은 사업장은 표본이 작아 제외

SAMPLE_NAMES = ["삼성전자", "에스케이하이닉스", "네이버", "카카오", "현대자동차", "쿠팡", "토스", "우아한형제들"]


def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS est")
    con.execute(f"""
        CREATE TABLE est AS
        SELECT row_id, wkpl_nm, bzowr_no6, styl_cd, intp_cd, intp_nm, sido_cd, sggu_cd,
               jnngp_cnt, ntc_amt, nw_acqzr_cnt, lss_jnngp_cnt,
               ntc_amt * 1.0 / jnngp_cnt                          AS prem_per_person,
               ntc_amt * 1.0 / jnngp_cnt / {RATE}                 AS est_monthly,
               ntc_amt * 1.0 / jnngp_cnt / {RATE} * 12            AS est_annual,
               ntc_amt * 1.0 / jnngp_cnt / {RATE} / {CAP}         AS cap_ratio,
               lss_jnngp_cnt * 1.0 / jnngp_cnt                    AS monthly_exit_rate,
               nw_acqzr_cnt * 1.0 / jnngp_cnt                     AS monthly_hire_rate
        FROM nps_raw
        WHERE join_stcd = 1 AND jnngp_cnt >= {MIN_MEMBERS} AND ntc_amt > 0
    """)
    con.commit()

    out = ["# 1차 연봉 추정 (2026-09, 가입자 10명 이상 등록 사업장)\n",
           f"- 보험료율 {RATE:.1%}, 기준소득월액 상한 {CAP:,}원",
           "- 추정 연봉 = 당월고지금액 ÷ 가입자수 ÷ 보험료율 × 12",
           "- 상한 적용 때문에 실제보다 낮게 나오는 방향의 오차가 있다 (cap_ratio가 1에 가까울수록 심함)\n"]

    n = con.execute("SELECT COUNT(*), SUM(jnngp_cnt) FROM est").fetchone()
    out.append(f"대상 사업장 **{n[0]:,}곳**, 가입자 **{n[1]:,}명**\n")

    out.append("## 규모별 추정 연봉 (가입자 가중 평균, 만 원)\n")
    out.append("| 규모 | 사업장 수 | 가중 평균 연봉 | 평균 cap_ratio | 월 퇴사율 |")
    out.append("|---|---|---|---|---|")
    for r in con.execute("""
        SELECT CASE WHEN jnngp_cnt < 50 THEN '10~49명' WHEN jnngp_cnt < 300 THEN '50~299명'
                    WHEN jnngp_cnt < 1000 THEN '300~999명' ELSE '1000명 이상' END band,
               COUNT(*), SUM(est_annual * jnngp_cnt) / SUM(jnngp_cnt),
               AVG(cap_ratio), SUM(lss_jnngp_cnt) * 1.0 / SUM(jnngp_cnt),
               MIN(jnngp_cnt)
        FROM est GROUP BY band ORDER BY MIN(jnngp_cnt)"""):
        out.append(f"| {r[0]} | {r[1]:,} | {r[2] / 1e4:,.0f} | {r[3]:.2f} | {r[4]:.2%} |")

    out.append("\n## 상한 근접 사업장 (평균 기준소득월액이 상한의 90% 이상)\n")
    r = con.execute("SELECT COUNT(*), SUM(jnngp_cnt) FROM est WHERE cap_ratio >= 0.9").fetchone()
    out.append(f"**{r[0]:,}곳** (가입자 {r[1] or 0:,}명) — 이 회사들은 추정 연봉이 실제보다 크게 낮을 가능성이 높다.\n")

    out.append("## 업종별 추정 연봉 상위 10 (사업장 30곳 이상 업종, 가입자 가중)\n")
    out.append("| 업종 | 사업장 수 | 가중 평균 연봉(만 원) | 평균 cap_ratio |")
    out.append("|---|---|---|---|")
    for r in con.execute("""
        SELECT intp_nm, COUNT(*), SUM(est_annual * jnngp_cnt) / SUM(jnngp_cnt), AVG(cap_ratio)
        FROM est WHERE intp_cd <> '999999'
        GROUP BY intp_nm HAVING COUNT(*) >= 30 ORDER BY 3 DESC LIMIT 10"""):
        out.append(f"| {r[0]} | {r[1]:,} | {r[2] / 1e4:,.0f} | {r[3]:.2f} |")

    out.append("\n## 잘 알려진 회사 예시 (사업장명에 이름이 포함된 상위 가입자 사업장)\n")
    out.append("| 검색어 | 사업장명 | 가입자수 | 추정 연봉(만 원) | cap_ratio | 월 퇴사율 |")
    out.append("|---|---|---|---|---|---|")
    for name in SAMPLE_NAMES:
        r = con.execute("""
            SELECT wkpl_nm, jnngp_cnt, est_annual, cap_ratio, monthly_exit_rate
            FROM est WHERE wkpl_nm LIKE ? ORDER BY jnngp_cnt DESC LIMIT 1""", (f"%{name}%",)).fetchone()
        if r:
            out.append(f"| {name} | {r[0]} | {r[1]:,} | {r[2] / 1e4:,.0f} | {r[3]:.2f} | {r[4]:.2%} |")
        else:
            out.append(f"| {name} | (없음) | | | | |")

    con.close()
    REPORT_PATH.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
