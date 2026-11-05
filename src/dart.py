"""OpenDART에서 기업 고유번호 목록과 상장사 직원 현황(1인 평균 급여)을 받는다.

사용법 (WSL)
  ~/venvs/pension/bin/python src/dart.py corpcode            # 기업 고유번호 목록 → data/raw/dart_corpcode.parquet
  ~/venvs/pension/bin/python src/dart.py test                # 삼성전자 1건으로 키 확인
  ~/venvs/pension/bin/python src/dart.py fetch 2025          # 상장사 직원 현황 → data/raw/dart_emp_2025.jsonl
  ~/venvs/pension/bin/python src/dart.py company 2025        # 급여 검증 통과 회사의 기업개황(사업자번호·주소) → data/raw/dart_company.jsonl

API 키는 .env 또는 .env.txt 의 DART_API_KEY 에서 읽는다. 키는 화면에 출력하지 않는다.
"""
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd

BASE = "https://opendart.fss.or.kr/api"
RAW = Path("data/raw")
CORP_PATH = RAW / "dart_corpcode.parquet"
SLEEP = 0.2  # 호출 간격(초). 하루 20,000건 한도와 분당 제한을 넉넉히 피한다.


def load_key():
    for name in (".env", ".env.txt"):
        p = Path(name)
        if p.exists():
            m = re.search(r"DART_API_KEY\s*=\s*['\"]?([A-Za-z0-9]+)", p.read_text(encoding="utf-8-sig"))
            if m:
                return m.group(1)
    sys.exit("DART_API_KEY를 .env 또는 .env.txt에서 찾지 못했습니다.")


def get(path, **params):
    url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read()


def corpcode(key):
    data = get("corpCode.xml", crtfc_key=key)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("CORPCODE.xml"))
    rows = [{c.tag: (c.text or "").strip() for c in item} for item in root.iter("list")]
    df = pd.DataFrame(rows)
    df.to_parquet(CORP_PATH, index=False)
    listed = df[df["stock_code"] != ""]
    print(f"기업 {len(df):,}곳, 그중 상장사(종목코드 있음) {len(listed):,}곳 → {CORP_PATH}")


def emp_status(key, corp_code, year):
    body = get("empSttus.json", crtfc_key=key, corp_code=corp_code, bsns_year=year, reprt_code="11011")
    return json.loads(body)


def test(key):
    res = emp_status(key, "00126380", "2025")  # 삼성전자
    print("status:", res.get("status"), res.get("message"))
    for row in res.get("list", [])[:4]:
        print({k: row.get(k) for k in ("fo_bbm", "sexdstn", "sm", "avrg_cnwk_sdytrn", "jan_salary_am")})


def fetch(key, year):
    out_path = RAW / f"dart_emp_{year}.jsonl"
    done = set()
    if out_path.exists():  # 중간에 끊겨도 이어서 받는다
        done = {json.loads(line)["corp_code"] for line in out_path.open(encoding="utf-8")}
    corps = pd.read_parquet(CORP_PATH)
    listed = corps[(corps["stock_code"] != "") & ~corps["corp_code"].isin(done)]
    print(f"받을 상장사 {len(listed):,}곳 (이미 받은 {len(done):,}곳 제외)", flush=True)

    with out_path.open("a", encoding="utf-8") as f:
        for i, c in enumerate(listed.itertuples(), 1):
            try:
                res = emp_status(key, c.corp_code, year)
            except Exception as e:  # 네트워크 오류는 기록만 하고 다음에 다시 받는다
                print(f"  오류 {c.corp_name}: {e}", flush=True)
                time.sleep(2)
                continue
            if res.get("status") == "020":
                print("하루 요청 한도 초과. 내일 같은 명령으로 이어서 받으면 됩니다.", flush=True)
                break
            f.write(json.dumps({"corp_code": c.corp_code, "corp_name": c.corp_name,
                                "status": res.get("status"), "list": res.get("list", [])},
                               ensure_ascii=False) + "\n")
            if i % 200 == 0:
                print(f"  {i:,}/{len(listed):,} 진행", flush=True)
            time.sleep(SLEEP)
    print("완료:", out_path, flush=True)


