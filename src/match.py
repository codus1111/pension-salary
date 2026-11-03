"""DART 상장사와 국민연금 회사(companies.parquet)를 매칭한다.

매칭 순서
1. 사업자번호 앞 6자리가 같은 국민연금 회사 중에서 이름이 가장 비슷한 곳 (이름 유사도 0.85 이상)
   - 이름은 종목명(한화생명)과 기업개황의 정식 이름(한화생명보험) 둘 다 비교한다
   - 한쪽 이름이 다른 쪽에 통째로 들어 있으면 유사도 0.9로 본다
2. 1이 없으면 이름이 똑같은 국민연금 회사로 매칭: 하나뿐이거나, 가장 큰 곳이 두 번째보다 5배 이상 클 때
3. 매칭된 회사와 이름·업종이 같고 사업자번호만 다른 회사(공장·지점)를 합친다: 기아 4곳 → 1곳
이름 비교 전에 DART의 영문 약자를 한글 읽기로 바꾼다: SK하이닉스 → 에스케이하이닉스

결과: data/processed/matched_2025.parquet, reports/match.md
사용법 (WSL): ~/venvs/pension/bin/python src/match.py 2025
"""
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from companies import normalize  # noqa: E402

PROC = Path("data/processed")
RAW = Path("data/raw")
MIN_SIMILARITY = 0.85
RATE = 0.095
CAP = 6_590_000

LETTERS = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지", "H": "에이치",
    "I": "아이", "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔", "O": "오", "P": "피",
    "Q": "큐", "R": "알", "S": "에스", "T": "티", "U": "유", "V": "브이", "W": "더블유", "X": "엑스",
    "Y": "와이", "Z": "제트",
}
# 약자가 아니라 단어로 읽는 영문 이름. 한글 표기가 자주 다른 상장사 일부.
WORDS = {"naver": "네이버", "posco": "포스코", "hanwha": "한화", "lotte": "롯데", "kakao": "카카오"}


def to_hangul(name):
    """영문을 한글 읽기로: 'SK하이닉스' → '에스케이하이닉스', 'NAVER' → '네이버'."""
    s = name
    for en, ko in WORDS.items():
        s = re.sub(en, ko, s, flags=re.IGNORECASE)
    # 5자 이하 영문 묶음은 약자로 보고 글자 단위로 읽는다. 더 긴 영문 단어는 그대로 둔다.
    s = re.sub(r"[A-Za-z]+", lambda m: "".join(LETTERS[c] for c in m.group().upper())
               if len(m.group()) <= 5 else m.group(), s)
    return s.lower()


def key_name(name):
    """국민연금·DART 양쪽에 똑같이 쓰는 비교용 이름."""
    base, _ = normalize(name)
    return re.sub(r"[^0-9a-z가-힣]", "", to_hangul(base))


def similarity(a, b):
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 3 and (a in b or b in a):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


def load_dart(year):
    sal = pd.read_parquet(PROC / f"dart_salary_{year}.parquet")
    sal = sal[sal["dart_avg_salary_ok"]]
    comp = pd.DataFrame([json.loads(l) for l in (RAW / "dart_company.jsonl").open(encoding="utf-8")])
    comp = comp[comp["status"] == "000"].rename(columns={"corp_name": "formal_name"})
    comp = comp[["corp_code", "formal_name", "bizr_no", "adres", "induty_code"]]
    dart = sal.merge(comp, on="corp_code", how="inner")
    dart["bizr6"] = dart["bizr_no"].fillna("").str.replace("-", "").str[:6]
    dart["key_nm"] = dart["corp_name"].map(key_name)
    dart["key_nm2"] = dart["formal_name"].fillna("").map(key_name)
    return dart


def find_match(d, by_no, by_name):
    names = {d.key_nm, d.key_nm2} - {""}
    cands = by_no.get(d.bizr6)
    if cands is not None:
        sims = cands["key_nm"].map(lambda n: max(similarity(x, n) for x in names))
        i = sims.idxmax()
        if sims[i] >= MIN_SIMILARITY:
            return cands.loc[i], "사업자번호+이름", sims[i]
    for n in names:
        same = by_name.get(n)
        if same is None:
            continue
        top = same.nlargest(2, "members")
        if len(top) == 1:
            return top.iloc[0], "이름만(유일)", 1.0
        if top.iloc[0]["members"] >= 5 * max(top.iloc[1]["members"], 1):
            return top.iloc[0], "이름만(가장 큰 곳)", 1.0
    return None, None, 0.0


