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

import numpy as np
import pandas as pd
from mcp.server.mcpserver import MCPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from match import to_hangul  # noqa: E402
from brands import BRANDS, UNVERIFIED, brand_note, to_legal  # noqa: E402
import filters  # noqa: E402

# 분석한 컴퓨터에는 data/processed, 웹 배포(저장소)에는 작게 만든 data/app만 있다 (src/make_app_data.py)
DATA_DIR = Path(os.environ["PENSION_DATA_DIR"]) if os.environ.get("PENSION_DATA_DIR") else (
    ROOT / "data/processed" if (ROOT / "data/processed/serving.parquet").exists() else ROOT / "data/app")
DATA = pd.read_parquet(DATA_DIR / "serving.parquet")
# 업종 1,232가지 → 14개 묶음 (소규모 사업장 평균·웹 필터용). 글자 열로 두면 51만 줄에 약 115MB라 category로
DATA["group"] = filters.add_groups(DATA).astype("category")
# 여러 시·도에 사업장이 있는 회사의 지역별 몫 (src/make_region_data.py). 지역으로 거를 때 그 지역 사업장만 본다
REGION_SITES = (pd.read_parquet(DATA_DIR / "region_sites.parquet")
                if (DATA_DIR / "region_sites.parquet").exists() else pd.DataFrame())
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
    "연봉이 오르는지·추이를 물으면 salary_trend의 change_text와 notes(직원 수 변화, 상한 영향)를 함께 전한다. "
    "이것은 '회사 평균의 연도별 변화'이지 '한 사람의 연차별 연봉'이 아니라고 분명히 말한다. "
    "신입·연차별 연봉을 물으면 tenure_curve의 salary_text(1년 미만·1~3년·3~5년·5~10년·10년 이상)와 growth_text를 전하고, "
    "'정부 통계의 업종 연차 비율을 회사 평균에 곱한 참고값(검증 안 됨)'이라고 꼭 밝힌다. dart_compare_text가 있으면 비교로 덧붙인다. "
    "답에는 도구 결과의 영어 필드 이름(예: avg_income_vs_cap_pct)을 쓰지 말고 우리말로만 설명한다. "
    f"보험료 상한은 기억으로 쓰지 말고 지금 값(기준소득월액 월 {META['cap_monthly'] / 1e4:,.0f}만 원, 연 {CAP_ANNUAL / 1e4:,.0f}만 원)만 쓴다. "
    "정확도를 물으면 method_and_limits의 accuracy_text 숫자를 꼭 넣는다. "
    "데이터 기준: 추정 연봉은 국민연금 2026년 9월 자료(2025년 소득 반영), 검증·공시 연봉은 DART 2025 사업연도 사업보고서"
    "(대부분 2025.1.1~12.31), 1년 퇴사율은 국민연금 2025년 1~12월. 기준 시점을 물으면 이대로 답한다. "
    "답에는 confidence(정확도 신호등)의 light와 reason을 꼭 넣고, 퇴사·분위기를 물으면 turnover.year_2025의 compare_text와 change_text(2025년 12개월)를 먼저 쓰고, "
    "이번 달 값(turnover.compare_text)은 보조로만 쓴다. year_2025가 없으면 이번 달 값만 쓴다. "
    "'비슷한데 연봉 더 높은 곳', '이직할 만한 곳'을 물으면 similar_companies를 호출한다. "
    "사용자가 지역을 붙여 물으면(예: 삼성전자 부산) get_salary_estimate에 region을 넘기고 region_detail을 전한다. "
    "직원 10명 미만 회사는 small_business_group(같은 지역·업종 묶음의 소규모 사업장 평균)을 함께 전한다. "
    "shrunk_estimate가 있으면 원래 추정을 먼저 말하고, '참고로 업종 평균을 반영하면 …(검증 안 된 값)'이라고만 덧붙인다. "
    "이 값은 회사 전체 직원의 평균 추정치이며 개인의 연봉이나 직무별 연봉이 아니다. "
    "추정 방법이나 한계를 물으면 method_and_limits를 호출한다. "
    "말투: 사람이 쓴 것처럼 짧고 담백한 존댓말(~요)로 쓴다. 줄표(—), 줄마다 붙는 이모지, 굵은 글씨 남발, "
    "'결론적으로', '정리하면', '~해 드립니다' 같은 상투적인 말은 쓰지 않는다. 제목과 목록은 꼭 필요할 때만 쓴다."
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


