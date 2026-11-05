"""조건으로 회사 찾기: 업종 묶음·지역·규모·연봉대로 거른다 (AI를 거치지 않아 무료·즉시).

국민연금 업종은 1,232가지로 너무 잘게 나뉘어 있어서, 이름에 든 낱말로 14개 묶음으로 모은다.
위에서부터 먼저 걸리는 묶음으로 간다 (예: "반도체 제조업"은 제조보다 반도체·전자가 먼저).
"""
import re

import pandas as pd

GROUPS = [
    ("IT·소프트웨어", "소프트웨어|정보 서비스|데이터베이스|포털|시스템 통합|프로그래밍|자료 처리|호스팅|게임|전자상거래"),
    ("금융·보험", "은행|금융|증권|보험|신용|투자|자산 운용|카드|저축|여신"),
    ("반도체·전자", "반도체|전자 부품|전자부품|디스플레이|통신장비|컴퓨터 제조|인쇄회로|전자집적"),
    ("자동차·기계·조선", "자동차|기계|엔진|선박|항공기|로봇|금형|장비 제조"),
    ("화학·제약·바이오", "의약|화학|화장품|바이오|플라스틱|고무|석유|정제"),
    ("에너지·통신", "발전업|전기 공급|가스|에너지|통신업|전기 통신"),
    ("미디어·광고·엔터", "광고|방송|출판|영화|음악|오디오|콘텐츠|신문|매니저업|기록매체"),
    ("건설·부동산", "건설|공사업|토목|건축|부동산|임대업"),
    ("유통·물류", "도매|소매|운송|물류|창고|택배|화물|슈퍼마켓"),
    ("의료·복지", "병원|의원|요양|복지|보건"),
    ("교육·연구", "교육|학원|학교|연구개발"),
    ("숙박·음식", "음식점|숙박|호텔|주점|커피"),
    ("기타 제조", "제조업"),
]
UNKNOWN = "업종 정보 없음"
OTHER = "기타 서비스"
GROUP_NAMES = [g for g, _ in GROUPS] + [OTHER, UNKNOWN]

SIZES = {"전체": (0, None), "50명 미만": (0, 50), "50~300명": (50, 300),
         "300~1,000명": (300, 1000), "1,000명 이상": (1000, None)}


def group_of(industry):
    if not isinstance(industry, str) or industry in ("BIZ_NO미존재사업장", "해당없음", ""):
        return UNKNOWN
    for name, pattern in GROUPS:
        if re.search(pattern, industry):
            return name
    return OTHER


def add_groups(data):
    """업종 이름 1,232가지만 묶음을 계산해서 회사 51만 곳에 붙인다."""
    names = data["intp_nm"].astype("object")
    mapping = {n: group_of(n) for n in names.dropna().unique()}
    return names.map(mapping).fillna(UNKNOWN)


def in_regions(data, regions, region_sites=None):
    """그 지역 '사업장'만 남긴다. 여러 시·도에 사업장이 있는 회사는 회사 전체 대신 그 지역 몫(region_sites)을 쓴다.

    예: 현대제철을 충남으로 거르면 회사 전체 11,110명이 아니라 충남 사업장 6,694명과 그 추정 연봉이 나온다.
    사업장이 한 시·도에만 있는 회사(삼성전자 등 전국 직원을 본사로 신고한 회사 포함)는 그 시·도로만 잡힌다.
    """
    if not regions:
        return data
    if region_sites is None or region_sites.empty:
        return data[data["sido"].isin(regions)]
    split = data["company_key"].isin(region_sites["company_key"])
    whole = data[~split & data["sido"].isin(regions)]
    part = region_sites[region_sites["sido"].isin(regions)]
    info = data.set_index("company_key").loc[part["company_key"], ["group", "cap_ratio"]].reset_index(drop=True)
    part = part.reset_index(drop=True).assign(group=info["group"], cap_ratio=info["cap_ratio"], dart_avg_salary=float("nan"))
    # 회사 일부만 보는 줄은 이름 뒤에 지역을 붙이고, 회사 전체의 공시 연봉은 비교하지 않는다
    partial = part["members"] < part["company_members"]
    part.loc[partial, "sample_nm"] = part.loc[partial, "sample_nm"].astype(str) + " (" + part.loc[partial, "sido"].astype(str) + " 사업장)"
    return pd.concat([whole, part], ignore_index=True)


