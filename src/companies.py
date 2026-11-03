"""사업장명을 정규화하고 지점·공장을 회사 단위로 합친다.

결과
- data/processed/sites.parquet      사업장별 정규화 이름, 지점 여부, 일용직 여부
- data/processed/companies.parquet  회사(정규화 이름 + 사업자번호 앞 6자리) 단위 집계
- reports/companies.md              합치기 결과 요약

사용법 (WSL): ~/venvs/pension/bin/python src/companies.py
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path("data/processed/nps.db")
OUT_DIR = Path("data/processed")
REPORT_PATH = Path("reports/companies.md")

RATE = 0.095
CAP = 6_590_000

# 법인 형태 표기. 긴 것부터 지워야 "유한책임회사"가 "유한회사"보다 먼저 처리된다.
LEGAL_FORMS = [
    "유한책임회사", "주식회사", "유한회사", "합자회사", "합명회사",
    "사단법인", "재단법인", "사회복지법인", "의료법인", "학교법인",
    "농업회사법인", "어업회사법인", "영농조합법인", "법무법인", "세무법인", "회계법인", "특허법인", "노무법인",
    "(주)", "(유)", "(유한)", "(합자)", "(합)", "(자)", "(사)", "(재)", "(사복)", "(의)", "(사단법인)", "㈜",
]
LEGAL_RE = re.compile("|".join(re.escape(f) for f in sorted(LEGAL_FORMS, key=len, reverse=True)))

# 지점·공장 등을 나타내는 끝말
BRANCH_RE = re.compile(r"(지점|지사|공장|사업소|사업장|영업소|출장소|본사|본점|연구소|물류센터|센터)$")
# 일용직·현장용 사업장 표시. "공사"는 한국전력공사 같은 공기업까지 걸려서 쓰지 않는다.
DAILY_RE = re.compile(r"일용|공구\)|공공근로")


def normalize(name):
    """원래 이름 → (회사 기본 이름, 지점 이름) 추정."""
    s = name.replace("（", "(").replace("）", ")").strip()
    # "/일용/..." "-(일용)..." 처럼 뒤에 붙은 현장 설명 제거
    s = re.split(r"\s*/\s*|-\(", s, maxsplit=1)[0]

    branch = ""
    m = LEGAL_RE.search(s)
    if m and LEGAL_RE.sub("", s[:m.start()]).strip() and s[m.end():].strip():
        # "미원상사(주)전주공장" → 법인 표기 앞이 회사, 뒤가 지점.
        # 앞부분이 법인 표기뿐이면("농업회사법인(주)OO") 이 규칙을 쓰지 않는다.
        branch = s[m.end():].strip()
        s = s[:m.start()]
    s = LEGAL_RE.sub(" ", s)

    # 남은 괄호 내용은 지점·현장 설명으로 본다: "프린테크케이알(화성공장)"
    paren = re.findall(r"\(([^)]*)\)", s)
    if paren:
        branch = branch or paren[-1]
        s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[()]", " ", s)  # 짝이 맞지 않는 괄호

    # 띄어쓰기로 나뉜 마지막 단어가 지점 끝말이면 떼어낸다: "삼보미네랄 영월지점"
    tokens = s.split()
    if len(tokens) >= 2 and BRANCH_RE.search(tokens[-1]):
        branch = branch or tokens[-1]
        tokens = tokens[:-1]

    base = "".join(tokens).lower()
    if not base and branch:
        # "법무법인(율촌)"처럼 괄호 안이 실제 이름인 경우
        base, branch = re.sub(r"\s+", "", branch).lower(), ""
    return base, branch.strip()


def main():
    con = sqlite3.connect(DB_PATH)
    sites = pd.read_sql(
        "SELECT row_id, wkpl_nm, bzowr_no6, styl_cd, intp_cd, intp_nm, sido_cd, sggu_cd, "
        "jnngp_cnt, ntc_amt, nw_acqzr_cnt, lss_jnngp_cnt "
        "FROM nps_raw WHERE join_stcd = 1 AND jnngp_cnt > 0", con)
    con.close()

    parsed = sites["wkpl_nm"].map(normalize)
    sites["base_nm"] = parsed.str[0]
    sites["branch_nm"] = parsed.str[1]
    sites["is_daily"] = sites["wkpl_nm"].str.contains(DAILY_RE)
    sites["company_key"] = sites["base_nm"] + "|" + sites["bzowr_no6"]
    sites.to_parquet(OUT_DIR / "sites.parquet", index=False)

    # 회사 단위 집계: 일용직 사업장은 연봉 추정에서 뺀다 (일당·단기 근로라 월 소득이 낮게 잡힘)
    regular = sites[~sites["is_daily"]]
    companies = (
        regular.groupby("company_key")
        .agg(base_nm=("base_nm", "first"), bzowr_no6=("bzowr_no6", "first"),
             sample_nm=("wkpl_nm", lambda s: s.iloc[s.str.len().argmin()]),
             n_sites=("row_id", "size"), members=("jnngp_cnt", "sum"), ntc_amt=("ntc_amt", "sum"),
             hires=("nw_acqzr_cnt", "sum"), exits=("lss_jnngp_cnt", "sum"),
             intp_nm=("intp_nm", "first"))
        .reset_index()
    )
    companies["est_annual"] = companies["ntc_amt"] / companies["members"] / RATE * 12
    companies["cap_ratio"] = companies["ntc_amt"] / companies["members"] / RATE / CAP
    companies["monthly_exit_rate"] = companies["exits"] / companies["members"]
    companies.to_parquet(OUT_DIR / "companies.parquet", index=False)

    write_report(sites, companies)


def write_report(sites, companies):
    out = ["# 회사 단위로 합치기 (2026-09, 등록 사업장)\n"]
    out.append(f"- 등록 사업장 **{len(sites):,}곳** → 회사 **{len(companies):,}곳** (일용직 사업장 제외 후)")
    multi = companies[companies["n_sites"] > 1]
    out.append(f"- 사업장이 2곳 이상으로 합쳐진 회사: **{len(multi):,}곳** (사업장 {multi['n_sites'].sum():,}곳)")
    daily = sites[sites["is_daily"]]
    out.append(f"- 일용직·공사 현장 사업장: **{len(daily):,}곳**, 가입자 {daily['jnngp_cnt'].sum():,}명\n")

    d_sal = (daily["ntc_amt"].sum() / daily["jnngp_cnt"].sum()) / RATE * 12 / 1e4
    r = sites[~sites["is_daily"]]
    r_sal = (r["ntc_amt"].sum() / r["jnngp_cnt"].sum()) / RATE * 12 / 1e4
    out.append(f"일용직 사업장의 가입자 가중 추정 연봉은 **{d_sal:,.0f}만 원**, 나머지는 **{r_sal:,.0f}만 원**. "
               "일용직 사업장은 공사 현장별로 따로 등록된 단기 고용이라 회사 본체의 연봉과 성격이 달라서, "
               "회사 단위 집계에서는 분리했다.\n")

    out.append("## 사업장 수가 가장 많은 회사 10곳\n")
    out.append("| 정규화 이름 | 사업자번호 6자리 | 사업장 수 | 가입자 | 추정 연봉(만 원) |")
    out.append("|---|---|---|---|---|")
    for _, c in companies.nlargest(10, "n_sites").iterrows():
        out.append(f"| {c.base_nm} | {c.bzowr_no6} | {c.n_sites:,} | {c.members:,} | {c.est_annual / 1e4:,.0f} |")

    out.append("\n## 정규화 예시 (무작위 15건)\n")
    out.append("| 원래 이름 | 회사 기본 이름 | 지점 | 일용 |")
    out.append("|---|---|---|---|")
    for _, s in sites.sample(15, random_state=7).iterrows():
        out.append(f"| {s.wkpl_nm} | {s.base_nm} | {s.branch_nm} | {'예' if s.is_daily else ''} |")

    # 같은 정규화 이름인데 사업자번호 6자리가 다른 경우: 다른 회사일 수도, 지점별 번호일 수도 있다
    spread = companies.groupby("base_nm")["bzowr_no6"].nunique()
    out.append(f"\n## 확인이 필요한 경우\n")
    out.append(f"- 같은 정규화 이름이 서로 다른 사업자번호 6자리로 나뉜 이름: **{(spread > 1).sum():,}개**")
    out.append("  - 동명이인 회사일 수도, 지점마다 사업자번호가 따로 있는 같은 회사일 수도 있다. "
               "DART 매칭 단계에서 주소·업종으로 구분한다.")
    out.append("- 상위 예시: " + ", ".join(f"{n}({k}개)" for n, k in spread.nlargest(8).items()))

    REPORT_PATH.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