# 업종 묶음별 월 퇴사율 중간값 (직원 30명 이상). 금융 0.6% ~ 숙박·음식 3.6%로 업종마다 달라서 업종과 비교한다
EXIT_MEDIAN = DATA[DATA["members"] >= 30].groupby("group")["monthly_exit_rate"].median().to_dict()
# 2025년 1~12월로 계산한 1년 퇴사율·직원 수 추이 (src/make_turnover_data.py). 한 달치보다 덜 흔들린다
_load = lambda name: (pd.read_parquet(DATA_DIR / name).set_index("company_key")  # noqa: E731
                      if (DATA_DIR / name).exists() else pd.DataFrame())
TURNOVER, HEADCOUNT = _load("turnover_2025.parquet"), _load("headcount_2025.parquet")
# 연봉 상승 추이: 해마다 9월 자료의 1차 추정 (2019~2025년 소득, src/make_trend_data.py)
TREND = _load("trend.parquet")
TREND_YEARS = sorted(int(c[4:]) for c in TREND.columns if c.startswith("est_")) if not TREND.empty else []


def _trend(key):
    """연도별 1차 추정 연봉과 직원 수. 신입을 많이 뽑으면 평균이 내려가 보여서 직원 수를 같이 준다."""
    if TREND.empty or key not in TREND.index:
        return None
    t = TREND.loc[key]
    pts = [(y, t[f"est_{y}"], t[f"members_{y}"]) for y in TREND_YEARS if not pd.isna(t[f"est_{y}"])]
    if len(pts) < 3:
        return None
    (y0, e0, m0), (y1, e1, m1) = pts[0], pts[-1]
    cagr = float((e1 / e0) ** (1 / (y1 - y0)) - 1) if e0 > 0 and y1 > y0 else None  # float32 그대로면 JSON이 안 된다
    notes = []
    if m0 > 0 and m1 / m0 > 1.3 and e1 < max(e for _, e, _ in pts):
        notes.append(f"직원이 {int(m0):,}명에서 {int(m1):,}명으로 늘었어요. 새로 뽑은 사람이 많으면 평균이 낮아 보이는데, "
                     "연봉이 깎였다는 뜻은 아니에요.")
    if t[f"cap_{y1}"] >= 0.9:
        # 연도는 그래프 첫해부터 (롯데이노베이트처럼 2023년부터 있는 회사에 '2019년'을 쓰면 안 맞는다)
        notes.append(f"평균 소득이 보험료 상한 가까이라, {y0}~{y1}년에 상한이 오른 만큼만 오른 것처럼 보일 수 있어요. "
                     "실제로는 더 올랐을 수 있어요.")
    return {"years": [p[0] for p in pts], "salary_manwon": [int(p[1]) for p in pts], "members": [int(p[2]) for p in pts],
            "change_text": f"{y0}년 {_won_text(e0 * 1e4)} → {y1}년 {_won_text(e1 * 1e4)}"
                           + (f" (연평균 {cagr:+.1%})" if cagr is not None else ""),
            "annual_growth_pct": None if cagr is None else round(cagr * 100, 1),
            "basis": "해마다 9월 국민연금 자료(그 전해 소득)로 계산했어요. 보정 전 값이라 지금 추정 연봉과 조금 다를 수 있어요",
            "meaning": "그해 회사에 있던 직원 전체의 평균 연봉 변화다. 한 사람이 입사 후 연차가 쌓이며 오르는 연봉이 아니다",
            "notes": notes}


# 상장사 공식 홈페이지 (DART 기업개황 hm_url, src/make_link_data.py). 웹 화면의 '공식 홈페이지' 버튼용
HOMEPAGE = _load("homepage.parquet")["hm_url"].to_dict() if (DATA_DIR / "homepage.parquet").exists() else {}

# 연차별 참고 연봉: 국민연금에는 사람별 근속이 없어서, 정부 통계(고용형태별노동실태조사 2025)의 업종 × 근속 구간 임금 비율을
# 회사 평균 추정에 곱한다. 상장사 공시(평균 근속연수 ↔ 평균 급여) 기울기는 비교용. 근거: reports/tenure_check.md
_TENURE_FILE = ROOT / "data/app/tenure_wage_2025.json"  # 분석·배포 모두 같은 파일 (작은 참고 자료)
TENURE = json.loads(_TENURE_FILE.read_text(encoding="utf-8")) if _TENURE_FILE.exists() else None
TENURE_LABELS = ["1년 미만 (신입)", "1~3년", "3~5년", "5~10년", "10년 이상"]


