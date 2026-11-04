"""회사 연봉 AI 에이전트 — 웹 화면 (Streamlit).

src/agent.py의 에이전트(직접 만든 반복 구조 + 도구 5개)를 그대로 쓰고, 화면만 붙인다.
- 비밀번호: 무료 AI 한도를 다른 사람이 다 쓰지 않도록 간단한 비밀번호를 건다
- 비밀 값(GEMINI_API_KEY, APP_PASSWORD)은 코드가 아니라 Streamlit의 secrets 설정에서 읽는다
- 답변 아래에 도구 결과(추정값·범위)로 그래프와 숫자 카드를 그린다. 글은 AI가, 숫자 그림은 데이터에서 바로
로컬 실행 (WSL): ~/venvs/pension/bin/streamlit run app/streamlit_app.py
"""
import base64
import html
import os
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
GITHUB = "https://github.com/codus1111/pension-salary"

st.set_page_config(page_title="회사 연봉 AI", page_icon="💼", layout="wide", initial_sidebar_state="collapsed")

HERO = base64.b64encode((ROOT / "app" / "static" / "hero.webp").read_bytes()).decode()
SUGGESTIONS = [
    ("회사 연봉 알아보기", "토스 평균 연봉 어느 정도야?"),
    ("두 회사 비교하기", "네이버랑 카카오 비교해줘"),
    ("업종별로 살펴보기", "증권업계에서 연봉 높은 회사 어디야?"),
]

