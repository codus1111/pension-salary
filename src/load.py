"""국민연금 가입 사업장 CSV를 SQLite로 적재한다.

사용법: python src/load.py data/raw/nps_2026-09.csv
"""
import csv
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/processed/nps.db")

# 원본 한글 컬럼 → 영문 컬럼 (공공데이터포털 컬럼 정의서의 영문명 기준)
COLUMNS = [
    ("data_ym", "TEXT"),          # 자료생성년월
    ("wkpl_nm", "TEXT"),          # 사업장명
    ("bzowr_no6", "TEXT"),        # 사업자등록번호 (앞 6자리만 공개)
    ("join_stcd", "INTEGER"),     # 사업장가입상태코드 1 등록 2 탈퇴
    ("zip", "TEXT"),              # 우편번호
    ("addr_jibun", "TEXT"),       # 사업장지번상세주소
    ("addr_road", "TEXT"),        # 사업장도로명상세주소
    ("ldong_cd", "TEXT"),         # 고객법정동주소코드
    ("hdong_cd", "TEXT"),         # 고객행정동주소코드
    ("sido_cd", "TEXT"),          # 법정동주소광역시도코드
    ("sggu_cd", "TEXT"),          # 법정동주소광역시시군구코드
    ("emd_cd", "TEXT"),           # 법정동주소광역시시군구읍면동코드
    ("styl_cd", "INTEGER"),       # 사업장형태구분코드 1 법인 2 개인
    ("intp_cd", "TEXT"),          # 사업장업종코드
    ("intp_nm", "TEXT"),          # 사업장업종코드명
    ("adpt_dt", "TEXT"),          # 적용일자
    ("re_adpt_dt", "TEXT"),       # 재등록일자
    ("rrg_dt", "TEXT"),           # 탈퇴일자
    ("jnngp_cnt", "INTEGER"),     # 가입자수
    ("ntc_amt", "INTEGER"),       # 당월고지금액
    ("nw_acqzr_cnt", "INTEGER"),  # 신규취득자수
    ("lss_jnngp_cnt", "INTEGER"), # 상실가입자수
]


def to_value(raw, col_type):
    raw = raw.strip()
    if raw == "":
        return None
    if col_type == "INTEGER":
        try:
            return int(raw)
        except ValueError:
            return None
    return raw


def main(csv_path):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS nps_raw")
    con.execute(
        "CREATE TABLE nps_raw (row_id INTEGER PRIMARY KEY, "
        + ", ".join(f"{name} {typ}" for name, typ in COLUMNS)
        + ")"
    )

    placeholders = ", ".join("?" for _ in COLUMNS)
    insert_sql = f"INSERT INTO nps_raw ({', '.join(n for n, _ in COLUMNS)}) VALUES ({placeholders})"

    bad_rows = 0
    with open(csv_path, encoding="cp949", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert len(header) == len(COLUMNS), f"컬럼 수가 다릅니다: {len(header)}"
        batch = []
        for row in reader:
            if len(row) != len(COLUMNS):
                bad_rows += 1
                continue
            batch.append([to_value(v, t) for v, (_, t) in zip(row, COLUMNS)])
            if len(batch) >= 50_000:
                con.executemany(insert_sql, batch)
                batch.clear()
        con.executemany(insert_sql, batch)

    con.commit()
    total = con.execute("SELECT COUNT(*) FROM nps_raw").fetchone()[0]
    con.close()
    print(f"적재 완료: {total:,}행, 컬럼 수가 맞지 않아 건너뛴 행: {bad_rows:,}")


if __name__ == "__main__":
    main(sys.argv[1])
