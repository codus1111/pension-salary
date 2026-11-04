"""회사 연봉 추정 MCP 서버.

국민연금 가입 사업장 데이터로 추정하고 DART 상장사 급여로 검증·보정한 결과를 도구로 제공한다.
Claude 같은 AI가 이 도구들을 골라 써서 "이 회사 연봉 어때?" 같은 질문에 근거를 들어 답한다.

도구
- search_company      : 회사 이름으로 후보 찾기
- get_salary_estimate : 한 회사의 추정 연봉, 오차 범위, 퇴사율, 업종 내 위치
- compare_companies   : 여러 회사를 한 표로 비교
- industry_ranking    : 업종 안에서 추정 연봉 상위 회사
- method_and_limits   : 추정 방법과 한계 설명

실행 (WSL): ~/venvs/pension/bin/python src/mcp_server.py   (stdio)
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from match import to_hangul  # noqa: E402
from brands import to_legal  # noqa: E402
import filters  # noqa: E402

# 분석한 컴퓨터에는 data/processed, 웹 배포(저장소)에는 작게 만든 data/app만 있다 (src/make_app_data.py)
DATA_DIR = Path(os.environ["PENSION_DATA_DIR"]) if os.environ.get("PENSION_DATA_DIR") else (
    ROOT / "data/processed" if (ROOT / "data/processed/serving.parquet").exists() else ROOT / "data/app")
DATA = pd.read_parquet(DATA_DIR / "serving.parquet")
DATA["group"] = filters.add_groups(DATA)  # 업종 1,232가지 → 14개 묶음 (소규모 사업장 평균·웹 필터용)
META = json.loads((DATA_DIR / "serving_meta.json").read_text(encoding="utf-8"))
CAP_ANNUAL = META["cap_monthly"] * 12

# MCP 서버와 직접 만든 에이전트(src/agent.py)가 같은 안내문을 쓴다
INSTRUCTIONS = (
    "한국 회사의 평균 연봉을 국민연금 가입 사업장 데이터로 추정하는 도구다. "
    "회사 이름을 받으면 먼저 search_company로 후보를 찾고, 후보가 여럿이면 지역·업종·가입자 수로 "
    "사용자가 말한 회사가 맞는지 확인한 뒤 get_salary_estimate나 compare_companies를 호출한다. "
    "국민연금에는 법인명으로 등록돼 있어 브랜드명과 다를 수 있다(예: 토스 → 비바리퍼블리카, 배민 → 우아한형제들). "
    "검색 결과가 작은 회사뿐이거나 업종이 안 맞으면, 알고 있는 법인명으로 다시 검색한다. "
    "답할 때는 추정값만 말하지 말고 오차 범위와 신뢰도 메모(notes)를 함께 전한다. 범위는 두 단계로 말한다: "
    "'가장 가능성 높은 범위(2곳 중 1곳)'는 likely_range_text, '넓게 보면(10곳 중 8곳)'은 range_text. "
    "금액은 직접 계산하거나 단위를 바꾸지 말고 *_text 필드('1억 171만 원' 꼴)를 그대로 옮겨 쓴다. "
    "업종 안의 위치는 industry_position_text를 그대로 쓴다. "
    "직원 10명 미만 회사는 small_business_group(같은 지역·업종 묶음의 소규모 사업장 평균)을 함께 전한다. "
    "이 값은 회사 전체 직원의 평균 추정치이며 개인의 연봉이나 직무별 연봉이 아니다. "
    "추정 방법이나 한계를 물으면 method_and_limits를 호출한다."
)

mcp = MCPServer(name="company-salary", title="회사 연봉 추정 (국민연금 기반)", instructions=INSTRUCTIONS)


def _manwon(v):
    return None if pd.isna(v) else int(round(v / 1e4))


def _won_text(v):
    """원 단위 금액 → '1억 171만 원', '9,099만 원', '1억 원'.

    에이전트 평가에서 작은 모델이 10171(만 원)을 '1억 71만 원'으로 옮기다 틀려서, 읽는 형태를 도구가 만들어 준다.
    """
    m = _manwon(v)
    if m is None:
        return None
    eok, man = divmod(m, 10_000)
    if not eok:
        return f"{man:,}만 원"
    return f"{eok}억 {man:,}만 원" if man else f"{eok}억 원"


def _text(v):
    """빈 값(NaN)은 None으로. NaN은 JSON에 없는 값이라 모델 API가 요청을 거절한다."""
    return None if pd.isna(v) else v


def _key(text):
    return "".join(ch for ch in to_hangul(text) if ch.isalnum())


def _row(company_key):
    r = DATA[DATA["company_key"] == company_key]
    if r.empty:
        raise ValueError(f"company_key '{company_key}'를 찾지 못했다. search_company로 먼저 찾아라.")
    return r.iloc[0]


def _notes(r):
    notes = []
    if r["members"] < 10:
        notes.append("가입자 10명 미만이라 추정이 크게 흔들릴 수 있다.")
    elif r["members"] < 100:
        notes.append("가입자 100명 미만인 회사는 검증 데이터(상장사)에 적어 오차가 더 클 수 있다.")
    if r["cap_ratio"] >= 0.9:
        notes.append("평균 소득이 보험료 상한에 거의 닿아 있어 1차 추정은 실제보다 크게 낮다. "
                     "보정값을 쓰지만 고연봉 회사(특히 성과급 비중이 큰 업종)는 여전히 낮게 나올 수 있다.")
    elif r["cap_ratio"] >= META["near_cap"]:
        notes.append("평균 소득이 상한에 가까워 보정 모델을 적용했다.")
    hire_rate, exit_rate = r["hires"] / r["members"], r["exits"] / r["members"]
    if r["members"] >= 30 and max(hire_rate, exit_rate) > 0.10:
        notes.append(f"이번 달 입·퇴사가 비정상적으로 많다(신규 {int(r['hires'])}명, 상실 {int(r['exits'])}명, "
                     f"가입자의 {hire_rate:.0%}·{exit_rate:.0%}). 계열사 간 이동이나 조직 개편일 수 있어 "
                     "한 달치 퇴사율로 회사를 판단하면 안 되고, 추정 연봉도 흔들릴 수 있다. "
                     "보통 회사의 월 퇴사율은 2% 안팎이다.")
    if r["n_sites"] > 1:
        notes.append(f"지점·공장 {int(r['n_sites'])}곳을 합친 값이다.")
    if not pd.isna(r["dart_avg_salary"]):
        notes.append("상장사라 DART 사업보고서의 실제 1인 평균 급여가 있다. 이 값이 가장 정확하다.")
    return notes


def _summary(r):
    band = META["intervals"].get(r["interval_key"], {})
    return {
        "company_key": r["company_key"],
        "name": r["sample_nm"],
        "industry": _text(r["intp_nm"]),
        "region": _text(r["sido"]),
        "members": int(r["members"]),
        "estimated_salary_manwon": _manwon(r["est_corrected"]),
        "estimated_salary_text": _won_text(r["est_corrected"]),
        "range_manwon": [_manwon(r["range_low"]), _manwon(r["range_high"])],
        "range_text": f"{_won_text(r['range_low'])} ~ {_won_text(r['range_high'])}",
        "range_meaning": "80% 범위: 비슷한 상장사(같은 소득 구간·비슷한 규모) 10곳 중 8곳의 실제 평균 급여가 이 안에 있었다",
        "likely_range_manwon": [_manwon(r["range50_low"]), _manwon(r["range50_high"])],
        "likely_range_text": f"{_won_text(r['range50_low'])} ~ {_won_text(r['range50_high'])}",
        "likely_range_meaning": "50% 범위: 2곳 중 1곳이 이 안에 있었다. 가장 가능성 높은 범위",
        "range_basis": r["interval_key"],
        "first_estimate_manwon": _manwon(r["est_annual"]),
        # 에이전트 시험에서 모델이 cap_ratio 0.76을 "최고액 납부자 76%"로 오해해서, 이름과 뜻을 풀어서 준다
        "avg_income_vs_cap_pct": round(float(r["cap_ratio"]) * 100),
        "avg_income_vs_cap_meaning": (f"이 회사 가입자의 평균 기준소득월액이 보험료 상한(월 {META['cap_monthly'] / 1e4:,.0f}만 원)의 "
                                      f"{float(r['cap_ratio']) * 100:.0f}% 수준이라는 뜻. 상한에 걸린 직원의 비율이 아니다. "
                                      "90% 이상이면 고연봉 직원이 많아 1차 추정이 실제보다 낮게 나오기 쉽다."),
        "cap_monthly_won": META["cap_monthly"],
        "validation_mape_for_similar": round(band.get("mape", float("nan")), 3),
        "monthly_exit_rate": round(float(r["monthly_exit_rate"]), 4),
        "monthly_hires": int(r["hires"]),
        "monthly_exits": int(r["exits"]),
        # 웹 시험에서 "업종 상위 89%"(실제로는 상위 11%)로 잘못 읽어서, 상위 몇 %인지로 바꿔서 준다
        "industry_top_pct": None if pd.isna(r["industry_pct"]) else max(1, round((1 - float(r["industry_pct"])) * 100)),
        "industry_position_text": None if pd.isna(r["industry_pct"]) else
            f"같은 업종 {int(r['industry_n']):,}곳 중 연봉 상위 {max(1, round((1 - float(r['industry_pct'])) * 100))}%",
        "industry_companies": None if pd.isna(r["industry_n"]) else int(r["industry_n"]),
        "dart_actual_salary_manwon": _manwon(r["dart_avg_salary"]),
        "dart_actual_salary_text": _won_text(r["dart_avg_salary"]),
        "dart_tenure_years": None if pd.isna(r["tenure_years"]) else round(float(r["tenure_years"]), 1),
        "notes": _notes(r),
        "small_business_group": _small_group(r),
    }


def _small_group(r):
    """10명 미만이면 한 곳만 보면 흔들리니, 같은 업종 묶음·지역의 소규모 사업장 평균을 같이 준다."""
    if r["members"] >= 10:
        return None
    s = filters.small_summary(DATA, [r["group"]], [r["sido"]] if not pd.isna(r["sido"]) else [])
    if not s:
        return None
    return {**s, "avg_text": _won_text(s["avg_manwon"] * 1e4),
            "meaning": f"{_text(r['sido']) or '전국'}의 '{r['group']}' 업종 묶음에서 직원 10명 미만 사업장 {s['count']:,}곳을 "
                       "하나로 묶은 평균(일하는 사람 기준). 이 회사 하나의 추정보다 안정적이니 함께 전한다."}


@mcp.tool()
def search_company(query: str, limit: int = 8) -> list[dict]:
    """회사 이름으로 국민연금 가입 회사 후보를 찾는다.

    정확히 같은 이름 → 이름으로 시작 → 이름이 포함된 순서로, 같은 순위 안에서는 가입자가 많은 순.
    가입자 10명 미만 회사는 뒤로 미룬다. 영문 약자는 한글로 바꿔 찾는다(SK하이닉스 → 에스케이하이닉스).
    브랜드명이 아니라 법인명으로 등록돼 있다(토스 → 비바리퍼블리카). 결과의 company_key를 다른 도구에 넘긴다.
    """
    k = _key(to_legal(query) or query)  # 브랜드명이면 법인명으로 바꿔 찾는다 (토스 → 비바리퍼블리카)
    if not k:
        return []
    hit = DATA[DATA["key_nm"].str.contains(k, regex=False)].copy()
    hit["rank"] = (hit["key_nm"] != k).astype(int) + (~hit["key_nm"].str.startswith(k)).astype(int)
    # 법인명이 검색어의 앞부분인 큰 회사: "엔씨소프트" → "엔씨"(법인명 변경), "삼성전자주식회사" → "삼성전자"
    big = DATA[(DATA["members"] >= 100) & (DATA["key_nm"].str.len() >= 2)]
    prefix = big[big["key_nm"].map(lambda n: k.startswith(n) and n != k)].assign(rank=3)
    hit = pd.concat([hit, prefix[~prefix["company_key"].isin(hit["company_key"])]])
    hit["tiny"] = (hit["members"] < 10).astype(int)
    hit = hit.sort_values(["tiny", "rank", "members"], ascending=[True, True, False]).head(max(1, min(limit, 20)))
    return [{"company_key": r.company_key, "name": r.sample_nm, "industry": _text(r.intp_nm), "region": _text(r.sido),
             "members": int(r.members), "listed": not pd.isna(r.dart_avg_salary)} for r in hit.itertuples()]


@mcp.tool()
def get_salary_estimate(company_key: str) -> dict:
    """한 회사의 추정 평균 연봉(만 원), 오차 범위, 월 퇴사율, 업종 내 위치, 주의 사항을 돌려준다."""
    return _summary(_row(company_key))


@mcp.tool()
def compare_companies(company_keys: list[str]) -> list[dict]:
    """여러 회사(최대 5곳)의 추정 연봉·범위·규모·퇴사율을 한 번에 돌려준다. 추정 연봉 높은 순."""
    rows = [_summary(_row(k)) for k in company_keys[:5]]
    return sorted(rows, key=lambda x: -(x["estimated_salary_manwon"] or 0))


@mcp.tool()
def industry_ranking(industry_keyword: str, min_members: int = 100, limit: int = 10) -> dict:
    """업종 이름에 키워드가 들어간 회사 중 추정 연봉 상위 회사와 업종 중간값을 돌려준다.

    예: "소프트웨어", "증권", "반도체". min_members로 너무 작은 회사는 뺀다.
    업종은 국민연금에 신고된 분류라 실제 사업과 다를 수 있다. 예: 대형 게임사(넥슨코리아, 크래프톤, 엔씨)는
    "게임"이 아니라 "응용 소프트웨어 개발 및 공급업"으로 등록돼 있다. 결과가 적으면 회사 이름으로 찾아 비교하라.
    """
    sub = DATA[DATA["intp_nm"].fillna("").str.contains(industry_keyword, regex=False)
               & (DATA["members"] >= min_members)]
    if sub.empty:
        return {"industries": [], "companies": [], "note": "해당 업종 회사를 찾지 못했다."}
    top = sub.nlargest(max(1, min(limit, 20)), "est_corrected")
    note = None
    if len(sub) < 10:
        note = (f"이 업종 키워드로 잡힌 회사가 {len(sub)}곳뿐이다. 업종은 국민연금 신고 분류라, 같은 업계의 큰 회사가 "
                "다른 업종(예: 응용 소프트웨어 개발)으로 등록돼 있을 수 있다. 사용자가 생각하는 대표 회사들을 "
                "search_company로 찾아 compare_companies로 비교하는 편이 낫다.")
    return {
        "note": note,
        "industries": sub["intp_nm"].value_counts().head(5).to_dict(),
        "company_count": int(len(sub)),
        "median_salary_manwon": _manwon(sub["est_corrected"].median()),
        "median_salary_text": _won_text(sub["est_corrected"].median()),
        "companies": [{"company_key": r.company_key, "name": r.sample_nm, "members": int(r.members),
                       "estimated_salary_manwon": _manwon(r.est_corrected),
                       "estimated_salary_text": _won_text(r.est_corrected),
                       "range_manwon": [_manwon(r.range_low), _manwon(r.range_high)],
                       "range_text": f"{_won_text(r.range_low)} ~ {_won_text(r.range_high)}",
                       "likely_range_manwon": [_manwon(r.range50_low), _manwon(r.range50_high)],
                       "likely_range_text": f"{_won_text(r.range50_low)} ~ {_won_text(r.range50_high)}",
                       "dart_actual_salary_manwon": _manwon(r.dart_avg_salary),
                       "dart_actual_salary_text": _won_text(r.dart_avg_salary)} for r in top.itertuples()],
        "range_meaning": "range_text는 80% 범위(10곳 중 8곳), likely_range_text는 50% 범위(2곳 중 1곳). "
                         "자세한 주의 사항은 get_salary_estimate로 본다",
    }


@mcp.tool()
def method_and_limits() -> dict:
    """추정 방법, 검증 결과, 한계를 설명한다."""
    return {
        "data": f"국민연금 가입 사업장 {META['data_month']} (공공데이터포털), DART {META['dart_year']} 사업보고서",
        "method": [
            "1차 추정 = 당월 고지금액 ÷ 가입자 수 ÷ 보험료율(9.5%) × 12",
            f"보험료에는 상한이 있어 1차 추정은 연 {CAP_ANNUAL / 1e4:,.0f}만 원을 넘을 수 없다",
            f"평균 소득이 상한의 {int(META['near_cap'] * 100)}% 이상인 회사는 선형 회귀(업종 포함)로 보정",
            "오차 범위는 상장사 교차검증 결과를 (평균 소득 구간 × 회사 규모 300명 기준)별로 나눈 분위수: "
            "80% 범위(10~90%)와 50% 범위(25~75%)",
        ],
        "validation": {
            "companies": META["train_companies"],
            "mape_first_estimate": 0.146, "mape_corrected_model": 0.111,
            "by_band": META["intervals"],
        },
        "limits": [
            "회사 전체 평균이다. 직무·직급·개인 연봉이 아니다",
            "검증은 상장사로만 했다. 작은 비상장 회사는 오차가 더 클 수 있다",
            "성과급 비중이 큰 회사(증권, 반도체 등)는 보정 후에도 낮게 나오는 경향이 있다",
            "사업자번호가 앞 6자리만 공개돼 이름이 같은 다른 회사가 섞이거나, 지점이 따로 잡힐 수 있다",
            "퇴사율은 국민연금 상실자 수 기준이라 휴직·납부예외가 섞여 있다",
        ],
    }


if __name__ == "__main__":
    mcp.run()