# 디자인: 연한 하늘색 배경, 그림이 있는 큰 첫 화면, 둥근 검색창, 흰 카드
st.markdown(f"""<style>
:root {{ --ink:#192c49; --muted:#62758d; --blue:#0868ec; --line:#e1eaf5; }}
.stApp {{ background:#f2f6fb; }}
.stApp, .stApp p, .stApp li {{ color:var(--ink); }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display:none; }}
header[data-testid="stHeader"] {{ background:transparent; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width:min(1600px, 94vw); margin:0 auto; padding:1.6rem 2rem 2rem; }}
/* 큰 모니터(1600px 이상)에서는 글씨와 첫 화면도 같이 키운다 */
@media (min-width:1600px) {{
  .stApp p, .stApp li {{ font-size:17px; }}
  .s-hero h1 {{ font-size:56px !important; }}
  .s-desc {{ font-size:17px !important; }}
  .s-eyebrow {{ font-size:12px !important; }}
  .s-brand {{ font-size:24px !important; }}
  .st-key-hero {{ min-height:480px !important; padding:56px 52px 34px !important; }}
  .st-key-hero input {{ font-size:17px !important; }}
  .st-key-hero [data-testid="stFormSubmitButton"] button {{ min-height:52px; }}
  .s-h2 {{ font-size:25px !important; }}
  .s-caption, .s-note {{ font-size:14px !important; }}
  [class*="st-key-sg"] button {{ min-height:118px; }}
  [class*="st-key-sg"] button p {{ font-size:16px !important; }}
  [class*="st-key-sg"] button::before {{ font-size:13px !important; }}
  .s-card b {{ font-size:22px; }}
}}
.s-nav {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:18px; }}
.s-brand {{ font-size:20px; font-weight:800; letter-spacing:-.8px; color:var(--ink); }}
.s-brand span {{ color:var(--blue); }}
.s-nav a {{ color:#48617f !important; font-size:12px; text-decoration:none; border:1px solid #d9e5f4;
            background:white; padding:9px 16px; border-radius:99px; }}
.st-key-hero {{ position:relative; overflow:hidden; border:1px solid white; border-radius:30px; background:
               linear-gradient(90deg,#eef6ff 52%,#eef6ff00 68%),
               url(data:image/webp;base64,{HERO}) no-repeat right center / auto 100%, #eef6ff;
               box-shadow:0 14px 50px #7c9abb12; padding:42px 38px 26px; min-height:360px; }}
.s-eyebrow {{ font-size:10px; font-weight:750; letter-spacing:2px; color:#1766bf; margin:0 0 20px; }}
.s-hero h1 {{ font-size:clamp(28px,3.8vw,42px); font-weight:800; line-height:1.35; letter-spacing:-1.9px;
              padding:0; margin:0 0 18px; color:var(--ink); }}
.s-hero h1 [data-heading-text] {{ color:var(--ink); }}
.s-hero h1 .s-blue {{ color:var(--blue); }}
.s-hero [data-testid="stHeaderActionElements"] {{ display:none; }}
.s-desc {{ font-size:14px; line-height:1.85; color:#526a85 !important; margin:0 0 22px; }}
.st-key-hero [data-testid="stForm"] {{ max-width:680px; background:white; border:1px solid #c4d9f5; border-radius:99px;
               box-shadow:0 8px 28px #447bb91c; padding:6px 6px 6px 18px; }}
.st-key-hero [data-testid="stForm"] [data-testid="stHorizontalBlock"] {{ align-items:center; gap:6px; }}
.st-key-hero [data-testid="stTextInputRootElement"], .st-key-hero [data-baseweb="input"] {{ border:0 !important; background:transparent !important; }}
.st-key-hero input {{ font-size:15px; background:transparent !important; }}
.st-key-hero [data-testid="stFormSubmitButton"] button {{ background:var(--blue); color:white; border:0; border-radius:99px;
               min-height:44px; width:100%; font-weight:650; }}
.st-key-hero [data-testid="stFormSubmitButton"] button:hover {{ background:#0757c8; color:white; }}
.s-note {{ font-size:11px; color:#4f6e91 !important; margin:10px 0 0 18px; }}
.st-key-workspace {{ background:white; border:1px solid var(--line); border-radius:25px; padding:28px 30px;
                    margin-top:22px; box-shadow:0 10px 40px #7c9abb0a; }}
.st-key-explore {{ background:white; border:1px solid var(--line); border-radius:25px; padding:28px 30px;
                  margin:4px 0 18px; box-shadow:0 10px 40px #7c9abb0a; }}
@media (max-width:640px) {{ .st-key-explore {{ padding:22px 16px; }} }}
.s-h2 {{ font-size:21px; font-weight:750; letter-spacing:-.7px; margin:0 0 4px; color:var(--ink); }}
.s-caption {{ font-size:13px; color:var(--muted) !important; margin:0; }}
[class*="st-key-sg"] button {{ background:#f5f9fe; border:1px solid #e5eef9; border-radius:16px; min-height:96px;
               width:100%; justify-content:flex-start; text-align:left; padding:16px 14px; color:#24456c; }}
[class*="st-key-sg"] button:hover {{ background:#edf5ff; border-color:#a9cafa; color:#24456c; }}
[class*="st-key-sg"] button p {{ font-size:13px; font-weight:500; }}
[class*="st-key-sg"] button::before {{ position:absolute; top:14px; left:14px; color:#4572a9; font-size:11px; font-weight:650; }}
.st-key-sg0 button::before {{ content:"🏢  회사 연봉 알아보기"; }}
.st-key-sg1 button::before {{ content:"⚖️  두 회사 비교하기"; }}
.st-key-sg2 button::before {{ content:"📊  업종별로 살펴보기"; }}
[class*="st-key-sg"] button > div {{ margin-top:18px; width:100%; justify-content:flex-start; text-align:left; }}
[class*="st-key-sg"] button p {{ text-align:left; }}
.st-key-reset button {{ border-radius:12px; border:1px solid #dbe6f4; color:#24456c; font-size:12px; }}
.s-user {{ width:fit-content; max-width:75%; margin:6px 0 16px auto; background:#edf4ff; border:1px solid #e6eef8; border-radius:16px 16px 4px 16px; padding:14px 18px;
           font-size:14px; line-height:1.8; }}
.s-user b, .s-who {{ display:block; color:#216aca; font-size:11px; font-weight:700; margin-bottom:4px; }}
[class*="st-key-answer"] p, [class*="st-key-answer"] li {{ font-size:14.5px; line-height:1.8; }}
[class*="st-key-answer"] h1, [class*="st-key-answer"] h2, [class*="st-key-answer"] h3 {{ font-size:17px; padding:10px 0 4px; }}
[class*="st-key-answer"] {{ background:#f7faff; border:1px solid #e6eef8; border-radius:16px; padding:16px 20px; margin-bottom:10px; }}
.s-cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin:6px 0 4px; }}
.s-card {{ background:white; border:1px solid var(--line); border-radius:14px; padding:12px 14px; }}
.s-card small {{ display:block; color:var(--muted); font-size:11px; margin-bottom:4px; }}
.s-card b {{ font-size:18px; letter-spacing:-.5px; color:var(--ink); }}
.s-card em {{ display:block; font-style:normal; color:var(--muted); font-size:11px; margin-top:2px; }}
.s-card.main b {{ color:var(--blue); }}
.s-cards3 {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
.s-cards2 {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
.s-basis {{ background:white; border:1px solid var(--line); border-radius:20px; padding:18px 22px; margin:4px 0 14px; }}
.s-basis > b {{ font-size:15px; color:var(--ink); }}
.s-basis table {{ width:100%; border-collapse:collapse; margin-top:8px; font-size:13px; }}
.s-basis th {{ width:24%; text-align:left; color:#4572a9; font-weight:650; vertical-align:top; padding:9px 10px 9px 0; border:0;
               border-top:1px solid #edf2f8; }}
.s-basis td {{ padding:9px 0; border:0; border-top:1px solid #edf2f8; color:var(--ink); }}
.s-basis td span {{ color:var(--muted); font-size:12px; }}
@media (max-width:640px) {{ .s-basis th, .s-basis td {{ display:block; width:100%; }} .s-basis td {{ border-top:0; padding-top:0; }} }}
.s-cards1 {{ grid-template-columns:1fr; }}
.hc {{ background:white; border:1px solid var(--line); border-radius:14px; padding:12px 14px 8px; margin:10px 0 4px; }}
.hc small {{ color:var(--muted); font-size:11px; }}
.hc-bars {{ display:grid; grid-template-columns:repeat(12,1fr); gap:6px; height:84px; align-items:end; margin-top:8px; }}
.hc-bar {{ display:flex; flex-direction:column; justify-content:flex-end; height:100%; }}
.hc-bar span {{ display:block; background:#8dbaf5; border-radius:4px 4px 0 0; min-height:3px; }}
.hc-bar:hover span {{ background:#0868ec; }}
.hc-bar em {{ font-style:normal; font-size:10px; color:#8193a8; text-align:center; margin-top:3px; }}
/* HTML 범위 그래프 */
.rc {{ margin:12px 0 4px; }}
.rc-row {{ display:grid; grid-template-columns:minmax(90px,190px) 1fr 64px; gap:12px; align-items:center; min-height:34px; }}
.rc-name {{ font-size:13px; color:#3a5170; text-align:right; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.rc-track {{ position:relative; height:20px; background:repeating-linear-gradient(90deg,transparent 0 calc(16.66% - 1px),#edf2f8 0 16.66%); border-radius:6px; }}
.rc-track span {{ position:absolute; top:0; height:20px; border-radius:6px; }}
.rc-w {{ background:#dbe8fb; }}
.rc-l {{ background:#8dbaf5; }}
.rc-e {{ width:14px !important; height:14px !important; top:3px !important; margin-left:-7px; background:#0868ec;
         transform:rotate(45deg); border-radius:2px !important; box-shadow:0 0 0 2px white; }}
.rc-d {{ width:4px; margin-left:-2px; top:-4px !important; height:28px !important; background:#f08c2e; border-radius:2px !important; }}
.rc-val {{ font-size:12px; color:#62758d; font-variant-numeric:tabular-nums; display:flex; flex-direction:column; line-height:1.3; }}
.rc-val .v-e {{ color:#0868ec; }}
.rc-val .v-d {{ color:#d9731a; }}
.rc-legend {{ display:flex; flex-wrap:wrap; gap:6px 18px; font-size:12px; color:#3a5170; margin:0 0 10px; }}
.rc-legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.rc-legend i {{ display:inline-block; }}
.rc-legend .rc-unit {{ margin-left:auto; color:#8193a8; }}
.k-e {{ width:10px; height:10px; background:#0868ec; transform:rotate(45deg); border-radius:1px; }}
.k-l {{ width:22px; height:10px; background:#8dbaf5; border-radius:4px; }}
.k-d {{ width:4px; height:14px; background:#f08c2e; border-radius:2px; }}
.rc-axis {{ min-height:22px; }}
.rc-ticks {{ background:none; height:16px; }}
.rc-ticks span {{ transform:translateX(-50%); font-size:11px; color:#8193a8; white-space:nowrap; height:auto; }}
.s-table {{ overflow-x:auto; margin:6px 0 10px; border:1px solid var(--line); border-radius:14px; }}
.s-table table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.s-table th {{ background:#f5f9fe; color:#4a5f7a; font-weight:650; text-align:left; padding:9px 12px; border:0; }}
.s-table td {{ padding:8px 12px; border:0; border-top:1px solid #edf2f8; }}
.s-table .t-num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
@media (max-width:640px) {{
  /* 휴대폰: 회사 이름은 막대 위 한 줄, 눈금은 하나 걸러 */
  .rc-row {{ grid-template-columns:1fr 46px; gap:2px 8px; min-height:0; margin-bottom:6px; }}
  .rc-name {{ grid-column:1 / -1; text-align:left; font-size:12px; }}
  .rc-axis .rc-name {{ display:none; }}
  .rc-ticks span:nth-child(even) {{ display:none; }}
  .s-cards.s-cards3 {{ grid-template-columns:1fr; }}
  [class*="st-key-answer"] {{ padding:12px 10px; }}
  .s-table .t-hide {{ display:none; }}
}}
.s-small {{ background:#f5f9fe; border:1px solid #e5eef9; border-radius:16px; padding:14px 16px; margin:6px 0 12px; }}
.s-small > small {{ color:#4572a9; font-size:12px; font-weight:650; }}
.s-small > em {{ display:block; font-style:normal; color:var(--muted); font-size:11px; margin-top:6px; }}
@media (max-width:640px) {{ .s-small .s-cards {{ grid-template-columns:1fr !important; }} }}
.s-foot {{ display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; color:#6d8098; font-size:11px;
           padding:22px 4px 4px; }}
.s-foot a {{ color:#48617f !important; }}
[data-testid="stExpander"] details {{ border:1px solid var(--line); border-radius:15px; background:#ffffffb8; }}
@media (max-width:640px) {{
  .st-key-hero {{ background-size:100% auto; background-position:center bottom; padding:28px 20px 22px; min-height:420px; }}
  .s-hero h1 {{ font-size:30px; letter-spacing:-1.3px; }}
  .st-key-workspace {{ padding:22px 16px; }}
  .s-cards {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .s-user {{ max-width:88%; }}
  /* 좁은 화면에서도 검색창(입력칸+버튼)과 제목줄(제목+초기화)은 한 줄로 */
  .st-key-hero [data-testid="stHorizontalBlock"], .st-key-whead [data-testid="stHorizontalBlock"] {{ flex-wrap:nowrap; }}
  .st-key-hero [data-testid="stColumn"]:first-child, .st-key-whead [data-testid="stColumn"]:first-child {{ flex:1 1 auto; min-width:0; width:auto; }}
  .st-key-hero [data-testid="stColumn"]:last-child, .st-key-whead [data-testid="stColumn"]:last-child {{ flex:0 0 72px; min-width:72px; width:72px; }}
  .st-key-hero [data-testid="stForm"] {{ padding:4px 4px 4px 12px; }}
  .st-key-hero input {{ font-size:16px; }}
  [class*="st-key-sg"] button {{ min-height:76px; }}
}}
</style>""", unsafe_allow_html=True)


