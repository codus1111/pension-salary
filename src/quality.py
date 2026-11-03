"""nps_raw 테이블의 데이터 품질을 SQL로 점검하고 reports/quality.md로 저장한다.

사용법: python src/quality.py
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/processed/nps.db")
REPORT_PATH = Path("reports/quality.md")

# 2026-09 기준: 보험료율 9.5%(2026.1~), 기준소득월액 상한 637만 원(2025.7~2026.6 적용분이 2026.6까지,
# 2026.7~ 659만 원). 하한은 2026.7~ 41만 원으로 가정 — 이상치 판정용 대략값.
RATE = 0.095
CAP = 6_590_000
FLOOR = 410_000

CHECKS = [
    ("전체 행 수", "SELECT COUNT(*) FROM nps_raw"),
    ("등록(1) / 탈퇴(2) 사업장",
     "SELECT join_stcd, COUNT(*) FROM nps_raw GROUP BY join_stcd"),
    ("법인(1) / 개인(2) 사업장",
     "SELECT styl_cd, COUNT(*) FROM nps_raw GROUP BY styl_cd"),
    ("가입자수 0 또는 빈칸", "SELECT COUNT(*) FROM nps_raw WHERE COALESCE(jnngp_cnt,0)=0"),
    ("당월고지금액 0 또는 빈칸", "SELECT COUNT(*) FROM nps_raw WHERE COALESCE(ntc_amt,0)=0"),
    ("업종코드 빈칸", "SELECT COUNT(*) FROM nps_raw WHERE intp_cd IS NULL"),
    ("업종코드 999999 (BIZ_NO미존재사업장)", "SELECT COUNT(*) FROM nps_raw WHERE intp_cd='999999'"),
    ("사업자번호 빈칸", "SELECT COUNT(*) FROM nps_raw WHERE bzowr_no6 IS NULL"),
    ("사업자번호 길이 분포",
     "SELECT LENGTH(bzowr_no6), COUNT(*) FROM nps_raw GROUP BY 1 ORDER BY 2 DESC"),
    ("가입자수 분포 (구간별 사업장 수)", """
        SELECT CASE WHEN jnngp_cnt < 10 THEN '1) 10명 미만'
                    WHEN jnngp_cnt < 50 THEN '2) 10~49명'
                    WHEN jnngp_cnt < 300 THEN '3) 50~299명'
                    WHEN jnngp_cnt < 1000 THEN '4) 300~999명'
                    ELSE '5) 1000명 이상' END AS band,
               COUNT(*), SUM(jnngp_cnt)
        FROM nps_raw WHERE join_stcd = 1 GROUP BY band ORDER BY band"""),
    (f"1인당 보험료가 상한({CAP:,}원 × {RATE})보다 큰 사업장 (논리적으로 불가능)", f"""
        SELECT COUNT(*) FROM nps_raw
        WHERE jnngp_cnt > 0 AND ntc_amt * 1.0 / jnngp_cnt > {CAP * RATE}"""),
    (f"1인당 보험료가 하한({FLOOR:,}원 × {RATE})보다 작은 사업장", f"""
        SELECT COUNT(*) FROM nps_raw
        WHERE jnngp_cnt > 0 AND ntc_amt > 0 AND ntc_amt * 1.0 / jnngp_cnt < {FLOOR * RATE}"""),
    ("이름+사업자번호가 같은 사업장이 여러 행인 경우 (지점 분리 의심)", """
        SELECT COUNT(*), SUM(n) FROM (
            SELECT wkpl_nm, bzowr_no6, COUNT(*) n FROM nps_raw
            WHERE join_stcd = 1 GROUP BY 1, 2 HAVING n > 1)"""),
    ("사업자번호 앞 6자리 하나를 공유하는 서로 다른 사업장명 수 (상위 5)", """
        SELECT bzowr_no6, COUNT(DISTINCT wkpl_nm) names FROM nps_raw
        WHERE join_stcd = 1 GROUP BY 1 ORDER BY 2 DESC LIMIT 5"""),
    ("월 퇴사율(상실/가입자) 50% 초과 사업장 (가입자 10명 이상)", """
        SELECT COUNT(*) FROM nps_raw
        WHERE join_stcd = 1 AND jnngp_cnt >= 10 AND lss_jnngp_cnt * 1.0 / jnngp_cnt > 0.5"""),
]


def fmt(rows):
    if len(rows) == 1 and len(rows[0]) == 1:
        v = rows[0][0]
        return f"**{v:,}**" if isinstance(v, (int, float)) else f"**{v}**"
    lines = []
    for r in rows:
        lines.append("- " + " | ".join(f"{v:,}" if isinstance(v, (int, float)) else str(v) for v in r))
    return "\n".join(lines)


def main():
    con = sqlite3.connect(DB_PATH)
    out = ["# 데이터 품질 점검 (국민연금 가입 사업장, 자료생성년월 2026-09)\n"]
    for title, sql in CHECKS:
        rows = con.execute(sql).fetchall()
        out.append(f"## {title}\n{fmt(rows)}\n")
    con.close()
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