def company(key, year):
    """기업개황: 사업자등록번호 전체, 주소, 업종코드. 국민연금 사업장과 매칭할 때 쓴다."""
    out_path = RAW / "dart_company.jsonl"
    done = set()
    if out_path.exists():
        done = {json.loads(line)["corp_code"] for line in out_path.open(encoding="utf-8")}
    targets = pd.read_parquet(Path("data/processed") / f"dart_salary_{year}.parquet")
    targets = targets[targets["dart_avg_salary_ok"] & ~targets["corp_code"].isin(done)]
    print(f"받을 회사 {len(targets):,}곳 (이미 받은 {len(done):,}곳 제외)", flush=True)

    with out_path.open("a", encoding="utf-8") as f:
        for i, c in enumerate(targets.itertuples(), 1):
            try:
                res = json.loads(get("company.json", crtfc_key=key, corp_code=c.corp_code))
            except Exception as e:
                print(f"  오류 {c.corp_name}: {e}", flush=True)
                time.sleep(2)
                continue
            if res.get("status") == "020":
                print("하루 요청 한도 초과. 내일 같은 명령으로 이어서 받으면 됩니다.", flush=True)
                break
            keep = {k: res.get(k) for k in ("status", "corp_name", "corp_name_eng", "stock_code", "bizr_no",
                                            "adres", "induty_code", "est_dt")}
            f.write(json.dumps({"corp_code": c.corp_code, **keep}, ensure_ascii=False) + "\n")
            f.flush()
            if i % 200 == 0:
                print(f"  {i:,}/{len(targets):,} 진행", flush=True)
            time.sleep(SLEEP)
    print("완료:", out_path, flush=True)


def homepage(key):
    """기업개황의 홈페이지 주소(hm_url)만 따로 받는다. 웹 화면의 '공식 홈페이지' 버튼용.

    dart_company.jsonl을 만들 때는 매칭에 필요한 칸만 남겨서 홈페이지가 없었다. 이어받기 지원.
    """
    src, out_path = RAW / "dart_company.jsonl", RAW / "dart_homepage.jsonl"
    codes = [json.loads(line)["corp_code"] for line in src.open(encoding="utf-8")]
    done = set()
    if out_path.exists():
        done = {json.loads(line)["corp_code"] for line in out_path.open(encoding="utf-8")}
    todo = [c for c in codes if c not in done]
    print(f"받을 회사 {len(todo):,}곳 (이미 받은 {len(done):,}곳 제외)", flush=True)
    with out_path.open("a", encoding="utf-8") as f:
        for i, code in enumerate(todo, 1):
            try:
                res = json.loads(get("company.json", crtfc_key=key, corp_code=code))
            except Exception as e:
                print(f"  오류 {code}: {e}", flush=True)
                time.sleep(2)
                continue
            if res.get("status") == "020":
                print("하루 요청 한도 초과. 내일 같은 명령으로 이어서 받으면 됩니다.", flush=True)
                break
            f.write(json.dumps({"corp_code": code, "hm_url": (res.get("hm_url") or "").strip()}, ensure_ascii=False) + "\n")
            f.flush()
            if i % 200 == 0:
                print(f"  {i:,}/{len(todo):,} 진행", flush=True)
            time.sleep(SLEEP)
    print("완료:", out_path, flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1]
    key = load_key()
    if cmd == "corpcode":
        corpcode(key)
    elif cmd == "test":
        test(key)
    elif cmd == "fetch":
        fetch(key, sys.argv[2])
    elif cmd == "company":
        company(key, sys.argv[2])
    elif cmd == "homepage":
        homepage(key)