# 데이터 기준 날짜 (화면 아래 표로 보여준다)
DATA_BASIS = [
    ("추정 연봉", "국민연금 가입 사업장 2026년 9월 자료",
     "보험료의 기준이 되는 소득(기준소득월액)은 매년 7월에 전년도 소득으로 다시 정해져서, 2026년 9월 자료는 2025년 소득을 반영해요."),
    ("검증·보정 기준", "DART 2025 사업연도 사업보고서",
     "대부분 2025년 1월 1일 ~ 12월 31일 사업연도이고, 보통 2026년 3월에 공시된 자료예요. 상장사 2,392곳의 1인 평균 급여를 정답으로 썼어요."),
    ("1년 퇴사율 · 직원 수 추이", "국민연금 2025년 1월 ~ 12월 (12개월)",
     "12개월 동안의 자격 상실자 합계 ÷ 12개월 평균 가입자예요. 계열사 이동도 포함돼요."),
    ("이번 달 입·퇴사", "국민연금 2026년 9월 한 달", "한 달치라 개편·이동이 있으면 크게 흔들려요. 참고용이에요."),
]
DATA_BASIS_HTML = ('<div class="s-basis"><b>📅 데이터 기준 날짜</b><table>' + "".join(
    f"<tr><th>{a}</th><td><b>{b}</b><br><span>{c}</span></td></tr>" for a, b, c in DATA_BASIS) + "</table></div>")