def _dart_tenure_slopes():
    """업종 묶음별로 '평균 근속이 1년 긴 상장사는 평균 급여가 몇 % 높은가' (직원 수 로그로 규모를 뺀 회귀, 30곳 이상)."""
    d = DATA[(DATA["dart_avg_salary"] > 0) & (DATA["tenure_years"] > 0)]
    out = {}
    for g, s in d.groupby("group", observed=True):
        if len(s) >= 30:
            X = np.column_stack([np.ones(len(s)), s["tenure_years"], np.log(s["members"])])
            b = np.linalg.lstsq(X, np.log(s["dart_avg_salary"].astype(float)), rcond=None)[0]
            out[g] = (round(float(np.exp(b[1]) - 1) * 100, 1) + 0.0, len(s))  # -0.0 → 0.0
    return out


DART_TENURE = _dart_tenure_slopes() if TENURE else {}


# 단기·교대 근로가 많아 오래 다닌 사람이 적은 업종 (2025년 1년 퇴사율 중간값 43~77%, 직원 100명 이상)
SHORT_RE = __import__("re").compile("음식|음료|커피|주점|제과|제빵|구내식당|호텔|숙박|청소|경비|경호|건물 관리|부동산 관리|"
                                    "인력 공급|고용 알선|공사업")
MIN_WAGE_YEAR = 10_320 * 209 * 12  # 2026년 최저임금(시급 10,320원)으로 주 40시간 1년 ≈ 2,588만 원
TENURE_MID = [0.5, 2, 4, 7.5, 15]  # 근속 구간 가운데 값 (10년 이상은 15년으로 본다)


def _curve_at(w, t):
    """업종 곡선에서 근속 t년의 임금 (구간 가운데 값 사이를 로그로 잇는다. 0.5~15년 밖은 끝값)."""
    t = min(max(t, TENURE_MID[0]), TENURE_MID[-1])
    lw = np.log(w[1:])
    return float(np.exp(np.interp(t, TENURE_MID, lw)))


def _industry_tenure(w):
    """업종 평균 임금(전근속)이 곡선에서 몇 년 차에 해당하는지 (= 업종의 실질 평균 근속)."""
    return float(np.interp(np.log(w[0]), np.log(w[1:]), TENURE_MID))


def _size_tenure(members):
    bands = TENURE.get("size_tenure", {}).get("bands", [])
    val = TENURE.get("size_tenure", {}).get("all", 7.1)
    for lo, t in bands:
        if members >= lo:
            val = t
    return val


def _tenure_cap(key):
    """직원 수 추이로 본 평균 근속의 최대치. k년 전 직원 수 ÷ 지금 직원 수보다 많은 사람이 k년 넘게 다녔을 수는 없다.

    토스처럼 6년 새 직원이 5배가 된 회사는 대부분 최근 입사자라, 규모 평균(10년 넘게)을 쓰면 신입 연봉이 크게 나온다.
    """
    if TREND.empty or key not in TREND.index:
        return None
    t = TREND.loc[key]
    m = [t[f"members_{y}"] for y in TREND_YEARS]
    if any(pd.isna(v) or v <= 0 for v in m):
        return None
    now = m[-1]
    shares = [min(1.0, v / now) for v in reversed(m[:-1])]   # 1년 전, 2년 전, …
    if shares[-1] > 0.6:  # 자료 첫해보다 직원이 1.7배 넘게 늘지 않았으면 오래 다닌 사람이 많을 수 있어 제한하지 않는다
        return None
    return 0.5 + sum(shares) + shares[-1] * 3                 # 자료보다 더 오래된 근속은 최대 3년 더로 본다