def with_siblings(best, nps_by_name):
    """이름·업종이 같고 사업자번호만 다른 국민연금 회사(공장·지점)를 합친 값을 돌려준다."""
    same = nps_by_name.get(best["key_nm"])
    group = same[same["intp_nm"] == best["intp_nm"]] if same is not None else None
    if group is None or group.empty:  # 업종 이름이 비어 있으면 매칭된 회사 하나만 쓴다
        group = best.to_frame().T
    members, ntc, exits = group["members"].sum(), group["ntc_amt"].sum(), group["exits"].sum()
    return {
        "nps_n_numbers": len(group), "nps_members": members,
        "nps_est_annual": ntc / members / RATE * 12,
        "cap_ratio": ntc / members / RATE / CAP,
        "monthly_exit_rate": exits / members,
        # 합치기 전(사업자번호 하나) 값도 남겨서 합치기 효과를 비교한다
        "nps_members_single": best["members"],
    }


def main(year):
    dart = load_dart(year)
    nps = pd.read_parquet(PROC / "companies.parquet")
    nps["key_nm"] = nps["base_nm"].map(lambda s: re.sub(r"[^0-9a-z가-힣]", "", to_hangul(s)))
    by_no = {k: g for k, g in nps.groupby("bzowr_no6")}
    by_name = {k: g for k, g in nps.groupby("key_nm")}

    rows = []
    for d in dart.itertuples():
        best, method, score = find_match(d, by_no, by_name)
        row = {
            "corp_code": d.corp_code, "corp_name": d.corp_name, "formal_name": d.formal_name,
            "dart_key_nm": d.key_nm, "dart_employees": d.employees, "dart_avg_salary": d.dart_avg_salary,
            "tenure_years": d.tenure_years, "method": method, "similarity": score,
        }
        if best is not None:
            row.update({"nps_key": best["company_key"], "nps_name": best["sample_nm"], "intp_nm": best["intp_nm"],
                        **with_siblings(best, by_name)})
        rows.append(row)
    m = pd.DataFrame(rows)
    m["size_ratio"] = m["nps_members"] / m["dart_employees"]
    m["size_ok"] = m["size_ratio"].between(0.5, 2.0)
    m.to_parquet(PROC / f"matched_{year}.parquet", index=False)
    write_report(m)


def write_report(m):
    hit = m[m["method"].notna()]
    out = ["# 국민연금 ↔ DART 매칭 결과\n",
           f"- DART 회사(급여 검증 통과 + 기업개황 있음) **{len(m):,}곳** 중 매칭 **{len(hit):,}곳** ({len(hit) / len(m):.1%})"]
    for k, v in hit["method"].value_counts().items():
        out.append(f"  - {k}: {v:,}곳")
    out.append(f"- 직원 수가 서로 0.5~2배 안에 드는 매칭(신뢰할 만한 매칭): **{hit['size_ok'].sum():,}곳** "
               f"({hit['size_ok'].mean():.1%})")
    single_ok = (hit["nps_members_single"] / hit["dart_employees"]).between(0.5, 2.0)
    merged = hit[hit["nps_n_numbers"] > 1]
    out.append(f"  - 공장·지점 합치기 전에는 {single_ok.sum():,}곳({single_ok.mean():.1%}). "
               f"사업자번호 여러 개를 합친 회사 {len(merged):,}곳\n")

    out.append("## 직원 수가 크게 다른 매칭 예시 (잘못 매칭됐을 수 있음)\n")
    out.append("| DART 이름 | 국민연금 이름 | 방법 | 유사도 | DART 직원 | 국민연금 가입자 |")
    out.append("|---|---|---|---|---|---|")
    for r in hit[~hit["size_ok"]].nlargest(10, "dart_employees").itertuples():
        out.append(f"| {r.corp_name} | {r.nps_name} | {r.method} | {r.similarity:.2f} | "
                   f"{r.dart_employees:,.0f} | {r.nps_members:,.0f} |")

    out.append("\n## 매칭 실패 예시 (직원 수 상위 10)\n")
    out.append("| DART 이름 | 한글 변환 이름 | 직원 수 |")
    out.append("|---|---|---|")
    for r in m[m["method"].isna()].nlargest(10, "dart_employees").itertuples():
        out.append(f"| {r.corp_name} | {r.dart_key_nm} | {r.dart_employees:,.0f} |")

    Path("reports/match.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