def secret(name):
    try:
        return st.secrets[name]
    except Exception:  # secrets 파일이 없을 때 (로컬): 환경 변수나 .env에서 읽는다
        return os.environ.get(name)


def nav():
    st.markdown(f'<div class="s-nav"><div class="s-brand">회사 연봉 <span>AI</span></div>'
                f'<a href="{GITHUB}" target="_blank">프로젝트 살펴보기</a></div>', unsafe_allow_html=True)


def hero_copy():
    st.markdown('<div class="s-hero"><p class="s-eyebrow">COMPANY SALARY INTELLIGENCE</p>'
                '<h1>궁금했던 회사 연봉,<br><span class="s-blue">데이터로 알아보세요.</span></h1>'
                '<p class="s-desc">국민연금 데이터와 기업 공시를 바탕으로<br>'
                '평균 연봉부터 회사 비교까지, AI와 함께 살펴보세요.</p></div>', unsafe_allow_html=True)


# 비밀번호 확인
password = secret("APP_PASSWORD")
if password and not st.session_state.get("authed"):
    nav()
    with st.container(key="hero"):
        hero_copy()
        with st.form("login", border=False):
            c1, c2 = st.columns([5, 1])
            typed = c1.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요", label_visibility="collapsed")
            ok = c2.form_submit_button("입장", use_container_width=True)
        st.markdown('<p class="s-note">무료 AI 사용량을 지키기 위해 비밀번호를 받고 있어요.</p>', unsafe_allow_html=True)
    if ok and typed:
        if typed == password:
            st.session_state["authed"] = True
            st.rerun()
        st.error("비밀번호가 맞지 않아요.")
    st.stop()