def _tenure_curve(r):
    """연차별 참고 연봉. 회사 평균이 업종 곡선의 '평균 근속 몇 년 차'에 해당한다고 보고, 그 값으로 나눠 구간별로 늘리거나 줄인다.

    처음에는 업종 평균 대비 비율을 그대로 곱했는데, 근속이 긴 대기업(삼성전자 평균 13.7년)은 회사 평균이 이미 고참 쪽이라
    신입이 크게 나왔다(카카오 신입 7,679만 원). 그래서 회사 평균의 위치를 근속으로 맞춘다:
    상장사는 사업보고서의 평균 근속연수, 나머지는 같은 직원 규모의 평균 근속(정부 통계: 5~9인 5.9년 ~ 500인 이상 10.8년)을
    업종 평균 근속에 비례해 쓴다.
    """
    # 상장사는 사업보고서의 실제 평균 급여, 아니면 추정 연봉을 기준으로 한다
    actual = not pd.isna(r["dart_avg_salary"]) and r["dart_avg_salary"] > 0
    base = r["dart_avg_salary"] if actual else r["est_corrected"]
    if not TENURE or pd.isna(base):
        return None
    industry = TENURE["group_to_industry"].get(r["group"], "전체")
    w = TENURE["wage_thousand_won"][industry]
    t_ind = _industry_tenure(w)
    if not pd.isna(r["tenure_years"]) and r["tenure_years"] > 0:
        t_co = float(r["tenure_years"])
        tenure_text = f"이 회사 평균 근속 {t_co:.1f}년 (사업보고서)"
    else:
        size_t = _size_tenure(int(r["members"]))
        t_co = t_ind * size_t / TENURE["size_tenure"]["all"] if "size_tenure" in TENURE else t_ind
        tenure_text = f"평균 근속 약 {t_co:.1f}년으로 가정 (같은 직원 규모 평균 {size_t}년, 정부 통계)"
        cap = _tenure_cap(r["company_key"])
        if cap is not None and cap < t_co:
            t_co = cap
            tenure_text = f"평균 근속 약 {t_co:.1f}년으로 가정 (최근 몇 년 새 직원이 크게 늘어, 직원 수 추이로 본 최대치)"
        # 요식업·호텔·청소·경비·시설관리·인력 공급·공사 현장은 단기 근로가 많아 오래 다닌 사람이 적다: 평균 근속 ≈ 1 ÷ 1년 퇴사율 (25% 이상일 때만).
        # 다른 업종은 퇴사율에 계열사 이동이 섞여(토스 57%) 근속을 너무 짧게 잡게 돼 적용하지 않는다.
        # 스타벅스(에스씨케이컴퍼니)는 '커피 및 차류 도매업'으로 등록돼 있어 업종 이름으로도 찾는다
        key = r["company_key"]
        food = r["group"] == "숙박·음식" or bool(SHORT_RE.search(str(r["intp_nm"] or "")))
        if food and not TURNOVER.empty and key in TURNOVER.index:
            rate = float(TURNOVER.loc[key, "annual_exit_rate"])
            if rate >= 0.25 and 1 / rate < t_co:
                t_co = 1 / rate
                tenure_text = f"평균 근속 약 {t_co:.1f}년으로 가정 (2025년 1년 퇴사율 {rate:.0%}로 본 값)"
    anchor = _curve_at(w, t_co)
    ratios = [v / anchor for v in w[1:]]
    # 회사 평균이 낮은 곳(단시간 근로자가 많이 섞인 곳)은 신입 값이 최저임금 1년치보다 낮게 나와서(점검 754곳), 그 아래로는 내리지 않는다
    floored = any(base * x < MIN_WAGE_YEAR for x in ratios)
    vals = [max(base * x, MIN_WAGE_YEAR) for x in ratios]
    years = [max(base * _curve_at(w, t + 0.5) / anchor, MIN_WAGE_YEAR) for t in range(21)]
    first, last = w[1], w[5]
    dart = DART_TENURE.get(r["group"])
    out = {"industry_basis": industry.split(".")[-1],
           "buckets": TENURE_LABELS,
           "ratio_to_average": [round(v / base, 2) for v in vals],
           "base_text": ("공시 평균 급여 " if actual else "추정 평균 연봉 ") + _won_text(base),
           "tenure_text": tenure_text,
           "salary_manwon": [_manwon(v) for v in vals],
           "salary_text": [_won_text(v) for v in vals],
           # '내 연차' 입력용: 0년 차(신입) ~ 20년 차. t년 차는 근속 t+0.5년으로 본다
           "by_year_manwon": [_manwon(v) for v in years],
           "growth_text": f"같은 업종에서 10년 이상 근속자의 임금은 1년 미만의 약 {last / first:.1f}배",
           "dart_compare_text": (None if dart is None else
                                 f"같은 업종 상장사 {dart[1]:,}곳을 보면 평균 근속이 1년 긴 회사의 평균 급여가 "
                                 + ("거의 같아요. " if abs(dart[0]) < 0.5 else f"{dart[0]:+.1f}% 차이 나요. ")
                                 + "회사끼리 비교한 값이라 한 사람이 받는 상승폭보다는 작게 나와요"),
           "basis": ("고용노동부 고용형태별노동실태조사 2025(상용 5인 이상)의 업종별 근속 임금을 "
                     "이 회사 평균 연봉(상장사는 공시값)에 맞춰 계산했어요"),
           "meaning": ("이 회사가 실제로 연차별로 주는 연봉은 아니에요. 업종 평균의 연차별 차이를 이 회사에 대입해 본 값이라 "
                       "호봉 체계나 성과급에 따라 많이 다를 수 있어요. 대기업은 성과급이 고참에게 몰려 있어 신입 값이 높게 나오기 쉬워요")}
    if floored:
        out["meaning"] += (". 최저임금 1년치(약 2,588만 원)보다 낮게 계산된 연차는 최저임금으로 맞췄어요. "
                           "단시간 근로자가 많아 회사 평균이 낮게 잡힌 것 같아요")
        out["floored_to_min_wage"] = True
    if r["cap_ratio"] >= 0.9 and not actual:
        out["meaning"] += ". 평균 소득이 보험료 상한 가까이라 회사 평균 추정부터 낮게 나왔을 수 있어요"
    return out