def find(data, groups=(), regions=(), size="전체", salary=(None, None), growing=False, listed=False,
         min_members=10, limit=20, region_sites=None, hiring=None):
    """조건에 맞는 회사를 추정 연봉 높은 순으로. 10명 미만은 숫자가 불안정해서 빼고 small_summary로 묶어 본다.

    hiring: 회사별 2025년 1년 입사율(company_key → 비율). 주면 '요즘 채용 많이 하는 순'으로 줄 세운다.
    직원 30명 미만은 몇 명만 뽑아도 비율이 크게 튀어서 뺀다.
    """
    data = in_regions(data, regions, region_sites)
    m = data["members"] >= min_members
    if groups:
        m &= data["group"].isin(groups)
    lo, hi = SIZES[size]
    m &= data["members"] >= max(lo, min_members)
    if hi:
        m &= data["members"] < hi
    if salary[0] is not None:
        m &= data["est_corrected"] >= salary[0] * 1e4
    if salary[1] is not None:
        m &= data["est_corrected"] <= salary[1] * 1e4
    if growing:
        m &= data["hires"] > data["exits"]
    if listed:
        m &= data["dart_avg_salary"].notna()
    sub = data[m]
    if hiring is not None:
        sub = sub[sub["members"] >= 30].assign(hire_rate=lambda x: x["company_key"].map(hiring)).dropna(subset=["hire_rate"])
        return len(sub), sub.nlargest(limit, "hire_rate")
    return len(sub), sub.nlargest(limit, "est_corrected")


def small_summary(data, groups=(), regions=(), small=10, region_sites=None):
    """직원 10명 미만 사업장은 한 곳씩 보면 숫자가 흔들려서, 조건이 같은 곳끼리 하나로 묶어 평균을 낸다.

    평균은 직원 수로 가중한다: (각 회사 추정 연봉 × 직원 수)의 합 ÷ 전체 직원 수 = 소규모 사업장에서 일하는 사람의 평균.
    """
    data = in_regions(data, regions, region_sites)
    m = (data["members"] > 0) & (data["members"] < small)
    if groups:
        m &= data["group"].isin(groups)
    sub = data[m & data["est_corrected"].notna()]
    if sub.empty:
        return None
    w = sub["members"].astype(float)
    q25, q75 = sub["est_corrected"].quantile([0.25, 0.75]) / 1e4
    return {"count": int(len(sub)), "workers": int(w.sum()),
            "avg_manwon": int(round((sub["est_corrected"] * w).sum() / w.sum() / 1e4)),
            "median_manwon": int(round(sub["est_corrected"].median() / 1e4)),
            # 작은 사업장끼리도 차이가 커서, 가운데 50% 사업장이 어디쯤인지도 준다
            "middle50_manwon": [int(round(q25)), int(round(q75))]}


SHRINK_K = 10      # '사람 10명어치' 무게를 업종 평균에 준다: 직원 10명이면 회사 값과 업종 평균을 반반
SHRINK_UNDER = 20  # 20명 이상은 원래 결과만 보여준다 (사용자와 정한 기준)


def cell_means(data):
    """(시·도, 업종 묶음)마다 SHRINK_UNDER(20명) 미만 회사의 일하는 사람 기준 평균 추정 연봉. 수축 추정의 당기는 쪽.

    처음엔 모든 회사로 평균을 냈더니 큰 회사 직원이 대부분이라, 작은 회사를 큰 회사 수준으로 끌어올렸다
    (시즈닝게임즈 3,452만 → 5,045만, 경기 IT 평균 6,318만). 비슷한 규모끼리의 평균으로 바꿨다.
    """
    d = data[(data["members"] > 0) & (data["members"] < SHRINK_UNDER)]
    w = d["members"].astype(float)
    g = (d.assign(_w=w, _x=d["est_corrected"] * w).groupby(["sido", "group"], observed=True)[["_x", "_w"]].sum())
    return (g["_x"] / g["_w"]).to_dict()


def shrink(est, members, cell_mean, k=SHRINK_K):
    """수축 추정(참고용·검증 안 됨): 직원이 적을수록 같은 지역·업종 평균 쪽으로 당긴다.

    값 = (직원 수 × 회사 추정 + k × 업종 평균) ÷ (직원 수 + k). 3명이면 업종 평균 쪽 77%, 10명이면 반반, 19명이면 34%.
    작은 회사는 몇 사람 소득에 크게 흔들려서 흔들림은 줄지만, 10명 미만 상장사가 거의 없어 더 정확해지는지는
    확인할 수 없다. 작지만 연봉이 아주 높은 회사는 오히려 끌려 내려갈 수 있다. 그래서 원래 추정을 바꾸지 않고 따로 보여준다.
    """
    w = members / (members + k)
    return w * est + (1 - w) * cell_mean, w


def to_rows(top):
    """그래프(range_chart)가 쓰는 꼴로 바꾼다. 도구 결과와 같은 키를 쓴다."""
    man = lambda v: None if pd.isna(v) else int(round(v / 1e4))  # noqa: E731
    text = lambda v: None if pd.isna(v) else v  # noqa: E731  빈 지역·업종(NaN)은 None으로
    return [{"company_key": r.company_key, "name": r.sample_nm, "industry": text(r.intp_nm), "region": text(r.sido),
             "members": int(r.members), "estimated_salary_manwon": man(r.est_corrected),
             "range_manwon": [man(r.range_low), man(r.range_high)],
             "likely_range_manwon": [man(r.range50_low), man(r.range50_high)],
             "dart_actual_salary_manwon": man(r.dart_avg_salary),
             "hire_rate_pct": None if not hasattr(r, "hire_rate") else round(float(r.hire_rate) * 100)}
            for r in top.itertuples()]