if secret("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = secret("GEMINI_API_KEY")


@st.cache_resource(show_spinner="데이터를 불러오는 중이에요 (처음 한 번만, 몇 초 걸려요)")
def load_agent():
    import agent  # 51만 개 회사 데이터를 불러온다
    return agent, agent.GeminiProvider()


agent, provider = load_agent()


filters, DATA, REGION = agent.tools.filters, agent.tools.DATA, agent.tools.REGION_SITES  # 에이전트 도구와 같은 표
import evaluate  # noqa: E402  답 속 금액 대조에 평가 채점기의 함수를 그대로 쓴다


# ---------- 답변 아래 그림: 도구 결과에서 회사별 추정값·범위를 모아 그린다 ----------
def collect(trace):
    """도구 결과에서 그래프로 그릴 회사 목록을 뽑는다. 비교·순위 결과가 있으면 그것을, 없으면 단일 조회들을."""
    ranking = compare = None
    singles = {}
    for t in trace:
        r = t.get("result")
        if t["tool"] == "compare_companies" and isinstance(r, list):
            compare = r
        elif t["tool"] in ("industry_ranking", "similar_companies") and isinstance(r, dict) and r.get("companies"):
            ranking = r["companies"]
        elif t["tool"] == "get_salary_estimate" and isinstance(r, dict) and r.get("estimated_salary_manwon"):
            singles[r["company_key"]] = r
    if compare:
        return "compare", compare
    if ranking:
        return "ranking", ranking
    if singles:
        return ("single" if len(singles) == 1 else "compare"), list(singles.values())
    return None, []


def range_chart(rows):
    """회사마다 넓은 범위(80%)·가능성 높은 범위(50%)·추정값(◆)·공시 연봉(|)을 한 줄에 그린다.

    그래프 라이브러리(Vega) 대신 HTML로 직접 그린다: 배포 직후 브라우저가 그래프용 파일을 못 받아
    'Failed to fetch dynamically imported module' 오류가 난 적이 있어서, 추가 파일 없이 보이게 했다.
    """
    rows = sorted([r for r in rows if r.get("estimated_salary_manwon")], key=lambda r: -r["estimated_salary_manwon"])
    if not rows:
        return None
    # 처음엔 넓은 범위(80%)·가능성 높은 범위(50%)를 둘 다 그렸더니 한눈에 안 들어온다는 의견이 있어서,
    # 막대는 '예상 범위(50%)' 하나만 그리고 80% 범위는 마우스를 올렸을 때 글로만 보여준다
    pair = lambda r, k: (r.get(k) or [None, None])  # noqa: E731
    vals = [v for r in rows for v in (*pair(r, "likely_range_manwon"), r["estimated_salary_manwon"],
                                      r.get("dart_actual_salary_manwon")) if v]
    span = max(vals) - min(vals)
    step = 1000 if span > 3000 else 500 if span > 1000 else 200
    lo, hi = (min(vals) // step) * step, -(-max(vals) // step) * step
    hi = hi if hi > lo else lo + step
    pos = lambda v: (v - lo) / (hi - lo) * 100  # noqa: E731
    lines, any_dart = [], False
    for r in rows:
        (a, b), (c, d) = pair(r, "range_manwon"), pair(r, "likely_range_manwon")
        est, dart = r["estimated_salary_manwon"], r.get("dart_actual_salary_manwon")
        any_dart |= bool(dart)
        tip = f"추정 {est:,}만 원" + (f" · 예상 범위 {c:,}~{d:,}만" if c else "") + \
              (f" · 넓게 보면 {a:,}~{b:,}만" if a else "") + (f" · 실제 공시 {dart:,}만" if dart else "")
        bars = (f'<span class="rc-l" style="left:{pos(c):.1f}%;width:{pos(d) - pos(c):.1f}%"></span>' if c else "") + \
               f'<span class="rc-e" style="left:{pos(est):.1f}%"></span>' + \
               (f'<span class="rc-d" style="left:{pos(dart):.1f}%"></span>' if dart else "")
        val = f'<b class="v-e">{est:,}</b>' + (f'<b class="v-d">{dart:,}</b>' if dart else "")
        lines.append(f'<div class="rc-row" title="{html.escape(tip)}"><div class="rc-name">{html.escape(r["name"])}</div>'
                     f'<div class="rc-track">{bars}</div><div class="rc-val">{val}</div></div>')
    n_ticks = int((hi - lo) / step)
    skip = max(1, -(-n_ticks // 6))
    ticks = "".join(f'<span style="left:{pos(lo + i * step):.1f}%">{lo + i * step:,}</span>'
                    for i in range(0, n_ticks + 1, skip))
    legend = ('<div class="rc-legend"><span><i class="k-e"></i>추정 연봉</span>'
              '<span><i class="k-l"></i>예상 범위 (비슷한 회사 2곳 중 1곳이 이 안)</span>'
              + ('<span><i class="k-d"></i>실제 공시 연봉 (상장사)</span>' if any_dart else "")
              + '<span class="rc-unit">단위: 만 원</span></div>')
    return (f'<div class="rc">{legend}{"".join(lines)}<div class="rc-row rc-axis"><div class="rc-name"></div>'
            f'<div class="rc-track rc-ticks">{ticks}</div><div class="rc-val"></div></div></div>')


BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def grounded(a, tol, nums, main):
    """답 속 금액이 도구 결과로 설명되는지. 평가보다 너그럽게 본다 (사용자에게 괜한 경고를 띄우지 않도록).

    - 도구 결과 금액 그대로 (±tol)
    - 회사 연봉끼리의 차이: "네이버가 약 2,800만 원 높다"(공시 14,096 - 11,206 = 2,890)처럼 AI가 계산해 말한 값.
      범위 끝값까지 넣으면 차이 조합이 너무 많아 아무 숫자나 통과하므로, 추정·공시 연봉(main)끼리만 본다
    - '약 …'·'1.4억'처럼 줄여 쓴 금액(tol > 1)은 4%까지 허용
    """
    slack = max(tol, a * 0.04) if tol > 1 else tol
    if any(abs(a - n) <= slack for n in nums):
        return True
    main = sorted(main)
    return any(abs(a - abs(x - y)) <= slack for i, x in enumerate(main) for y in main[i + 1:])


def main_salaries(trace):
    """도구 결과에서 회사별 추정 연봉·공시 연봉만 모은다 (차이 계산 허용용)."""
    out = set()

    def walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k in ("estimated_salary_manwon", "dart_actual_salary_manwon") and isinstance(x, (int, float)):
                    out.add(int(x))
                else:
                    walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    for t in trace:
        walk(t.get("result"))
    return out


def show_answer(text, unchecked=()):
    """AI 답변을 그린다.

    - 굵은 글씨: Markdown은 '**…(…)**의'처럼 닫는 ** 앞이 괄호, 뒤가 한글이면 굵게 인식하지 못해 별표가 그대로 보였다.
      그래서 **…**를 직접 <b>로 바꾼다 (다른 HTML은 이스케이프해서 그대로 글자로 보이게)
    - 숫자 대조: 답 속 금액이 도구 결과에 없으면(옮겨 적다 '1억'을 빠뜨린 경우 등) 경고를 단다
    """
    safe = BOLD_RE.sub(r"<b>\1</b>", html.escape(text or "", quote=False))
    st.markdown(safe, unsafe_allow_html=True)
    if unchecked:
        shown = ", ".join(f"{a:,}만 원" for a in unchecked[:3])
        st.warning(f"글 속 금액 일부({shown})가 데이터와 맞지 않아요. AI가 옮겨 적다 틀렸을 수 있어요. "
                   "아래 카드와 그래프의 숫자는 데이터에서 바로 가져온 값이라 정확해요.", icon="⚠️")


def card(label, value, sub="", main=False):
    return (f'<div class="s-card{" main" if main else ""}"><small>{label}</small><b>{html.escape(str(value))}</b>'
            f'{f"<em>{html.escape(sub)}</em>" if sub else ""}</div>')


def single_cards(r):
    cards = [card("추정 평균 연봉", r["estimated_salary_text"], "회사 전체 평균", main=True),
             card("가장 가능성 높은 범위", r["likely_range_text"].replace(" 원", ""), "2곳 중 1곳이 이 안"),
             card("직원 수", f"{r['members']:,}명", r.get("region") or "")]
    if r.get("dart_actual_salary_text"):
        cards.append(card("실제 공시 연봉", r["dart_actual_salary_text"], "상장사 사업보고서"))
    elif r.get("industry_top_pct"):
        cards.append(card("업종 안 위치", f"상위 {r['industry_top_pct']}%", f"{r['industry_companies']:,}곳 중"))
    # 둘째 줄: 정확도 신호등 · 퇴사율 · 인원 변화
    conf, to = r.get("confidence") or {}, r.get("turnover") or {}
    second = []
    if conf:
        second.append(card("정확도", f"{conf['light']} {conf['level']}", conf["reason"]))
    year = (to or {}).get("year_2025")
    if year:  # 2025년 12개월 실제 합계가 있으면 그걸 먼저 보여준다
        med = year.get("industry_median_annual_exit_rate_pct")
        p = year["annual_exit_rate_pct"]
        second.append(card("1년 퇴사율 (2025년)", f"{p}%",
                           (f"100명 중 {p}명꼴로 나감" if p <= 100 else "단기직이 여러 번 들고 남 (100% 넘음)")
                           + (f" · 업종 중간값 {med}%" if med is not None else " · 직원이 적어 참고만")))
        if year["members_jan"] > 0 and year["members_dec"] > 0:
            diff = year["members_dec"] - year["members_jan"]
            second.append(card("1년 직원 수 변화", f"{diff:+,}명",
                               f"2025년 1월 {year['members_jan']:,} → 12월 {year['members_dec']:,}"))
    elif to:
        med = to.get("industry_median_monthly_exit_rate_pct")
        second.append(card("월 퇴사율" + (" ⚠️" if to.get("unusual_month") else ""), f"{to['monthly_exit_rate_pct']}%",
                           "이번 달 이동이 유난히 많음 (개편 등)" if to.get("unusual_month") else
                           f"업종 중간값 {med}%" if med is not None else "직원이 적어 참고만"))
        second.append(card("이번 달 인원 변화", f"{to['net_change']:+,}명", f"입사 {to['hires']:,} · 퇴사 {to['exits']:,}"))
    out = '<div class="s-cards">' + "".join(cards) + "</div>"
    if second:
        out += f'<div class="s-cards s-cards{len(second)}">' + "".join(second) + "</div>"
    if year and year.get("monthly_members"):
        out += headcount_chart(year["monthly_members"])
    return out


def headcount_chart(series):
    """2025년 월별 직원 수 막대 (HTML). 위아래 차이가 보이도록 가장 작은 달의 90%를 바닥으로 둔다."""
    vals = {k: v for k, v in series.items() if v}
    if len(vals) < 6:
        return ""
    lo, hi = min(vals.values()) * 0.9, max(vals.values())
    bars = "".join(
        f'<div class="hc-bar" title="{k} · {v:,}명"><span style="height:{(v - lo) / (hi - lo or 1) * 100:.0f}%"></span>'
        f'<em>{int(k[5:])}월</em></div>' for k, v in vals.items())
    return (f'<div class="hc"><small>직원 수 추이 · 2025년 1~12월 (가장 적은 달 {min(vals.values()):,}명 · '
            f'가장 많은 달 {max(vals.values()):,}명)</small><div class="hc-bars">{bars}</div></div>')


def similar_block(r):
    """비슷한 규모·업종에서 추정 연봉이 더 높은 회사 (AI 없이 데이터에서 바로)."""
    try:
        sim = agent.tools.similar_companies(r["company_key"], limit=5)
    except Exception:
        return
    if not sim["companies"]:
        return
    with st.expander(f"💼 비슷한 회사 중 연봉이 더 높은 곳 ({sim['count_higher']:,}곳 중 상위 {len(sim['companies'])}곳)"):
        st.caption(f"기준: {sim['basis']} · {sim['note']}")
        st.markdown(range_chart(sim["companies"]), unsafe_allow_html=True)


def show_visuals(kind, rows):
    if not kind:
        return
    if kind == "single":
        st.markdown(single_cards(rows[0]), unsafe_allow_html=True)
    chart = range_chart(rows[:10])
    if chart is not None:
        st.markdown(chart, unsafe_allow_html=True)
        if any(r.get("likely_range_manwon") and r["estimated_salary_manwon"] < r["likely_range_manwon"][0] for r in rows):
            st.caption("💡 파란 마름모가 막대보다 왼쪽에 있으면: 연봉이 높은 회사는 국민연금 상한 때문에 추정이 실제보다 "
                       "낮게 나오는 경향이 있어서, 실제 연봉은 막대(예상 범위) 쪽일 가능성이 더 커요.")
    if kind == "single":
        similar_block(rows[0])


# ---------- 화면 ----------
if "history" not in st.session_state:
    st.session_state["history"] = []   # 에이전트가 기억하는 대화 (도구 호출 포함)
    st.session_state["messages"] = []  # 화면에 보이는 대화

nav()
question = st.session_state.pop("pending_q", None)  # 아래 '조건으로 찾기'에서 누른 회사 질문
with st.container(key="hero"):
    hero_copy()
    with st.form("search", border=False, clear_on_submit=True):
        c1, c2 = st.columns([5, 1])
        typed = c1.text_input("질문", placeholder="🔍  회사 이름이나 궁금한 내용을 검색하세요", label_visibility="collapsed")
        if c2.form_submit_button("검색", use_container_width=True) and typed.strip():
            question = typed.strip()
    st.markdown('<p class="s-note">국민연금 2026년 9월 자료 · DART 2025 사업연도(2025.1.1~12.31) 공시로 검증</p>',
                unsafe_allow_html=True)

with st.container(key="workspace"):
    h1, h2 = st.container(key="whead").columns([5, 1], vertical_alignment="center")
    h1.markdown('<p class="s-h2">이렇게 검색해 보세요</p>'
                '<p class="s-caption">평균 연봉부터 회사 비교까지, 궁금한 내용을 자유롭게.</p>', unsafe_allow_html=True)
    if h2.button("초기화", key="reset", use_container_width=True):
        st.session_state["history"], st.session_state["messages"] = [], []
        st.rerun()
    for i, (col, (_, q)) in enumerate(zip(st.columns(3), SUGGESTIONS)):
        if col.button(q, key=f"sg{i}", use_container_width=True):
            question = q

    for i, m in enumerate(st.session_state["messages"]):
        if m["role"] == "user":
            st.markdown(f'<div class="s-user"><b>나</b>{html.escape(m["content"])}</div>', unsafe_allow_html=True)
        else:
            with st.container(key=f"answer{i}"):
                st.markdown('<span class="s-who">회사 연봉 AI</span>', unsafe_allow_html=True)
                show_answer(m["content"], m.get("unchecked", []))
                show_visuals(m.get("kind"), m.get("rows", []))
                if m.get("tools"):
                    st.caption("사용한 도구: " + " → ".join(m["tools"]))

    if question:
        st.session_state["messages"].append({"role": "user", "content": question})
        st.markdown(f'<div class="s-user"><b>나</b>{html.escape(question)}</div>', unsafe_allow_html=True)
        history = st.session_state["history"]
        before = len(history)
        with st.container(key=f"answer{len(st.session_state['messages'])}"):
            st.markdown('<span class="s-who">회사 연봉 AI</span>', unsafe_allow_html=True)
            with st.status("데이터를 찾아보는 중이에요…", expanded=False) as status:
                try:
                    out = agent.ask(question, provider, history=history, log=lambda s: status.write(s))
                    status.update(label="답을 찾았어요", state="complete")
                except Exception as e:
                    del history[before:]
                    status.update(label="답을 받지 못했어요", state="error")
                    out = None
                    st.error("AI 서버가 바쁘거나 오늘 무료 사용량을 다 썼어요. 잠시 뒤 다시 시도해 주세요.\n\n" + str(e)[:200])
            if out:
                tools = [t["tool"] for t in out["trace"]]
                kind, rows = collect(out["trace"])
                # 이 대화에서 도구가 돌려준 금액 전부와 답 속 금액을 대조한다 (평가 채점기와 같은 함수)
                st.session_state.setdefault("tool_nums", set()).update(evaluate.tool_numbers(out["trace"]))
                st.session_state.setdefault("main_nums", set()).update(main_salaries(out["trace"]))
                unchecked = [a for a, tol in evaluate.amounts_in(out["answer"] or "")
                             if not grounded(a, tol, st.session_state["tool_nums"], st.session_state["main_nums"])]
                show_answer(out["answer"], unchecked)
                show_visuals(kind, rows)
                if tools:
                    st.caption("사용한 도구: " + " → ".join(tools))
                st.session_state["messages"].append({"role": "assistant", "content": out["answer"], "tools": tools,
                                                     "kind": kind, "rows": rows, "unchecked": unchecked})

    st.markdown('<p class="s-caption" style="font-size:11px;margin-top:14px">회사 전체의 평균 추정치예요. '
                '신입·직무·개인 연봉과 다르며, 답변의 오차 범위도 함께 확인해 주세요.</p>', unsafe_allow_html=True)

def small_card(s, where):
    """10명 미만 소규모 사업장을 하나로 묶은 평균 카드."""
    return ('<div class="s-small"><small>🏠 소규모 사업장 (직원 10명 미만) · ' + html.escape(where) + '</small>'
            f'<div class="s-cards" style="grid-template-columns:repeat(3,minmax(0,1fr))">'
            + card("평균 추정 연봉", f"{s['avg_manwon']:,}만 원", "일하는 사람 기준 평균", main=True)
            + card("사업장 수", f"{s['count']:,}곳", f"일하는 사람 {s['workers']:,}명")
            + card("중간값", f"{s['median_manwon']:,}만 원", "사업장 한가운데 값")
            + '</div><em>작은 사업장은 한 곳씩 보면 오차가 커서 같은 조건끼리 묶어 평균을 냈어요.</em></div>')


def ask_about(name):
    st.session_state["pending_q"] = f"{name} 평균 연봉 자세히 알려줘"
    st.toast("위쪽 대화 칸에서 AI가 답하고 있어요 ⬆️")
    st.rerun()


# ---------- 조건으로 찾기: AI 없이 데이터에서 바로 (무료·즉시) ----------
with st.container(key="explore"):
    st.markdown('<p class="s-h2">회사 직접 찾기</p><p class="s-caption">AI를 거치지 않고 데이터에서 바로 찾아요. '
                '브랜드 이름(토스, 배민, 스타벅스 등)으로도 찾을 수 있어요.</p>', unsafe_allow_html=True)
    by_name, by_filter = st.tabs(["🔎 이름으로 찾기", "🎛️ 조건으로 찾기"])

    with by_name:
        name_q = st.text_input("회사 이름", placeholder="예: 토스, 배민, 현대차, 카카오", label_visibility="collapsed")
        if name_q.strip():
            hits = agent.tools.search_company(name_q, limit=8)
            if not hits:
                st.info("찾는 회사가 없어요. 정식 회사 이름(법인명)으로도 찾아보세요.")
            for j, h in enumerate(hits):
                c1, c2 = st.columns([5, 1], vertical_alignment="center")
                tiny = h["members"] < 10
                c1.markdown(f"**{h['name']}**{' `소규모`' if tiny else ''}  \n<span class='s-caption'>"
                            f"{h['industry'] if filters.group_of(h['industry']) != filters.UNKNOWN else '업종 정보 없음'}"
                            f" · {h['region'] or '-'} · {h['members']:,}명"
                            f"{' · 상장사' if h['listed'] else ''}</span>", unsafe_allow_html=True)
                if c2.button("AI에게 묻기", key=f"nm{j}", use_container_width=True):
                    ask_about(h["name"])
            # 10명 미만은 한 곳만 보면 오차가 커서, 같은 업종 묶음·지역의 소규모 사업장 평균을 같이 보여준다
            small = next((h for h in hits if h["members"] < 10), None)
            if small:
                g = filters.group_of(small["industry"])
                s = filters.small_summary(DATA, [g], [small["region"]] if small["region"] else [], region_sites=REGION)
                if s:
                    st.markdown(small_card(s, f"{small['region'] or '전국'} · {g}"), unsafe_allow_html=True)

    with by_filter:
        f1, f2 = st.columns(2)
        groups = f1.multiselect("업종", filters.GROUP_NAMES, placeholder="전체 업종")
        regions = f2.multiselect("지역", sorted(DATA["sido"].dropna().unique()), placeholder="전체 지역",
                                 help="그 지역에 있는 사업장 기준이에요. 여러 지역에 사업장이 있는 회사는 그 지역 몫만 계산해요. "
                                      "전국 직원을 본사 한 곳으로 신고한 회사(삼성전자 등)는 본사 지역에만 나와요.")
        f3, f4 = st.columns(2)
        size = f3.selectbox("회사 규모", list(filters.SIZES))
        salary = f4.select_slider("추정 연봉 (만 원)", options=[0, 3000, 4000, 5000, 6000, 7000, 8000, 10000, 20000],
                                  value=(0, 20000), format_func=lambda v: "0" if v == 0 else "2억 이상" if v == 20000 else f"{v:,}")
        f5, f6 = st.columns(2)
        growing = f5.checkbox("직원이 늘고 있는 회사만", help="이번 달 입사자가 퇴사자보다 많은 회사")
        listed = f6.checkbox("상장사만", help="실제 공시 연봉과 같이 볼 수 있어요")
        if size in ("전체", "50명 미만") and not listed:
            s = filters.small_summary(DATA, groups, regions, region_sites=REGION)
            if s:
                st.markdown(small_card(s, " · ".join(regions or ["전국"]) + " · " + (", ".join(groups) or "전체 업종")),
                            unsafe_allow_html=True)
        n, top = filters.find(DATA, groups, regions, size,
                              (salary[0] or None, None if salary[1] == 20000 else salary[1]), growing, listed, region_sites=REGION)
        st.caption(f"조건에 맞는 회사 {n:,}곳 (직원 10명 이상) · 추정 연봉 높은 순 상위 {len(top)}곳")
        if groups and filters.UNKNOWN not in groups:
            st.caption("💡 배민·당근처럼 업종이 비어 있는 큰 회사도 있어요. 안 보이면 '업종 정보 없음'도 골라 보세요.")
        if n:
            rows = filters.to_rows(top)
            # 표도 HTML로 그린다 (그래프와 같은 이유: 추가 파일 없이 보이게)
            body = "".join(
                f"<tr><td>{html.escape(r['name'])}</td><td class='t-hide'>{html.escape(str(r['industry'] or '-'))}</td>"
                f"<td>{html.escape(str(r['region'] or '-'))}</td><td class='t-num'>{r['members']:,}</td>"
                f"<td class='t-num'><b>{r['estimated_salary_manwon']:,}</b></td>"
                f"<td class='t-num t-hide'>{r['likely_range_manwon'][0]:,} ~ {r['likely_range_manwon'][1]:,}</td>"
                f"<td class='t-num t-hide'>{format(r['dart_actual_salary_manwon'], ',') if r['dart_actual_salary_manwon'] else '-'}</td></tr>"
                for r in rows)
            st.markdown("<div class='s-table'><table><thead><tr><th>회사</th><th class='t-hide'>업종</th><th>지역</th>"
                        "<th class='t-num'>직원 수</th><th class='t-num'>추정 연봉(만 원)</th>"
                        "<th class='t-num t-hide'>가능성 높은 범위</th><th class='t-num t-hide'>공시 연봉</th></tr></thead>"
                        f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
            chart = range_chart(rows[:10])
            if chart is not None:
                st.markdown(chart, unsafe_allow_html=True)
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            pick = c1.selectbox("자세히 볼 회사", [r["name"] for r in rows])
            if c2.button("AI에게 묻기", key="pick", use_container_width=True):
                ask_about(pick)

st.markdown(DATA_BASIS_HTML, unsafe_allow_html=True)

with st.expander("이 데이터는 어떻게 해석하면 되나요?"):
    st.markdown("**국민연금 공개 데이터로 추정하고, DART 공시로 검증해요.**\n\n"
                "- 국민연금 보험료로 회사의 평균 월급을 거꾸로 계산하고, 상장사 공시 연봉으로 오차를 보정했어요.\n"
                "- 상장사 2,392곳에서 확인한 오차로 **가능성 높은 범위(2곳 중 1곳)**와 **넓은 범위(10곳 중 8곳)**를 보여줘요.\n"
                "- 작은 비상장 회사나 성과급 비중이 큰 회사는 오차가 더 클 수 있어요.\n"
                "- 퇴사율은 국민연금 자격 상실 기준이라 실제 퇴사자 비율과 다를 수 있어요.")

st.markdown(f'<div class="s-foot"><span><b>회사 연봉 AI</b> · 만든 사람 김채연</span>'
            f'<span><a href="{GITHUB}" target="_blank">GitHub에서 코드와 검증 결과 보기</a> · '
            '데이터를 이해하고, 더 나은 선택을.</span></div>', unsafe_allow_html=True)