YEAR_EXIT_MEDIAN = ({} if TURNOVER.empty else
                    TURNOVER[TURNOVER["avg_members"] >= 30].join(DATA.set_index("company_key")["group"])
                    .groupby("group")["annual_exit_rate"].median().to_dict())


def _year_turnover(r):
    key = r["company_key"]
    if TURNOVER.empty or key not in TURNOVER.index:
        return None
    t = TURNOVER.loc[key]
    rate, med = float(t["annual_exit_rate"]), YEAR_EXIT_MEDIAN.get(r["group"])
    jan, dec = int(t["members_jan"]), int(t["members_dec"])
    out = {"period": "2025년 1~12월", "annual_exit_rate_pct": round(rate * 100),
           "annual_hire_rate_pct": round(float(t["annual_hire_rate"]) * 100),
           "exits_12m": int(t["exits_12m"]), "hires_12m": int(t["hires_12m"]), "avg_members": round(float(t["avg_members"])),
           "members_jan": jan, "members_dec": dec,
           "industry_median_annual_exit_rate_pct": None if med is None else round(med * 100)}
    if jan > 0 and dec > 0:
        out["change_text"] = f"2025년 1월 {jan:,}명 → 12월 {dec:,}명 ({dec - jan:+,}명, {(dec - jan) / jan:+.0%})"
    if t["avg_members"] < 30 or med is None:
        out["compare_text"] = f"2025년 1년 퇴사율 약 {rate:.0%}. 직원이 적어 업종과 비교하지 않는다."
    else:
        ratio = rate / med if med else float("inf")
        word = "낮은 편" if ratio < 0.7 else "높은 편" if ratio > 1.4 else "비슷한 편"
        out["compare_text"] = f"2025년 1년 퇴사율 약 {rate:.0%}로 같은 업종 묶음 중간값({med:.0%})보다 {word}"
    if key in HEADCOUNT.index:
        out["monthly_members"] = {c.replace("_", "-"): (None if pd.isna(v) else int(v)) for c, v in HEADCOUNT.loc[key].items()}
    return out


def _turnover(r):
    """이번 달 입사·퇴사(국민연금 취득·상실)로 본 퇴사율과 인원 변화. 한 달치라 참고용."""
    rate = float(r["monthly_exit_rate"])
    med = EXIT_MEDIAN.get(r["group"])
    net = int(r["hires"]) - int(r["exits"])
    out = {"monthly_exit_rate_pct": round(rate * 100, 1),
           "annual_exit_rate_rough_pct": round(min(rate * 12, 1) * 100),
           "hires": int(r["hires"]), "exits": int(r["exits"]), "net_change": net,
           "net_change_text": (f"이번 달 {net:+,}명 (" + ("늘어나는 중" if net > 0 else "줄어드는 중" if net < 0 else "변화 없음") + ")"),
           "industry_median_monthly_exit_rate_pct": None if med is None else round(med * 100, 1)}
    if r["members"] < 30 or med is None:
        out["compare_text"] = "직원이 적어 한 달 퇴사율은 몇 명만 나가도 크게 흔들린다. 참고만 한다."
    else:
        ratio = rate / med if med else float("inf")
        word = "낮은 편" if ratio < 0.7 else "높은 편" if ratio > 1.5 else "비슷한 편"
        out["compare_text"] = f"월 퇴사율 {rate:.1%}로 같은 업종 묶음 중간값({med:.1%})보다 {word}"
        if rate > 0.10:  # 토스: 한 달에 311명 상실·571명 취득. 계열사 이동·개편으로 보이는 달
            out["compare_text"] += (". 다만 이번 달은 입·퇴사가 비정상적으로 많아 계열사 이동이나 조직 개편일 수 있다. "
                                    "이 한 달로 퇴사가 많은 회사라고 판단하면 안 된다")
            out["unusual_month"] = True
    out["meaning"] = ("국민연금 자격 상실 기준이라 이직·퇴사 외에 계열사 이동도 들어간다. 1년 환산은 이번 달 값 × 12로 "
                      "단순 계산한 것이라, 가능하면 year_2025(12개월 실제 합계)를 쓴다.")
    out["year_2025"] = _year_turnover(r)
    return out


def _confidence(r):
    """정확도 신호등. 근거: 상장사 2,392곳 검증 오차(MAPE 7~13%)와 검증 데이터의 규모(90%가 36명 이상)."""
    band = META["intervals"].get(r["interval_key"], {})
    mape = band.get("mape", 0.15)
    if not pd.isna(r["dart_avg_salary"]):
        return {"level": "높음", "light": "🟢", "reason": "상장사라 사업보고서의 실제 평균 급여와 비교할 수 있어요."}
    if r["members"] < 30:
        return {"level": "낮음", "light": "🔴", "reason": "직원 30명 미만은 검증한 회사가 거의 없고, 몇 명의 소득에 크게 흔들려요."}
    if r["members"] >= 300 and mape <= 0.10:
        return {"level": "높음", "light": "🟢", "reason": f"비슷한 규모의 상장사 검증에서 평균 오차가 {mape:.0%}였어요."}
    return {"level": "보통", "light": "🟡", "reason": f"비슷한 상장사 검증에서 평균 오차가 {mape:.0%}였어요. 범위를 함께 보세요."}


# 업종 안 위치를 실제 공시 연봉으로도 보기 위해, 업종별(직원 10명 이상) 추정 연봉을 정렬해 둔다 (src/serving.py와 같은 기준)
_PEERS = {k: np.sort(g.to_numpy(dtype=float)) for k, g in
          DATA[(DATA["members"] >= 10) & DATA["est_corrected"].notna()].groupby("intp_nm")["est_corrected"]}


def _actual_top_pct(r):
    """실제 공시 연봉이 같은 업종 회사들의 (추정) 연봉 사이에서 상위 몇 %인지. 공시가 없으면 None."""
    arr = _PEERS.get(r["intp_nm"])
    if pd.isna(r["dart_avg_salary"]) or arr is None or len(arr) < 2:
        return None
    above = len(arr) - np.searchsorted(arr, float(r["dart_avg_salary"]), side="right")
    return max(1, round(above / len(arr) * 100))


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
        # 위의 순위는 '추정 연봉' 기준. 상장사는 실제 공시 연봉으로 본 순위도 준다 (추정과 공시가 다르면 순위도 다르다)
        "industry_top_pct_actual": _actual_top_pct(r),
        "dart_actual_salary_manwon": _manwon(r["dart_avg_salary"]),
        "dart_actual_salary_text": _won_text(r["dart_avg_salary"]),
        "dart_tenure_years": None if pd.isna(r["tenure_years"]) else round(float(r["tenure_years"]), 1),
        "notes": _notes(r),
        "small_business_group": _small_group(r),
        "shrunk_estimate": _shrunk(r),
        "salary_trend": _trend(r["company_key"]),
        "tenure_curve": _tenure_curve(r),
        "turnover": _turnover(r),
        "confidence": _confidence(r),
    }


CELL_MEANS = filters.cell_means(DATA)


def _shrunk(r):
    """직원 30명 미만 회사의 '업종 평균 반영 값' (참고용·검증 안 됨). 원래 추정은 바꾸지 않는다."""
    if r["members"] >= filters.SHRINK_UNDER or pd.isna(r["est_corrected"]):
        return None
    mean = CELL_MEANS.get((r["sido"], r["group"]))
    if mean is None or pd.isna(mean):
        return None
    val, w = filters.shrink(float(r["est_corrected"]), int(r["members"]), float(mean))
    return {"value_manwon": _manwon(val), "value_text": _won_text(val), "cell_mean_text": _won_text(mean),
            "own_weight_pct": round(w * 100),
            "meaning": (f"참고용·검증 안 됨. 직원이 {int(r['members'])}명뿐이라 몇 사람 소득에 크게 흔들려서, 같은 지역·업종의 "
                        f"{filters.SHRINK_UNDER}명 미만 회사 평균"
                        f"({_won_text(mean)})을 {100 - round(w * 100)}% 섞은 값. 작은 회사는 상장사가 거의 없어 이 값이 더 맞는지 "
                        "확인할 수 없다. 원래 추정을 먼저 말하고, 이 값은 '참고로'만 덧붙인다.")}


def _small_group(r):
    """10명 미만이면 한 곳만 보면 흔들리니, 같은 업종 묶음·지역의 소규모 사업장 평균을 같이 준다."""
    if r["members"] >= 10:
        return None
    s = filters.small_summary(DATA, [r["group"]], [r["sido"]] if not pd.isna(r["sido"]) else [], region_sites=REGION_SITES)
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
    out = [{"company_key": r.company_key, "name": r.sample_nm, "industry": _text(r.intp_nm), "region": _text(r.sido),
            "members": int(r.members), "listed": not pd.isna(r.dart_avg_salary)} for r in hit.itertuples()]
    note = brand_note(query)
    if note and out:  # 확인 안 된 브랜드 연결(라라스윗 → 오디너리)은 AI도 '추정'이라고 말하게
        out[0]["brand_note"] = note
    return out


def _jamo(text):
    """한글을 자모로 풀어 쓴다 ('카카오' → 'ㅋㅏㅋㅏㅇㅗ'). 글자 하나가 틀린 오타도 비슷하게 잡히게."""
    out = []
    for ch in text:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out += [chr(0x1100 + c // 588), chr(0x1161 + c % 588 // 28)] + ([chr(0x11A7 + c % 28)] if c % 28 else [])
        else:
            out.append(ch)
    return "".join(out)


_SUGGEST = None


def suggest_name(query: str) -> str | None:
    """검색 결과가 없을 때 가장 비슷한 회사·브랜드 이름 하나 ('카카우' → '카카오', '스타벅수' → '스타벅스').

    후보는 브랜드 사전과 직원 30명 이상 회사 이름 (작은 회사까지 넣으면 엉뚱한 이름이 잡힌다).
    """
    global _SUGGEST
    import difflib
    if _SUGGEST is None:
        big = DATA[DATA["members"] >= 30].sort_values("members", ascending=False).drop_duplicates("key_nm")
        names = {**{_key(b): b for b in [*BRANDS, *UNVERIFIED]}, **dict(zip(big["key_nm"], big["sample_nm"]))}
        _SUGGEST = {_jamo(k): v for k, v in names.items() if k}
    k = _key(query)
    if not k:
        return None
    best = difflib.get_close_matches(_jamo(k), list(_SUGGEST), n=1, cutoff=0.75)
    if not best or best[0] == _jamo(k):
        return None
    name = _SUGGEST[best[0]]
    top = search_company(name, limit=1)
    return name if top and top[0]["members"] >= 10 else None


def suggest_brand(query: str) -> str | None:
    """잘 알려진 브랜드와 한 글자쯤 다르면 그 브랜드 ('토수' → '토스'). 같은 이름의 작은 회사(토수종합건설)가 있어도 묻는다."""
    import difflib
    k = _key(query)
    if not k or to_legal(query):  # 이미 브랜드명이면 묻지 않는다
        return None
    brands = {_jamo(_key(b)): b for b in [*BRANDS, *UNVERIFIED]}
    best = difflib.get_close_matches(_jamo(k), list(brands), n=1, cutoff=0.7)
    if not best or best[0] == _jamo(k):
        return None
    b = brands[best[0]]
    # '카카오' → '카카오엔터', '현대' → '현대차'처럼 검색어가 브랜드 이름의 일부면 오타가 아니다. 글자 수도 비슷해야 한다
    if k in _key(b) or abs(len(_key(b)) - len(k)) > 1:
        return None
    return b


@mcp.tool()
def get_salary_estimate(company_key: str, region: str | None = None) -> dict:
    """한 회사의 추정 평균 연봉(만 원), 오차 범위, 월 퇴사율, 업종 내 위치, 주의 사항을 돌려준다.

    region(시·도 이름, 예: "부산")을 주면 그 지역 사업장만의 추정(region_detail)도 함께 준다.
    전국 직원을 사업장 한 곳으로 신고한 회사(삼성전자 등)는 지역별로 나눌 수 없어 그렇다고 알려준다.
    """
    out = _summary(_row(company_key))
    if region:
        out["region_detail"] = _region_detail(company_key, region.strip())
    return out


def _region_detail(company_key, region):
    sido = next((s for s in set(DATA["sido"].dropna()) if region.startswith(s) or s.startswith(region[:2])), None)
    if sido is None:
        return {"note": f"'{region}'은(는) 시·도 이름으로 알아보지 못했다. 서울·부산·경기처럼 시·도로 묻는다."}
    part = REGION_SITES[(REGION_SITES["company_key"] == company_key) & (REGION_SITES["sido"] == sido)] \
        if not REGION_SITES.empty else REGION_SITES
    if part.empty:
        home = _text(_row(company_key)["sido"])
        if home == sido:
            return {"region": sido, "note": f"이 회사는 사업장이 {sido}에만 등록돼 있어 회사 전체 추정이 곧 {sido} 추정이다."}
        return {"region": sido, "note": f"이 회사는 국민연금에 {sido} 사업장이 따로 등록돼 있지 않다. 직원을 {home or '다른 지역'} "
                                       "사업장 한 곳으로 몰아 신고하는 회사가 많아서, 지역별로 나눌 수 없고 회사 전체 추정만 있다."}
    p = part.iloc[0]
    return {"region": sido, "members": int(p["members"]), "company_members": int(p["company_members"]),
            "estimated_salary_text": _won_text(p["est_corrected"]),
            "likely_range_text": f"{_won_text(p['range50_low'])} ~ {_won_text(p['range50_high'])}",
            "range_text": f"{_won_text(p['range_low'])} ~ {_won_text(p['range_high'])}",
            "note": "그 지역 사업장의 보험료로 계산한 추정. 보정 모델은 회사 단위로 만들었으므로 지역 간 차이는 보험료 비율로 옮겼다."}


@mcp.tool()
def similar_companies(company_key: str, limit: int = 5) -> dict:
    """비슷한 회사 중 추정 연봉이 더 높은 곳을 찾는다 (이직 준비용).

    '비슷한' = 같은 업종(같은 업종 회사가 20곳 미만이거나 업종이 비어 있으면 같은 업종 묶음) + 직원 수 0.5~2배.
    추정 연봉이 이 회사보다 높은 곳을 높은 순으로. 직원 30명 미만 회사는 숫자가 흔들려서 뺀다.
    """
    r = _row(company_key)
    same = DATA["intp_nm"] == r["intp_nm"]
    basis = f"같은 업종({_text(r['intp_nm'])})"
    if filters.group_of(r["intp_nm"]) == filters.UNKNOWN or same.sum() < 20:
        same = DATA["group"] == r["group"]
        basis = f"같은 업종 묶음({r['group']})"
    lo, hi = max(30, r["members"] * 0.5), max(60, r["members"] * 2)
    pool = DATA[same & DATA["members"].between(lo, hi) & (DATA["est_corrected"] > r["est_corrected"])
                & (DATA["company_key"] != company_key)]
    top = pool.nlargest(max(1, min(limit, 10)), "est_corrected")
    return {"base": {"name": r["sample_nm"], "members": int(r["members"]), "estimated_salary_text": _won_text(r["est_corrected"])},
            "basis": f"{basis}, 직원 {int(lo):,}~{int(hi):,}명",
            "count_higher": int(len(pool)),
            "companies": [{"company_key": x.company_key, "name": x.sample_nm, "members": int(x.members),
                           "region": _text(x.sido), "estimated_salary_manwon": _manwon(x.est_corrected),
                           "estimated_salary_text": _won_text(x.est_corrected),
                           "range_manwon": [_manwon(x.range_low), _manwon(x.range_high)],
                           "likely_range_manwon": [_manwon(x.range50_low), _manwon(x.range50_high)],
                           "dart_actual_salary_manwon": _manwon(x.dart_avg_salary),
                           "monthly_exit_rate_pct": round(float(x.monthly_exit_rate) * 100, 1)} for x in top.itertuples()],
            "note": "추정치끼리 비교한 것이라 차이가 범위 안이면 실제로는 비슷할 수 있다."}


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
    # 대형 게임사는 '게임'이 아니라 '응용 소프트웨어 개발 및 공급업'으로 등록돼 있어 게임 키워드에 안 잡힌다
    # (평가 q13: 회사가 10곳 넘게 잡혀 위 안내가 안 나가자, 에이전트가 작은 게임사만 답했다)
    if "게임" in industry_keyword:
        note = ((note + " ") if note else "") + (
            "대형 게임사(넥슨코리아, 크래프톤, 엔씨, 넷마블, 스마일게이트)는 '응용 소프트웨어 개발 및 공급업'으로 등록돼 "
            "이 결과에 없다. 게임 회사를 물으면 이 회사들도 search_company로 찾아 compare_companies로 함께 비교한다.")
    return {
        "note": note,
        "cap_monthly_won": META["cap_monthly"],  # 상한을 말할 때 근거로 쓰도록 (평가 q12에서 기억으로 쓴 상한이 근거 없음으로 잡힘)
        "cap_text": f"보험료 상한: 기준소득월액 월 {META['cap_monthly'] / 1e4:,.0f}만 원, 연 {CAP_ANNUAL / 1e4:,.0f}만 원",
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
        # 평가에서 모델이 상한을 기억으로 '월 617만 원'(2025년 값)·'월 790만 원'으로 써서, 지금 값을 문장으로 준다
        "cap_text": f"보험료 상한: 기준소득월액 월 {META['cap_monthly'] / 1e4:,.0f}만 원 (2026년 7월부터), 연으로 {CAP_ANNUAL / 1e4:,.0f}만 원",
        "accuracy_text": f"상장사 {META['train_companies']:,}곳 교차검증: 평균 오차율 1차 추정 14.6% → 보정 후 11.1%. "
                         "순위 상관 0.88이라 금액보다 회사끼리 비교에 더 믿을 만하다",
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
