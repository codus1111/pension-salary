"""회사 연봉 AI 에이전트 — 웹 화면 (Streamlit).

src/agent.py의 에이전트(직접 만든 반복 구조 + 도구 5개)를 그대로 쓰고, 화면만 붙인다.
- 비밀번호: 무료 AI 한도를 다른 사람이 다 쓰지 않도록 간단한 비밀번호를 건다
- 비밀 값(GEMINI_API_KEY, APP_PASSWORD)은 코드가 아니라 Streamlit의 secrets 설정에서 읽는다
- 답변 아래에 도구 결과(추정값·범위)로 그래프와 숫자 카드를 그린다. 글은 AI가, 숫자 그림은 데이터에서 바로
로컬 실행 (WSL): ~/venvs/pension/bin/streamlit run app/streamlit_app.py
"""
import base64
import html
from urllib.parse import quote
import os
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
GITHUB = "https://github.com/codus1111/pension-salary"

st.set_page_config(page_title="회사 연봉 AI", page_icon=str(ROOT / "app" / "static" / "favicon.png"), layout="wide", initial_sidebar_state="collapsed")

HERO = base64.b64encode((ROOT / "app" / "static" / "hero.webp").read_bytes()).decode()
LOGO = base64.b64encode((ROOT / "app" / "static" / "favicon.png").read_bytes()).decode()  # 탭 아이콘과 같은 파란 구슬 ₩
SUGGESTIONS = [
    ("회사 연봉 알아보기", "토스 평균 연봉 어느 정도야?"),
    ("두 회사 비교하기", "네이버랑 카카오 비교해줘"),
    ("업종별로 살펴보기", "증권업계에서 연봉 높은 회사 어디야?"),
]

# 움직임 순서: n번째 줄은 조금씩 늦게 (줄이 나타나고 → 범위 막대가 늘어나고 → 점이 튀어나온다)
MOTION_DELAYS = "\n".join(
    f".gt tbody tr:nth-child({i}) {{ animation-delay:{(i - 1) * 0.05:.2f}s; }} "
    f".gt tbody tr:nth-child({i}) .gt-band {{ animation-delay:{0.15 + (i - 1) * 0.05:.2f}s; }} "
    f".gt tbody tr:nth-child({i}) .gt-est, .gt tbody tr:nth-child({i}) .gt-dart {{ animation-delay:{0.65 + (i - 1) * 0.05:.2f}s; }} "
    f".s-cards .s-card:nth-child({i}), .hc-bar:nth-child({i}) span {{ animation-delay:{(i - 1) * 0.06:.2f}s; }}"
    for i in range(1, 25))

# 디자인: 연한 하늘색 배경, 그림이 있는 큰 첫 화면, 둥근 검색창, 흰 카드
st.markdown(f"""<style>
:root {{ --ink:#192c49; --muted:#62758d; --blue:#0868ec; --line:#e1eaf5; }}
.stApp {{ background:#f2f6fb; }}
.stApp, .stApp p, .stApp li {{ color:var(--ink); }}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display:none; }}
header[data-testid="stHeader"] {{ background:transparent; }}
.block-container, [data-testid="stMainBlockContainer"] {{ max-width:min(1800px, 97vw); margin:0 auto; padding:1.2rem 1.5rem 2rem; }}
/* 큰 모니터(1600px 이상)에서는 글씨와 첫 화면도 같이 키운다 */
@media (min-width:1600px) {{
  .stApp p, .stApp li {{ font-size:17px; }}
  .s-hero h1 {{ font-size:56px !important; }}
  .s-desc {{ font-size:17px !important; }}
  .s-eyebrow {{ font-size:12px !important; }}
  .s-brand {{ font-size:24px !important; }}
  .st-key-hero {{ min-height:480px !important; padding:56px 52px 34px !important; }}
  .st-key-hero input, .st-key-askbox input {{ font-size:17px !important; }}
  .st-key-hero [data-testid="stFormSubmitButton"] button, .st-key-askbox [data-testid="stFormSubmitButton"] button {{ min-height:52px; }}
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
.s-brand {{ display:flex; align-items:center; gap:8px; }}
.s-brand img {{ width:30px; height:30px; }}
.s-nav a {{ color:#48617f !important; font-size:12px; text-decoration:none; border:1px solid #d9e5f4;
            background:white; padding:9px 16px; border-radius:99px; }}
.st-key-hero {{ position:relative; overflow:hidden; border:1px solid white; border-radius:30px; background:
               linear-gradient(90deg,#e5f1fd 52%,#e5f1fd00 68%),
               url(data:image/webp;base64,{HERO}) no-repeat right center / auto 100%, #e5f1fd;
               box-shadow:0 14px 50px #7c9abb12; padding:42px 38px 26px; min-height:360px; }}
.s-eyebrow {{ font-size:10px; font-weight:750; letter-spacing:2px; color:#1766bf; margin:0 0 20px; }}
.s-hero h1 {{ font-size:clamp(28px,3.8vw,42px); font-weight:800; line-height:1.35; letter-spacing:-1.9px;
              padding:0; margin:0 0 18px; color:var(--ink); }}
.s-hero h1 [data-heading-text] {{ color:var(--ink); }}
.s-hero h1 .s-blue {{ color:var(--blue); }}
.s-hero [data-testid="stHeaderActionElements"] {{ display:none; }}
.s-desc {{ font-size:14px; line-height:1.85; color:#526a85 !important; margin:0 0 22px; }}
.st-key-hero [data-testid="stForm"], .st-key-askbox [data-testid="stForm"] {{ max-width:680px; background:white; border:1px solid #c4d9f5; border-radius:99px;
               box-shadow:0 8px 28px #447bb91c; padding:6px 6px 6px 18px; }}
.st-key-hero [data-testid="stForm"] [data-testid="stHorizontalBlock"], .st-key-askbox [data-testid="stForm"] [data-testid="stHorizontalBlock"] {{ align-items:center; gap:6px; }}
.st-key-hero [data-testid="stTextInputRootElement"], .st-key-hero [data-baseweb="input"], .st-key-askbox [data-testid="stTextInputRootElement"], .st-key-askbox [data-baseweb="input"] {{ border:0 !important; background:transparent !important; }}
.st-key-hero input, .st-key-askbox input {{ font-size:15px; background:transparent !important; }}
.st-key-hero [data-testid="stFormSubmitButton"] button, .st-key-askbox [data-testid="stFormSubmitButton"] button {{ background:var(--blue); color:white; border:0; border-radius:99px;
               min-height:44px; width:100%; font-weight:650; }}
.st-key-hero [data-testid="stFormSubmitButton"] button:hover, .st-key-askbox [data-testid="stFormSubmitButton"] button:hover {{ background:#0757c8; color:white; }}
.s-note {{ font-size:11px; color:#4f6e91 !important; margin:10px 0 0 18px; }}
.st-key-askbox [data-testid="stForm"] {{ max-width:none; margin:14px 0 18px; }}
.s-suggest-title {{ font-size:13px !important; font-weight:650; color:#1766bf !important; margin:6px 0 2px; }}
.st-key-hero [class*="st-key-sg"] button {{ background:#ffffffcc; border-color:#d8e7f7; min-height:84px; }}
.st-key-hero [class*="st-key-sg"] button:hover {{ background:white; }}
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
.s-card.ref {{ background:#f6f8fb; border:1px dashed #c9d3e0; }}
.tr {{ background:white; border:1px solid var(--line); border-radius:14px; padding:12px 14px 8px; margin:10px 0 4px; }}
.tr > small {{ color:var(--muted); font-size:12px; }}
.tr > small b.up {{ color:#0868ec; }}
.tr > small b.down {{ color:#E0517A; }}
.tr-bars {{ display:grid; grid-auto-flow:column; grid-auto-columns:1fr; gap:10px; height:150px; align-items:end; margin-top:10px; }}
.tr-bar {{ display:flex; flex-direction:column; justify-content:flex-end; align-items:center; height:100%; }}
.tr-bar b {{ font-size:11px; color:#24456c; white-space:nowrap; margin-bottom:3px; }}
.tr-bar span {{ display:block; width:70%; max-width:46px; background:linear-gradient(180deg,#5b9bff,#0868ec);
                border-radius:6px 6px 0 0; min-height:4px; transform-origin:bottom; }}

.tr-bar em {{ font-style:normal; font-size:11px; color:#3a5170; margin-top:4px; }}
.tr-bar i {{ font-style:normal; font-size:10px; color:#8193a8; }}
/* 색 규칙: 파랑 = 국민연금으로 추정한 값 · 주황 = 사업보고서 실제 공시 · 회청색 = 정부 통계로 만든 참고값(검증 안 됨) */
:root {{ --teal:#8e9bb0; --teal-l:#c3ccd9; --teal-bg:#f6f8fb; --pink:#FF9EB5; --pink-t:#E0517A; }}
.tr.ref {{ background:var(--teal-bg); border:1px dashed #c9d3e0; }}
.tr.ref .tr-bar span {{ background:linear-gradient(180deg,var(--teal-l),var(--teal)); }}
.tr.ref > small b.up {{ color:#56657c; }}
.tr-bar:first-child b, .tr:not(.ref) .tr-bar:last-child b {{ font-size:12px; color:var(--ink); }}
.s-key {{ display:inline-flex; align-items:center; gap:5px; font-size:11px; color:#62758d; margin-left:8px; }}
.s-key i {{ display:inline-block; width:10px; height:10px; border-radius:3px; }}
.s-key .k-blue {{ background:#0868ec; }}
.s-key .k-teal {{ background:var(--teal); }}
.tr-basis {{ font-size:11px !important; color:#8193a8 !important; margin:6px 0 0; }}
.tr p:not(.tr-basis) {{ font-size:12px !important; color:#3a5170 !important; margin:4px 0 0; line-height:1.6; }}
@media (prefers-reduced-motion:no-preference) {{ .tr-bar span {{ animation:s-grow-y .6s cubic-bezier(.2,.7,.2,1) both; }} }}
@media (max-width:640px) {{ .tr-bars {{ gap:4px; height:130px; }} .tr-bar b {{ font-size:9px; }} }}
[class*="st-key-fb"] {{ margin-top:8px; }}
[class*="st-key-fb"] p.fb-q {{ font-size:12px !important; color:var(--muted) !important; margin:0; }}
[class*="st-key-fb"] button {{ min-height:30px !important; padding:2px 12px !important; border-radius:999px !important;
                               background:white !important; border:1px solid #d9e5f4 !important; }}
[class*="st-key-fb"] button p {{ font-size:13px !important; }}
.s-links {{ display:flex; flex-wrap:wrap; align-items:center; gap:6px 8px; margin:10px 0 4px; }}
.s-links small {{ font-size:11px; color:var(--muted); margin-right:2px; }}
.s-links a {{ font-size:12px; color:#24456c !important; text-decoration:none; background:white; border:1px solid #d9e5f4;
              border-radius:99px; padding:5px 11px; white-space:nowrap; }}
.s-links a:hover {{ border-color:#0868ec; color:#0868ec !important; }}
.s-links-top {{ margin:-2px 0 12px; gap:8px; }}
.s-links-top small {{ font-size:12px; font-weight:650; color:#1766bf; }}
.s-links-top a {{ font-size:13px; padding:8px 14px; border-color:#c4d9f5; box-shadow:0 2px 8px #447bb914; }}
.s-card.ref b {{ color:#56657c; }}
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
.rc-d {{ width:4px; margin-left:-2px; top:-4px !important; height:28px !important; background:var(--pink); border-radius:2px !important; }}
.rc-val {{ font-size:12px; color:#62758d; font-variant-numeric:tabular-nums; display:flex; flex-direction:column; line-height:1.3; }}
.rc-val .v-e {{ color:#0868ec; }}
.rc-val .v-d {{ color:var(--pink-t); }}
.rc-legend {{ display:flex; flex-wrap:wrap; gap:6px 18px; font-size:12px; color:#3a5170; margin:0 0 10px; }}
.rc-legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.rc-legend i {{ display:inline-block; }}
.rc-legend .rc-unit {{ margin-left:auto; color:#8193a8; }}
.k-e {{ width:10px; height:10px; background:#0868ec; transform:rotate(45deg); border-radius:1px; }}
.k-l {{ width:22px; height:10px; background:#8dbaf5; border-radius:4px; }}
.k-d {{ width:4px; height:14px; background:var(--pink); border-radius:2px; }}
/* 회사 하나: 눈금자 (그림 위에 말로 직접 표시) */
.sr {{ background:white; border:1px solid var(--line); border-radius:16px; padding:18px 22px 14px; margin:10px 0 8px; }}
.sr-head {{ font-size:17px !important; margin:0 0 4px; }}
.sr-help {{ font-size:12.5px !important; color:#62758d !important; margin:0 0 50px; line-height:1.6; }}
.sr-help b {{ color:#24456c; font-weight:650; }}
.sr-head b {{ color:var(--blue); }}
.sr-track {{ position:relative; height:16px; background:#edf2f8; border-radius:8px; margin:0 6% 40px; }}
.sr-band {{ position:absolute; top:0; height:16px; background:#a9cbf7; border-radius:8px; }}
.sr-band em {{ position:absolute; top:22px; font-style:normal; font-size:12px; color:#62758d; white-space:nowrap; }}
.sr-lo {{ left:0; transform:translateX(-50%); }}
.sr-hi {{ right:0; transform:translateX(50%); }}
.sr-mark {{ position:absolute; top:-6px; width:4px; height:28px; margin-left:-2px; border-radius:2px; }}
.sr-mark span {{ position:absolute; bottom:34px; left:50%; transform:translateX(-50%); white-space:nowrap; font-size:13px;
                 font-weight:700; padding:3px 9px; border-radius:99px; color:white; }}
.sr-est {{ background:#0868ec; }}
.sr-est span {{ background:#0868ec; }}
.sr-dart {{ background:var(--pink); }}
.sr-dart span {{ background:#FFE3EA; color:var(--pink-t) !important; border:1px solid var(--pink); bottom:auto; top:34px; }}
.sr-note {{ font-size:13px !important; color:#3a5170 !important; margin:30px 0 0; line-height:1.7; }}
/* 여러 회사: 표 + 간트 차트 */
.gt {{ background:white; border:1px solid var(--line); border-radius:16px; padding:14px 16px 6px; margin:10px 0 8px; overflow-x:auto; }}
.gt-legend {{ display:flex; flex-wrap:wrap; gap:4px 16px; font-size:12px; color:#3a5170; margin:0 0 6px 4px; }}
.gt-legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.gt-legend .gt-unit {{ margin-left:auto; color:#8193a8; }}
.k-gband {{ display:inline-block; width:22px; height:10px; background:#a9cbf7; border-radius:3px; }}
.k-gest {{ display:inline-block; width:10px; height:10px; background:#0868ec; border-radius:50%; }}
.k-gdart {{ display:inline-block; width:4px; height:14px; background:var(--pink); border-radius:2px; }}
.gt table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.gt th {{ text-align:left; color:#62758d; font-weight:600; font-size:12px; padding:8px 8px; border:0; border-bottom:1px solid var(--line); }}
.gt td {{ padding:9px 8px; border:0; border-top:1px solid #f0f4f9; vertical-align:middle; }}
.gt tbody tr:hover td {{ background:#f7faff; }}
.gt-rank {{ width:30px; color:#8193a8; font-variant-numeric:tabular-nums; text-align:center; }}
.gt-name {{ font-weight:600; color:var(--ink); min-width:140px; }}
.gt-name small, .gt-num small {{ display:block; font-weight:400; font-size:11px; color:#8193a8; }}
.gt th.gt-num {{ text-align:right; }}
[data-testid="stHeaderActionElements"] {{ display:none !important; }}  /* 소제목 옆 🔗 링크 아이콘 */
.gt-ticks span:first-child {{ transform:none; }}
.gt-ticks span:last-child {{ transform:translateX(-100%); }}
.ans-note {{ display:block; margin-top:8px; font-size:12.5px; color:#62758d; line-height:1.6; }}
.gt-num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
.gt-num .v-e {{ color:#0868ec; }}
.gt-num .v-d {{ color:var(--pink-t); }}
.gt-none {{ color:#b6c2d1; }}
.gt th.gt-chart, .gt td.gt-chart {{ width:38%; min-width:220px; padding-left:18px; padding-right:22px; }}
.gt-ticks {{ position:relative; height:16px; }}
.gt-ticks span {{ position:absolute; transform:translateX(-50%); font-size:11px; font-weight:400; color:#8193a8; white-space:nowrap; }}
.gt-track {{ position:relative; height:18px; background:repeating-linear-gradient(90deg,#f3f6fa 0 1px,transparent 1px 20%); }}
.gt-band {{ position:absolute; top:3px; height:12px; background:#a9cbf7; border-radius:6px; }}
.gt-est {{ position:absolute; top:2px; width:14px; height:14px; margin-left:-7px; background:#0868ec; border:2px solid white; border-radius:50%; }}
.gt-dart {{ position:absolute; top:-2px; width:4px; height:22px; margin-left:-2px; background:var(--pink); border-radius:2px; }}
.gt-small td {{ background:#f7f9fc; }}
.gt-small .gt-rank {{ font-size:11px; font-weight:700; color:#4572a9; }}
.gt-track-small .gt-band {{ background:#d5dce6; }}
.gt-track-small .gt-est {{ background:#62758d; }}
@media (max-width:640px) {{
  /* 휴대폰: 표 대신 회사 한 곳 = 카드 한 줄 (이름·금액 위, 범위 막대 아래) */
  .gt {{ padding:10px 12px 4px; }}
  .gt .t-hide, .gt thead {{ display:none; }}
  .gt table, .gt tbody {{ display:block; }}
  .gt tr {{ display:grid; grid-template-columns:24px 1fr auto auto; gap:2px 10px; align-items:center;
            padding:10px 2px; border-top:1px solid #f0f4f9; }}
  .gt td {{ display:block; padding:0; border:0; background:none !important; }}
  .gt-name {{ min-width:0; }}
  .gt th.gt-chart, .gt td.gt-chart {{ grid-column:1 / -1; min-width:0; width:auto; padding:8px 4px 2px; }}
  .gt-small {{ background:#f7f9fc; border-radius:10px; }}
}}
/* 움직임: 그려지는 순서대로 눈이 따라가게 (줄 → 막대 → 점). 움직임을 꺼둔 사용자에게는 나오지 않는다 */
@keyframes s-rise {{ from {{ opacity:0; transform:translateY(8px); }} to {{ opacity:1; transform:none; }} }}
@keyframes s-grow-x {{ from {{ transform:scaleX(0); }} to {{ transform:scaleX(1); }} }}
@keyframes s-grow-y {{ from {{ transform:scaleY(0); }} to {{ transform:scaleY(1); }} }}
@keyframes s-pop {{ 0% {{ opacity:0; transform:scale(0); }} 70% {{ opacity:1; transform:scale(1.25); }} 100% {{ transform:scale(1); }} }}
@keyframes s-fade {{ from {{ opacity:0; }} to {{ opacity:1; }} }}
@media (prefers-reduced-motion:no-preference) {{
  .gt tbody tr {{ animation:s-rise .45s ease-out both; }}
  .gt-band, .sr-band, .cb-bar {{ transform-origin:left center; animation:s-grow-x .7s cubic-bezier(.2,.7,.2,1) both; }}
  .gt-est, .gt-dart {{ animation:s-pop .45s ease-out both; }}
  .sr-mark {{ animation:s-pop .5s ease-out .65s both; }}
  .sr-note, .cb-label {{ animation:s-fade .5s ease-out .8s both; }}
  .s-card {{ animation:s-rise .45s ease-out both; }}
  .hc-bar span {{ transform-origin:bottom center; animation:s-grow-y .6s cubic-bezier(.2,.7,.2,1) both; }}
  .s-user, [class*="st-key-answer"] {{ animation:s-rise .35s ease-out both; }}
}}
{MOTION_DELAYS}
/* 여러 회사: 가로 막대 */
.cb {{ background:white; border:1px solid var(--line); border-radius:16px; padding:16px 20px 10px; margin:10px 0 8px; }}
.cb-head {{ font-size:12px !important; color:#62758d !important; margin:0 0 10px; }}
.cb-row {{ display:grid; grid-template-columns:minmax(120px,220px) 1fr; gap:14px; align-items:center; padding:8px 0;
           border-top:1px solid #f0f4f9; }}
.cb-name {{ font-size:14px; font-weight:600; color:var(--ink); }}
.cb-name small {{ display:block; font-size:11px; font-weight:400; color:#8193a8; margin-top:2px; }}
.cb-bars {{ display:flex; flex-direction:column; gap:5px; }}
.cb-head {{ display:flex; flex-wrap:wrap; gap:4px 16px; }}
.cb-head span {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; color:#3a5170; }}
.k-bar, .k-band, .k-dbar {{ display:inline-block; width:22px; height:10px; border-radius:3px; }}
.k-bar {{ background:#0868ec; }}
.k-band {{ background:#0868ec33; border:1.5px dashed #0868ec; }}
.k-dbar {{ background:var(--pink); }}
.cb-line {{ position:relative; height:24px; }}
.cb-line-d {{ height:20px; margin-top:4px; }}
.cb-bar {{ position:absolute; left:0; top:3px; height:18px; border-radius:6px; min-width:4px; }}
.cb-line-d .cb-bar {{ top:2px; height:14px; }}
.cb-band {{ position:absolute; top:0; height:24px; background:#0868ec26; border:1.5px dashed #0868ec; border-radius:6px; }}
.cb-label {{ position:absolute; top:50%; transform:translateY(-50%); white-space:nowrap; font-size:12px; line-height:1.25; }}
.cb-label b {{ font-weight:700; }}
.cb-label em {{ display:block; font-style:normal; font-size:11px; color:#5a7aa3; }}
.cb-line .v-e {{ color:#0868ec; }}
.cb-line .v-d {{ color:var(--pink-t); }}
.cb-est {{ background:#0868ec; }}
.cb-dart {{ background:var(--pink); }}
@media (max-width:640px) {{
  .cb-row {{ grid-template-columns:1fr; gap:6px; }}
  /* 좁은 화면: 금액 글자를 막대 오른쪽이 아니라 아래에 */
  .cb-line, .cb-line-d {{ height:auto; padding-top:26px; }}
  .cb-line-d {{ padding-top:20px; }}
  .cb-label {{ position:static; transform:none; display:block; margin-top:4px; }}
  .sr-track {{ margin:0 14% 40px; }}
}}
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
  .st-key-hero [data-testid="stForm"] [data-testid="stHorizontalBlock"], .st-key-askbox [data-testid="stHorizontalBlock"], .st-key-whead [data-testid="stHorizontalBlock"] {{ flex-wrap:nowrap; }}
  .st-key-hero [data-testid="stForm"] [data-testid="stColumn"]:first-child, .st-key-askbox [data-testid="stColumn"]:first-child, .st-key-whead [data-testid="stColumn"]:first-child {{ flex:1 1 auto; min-width:0; width:auto; }}
  .st-key-hero [data-testid="stForm"] [data-testid="stColumn"]:last-child, .st-key-askbox [data-testid="stColumn"]:last-child, .st-key-whead [data-testid="stColumn"]:last-child {{ flex:0 0 72px; min-width:72px; width:72px; }}
  .st-key-hero [data-testid="stForm"], .st-key-askbox [data-testid="stForm"] {{ padding:4px 4px 4px 12px; }}
  .st-key-hero input, .st-key-askbox input {{ font-size:16px; }}
  [class*="st-key-sg"] button {{ min-height:76px; }}
}}
/* 그래프 다듬기: 가는 막대·윗부분만 둥글게·부드러운 그라데이션·옅은 가로 눈금·조용한 숫자 */
.tr, .hc, .gt, .sr {{ border-radius:18px; border-color:#e6edf6; box-shadow:0 6px 24px #6a8bb30d; }}
.tr {{ padding:16px 18px 12px; }}
.tr-bars {{ height:160px; gap:14px; padding:0 4px; border-bottom:1px solid #e3eaf3;
           background-image:repeating-linear-gradient(0deg, transparent 0 calc(25% - 1px), #eef2f8 calc(25% - 1px) 25%); }}
.tr-bar span {{ width:42%; max-width:30px; border-radius:10px 10px 4px 4px;
               background:linear-gradient(180deg,#9cc2ff,#3d85f5); transition:filter .2s, transform .2s; }}
.tr-bar:hover span {{ filter:brightness(1.06) saturate(1.1); transform:scaleY(1.02); }}
.tr-bar b {{ font-size:11px; font-weight:600; color:#6b7b90; margin-bottom:5px; }}
.tr-bar em {{ font-size:11px; color:#4a5d78; margin-top:6px; }}
.tr.ref .tr-bar span {{ background:linear-gradient(180deg,#d3dae4,#8e9bb0); }}
.tr-bar:first-child b, .tr:not(.ref) .tr-bar:last-child b {{ color:var(--ink); font-size:12px; }}
.hc-bars {{ gap:7px; border-bottom:1px solid #e3eaf3; }}
.hc-bar {{ align-items:center; }}
.hc-bar span {{ width:52%; max-width:22px; background:linear-gradient(180deg,#c6dafb,#8db7f5); border-radius:6px 6px 2px 2px; }}
.hc-bar:hover span {{ background:linear-gradient(180deg,#9cc2ff,#3d85f5); }}
.gt-track {{ height:20px; }}
.gt-band {{ top:5px; height:10px; background:#d3e3fb; border-radius:99px; }}
.gt-est {{ top:3px; width:14px; height:14px; background:#2f7cf6; border:3px solid white; box-shadow:0 0 0 1px #2f7cf6; }}
.gt-dart {{ top:0; width:6px; height:20px; margin-left:-3px; border-radius:99px; box-shadow:0 0 0 2px white; }}
.k-gband {{ background:#d3e3fb; border-radius:99px; }}
.k-gest {{ background:#2f7cf6; }}
.k-gdart {{ width:6px; border-radius:99px; }}
.sr-track {{ height:12px; background:#eef2f8; border-radius:99px; }}
.sr-band {{ height:12px; background:#d3e3fb; border-radius:99px; }}
.sr-mark {{ width:4px; border-radius:99px; }}
.sr-est {{ background:#2f7cf6; }}
.sr-est span {{ background:#2f7cf6; box-shadow:0 4px 12px #2f7cf633; }}
.s-card {{ border-radius:16px; border-color:#e6edf6; box-shadow:0 4px 16px #6a8bb30a; }}
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
    """배포: Streamlit Secrets → 로컬: 환경 변수 → .env / .env.txt 파일 순서로 찾는다 (어느 PC에서든 같은 방식)."""
    try:
        return st.secrets[name]
    except Exception:
        pass
    if os.environ.get(name):
        return os.environ[name]
    for fname in (".env", ".env.txt"):
        p = ROOT / fname
        if p.exists():
            m = re.search(rf"^\s*{name}\s*=\s*['\"]?([^\s'\"#]*)", p.read_text(encoding="utf-8-sig"), re.M)
            if m and m.group(1) and m.group(1) != "여기에_키":
                return m.group(1)
    return None


def nav():
    st.markdown(f'<div class="s-nav"><div class="s-brand"><img src="data:image/png;base64,{LOGO}" alt="">회사 연봉 <span>AI</span></div>'
                f'<a href="{GITHUB}" target="_blank">프로젝트 살펴보기</a></div>', unsafe_allow_html=True)


def hero_copy():
    st.markdown('<div class="s-hero"><p class="s-eyebrow">COMPANY SALARY INTELLIGENCE</p>'
                '<h1>궁금했던 회사 연봉, <br><span class="s-blue">데이터로 알아보세요.</span></h1>'
                '<p class="s-desc">국민연금 데이터와 기업 공시를 바탕으로<br>'
                '평균 연봉부터 회사 비교까지, AI와 함께 살펴보세요.</p></div>', unsafe_allow_html=True)


# 공유 주소(?q=회사)는 들어오자마자 기억해 두고 주소창에서 지운다 (비밀번호 화면에서도). 새로고침하면 처음 화면이 나오게
if st.query_params.get("q"):
    st.session_state.setdefault("shared_q", st.query_params.get("q"))
    st.query_params.clear()

# 비밀번호 확인
password = secret("APP_PASSWORD")
if password and not st.session_state.get("authed"):
    # 비밀번호 화면은 첫 화면 하나뿐이라 아래가 비어 보여서, 화면 높이를 꽉 채우고 글씨·그림을 키운다
    st.markdown("""<style>
    .st-key-hero { min-height:calc(100vh - 130px) !important; display:flex; flex-direction:column; justify-content:center;
                   padding:6vh 5vw !important; background-size:auto 100% !important; background-position:right center !important; }
    .st-key-hero .s-hero h1 { font-size:clamp(34px, 4.6vw, 76px) !important; letter-spacing:-2px; }
    .st-key-hero .s-desc { font-size:clamp(15px, 1.2vw, 21px) !important; }
    .st-key-hero .s-eyebrow { font-size:clamp(11px, 0.8vw, 14px) !important; }
    .st-key-hero [data-testid="stForm"] { max-width:760px; }
    .st-key-hero [data-testid="stAlert"] { max-width:760px; margin-top:8px; }
    [data-stale="true"] [data-testid="stAlert"], [data-stale="true"][data-testid="stAlert"] { display:none !important; }
    .st-key-hero .s-points { display:flex; gap:10px; flex-wrap:wrap; margin:28px 0 0; }
    .st-key-hero .s-points span { background:#ffffffcc; border:1px solid #d8e7f7; border-radius:99px; padding:8px 14px;
                                  font-size:13px; color:#42658a; }
    @media (max-width:640px) {
      .st-key-hero { min-height:calc(100vh - 110px) !important; padding:28px 20px !important;
                     background-size:100% auto !important; background-position:center bottom !important; }
      .st-key-hero .s-hero h1 { font-size:29px !important; letter-spacing:-1.2px; }
    }
    </style>""", unsafe_allow_html=True)
    nav()
    with st.container(key="hero"):
        hero_copy()
        with st.form("login", border=False):
            c1, c2 = st.columns([5, 1])
            typed = c1.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요", label_visibility="collapsed")
            ok = c2.form_submit_button("입장", use_container_width=True)
        # 틀렸다는 안내는 화면 맨 아래가 아니라 입력칸 바로 밑에 (+ 오른쪽 아래 알림)
        if ok and typed:
            if typed == password:
                st.session_state["authed"] = True
                st.rerun()
            st.error("비밀번호가 맞지 않아요. 다시 입력해 주세요.", icon="🔒")
            st.toast("비밀번호가 맞지 않아요", icon="🔒")
        st.markdown('<p class="s-note">무료 AI 사용량을 지키기 위해 비밀번호를 받고 있어요.</p>'
                    '<div class="s-points"><span>🏢 회사 51만 곳</span><span>✅ 상장사 2,392곳 공시로 검증</span>'
                    '<span>📉 2025년 12개월 퇴사율</span><span>🔎 토스·배민 같은 브랜드명 검색</span></div>',
                    unsafe_allow_html=True)
    st.stop()

if secret("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = secret("GEMINI_API_KEY")


def code_version():
    """src/ 코드가 마지막으로 바뀐 시각. 이 값이 바뀌면 아래 캐시를 새로 만든다."""
    return max(p.stat().st_mtime for p in (ROOT / "src").glob("*.py"))


# 배포 후 화면 코드만 새것이 되고, 캐시에 남은 옛 도구 코드(filters 등)와 섞여 KeyError가 난 적이 있어서,
# 코드 버전을 캐시 키로 쓰고 바뀌면 모듈을 다시 읽는다. max_entries=1: 옛 데이터를 메모리에 두 벌 두지 않게
@st.cache_resource(show_spinner="데이터를 불러오는 중이에요 (처음 한 번만, 몇 초 걸려요)", max_entries=1)
def load_agent(version):
    import gc
    import importlib
    if "mcp_server" in sys.modules:  # 옛 데이터를 먼저 놓아줘야 새 데이터와 두 벌이 되지 않는다 (무료 서버 메모리 부족 방지)
        for attr in ("DATA", "TURNOVER", "HEADCOUNT", "REGION_SITES", "TREND"):
            setattr(sys.modules["mcp_server"], attr, None)
        gc.collect()
    for name in ("brands", "filters", "mcp_server", "agent"):  # 서로 import하는 순서대로
        if name in sys.modules:
            importlib.reload(sys.modules[name])
    import agent  # 51만 개 회사 데이터를 불러온다
    try:
        provider = agent.GeminiProvider()
    except (SystemExit, Exception):  # 키가 없는 PC에서도 '회사 직접 찾기'는 쓸 수 있게, AI만 끈다
        provider = None
    return agent, provider


@st.cache_resource(show_spinner=False)
def _loaded():
    """지금 메모리에 올라간 코드 버전 (모든 사용자가 공유)."""
    return {"version": None}


# 코드 버전이 바뀌면 옛 캐시를 먼저 비운 뒤 새로 만든다. 그냥 두면 새 캐시를 만드는 동안 옛 데이터가 남아 메모리가 두 배가 된다
_version = code_version()
if _loaded()["version"] not in (None, _version):
    load_agent.clear()
_loaded()["version"] = _version
try:
    agent, provider = load_agent(_version)
except Exception as e:  # 서버가 데이터를 못 불러오면 빈 화면 대신 이유와 할 일을 보여준다
    st.error("데이터를 불러오지 못했어요. 잠시 뒤 새로고침(F5) 해 주세요. 계속되면 아래 내용을 알려주세요.")
    st.caption(f"{type(e).__name__}: {str(e)[:300]}")
    st.stop()


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


def won(m):
    """만 원 단위 정수 → '1억 78만', '9,276만'."""
    if m is None:
        return "-"
    if not m:
        return "0"
    eok, man = divmod(int(m), 10_000)
    return (f"{eok}억 {man:,}만" if man else f"{eok}억") if eok else f"{man:,}만"


# 그래프는 라이브러리(Vega) 대신 HTML로 직접 그린다: 배포 직후 브라우저가 그래프용 파일을 못 받아
# 'Failed to fetch dynamically imported module' 오류가 난 적이 있어서, 추가 파일 없이 보이게 했다.
# 처음엔 범위 막대·마름모·주황 선을 범례로 설명했는데 "무슨 뜻인지 모르겠다, 오류인 줄 알았다"는 의견이 있어서,
# 범례 없이 그림 위에 말로 직접 적는 두 가지 모양으로 바꿨다.

def salary_ruler(r):
    """회사 하나: '이 사이일 가능성이 커요'를 크게 쓰고, 눈금자 위에 추정·실제 공시를 말로 직접 표시한다."""
    c, d = r.get("likely_range_manwon") or [None, None]
    est, dart = r["estimated_salary_manwon"], r.get("dart_actual_salary_manwon")
    if not c:
        return ""
    vals = [v for v in (c, d, est, dart) if v]
    pad = (max(vals) - min(vals)) * 0.12 or 500
    lo, hi = min(vals) - pad, max(vals) + pad
    pos = lambda v: (v - lo) / (hi - lo) * 100  # noqa: E731
    marks = f'<div class="sr-mark sr-est" style="left:{pos(est):.1f}%"><span>추정 {won(est)}</span></div>'
    if dart:
        marks += f'<div class="sr-mark sr-dart" style="left:{pos(dart):.1f}%"><span>실제 {won(dart)}</span></div>'
    if not dart:
        note = "상장사가 아니라 실제 공시 연봉이 없어요. 이 범위가 지금 알 수 있는 최선이에요."
    elif c <= dart <= d:
        note = f"실제 공시 연봉({won(dart)} 원)도 이 범위 안에 있어요. 추정이 잘 맞는 회사예요."
    elif dart > d:
        note = (f"실제 공시 연봉({won(dart)} 원)은 이 범위보다 높아요. 성과급이 많은 회사는 국민연금 자료에 덜 잡혀서 그래요. "
                "이럴 땐 공시 숫자를 보시면 돼요.")
    else:
        note = f"실제 공시 연봉({won(dart)} 원)은 이 범위보다 낮아요. 이럴 땐 공시 숫자를 보시면 돼요."
    # 점검에서 284곳(5%)은 추정값이 '가능성 높은 범위' 밖이었다. 비슷한 상장사들의 실제 연봉이 추정보다 한쪽으로 치우쳐 있어
    # 범위를 그만큼 옮겨 잡았기 때문이라, 화면에 이유를 같이 적는다
    if est < c or est > d:
        side = "높았" if est < c else "낮았"
        note = (f"추정값({won(est)} 원)이 범위 밖에 있는 건, 비슷한 회사들의 실제 연봉이 추정보다 대체로 {side}기 때문이에요. "
                f"그래서 범위를 그쪽으로 옮겨 잡았어요.<br>" + note)
    return (f'<div class="sr"><p class="sr-head">평균 연봉은 <b>{won(c)} ~ {won(d)} 원</b> 사이일 가능성이 커요</p>'
            '<p class="sr-help"><b>추정 연봉</b> = 국민연금 보험료로 거꾸로 계산한 이 회사 전체 직원의 평균 연봉 · '
            '<b>가능성 높은 범위</b> = 비슷한 회사 2곳 중 1곳은 실제 평균 연봉이 이 안에 있었어요</p>'
            f'<div class="sr-track"><div class="sr-band" style="left:{pos(c):.1f}%;width:{pos(d) - pos(c):.1f}%">'
            f'<em class="sr-lo">{won(c)}</em><em class="sr-hi">{won(d)}</em></div>{marks}</div>'
            f'<p class="sr-note">{note}</p></div>')


def compare_chart(rows, small=None, small_where="", keep_order=False):
    """여러 회사: 표 + 간트 차트. 한 줄이 회사 하나.

    막대그래프로는 "숫자가 많아 읽기 어렵다"는 의견이 있어서, 숫자는 표 칸에 글자로 두고, 맨 오른쪽 칸에는
    모든 회사를 같은 눈금 위에 범위 막대(간트 차트처럼)로 그려 회사끼리 위치를 바로 비교하게 했다.
    small: filters.small_summary 결과. 있으면 맨 아래에 '기타: 10명 미만 사업장' 한 줄을 회사처럼 넣는다.
    """
    rows = [r for r in rows if r.get("estimated_salary_manwon")]
    if not keep_order:  # '요즘 채용 많은 순'처럼 이미 줄 세운 결과는 그 순서를 지킨다
        rows = sorted(rows, key=lambda r: -r["estimated_salary_manwon"])
    if not rows:
        return None
    vals = [v for r in rows for v in (*(r.get("likely_range_manwon") or []), r["estimated_salary_manwon"],
                                      r.get("dart_actual_salary_manwon")) if v]
    if small and "middle50_manwon" not in small:  # 옛 코드가 만든 결과여도 화면이 깨지지 않게
        small = {**small, "middle50_manwon": [small["avg_manwon"], small["avg_manwon"]]}
    if small:
        vals += [*small["middle50_manwon"], small["avg_manwon"]]
    span = max(vals) - min(vals) or 1000
    step = next((s for s in (500, 1000, 2000, 2500, 5000, 10000, 20000) if span / s <= 4), 50000)  # 눈금 글자가 겹치지 않게 4칸 이하
    lo, hi = (min(vals) // step) * step, -(-max(vals) // step) * step
    pos = lambda v: (v - lo) / (hi - lo) * 100  # noqa: E731
    ticks = "".join(f'<span style="left:{pos(t):.1f}%">{won(t)}</span>' for t in range(lo, hi + 1, step))

    def gantt(band, mid, dart=None, cls=""):
        a, b = band
        out = (f'<div class="gt-track{cls}"><span class="gt-band" style="left:{pos(a):.1f}%;width:{pos(b) - pos(a):.1f}%"></span>'
               f'<span class="gt-est" style="left:{pos(mid):.1f}%"></span>')
        if dart:
            out += f'<span class="gt-dart" style="left:{pos(dart):.1f}%"></span>'
        return out + "</div>"

    # 연차별 참고 연봉(신입·5년 차)과 1년 입사율은 있는 결과에서만 칸을 만든다
    has_tc = any((r.get("tenure_curve") or {}).get("by_year_manwon") for r in rows)
    has_hire = any(r.get("hire_rate_pct") is not None for r in rows)

    def extra(r):
        out = ""
        if has_tc:
            by = (r.get("tenure_curve") or {}).get("by_year_manwon")
            out += (f"<td class='gt-num t-hide'>{won(by[0])}<small>5년 차 {won(by[5])}</small></td>" if by else
                    "<td class='gt-num t-hide'><span class=gt-none>-</span></td>")
        if has_hire:
            h = r.get("hire_rate_pct")
            out += f"<td class='gt-num'>{'-' if h is None else f'+{h}%'}</td>"
        return out

    body = []
    for i, r in enumerate(rows, 1):
        est, dart = r["estimated_salary_manwon"], r.get("dart_actual_salary_manwon")
        c, d = r.get("likely_range_manwon") or [None, None]
        region = r.get("region") if isinstance(r.get("region"), str) else None  # 지역이 빈 회사(NaN)도 있다
        info = " · ".join(x for x in (region, f"{r['members']:,}명" if r.get("members") else None) if x)
        body.append(
            f"<tr><td class='gt-rank'>{i}</td><td class='gt-name'>{html.escape(r['name'])}<small>{info}</small></td>"
            f"<td class='gt-num'><b class='v-e'>{won(est)}</b></td>"
            f"<td class='gt-num t-hide'>{f'{won(c)} ~ {won(d)}' if c else '-'}</td>"
            f"<td class='gt-num'>{f'<b class=v-d>{won(dart)}</b>' if dart else '<span class=gt-none>-</span>'}</td>"
            + extra(r) + f"<td class='gt-chart'>{gantt((c, d), est, dart) if c else ''}</td></tr>")
    if small:
        a, b = small["middle50_manwon"]
        body.append(
            f"<tr class='gt-small'><td class='gt-rank'>기타</td><td class='gt-name'>10명 미만 사업장 {small['count']:,}곳"
            f"<small>{html.escape(small_where)} · 일하는 사람 {small['workers']:,}명</small></td>"
            f"<td class='gt-num'><b>{won(small['avg_manwon'])}</b><small>평균</small></td>"
            f"<td class='gt-num t-hide'>{won(a)} ~ {won(b)}<small>가운데 50% 사업장</small></td>"
            f"<td class='gt-num'><span class='gt-none'>-</span></td>"
            + ("<td class='gt-num t-hide'></td>" if has_tc else "") + ("<td class='gt-num'></td>" if has_hire else "")
            + f"<td class='gt-chart'>{gantt((a, b), small['avg_manwon'], cls=' gt-track-small')}</td></tr>")
    # 색만으로 구분하지 않게 모양도 말로 적는다 (색 구분이 어려운 사람도 읽히게)
    legend = ('<div class="gt-legend"><span><i class="k-gband"></i>넓은 막대 = 예상 범위</span>'
              '<span><i class="k-gest"></i>동그라미 = 추정</span>'
              '<span><i class="k-gdart"></i>세로 선 = 실제 공시 (상장사만)</span><span class="gt-unit">금액 단위: 원</span></div>')
    heads = (('<th class="gt-num t-hide">신입 참고</th>' if has_tc else "")
             + ('<th class="gt-num">1년 새 직원</th>' if has_hire else ""))
    return (f'<div class="gt">{legend}<table><thead><tr><th></th><th>회사</th><th class="gt-num">추정 연봉</th>'
            f'<th class="gt-num t-hide">예상 범위</th><th class="gt-num">실제 (공시)</th>{heads}'
            f'<th class="gt-chart"><div class="gt-ticks">{ticks}</div></th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
FIELD_RE = re.compile(r"\s*\(?\s*`[a-z][a-z0-9]*(?:_[a-z0-9]+)+`\s*\)?")


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


NOTE_RE = re.compile(r"[ \t]*\(\s*(※(?:[^()]|\([^()]*\))*)\)")  # '(※ … (괄호) …)'까지
NOTE_MARK = "@@NOTE@@"


def show_answer(text, unchecked=()):
    """AI 답변을 그린다.

    - 굵은 글씨: Markdown은 '**…(…)**의'처럼 닫는 ** 앞이 괄호, 뒤가 한글이면 굵게 인식하지 못해 별표가 그대로 보였다.
      그래서 **…**를 직접 <b>로 바꾼다 (다른 HTML은 이스케이프해서 그대로 글자로 보이게)
    - 숫자 대조: 답 속 금액이 도구 결과에 없으면(옮겨 적다 '1억'을 빠뜨린 경우 등) 경고를 단다
    """
    # 답에 `avg_income_vs_cap_pct` 같은 도구 필드 이름이 섞여 나온 적이 있어서, 백틱 속 영어 변수 이름은 지운다
    text = FIELD_RE.sub("", text or "")
    # 답 끝에 붙는 '(※ …)' 설명은 문장 사이에 끼면 읽기 어려워서, 줄을 바꿔 작은 글씨로 아래에 둔다
    text = NOTE_RE.sub(lambda m: "\n\n" + NOTE_MARK + m.group(1).strip() + "\n\n", text)
    text = re.sub(r"(?<=[^\s(@])[ \t]*(※)", "\n\n" + NOTE_MARK + r"\1", text)
    # &와 <만 막는다. >까지 바꾸면 Markdown 인용 상자(> …)가 '&gt;' 글자로 보였다
    safe = BOLD_RE.sub(r"<b>\1</b>", text.replace("&", "&amp;").replace("<", "&lt;"))
    safe = re.sub(re.escape(NOTE_MARK) + r"([^\n]+)", r'<span class="ans-note">\1</span>', safe)
    st.markdown(safe, unsafe_allow_html=True)
    if unchecked:
        shown = ", ".join(f"{a:,}만 원" for a in unchecked[:3])
        st.warning(f"글 속 금액 일부({shown})가 데이터와 맞지 않아요. AI가 옮겨 적다 틀렸을 수 있어요. "
                   "아래 카드와 그래프의 숫자는 데이터에서 바로 가져온 값이라 정확해요.", icon="⚠️")


LEGAL_RE = re.compile(r"\((?:주|유|재|사)\)|（주）|주식회사|유한회사|유한책임회사|농업회사법인|사단법인|재단법인|\(.*?[A-Za-z].*?\)")


def search_name(name):
    """채용 사이트 검색용 이름: '（주）비바리퍼블리카' → '비바리퍼블리카', '라라위드(LaLa with Inc.)' → '라라위드'."""
    return re.sub(r"\s+", " ", LEGAL_RE.sub(" ", name or "")).strip() or (name or "")


def links_html(name, company_key=None):
    """회사 이름으로 바로 가는 버튼 4개. 공고는 사이트 약관상 가져오지 않고 그 사이트의 검색 결과로 보낸다.

    블라인드는 재직자 인증이 있어야 제대로 볼 수 있어 취준생에게 쓸모가 없어서 넣지 않았다.
    공식 홈페이지: 상장사는 DART에 등록된 주소, 나머지는 '회사명 공식 홈페이지' 검색.
    """
    q = quote(search_name(name))
    home = (getattr(agent.tools, "HOMEPAGE", {}) or {}).get(company_key)
    items = [
        ("🏢 공식 홈페이지" if home else "🏢 홈페이지 찾기",
         home or f"https://search.naver.com/search.naver?query={q}+%EA%B3%B5%EC%8B%9D+%ED%99%88%ED%8E%98%EC%9D%B4%EC%A7%80"),
        ("💼 사람인 채용공고", f"https://www.saramin.co.kr/zf_user/search?searchword={q}"),
        ("💼 잡코리아 채용공고", f"https://www.jobkorea.co.kr/Search/?stext={q}"),
        ("⭐ 잡플래닛 리뷰", f"https://www.jobplanet.co.kr/search?query={q}"),
    ]
    return ('<div class="s-links"><small>🔗 바로 가기</small>' + "".join(
        f'<a href="{html.escape(u)}" target="_blank" rel="noopener noreferrer">{t}</a>' for t, u in items) + "</div>")


def card(label, value, sub="", main=False, ref=False):
    cls = " main" if main else " ref" if ref else ""
    return (f'<div class="s-card{cls}"><small>{label}</small><b>{html.escape(str(value))}</b>'
            f'{f"<em>{html.escape(sub)}</em>" if sub else ""}</div>')


def single_cards(r):
    # 범위는 위의 눈금자(salary_ruler)가 크게 보여주므로 카드에서는 뺀다
    cards = [card("추정 평균 연봉", r["estimated_salary_text"], "국민연금으로 계산한 회사 전체 평균", main=True)]
    sh = r.get("shrunk_estimate")
    if sh:  # 30명 미만: 같은 지역·업종 평균 쪽으로 당긴 값 (수축 추정, 참고용)
        cards.append(card("업종 평균 반영 · 참고용", sh["value_text"],
                          f"검증 안 됨 · 같은 지역·업종 작은 회사 평균 {sh['cell_mean_text']}을 "
                          f"{100 - sh['own_weight_pct']}% 섞음", ref=True))
    if r.get("dart_actual_salary_text"):
        cards.append(card("실제 공시 연봉", r["dart_actual_salary_text"], "회사가 사업보고서에 공개한 값"))
    cards.append(card("직원 수", f"{r['members']:,}명", r.get("region") or ""))
    if r.get("industry_top_pct"):
        act = r.get("industry_top_pct_actual")
        cards.append(card("같은 업종 안에서 (추정 연봉 기준)", f"상위 {r['industry_top_pct']}%",
                          f"{r['industry_companies']:,}곳 중" + (f" · 실제 공시로 보면 상위 {act}%" if act else " 연봉 순위")))
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
    if r.get("tenure_curve"):
        out += tenure_chart(r["tenure_curve"])
    if r.get("salary_trend"):
        out += trend_chart(r["salary_trend"])
    if year and year.get("monthly_members"):
        out += headcount_chart(year["monthly_members"])
    return out  # 바로 가기 버튼(홈페이지·채용공고·리뷰)은 맨 아래에 묻혀 찾기 어려워서 결론 바로 밑으로 옮겼다 (render_result)


def tenure_chart(tc):
    """연차별 참고 연봉 (신입 → 10년 이상). 정부 통계의 업종 근속 구간 비율 × 회사 평균. 검증 안 된 참고값이라 점선 카드."""
    vals = tc["salary_manwon"]
    hi = max(vals)
    bars = "".join(
        f'<div class="tr-bar" title="{html.escape(lab)} · 약 {won(v)} 원 · 회사 평균의 {x:.0%}">'
        f'<b>{won(v)}</b><span style="height:{v / hi * 100:.0f}%"></span><em>{html.escape(lab.split(" (")[0])}</em>'
        f'<i>{x:.0%}</i></div>'
        for lab, v, x in zip(tc["buckets"], vals, tc["ratio_to_average"]))
    head = (f'<small>연차별 참고 연봉 (신입 → 10년 이상) <span class="s-key"><i class="k-teal"></i>회청색 = 정부 통계로 만든 참고값</span> · '
            f'신입 약 <b class="up">{won(vals[0])} 원</b> · '
            f'{html.escape(tc["growth_text"])}</small>')
    dart = f'<p>{html.escape(tc["dart_compare_text"])}</p>' if tc.get("dart_compare_text") else ""
    return (f'<div class="tr ref">{head}<div class="tr-bars">{bars}</div>'
            f'<p class="tr-basis">막대 아래 %는 회사 평균 대비 · 기준 {html.escape(tc["base_text"])} · '
            f'{html.escape(tc.get("tenure_text", ""))} · '
            f'정부 통계 업종: {html.escape(tc["industry_basis"])} · {html.escape(tc["basis"])}</p>'
            f'<p>{html.escape(tc["meaning"])}</p>{dart}</div>')


def trend_chart(tr):
    """연봉 상승 추이 (2019~2025년 소득). 막대 = 그해 1차 추정 연봉, 아래 = 그해 직원 수.

    신입·경력 채용이 많으면 평균이 내려가 보이므로(토스: 직원 2배 → 평균 하락) 직원 수를 꼭 같이 보여준다.
    """
    vals = tr["salary_manwon"]
    hi = max(vals)
    bars = "".join(
        f'<div class="tr-bar" title="{y}년 소득 · {won(v)} 원 · 직원 {m:,}명">'
        f'<b>{won(v)}</b><span style="height:{v / hi * 100:.0f}%"></span><em>{y}</em><i>{m:,}명</i></div>'
        for y, v, m in zip(tr["years"], vals, tr["members"]))
    g = tr.get("annual_growth_pct")
    # '한 사람이 연차가 쌓이며 오르는 연봉'으로 오해하지 않게, 그해 회사 전체 평균의 변화라고 이름에 적는다
    key = '<span class="s-key"><i class="k-blue"></i>파랑 = 국민연금으로 추정한 값</span>'
    head = (f'<small>회사 평균 연봉 변화 (연도별) {key} · {tr["change_text"]}</small>'
            if g is None else f'<small>회사 평균 연봉 변화 (연도별) {key} · 연평균 <b class="{"up" if g >= 0 else "down"}">{g:+.1f}%</b> · '
                                f'{html.escape(tr["change_text"].split(" (")[0])}</small>')
    notes = "".join(f"<p>{html.escape(n)}</p>" for n in tr.get("notes", []))
    return (f'<div class="tr">{head}<div class="tr-bars">{bars}</div>'
            f'<p class="tr-basis">그해 회사에 있던 직원 전체의 평균이에요 (한 사람의 연차별 연봉이 아니에요) · '
            f'막대 아래 숫자는 그해 직원 수 · {html.escape(tr["basis"])}</p>{notes}</div>')


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
        st.markdown(compare_chart(sim["companies"]), unsafe_allow_html=True)


APP_URL = "https://yeon-salary-agent.streamlit.app"


def conclusion(m):
    """맨 위 한 줄 결론. 자세한 내용(눈금자·카드·그래프·AI 설명)은 이 아래에 펼쳐서 보여준다."""
    kind, rows = m.get("kind"), m.get("rows") or []
    if m.get("mode") == "filter":
        if not rows:
            return "조건에 맞는 회사가 없어요. 조건을 조금 넓혀 보세요."
        top = rows[0]
        if m.get("hiring"):
            return (f"조건에 맞는 회사 <b>{m['n']:,}곳</b> 중 2025년에 직원을 가장 많이 늘린 곳은 <b>{html.escape(top['name'])}</b>"
                    f" (1년 새 직원 +{top.get('hire_rate_pct')}% · 추정 연봉 약 {won(top['estimated_salary_manwon'])} 원)")
        return (f"조건에 맞는 회사 <b>{m['n']:,}곳</b> 중 추정 연봉이 가장 높은 곳은 <b>{html.escape(top['name'])}</b>"
                f" (약 {won(top['estimated_salary_manwon'])} 원)")
    if kind == "single" and rows:
        r = rows[0]
        c, d = r.get("likely_range_manwon") or [None, None]
        conf = r.get("confidence") or {}
        brand = m.get("brand")
        who = (f"<b>{html.escape(brand)}</b>의 법인인 <b>{html.escape(r['name'])}</b>" if brand
               else f"<b>{html.escape(r['name'])}</b>")
        parts = [f"{who} 평균 연봉 <b>약 {won(r['estimated_salary_manwon'])} 원</b>"]
        if r.get("dart_actual_salary_manwon"):
            parts.append(f"실제 공시 <b>{won(r['dart_actual_salary_manwon'])} 원</b>")
        elif c:
            parts.append(f"가능성 높은 범위 {won(c)} ~ {won(d)} 원")
        if r.get("industry_top_pct"):
            act = r.get("industry_top_pct_actual")
            parts.append(f"같은 업종 상위 {act}% (실제 공시 기준)" if act else f"같은 업종 상위 {r['industry_top_pct']}% (추정 기준)")
        if conf:
            parts.append(f"정확도 {conf['light']} {conf['level']}")
        return " · ".join(parts)
    if kind in ("compare", "ranking") and rows:
        ok = sorted([r for r in rows if r.get("estimated_salary_manwon")], key=lambda r: -r["estimated_salary_manwon"])
        if len(ok) >= 2:
            hi, lo = ok[0], ok[-1]
            return (f"{len(ok)}곳 중 추정 연봉이 가장 높은 곳은 <b>{html.escape(hi['name'])}</b> (약 {won(hi['estimated_salary_manwon'])} 원), "
                    f"가장 낮은 곳은 {html.escape(lo['name'])} (약 {won(lo['estimated_salary_manwon'])} 원)")
    return None


def my_year_box(r, i):
    """④ '내 연차'를 넣으면 그 연차의 참고 연봉 (정부 통계 업종 곡선 × 회사 평균, 검증 안 된 참고값)."""
    by = (r.get("tenure_curve") or {}).get("by_year_manwon")
    if not by:
        return
    with st.container(key=f"myyear{i}"):
        c1, c2 = st.columns([2, 3], vertical_alignment="center")
        y = c1.slider("내 연차", 0, 20, 3, key=f"yr{i}", format="%d년 차", help="0년 차 = 신입. 20년 차까지 볼 수 있어요.")
        c2.markdown(f'<p class="s-myyear">{"신입" if y == 0 else f"{y}년 차"} 참고 연봉 <b>약 {won(by[y])} 원</b>'
                    f'<br><span>업종의 연차별 임금 차이를 이 회사에 적용한 참고값이에요 (검증 안 됨)</span></p>',
                    unsafe_allow_html=True)


def share_box(name):
    """⑦ 이 회사 결과를 바로 여는 주소. 친구에게 보내거나 포트폴리오 시연에 쓴다 (비밀번호는 따로 필요)."""
    url = f"{secret('APP_URL') or APP_URL}/?q={quote(search_name(name))}"
    with st.expander("🔗 이 결과 공유하기"):
        st.code(url, language=None)
        st.caption("오른쪽 위 버튼으로 복사해서 보내면, 받은 사람이 열자마자 이 회사 결과가 나와요. (비밀번호가 있으면 입장 후)")


# '왜 다를까요?' 창: 실제 공시가 더 높은 회사와 추정이 더 높은 회사는 이유가 달라서 따로 보여준다
WHY_ACTUAL_HIGHER = """**실제 공시 연봉이 추정보다 높은 이유**

1. 보험료 상한. 국민연금은 월 소득 659만 원(연 7,908만 원)까지만 보험료를 매겨요. 그 이상은 자료에 안 보여서, 고연봉자가 많을수록 추정이 낮아져요. 보정 모델로 끌어올리긴 하지만 다 메우지는 못해요.
2. 성과급과 수당. 국민연금에는 식대 같은 비과세 수당이 빠지고 성과급도 일부만 들어가요. 사업보고서 평균 급여에는 성과급과 상여금이 다 들어가요.
3. 시점. 국민연금 기준 소득은 매년 7월에 전년도 소득으로 정해져요. 그해 성과급이 많이 올랐다면 국민연금에는 아직 덜 반영돼 있어요.

실제 공시 연봉이 있으면 그 숫자가 더 정확해요."""

WHY_EST_HIGHER = """**추정 연봉이 실제 공시보다 높은 이유**

1. 세는 사람. 사업보고서 평균 급여는 계약직과 중간에 들어온 사람까지 넣고, 1년 동안 준 급여를 평균 직원 수로 나눠요. 중간 입사자는 몇 달 치만 받아서 평균이 내려가요.
2. 임원 포함 여부. 사업보고서는 임원을 빼고 계산하지만, 국민연금 가입자에는 임원도 들어가요.
3. 사업장 범위. 지점이나 공장을 따로 신고한 회사는 국민연금에 본사만 잡혀요. 본사는 연봉이 높은 직군이 많아 추정이 더 높게 나오기 쉬워요.
4. 보정 모델. 비슷한 규모와 소득대의 상장사에 맞춰 보정하는데, 그 회사들보다 실제로 덜 주는 회사는 추정이 높게 나와요.

실제 공시 연봉이 있으면 그 숫자가 더 정확해요."""


def show_visuals(kind, rows, i=0):
    if not kind:
        return
    if kind == "single":
        r = rows[0]
        st.markdown(salary_ruler(r), unsafe_allow_html=True)
        if r.get("dart_actual_salary_manwon"):  # 상장사: 추정과 실제 공시가 왜 다른지 (한 줄은 늘 보이고, 자세한 건 눌러서)
            c1, c2 = st.columns([5, 1.3], vertical_alignment="center")
            est, dart = r["estimated_salary_manwon"], r["dart_actual_salary_manwon"]
            if dart >= est:  # 공시가 더 높다: 보험료 상한 때문에 고연봉·성과급이 덜 잡힘
                why = ("실제 공시가 더 높은 건 주로 보험료 상한 때문이에요. 국민연금은 월 659만 원까지만 소득을 잡아서 "
                       "연봉이 높거나 성과급이 많은 회사일수록 추정이 낮게 나와요.")
            else:  # 추정이 더 높다: 세는 사람·사업장 범위가 다름
                why = ("추정이 더 높은 건 주로 세는 사람이 달라서예요. 사업보고서는 계약직과 중간 입사자까지 넣은 회사 전체 평균이고, "
                       "국민연금은 이 사업장 가입자(임원 포함, 본사 위주)만 봐요.")
            c1.markdown(f'<p class="s-why">{why}</p>', unsafe_allow_html=True)
            with c2.popover("공시가 왜 더 높을까요?" if dart >= est else "추정이 왜 더 높을까요?",
                            icon=":material/help_outline:", use_container_width=True):
                st.markdown(WHY_ACTUAL_HIGHER if dart >= est else WHY_EST_HIGHER)
        st.markdown(single_cards(r), unsafe_allow_html=True)
        my_year_box(r, i)
        similar_block(r)
        share_box(r["name"])
        return
    chart = compare_chart(rows[:10])
    if chart is not None:
        st.markdown(chart, unsafe_allow_html=True)


# ---------- 화면 ----------
if "history" not in st.session_state:
    st.session_state["history"] = []   # 에이전트가 기억하는 대화 (도구 호출 포함)
    st.session_state["messages"] = []  # 화면에 보이는 결과 (최근 것이 위)

# 첫 화면: 그림 배경 위에 제목 → 검색창 하나(조건 필터 포함) → 예시. 들어오자마자 여기서 바로 검색한다
st.markdown("""<style>
.st-key-hero { min-height:0 !important; padding:30px 38px 18px !important;
               /* 구슬 그림 크기·위치를 고정: 검색 목록이 열려 상자가 커져도 그림이 커졌다 작아졌다 하지 않게 */
               background-size:100% 100%, auto 520px !important; background-position:0 0, right -40px top -30px !important; }
.s-eyebrow { margin:0 0 8px !important; }
.s-hero h1 { margin:0 0 6px !important; line-height:1.25 !important; }
.s-desc { margin:0 0 14px !important; line-height:1.6 !important; }
.st-key-hero [data-testid="stForm"] { max-width:760px; margin:0 0 10px; }
.st-key-hero [data-testid="stExpander"] { max-width:760px; }
.st-key-hero [data-testid="stExpander"] details { background:#ffffffd9 !important; border-color:#d3e3f6 !important; }
.st-key-filterbox { max-width:760px; background:#ffffffd9; border:1px solid #d3e3f6; border-radius:15px; padding:12px 18px 10px; }
[class*="st-key-whohead"] { margin-bottom:2px; }
[class*="st-key-whohead"] button { min-height:0 !important; padding:0 4px !important; }
[class*="st-key-whohead"] button p { font-size:12px !important; color:#0868ec !important; }
.s-filter-h { font-size:13px !important; font-weight:650; color:#24456c !important; margin:0 0 4px !important; }
.st-key-filterbox [data-testid="stForm"] { max-width:none; border:0; border-radius:14px; box-shadow:none;
               background:transparent; padding:4px 2px; }
.st-key-hero [data-testid="stExpander"] [data-testid="stForm"] { max-width:none; border:0; border-radius:14px; box-shadow:none;
               background:transparent; padding:4px 2px; }
.st-key-hero [data-testid="stExpander"] summary p { font-size:13px !important; font-weight:650; color:#24456c !important; }
.st-key-hero [class*="st-key-sg"] button { min-height:0 !important; padding:8px 14px !important; border-radius:99px !important; }
.st-key-hero [class*="st-key-sg"] button::before { display:none; }
.st-key-hero [class*="st-key-sg"] button > div { margin-top:0 !important; }
.st-key-hero .s-suggest-title { margin:10px 0 0 !important; }
.st-key-hero .s-note { margin:6px 0 0 4px !important; }
.st-key-workspace { margin-top:14px !important; padding-top:20px !important; }
.s-concl { background:#eef5ff; border:1px solid #cfe1f8; border-radius:14px; padding:13px 16px; margin:2px 0 10px;
           font-size:15.5px !important; line-height:1.7; color:var(--ink) !important; }
.s-concl b { color:#0757c8; }
.s-detail-h { font-size:12px !important; font-weight:700; color:#4572a9 !important; letter-spacing:.5px; margin:12px 0 2px !important; }
.s-ai-note { font-size:12px !important; color:#8193a8 !important; margin:4px 0 8px !important; }
.s-why { font-size:12.5px !important; color:#3a5170 !important; margin:0 !important; line-height:1.6; }
.s-myyear { font-size:14px !important; margin:0 !important; line-height:1.6; }
.s-myyear b { color:#56657c; font-size:17px; }
.s-myyear span { font-size:11.5px; color:#8193a8; }
[class*="st-key-myyear"] { background:#f6f8fb; border:1px dashed #c9d3e0; border-radius:14px; padding:8px 16px 4px; margin:8px 0; }
.s-cand { font-size:13px !important; margin:0 !important; }
.s-cand small { color:#8193a8; }
/* 검색창 예시가 몇 초마다 위로 돌아가며 바뀐다 (칸을 누르면 사라진다) */
.st-key-searchbox { max-width:760px; background:white; border:1px solid #c4d9f5; border-radius:99px;
                    box-shadow:0 8px 28px #447bb91c; padding:6px 6px 6px 14px; margin:0 0 10px; }
.st-key-searchbox [data-testid="stHorizontalBlock"] { align-items:center; gap:6px; flex-wrap:nowrap; }
.st-key-searchbox .react-aria-ComboBox { position:relative; }
/* 후보 맨 위 'Add: 토'(영어)를 우리말로 */
[role="option"][data-key="__creatable__"] > div { font-size:0 !important; }
[role="option"][data-key="__creatable__"] > div::before { content:"🔍  입력한 그대로 검색 (질문도 돼요)"; font-size:13px; color:#0757c8; }
.st-key-searchbox .react-aria-ComboBox > div { border:0 !important; background:transparent !important; box-shadow:none !important; }
.st-key-searchbox .react-aria-ComboBox button[aria-label="Open"] { display:none; }
.st-key-searchbox input { font-size:15px !important; }
.st-key-searchbox input:not(:focus)::placeholder { color:transparent !important; }
.st-key-searchbox button[kind="primary"] { background:var(--blue); border:0; border-radius:99px; min-height:44px; font-weight:650; }
.st-key-searchbox .react-aria-ComboBox::after {
  content:"🔍  토스"; position:absolute; left:12px; top:50%; transform:translateY(-50%); pointer-events:none;
  color:#8193a8; font-size:15px; white-space:nowrap; overflow:hidden; max-width:calc(100% - 24px);
  animation:s-roll 21s ease-in-out infinite; }
.st-key-searchbox .react-aria-ComboBox:focus-within::after,
.st-key-searchbox .react-aria-ComboBox:has(input:not(:placeholder-shown))::after { display:none; }
@media (max-width:640px) {
  .st-key-searchbox [data-testid="stColumn"]:first-child { flex:1 1 auto; min-width:0; width:auto; }
  .st-key-searchbox [data-testid="stColumn"]:last-child { flex:0 0 72px; min-width:72px; width:72px; }
  .st-key-searchbox { padding:4px 4px 4px 8px; }
}
@keyframes s-roll { 0.00% { content:"🔍  토스"; opacity:0; transform:translateY(55%); } 1.71% { content:"🔍  토스"; opacity:1; transform:translateY(-50%); } 12.14% { content:"🔍  토스"; opacity:1; transform:translateY(-50%); } 14.27% { content:"🔍  토스"; opacity:0; transform:translateY(-150%); } 14.29% { content:"🔍  네이버랑 카카오 비교해줘"; opacity:0; transform:translateY(55%); } 16.00% { content:"🔍  네이버랑 카카오 비교해줘"; opacity:1; transform:translateY(-50%); } 26.43% { content:"🔍  네이버랑 카카오 비교해줘"; opacity:1; transform:translateY(-50%); } 28.56% { content:"🔍  네이버랑 카카오 비교해줘"; opacity:0; transform:translateY(-150%); } 28.57% { content:"🔍  삼성전자 신입 연봉"; opacity:0; transform:translateY(55%); } 30.29% { content:"🔍  삼성전자 신입 연봉"; opacity:1; transform:translateY(-50%); } 40.71% { content:"🔍  삼성전자 신입 연봉"; opacity:1; transform:translateY(-50%); } 42.84% { content:"🔍  삼성전자 신입 연봉"; opacity:0; transform:translateY(-150%); } 42.86% { content:"🔍  스타벅스"; opacity:0; transform:translateY(55%); } 44.57% { content:"🔍  스타벅스"; opacity:1; transform:translateY(-50%); } 55.00% { content:"🔍  스타벅스"; opacity:1; transform:translateY(-50%); } 57.13% { content:"🔍  스타벅스"; opacity:0; transform:translateY(-150%); } 57.14% { content:"🔍  현대자동차 5년 차 연봉"; opacity:0; transform:translateY(55%); } 58.86% { content:"🔍  현대자동차 5년 차 연봉"; opacity:1; transform:translateY(-50%); } 69.29% { content:"🔍  현대자동차 5년 차 연봉"; opacity:1; transform:translateY(-50%); } 71.41% { content:"🔍  현대자동차 5년 차 연봉"; opacity:0; transform:translateY(-150%); } 71.43% { content:"🔍  증권업계 연봉 높은 회사"; opacity:0; transform:translateY(55%); } 73.14% { content:"🔍  증권업계 연봉 높은 회사"; opacity:1; transform:translateY(-50%); } 83.57% { content:"🔍  증권업계 연봉 높은 회사"; opacity:1; transform:translateY(-50%); } 85.70% { content:"🔍  증권업계 연봉 높은 회사"; opacity:0; transform:translateY(-150%); } 85.71% { content:"🔍  배민 1년 퇴사율"; opacity:0; transform:translateY(55%); } 87.43% { content:"🔍  배민 1년 퇴사율"; opacity:1; transform:translateY(-50%); } 97.86% { content:"🔍  배민 1년 퇴사율"; opacity:1; transform:translateY(-50%); } 99.99% { content:"🔍  배민 1년 퇴사율"; opacity:0; transform:translateY(-150%); } }
@media (min-width:1600px) { .st-key-hero { padding:36px 48px 20px !important; } .s-hero h1 { font-size:46px !important; } }
@media (max-width:640px) {
  .st-key-hero { padding:22px 16px 14px !important; background-size:100% auto !important; background-position:center bottom !important; }
  .s-desc br { display:none; }
  .st-key-hero [data-testid="stColumn"] { margin-bottom:-8px; }
  .s-concl { font-size:14.5px !important; padding:11px 12px; }
}
</style>""", unsafe_allow_html=True)
nav()

question = st.session_state.pop("pending_q", None)   # AI에게 물을 질문
search_q = st.session_state.pop("pending_search", None)  # 회사 바로 보기
# ⑦ 공유 주소(?q=회사)로 들어오면 그 회사를 바로 보여준다 (한 번만)
# 주소창에는 남기지 않는다: 새로고침하면 검색 기록 없이 처음 화면이 나오게
if st.session_state.get("shared_q"):
    search_q = st.session_state.pop("shared_q")

import streamlit.components.v1 as components  # noqa: E402

searchbox = components.declare_component("searchbox", path=str(ROOT / "app" / "components" / "searchbox"))
EXAMPLES = ["토스 평균 연봉 어느 정도야?", "네이버랑 카카오 비교해줘", "증권업계에서 연봉 높은 회사 어디야?",
            "삼성전자 신입 연봉", "스타벅스", "현대자동차 5년 차 연봉", "배민 1년 퇴사율"]


def brand_label(b):
    """브랜드 사전은 소문자로 적어 둬서, 영문 브랜드는 화면에 대문자로 ('kt&g' → 'KT&G')."""
    return b.upper() if b.isascii() else b


@st.cache_data(max_entries=1, show_spinner=False)  # 'Running search_options(...)' 같은 내부 문구가 화면에 보이지 않게
def search_options(version):
    """검색칸 아래 목록 후보: [보이는 이름, 업종·지역·직원 수, 검색할 이름]. 브랜드명(토스 → 비바리퍼블리카) 먼저, 그다음 직원 300명 이상 회사 큰 순.

    처음엔 브랜드마다 51만 곳을 검색해서(55번) 몇 초 걸렸다. 법인명이 정확히 같은 큰 회사를 표에서 한 번에 찾게 바꿨다.
    """
    big = DATA[DATA["members"] >= 30].sort_values("members", ascending=False).drop_duplicates("key_nm")
    by_key = big.set_index("key_nm")
    info = lambda r: f"{r['group']} · {r['sido'] if isinstance(r['sido'], str) else '-'} · {int(r['members']):,}명"  # noqa: E731
    out, used, used_en = [], set(), set()
    for b in agent.tools.BRANDS:
        k = agent.tools._key(agent.tools.to_legal(b) or b)
        if k in by_key.index:
            r = by_key.loc[k]
            # 같은 회사의 다른 이름은 한 번만 ('ktng'). 다만 영어 이름(toss)은 한글 이름(토스)과 따로 둬야 영어로 쳐도 뜬다
            seen_set = used_en if b.isascii() else used
            if r["company_key"] in seen_set:
                continue
            seen_set.add(r["company_key"])
            shown = brand_label(b)
            out.append([shown, f"{search_name(r['sample_nm'])} · " + info(r), shown, r["company_key"], agent.tools._key(b)])
    top = big[big["members"] >= 300]
    names = [search_name(n) for n in top["sample_nm"]]
    rows = top[["group", "sido", "members", "company_key", "key_nm"]].to_dict("records")
    seen = set()
    for n, r in zip(names, rows):
        if n and n not in seen and r["company_key"] not in used:  # 브랜드로 이미 나온 회사는 빼기
            seen.add(n)
            # 누르면 이름으로 다시 찾지 않고 이 회사를 바로 연다 ('kt service 남부'를 다시 찾다 다른 회사가 나왔다)
            out.append([n, info(r), n, r["company_key"], r["key_nm"]])
    return out


with st.container(key="hero"):
    hero_copy()
    # 검색칸: 글자를 치는 동안 칸 아래에 이름이 들어간 회사가 업종·지역·직원 수와 함께 주르륵 뜬다 ('토' → 토스, 토스뱅크 …).
    # Streamlit 기본 입력칸은 치는 도중에 반응하지 않아서 HTML·JS만으로 만든 컴포넌트를 쓴다 (app/components/searchbox)
    got = searchbox(options=search_options(_version), examples=EXAMPLES, key="sbox", default=None)
    if got and got.get("t") != st.session_state.get("sbox_t"):
        st.session_state["sbox_t"] = got["t"]
        if got.get("key"):  # 목록에서 고른 회사는 그 회사 그대로
            st.session_state["pending_key"] = (got["key"], got["q"])
        else:
            search_q = got["q"]
    # 접었다 펴는 칸이 아니라 늘 펼쳐 둔다 (누르지 않아도 조건을 바로 고를 수 있게)
    with st.container(key="filterbox"):
        st.markdown('<p class="s-filter-h">🎛️ 조건으로 찾기 · 업종 · 지역 · 규모 · 연봉 · 요즘 채용 많은 곳</p>',
                    unsafe_allow_html=True)
        with st.form("filters", border=False):
            f1, f2 = st.columns(2)
            groups = f1.multiselect("업종", filters.GROUP_NAMES, placeholder="전체 업종")
            regions = f2.multiselect("지역", sorted(DATA["sido"].dropna().unique()), placeholder="전체 지역",
                                     help="그 지역에 있는 사업장 기준이에요. 여러 지역에 사업장이 있는 회사는 그 지역 몫만 계산해요. "
                                          "전국 직원을 본사 한 곳으로 신고한 회사(삼성전자 등)는 본사 지역에만 나와요.")
            f3, f4 = st.columns(2)
            size = f3.selectbox("회사 규모", list(filters.SIZES))
            salary = f4.select_slider("추정 연봉 (만 원)", options=[0, 3000, 4000, 5000, 6000, 7000, 8000, 10000, 20000],
                                      value=(0, 20000),
                                      format_func=lambda v: "0" if v == 0 else "2억 이상" if v == 20000 else f"{v:,}")
            f5, f6, f7 = st.columns(3)
            hiring = f5.checkbox("요즘 채용 많은 순", help="2025년 1월 → 12월 직원이 많이 늘어난 순서예요 (사람을 실제로 늘린 곳). "
                                                 "직원 100명 이상만 보고, 사람이 계속 바뀌는 곳(1년 퇴사율 60% 넘음, 청소·경비·공사업 등)은 뺐어요")
            growing = f6.checkbox("직원이 늘고 있는 회사만", help="이번 달 입사자가 퇴사자보다 많은 회사")
            listed = f7.checkbox("상장사만", help="실제 공시 연봉과 같이 볼 수 있어요")
            if st.form_submit_button("이 조건으로 찾기", use_container_width=True):
                st.session_state["pending_filter"] = dict(groups=groups, regions=regions, size=size, salary=salary,
                                                          hiring=hiring, growing=growing, listed=listed)
    # 예시 질문 카드는 검색칸 속 돌아가는 예시와 겹쳐서 지우고, 그 질문들을 돌아가는 예시에 넣었다
    st.markdown('<p class="s-note">국민연금 2026년 9월 자료 · DART 2025 사업연도(2025.1.1~12.31) 공시로 검증</p>',
                unsafe_allow_html=True)


FEEDBACK_DIR = ROOT / "data/feedback"


def save_feedback(rec):
    """👍👎 한 건 저장. 항상 서버 로그와 로컬 파일에 남기고, FEEDBACK_URL(구글 시트 Apps Script)이 있으면 거기에도 보낸다.

    Community Cloud는 다시 시작하면 파일이 지워져서, 오래 모으려면 구글 시트를 연결한다 (tools/feedback_sheet.gs).
    로그인·이름 같은 개인 정보는 받지 않고 질문·답 앞부분·투표만 남긴다.
    """
    import json
    import urllib.request
    from datetime import datetime, timedelta, timezone
    rec = {"time": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S"), **rec}
    print("[피드백]", json.dumps(rec, ensure_ascii=False), flush=True)
    try:
        FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        with open(FEEDBACK_DIR / "feedback.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass
    url = secret("FEEDBACK_URL")
    if not url:
        return True
    try:
        body = json.dumps({**rec, "token": secret("FEEDBACK_TOKEN") or ""}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as res:
            return res.status < 400
    except Exception as e:  # 시트가 안 돼도 화면은 멈추지 않는다
        print("[피드백 전송 실패]", e, flush=True)
        return False


def feedback_bar(i, user, answer):
    """답 아래 '이 추정 도움이 됐나요? 👍 👎'. 👎는 아쉬운 점을 한 줄 더 받을 수 있다 (선택)."""
    state = f"fb_done{i}"
    with st.container(key=f"fb{i}"):
        done = st.session_state.get(state)
        if done == "up" or done == "sent":
            st.markdown('<p class="fb-q">의견 고마워요. 추정을 다듬는 데 쓸게요.</p>', unsafe_allow_html=True)
            return
        names = [r.get("name") for r in answer.get("rows", []) if isinstance(r, dict) and r.get("name")][:5]
        rec = {"question": user[:300], "answer": (answer.get("content") or "")[:500],
               "companies": ", ".join(names), "tools": " → ".join(answer.get("tools", []))}
        if done == "down":
            with st.form(f"fbform{i}", border=False):
                why = st.text_input("아쉬운 점", placeholder="어떤 점이 아쉬웠나요? (선택) 예: 실제 연봉과 달라요, 회사를 잘못 찾았어요",
                                    label_visibility="collapsed")
                if st.form_submit_button("보내기"):
                    save_feedback({**rec, "vote": "👎", "comment": why.strip()[:500]})
                    st.session_state[state] = "sent"
                    st.rerun()
            return
        row = st.container(horizontal=True, vertical_alignment="center", gap="small")
        row.markdown('<p class="fb-q">이 추정 도움이 됐나요?</p>', unsafe_allow_html=True, width="content")
        c1 = c2 = row
        if c1.button("👍", key=f"fbup{i}", help="도움이 됐어요"):
            save_feedback({**rec, "vote": "👍", "comment": ""})
            st.session_state[state] = "up"
            st.rerun()
        if c2.button("👎", key=f"fbdn{i}", help="아쉬워요"):
            st.session_state[state] = "down"
            st.rerun()


def small_card(s, where):
    """10명 미만 소규모 사업장을 하나로 묶은 평균 카드."""
    return ('<div class="s-small"><small>🏠 소규모 사업장 (직원 10명 미만) · ' + html.escape(where) + '</small>'
            f'<div class="s-cards" style="grid-template-columns:repeat(3,minmax(0,1fr))">'
            + card("평균 추정 연봉", f"{s['avg_manwon']:,}만 원", "일하는 사람 기준 평균", main=True)
            + card("사업장 수", f"{s['count']:,}곳", f"일하는 사람 {s['workers']:,}명")
            + card("가운데 50% 사업장", " ~ ".join(won(v) for v in s.get("middle50_manwon", [s["avg_manwon"]] * 2)),
                   "작은 곳끼리도 차이가 커요")
            + '</div><em>작은 사업장은 한 곳씩 보면 오차가 커서 같은 조건끼리 묶어 평균을 냈어요.</em></div>')


# 질문처럼 보이는 말 (이게 있으면 AI에게, 없고 회사 이름만이면 데이터에서 바로)
ASK_RE = re.compile(r"[?？]|비교|어디|추천|순위|높은|낮은|얼마|알려|어때|어떤|어느|이랑|랑 |하고 |\bvs\b|업계|업종|"
                    r"신입|퇴사|이직|분위기|왜|차이|해줘|할까|인가|일까")
TAIL_RE = re.compile(r"\s*(평균\s*)?(연봉|월급|급여)\s*(은|이|정보)?\s*$")
STOP = {"평균", "연봉", "월급", "급여", "회사", "비교", "정도", "어느", "얼마", "신입", "자세히", "알려줘", "해줘", "업계", "업종"}
JOSA_RE = re.compile(r"(이랑|랑|하고|와|과|은|는|이|가|을|를|의|도|에서|보다)$")


def strong_hits(q, hits):
    """검색어가 이름에 그대로 들어간, 직원 10명 이상인 회사들."""
    qk = agent.tools._key(agent.tools.to_legal(q) or q)
    return [h for h in hits if qk and qk in agent.tools._key(h["name"]) and h["members"] >= 10]


def detect_companies(text, limit=3):
    """질문 속 회사 이름 찾기 ('네이버랑 카카오 비교해줘' → 네이버, 카카오). AI보다 먼저 데이터 카드를 띄우는 데 쓴다."""
    found, keys = [], set()
    for tok in re.split(r"[\s,·/]+", text):
        tok = JOSA_RE.sub("", re.sub(r"[?？!.]", "", tok))
        if len(tok) < 2 or tok in STOP:
            continue
        hits = agent.tools.search_company(tok, limit=3)
        good = [h for h in strong_hits(tok, hits) if h["members"] >= 30]
        if good and good[0]["company_key"] not in keys:
            keys.add(good[0]["company_key"])
            found.append(good[0])
        if len(found) >= limit:
            break
    return found


def data_message(q, key=None):
    """AI 없이 데이터에서 바로 찾은 결과 (② 1초 안에 나온다)."""
    hits = agent.tools.search_company(q, limit=8)
    good = strong_hits(q, hits)
    if key is None and good:
        key = good[0]["company_key"]
    if key:
        r = agent.tools.get_salary_estimate(key)
        others = [h for h in hits if h["company_key"] != key][:5]
        # '토수'처럼 브랜드명(토스)과 한 글자 다르면, 같은 이름의 회사(토수종합건설)를 보여주면서도 '혹시 토스?'를 묻는다
        brand = agent.tools.suggest_brand(q) if hasattr(agent.tools, "suggest_brand") else None
        # 토스·라라스윗처럼 브랜드명으로 찾으면 결론에 '토스의 법인인 (주)비바리퍼블리카'로 적는다
        legal = agent.tools.to_legal(q)
        bname = brand_label(next((b for b in [*agent.tools.BRANDS, *agent.tools.UNVERIFIED]
                                  if agent.tools._key(b) == agent.tools._key(q)), q)) if legal else None
        return {"role": "assistant", "mode": "data", "kind": "single", "rows": [r], "candidates": others, "query": q,
                "note": agent.tools.brand_note(q) if hasattr(agent.tools, "brand_note") else None, "guess": brand,
                "brand": bname}
    guess = agent.tools.suggest_name(q) if hasattr(agent.tools, "suggest_name") else None
    if not hits:
        print(f"[검색 0건] {q}", flush=True)  # 배포 로그에 쌓아 브랜드명 사전 후보로 쓴다
    return {"role": "assistant", "mode": "data", "kind": None, "rows": [], "candidates": hits, "query": q,
            "guess": search_name(guess) if guess else None}


def filter_message(f):
    hire = None
    if f["hiring"] and not agent.tools.TURNOVER.empty:
        t = agent.tools.TURNOVER
        # '요즘 채용 많은 곳' = 사람을 실제로 늘린 곳: 2025년 1월 → 12월 직원 순증가율.
        # 입사율만 보면 사람이 계속 바뀌는 곳(입사율 150%·퇴사율도 높음)이 위로 올라와서, 퇴사율 60% 이하·직원 100명 이상만 보고
        # 단기 근로 업종(청소·경비·공사업 등)과 합병으로 보이는 3배 넘는 증가는 뺀다
        growth = (t["members_dec"] - t["members_jan"]) / t["members_jan"].where(t["members_jan"] > 0)
        keep = (t["avg_members"] >= 100) & (t["annual_exit_rate"] <= 0.6) & growth.between(0, 3)
        short = DATA.set_index("company_key")["intp_nm"].astype(str).str.contains(agent.tools.SHORT_RE.pattern, regex=True)
        hire = growth[keep]
        hire = hire[~hire.index.isin(short[short].index)]
    small = (filters.small_summary(DATA, f["groups"], f["regions"], region_sites=REGION)
             if f["size"] in ("전체", "50명 미만") and not f["listed"] and not f["growing"] and not f["hiring"] else None)
    where = " · ".join(f["regions"] or ["전국"]) + " · " + (", ".join(f["groups"]) or "전체 업종")
    salary = f["salary"]
    n, top = filters.find(DATA, f["groups"], f["regions"], f["size"],
                          (salary[0] or None, None if salary[1] == 20000 else salary[1]), f["growing"], f["listed"],
                          region_sites=REGION, hiring=hire)
    label = (f"🎛️ {where} · {f['size']}" + (" · 요즘 채용 많은 순" if f["hiring"] else "")
             + (" · 직원 느는 곳" if f["growing"] else "") + (" · 상장사" if f["listed"] else ""))
    return label, {"role": "assistant", "mode": "filter", "kind": "compare", "rows": filters.to_rows(top), "n": n,
                   "small": small, "where": where, "hiring": bool(f["hiring"]), "groups": f["groups"]}


def render_result(m, user, i):
    """결과 하나: ① 한 줄 결론 → ② 자세한 내용 (데이터 카드·그래프·AI 설명). 마우스를 올리지 않아도 다 보인다."""
    concl = conclusion(m)
    if concl:
        st.markdown(f'<p class="s-concl">{concl}</p>', unsafe_allow_html=True)
    if m.get("kind") == "single" and m.get("rows"):  # 다른 사이트로 가는 버튼은 결론 바로 밑에 (눈에 잘 띄게)
        r0 = m["rows"][0]
        st.markdown(links_html(r0["name"], r0.get("company_key")).replace('class="s-links"', 'class="s-links s-links-top"'),
                    unsafe_allow_html=True)
    mode = m.get("mode", "ai")
    if mode == "data" and not m.get("rows"):
        if m.get("guess"):
            st.button(f"🔎 '{m['guess']}'(으)로 검색하시겠어요?", key=f"guess{i}",
                      on_click=lambda g=m["guess"]: st.session_state.update(pending_search=g))
        if not m.get("candidates"):
            st.info("국민연금 공개 자료에서 이 이름을 찾지 못했어요. 정식 회사 이름(법인명)으로 다시 찾아보거나, "
                    "아래 버튼으로 채용 정보를 먼저 볼 수 있어요.")
            st.markdown(links_html(m["query"]), unsafe_allow_html=True)
        else:
            st.markdown('<p class="s-detail-h">비슷한 이름의 회사</p>', unsafe_allow_html=True)
        for j, h in enumerate(m.get("candidates", [])[:8]):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            c1.markdown(f'<p class="s-cand"><b>{html.escape(h["name"])}</b> <small>{html.escape(h["industry"] or "업종 정보 없음")}'
                        f' · {h["region"] or "-"} · {h["members"]:,}명{" · 상장사" if h["listed"] else ""}</small></p>',
                        unsafe_allow_html=True)
            c2.button("보기", key=f"cand{i}_{j}", use_container_width=True,
                      on_click=lambda k=h["company_key"], n=h["name"]: st.session_state.update(pending_key=(k, n)))
        tiny = next((h for h in m.get("candidates", []) if h["members"] < 10), None)
        if tiny:
            g = filters.group_of(tiny["industry"])
            s = filters.small_summary(DATA, [g], [tiny["region"]] if tiny["region"] else [], region_sites=REGION)
            if s:
                st.markdown(small_card(s, f"{tiny['region'] or '전국'} · {g}"), unsafe_allow_html=True)
        return
    if m.get("note"):
        st.caption("🔎 " + m["note"])
    if m.get("fallback"):
        st.markdown('<p class="s-ai-note">AI가 지금 답하지 못해서, AI 설명 없이 데이터에서 찾은 결과만 보여 드려요.</p>',
                    unsafe_allow_html=True)
    if m.get("content"):
        st.markdown('<p class="s-detail-h">AI 설명</p>', unsafe_allow_html=True)
        show_answer(m["content"], m.get("unchecked", []))
    st.markdown('<p class="s-detail-h">자세한 내용</p>', unsafe_allow_html=True)
    if mode == "filter":
        if m["rows"]:
            st.caption(f"조건에 맞는 회사 {m['n']:,}곳 (직원 10명 이상) · "
                       + ("2025년 직원 증가율 높은 순" if m.get("hiring") else "추정 연봉 높은 순") + f" 상위 {len(m['rows'])}곳"
                       + (" · 맨 아래 '기타'는 10명 미만 사업장을 묶은 평균이에요" if m.get("small") else ""))
            if m.get("groups") and filters.UNKNOWN not in m["groups"]:
                st.caption("배민, 당근처럼 업종이 비어 있는 큰 회사도 있어요. 안 보이면 '업종 정보 없음'도 골라 보세요.")
            st.markdown(compare_chart(m["rows"], m.get("small"), m.get("where", ""), keep_order=m.get("hiring", False)),
                        unsafe_allow_html=True)
            c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
            names = [r["name"] for r in m["rows"]]
            pick = c1.selectbox("자세히 볼 회사", names, key=f"pick{i}")
            row = m["rows"][names.index(pick)]
            c2.button("보기", key=f"pickb{i}", use_container_width=True,
                      on_click=lambda: st.session_state.update(pending_key=(row["company_key"], row["name"])))
    else:
        show_visuals(m.get("kind"), m.get("rows", []), i)
    if mode == "data" and m.get("candidates"):
        with st.expander(f"다른 후보 {len(m['candidates'])}곳 (이름이 비슷한 회사)"):
            for j, h in enumerate(m["candidates"]):
                c1, c2 = st.columns([5, 1], vertical_alignment="center")
                c1.markdown(f'<p class="s-cand"><b>{html.escape(h["name"])}</b> <small>{h["region"] or "-"} · '
                            f'{h["members"]:,}명</small></p>', unsafe_allow_html=True)
                c2.button("보기", key=f"oth{i}_{j}", use_container_width=True,
                          on_click=lambda k=h["company_key"], n=h["name"]: st.session_state.update(pending_key=(k, n)))
    if mode in ("data", "filter") and m.get("rows"):
        target = m["rows"][0]["name"] if mode == "data" else None
        if target:
            st.button("🤖 AI에게 더 자세히 묻기", key=f"askai{i}",
                      on_click=lambda t=target: st.session_state.update(pending_q=f"{t} 평균 연봉 자세히 알려줘"))
    if m.get("tools"):
        st.caption("사용한 도구: " + " → ".join(m["tools"]))
    feedback_bar(i, user, m)


def show_pair(user, answer, i):
    st.markdown(f'<div class="s-user"><b>나</b>{html.escape(user)}</div>', unsafe_allow_html=True)
    if answer:
        with st.container(key=f"answer{i}"):
            if answer.get("guess") and answer.get("rows"):
                # '토수' → 토수종합건설 결과는 그대로 두고, '혹시 토스?'는 이름표 옆에 작게만 묻는다
                head = st.container(key=f"whohead{i}", horizontal=True, vertical_alignment="center", gap="small")
                head.markdown('<span class="s-who">회사 연봉 AI</span>', unsafe_allow_html=True, width="content")
                head.button(f"혹시 '{answer['guess']}' 찾으셨나요? →", key=f"guess{i}", type="tertiary",
                            on_click=lambda g=answer["guess"]: st.session_state.update(pending_search=g))
            else:
                st.markdown('<span class="s-who">회사 연봉 AI</span>', unsafe_allow_html=True)
            render_result(answer, user, i)


# 검색어 정리: 회사 이름만이면 데이터에서 바로, 질문이면 AI에게
pk = st.session_state.pop("pending_key", None)
pf = st.session_state.pop("pending_filter", None)
new_user, new_msg = None, None
if pk:
    new_user, new_msg = pk[1], data_message(pk[1], key=pk[0])
elif pf:
    new_user, new_msg = filter_message(pf)
elif search_q:
    name_part = TAIL_RE.sub("", search_q)
    if name_part and not ASK_RE.search(name_part) and len(name_part.split()) == 1:
        new_user, new_msg = search_q, data_message(name_part)
    else:
        question = search_q

msgs = st.session_state["messages"]
if new_msg:
    msgs.append({"role": "user", "content": new_user})
    msgs.append(new_msg)
pairs = []
for i, m in enumerate(msgs):
    if m["role"] == "user":
        pairs.append([m["content"], None, i])
    elif pairs:
        pairs[-1][1], pairs[-1][2] = m, i

if question or pairs:
    # 검색한 뒤에는 첫 화면 설명·예시를 접어서, 결과가 스크롤 없이 검색창 바로 아래 보이게
    st.markdown("""<style>
    .st-key-hero .s-desc, .st-key-hero .s-suggest-title, .st-key-hero [class*="st-key-sg"],
    .st-key-hero .s-note, .st-key-hero .s-eyebrow { display:none !important; }
    .st-key-hero .s-hero h1 { font-size:clamp(22px,2.4vw,30px) !important; margin-bottom:10px !important; }
    .st-key-hero .s-hero h1 br { display:none; }
    .st-key-hero { padding:18px 30px 12px !important; min-height:0 !important; }
    .st-key-hero [data-testid="stHorizontalBlock"]:has([class*="st-key-sg"]) { display:none !important; }
    @media (max-width:640px) { .st-key-hero { padding:16px 14px 10px !important; background-size:60% auto !important;
                                              background-position:right bottom !important; } }
    </style>""", unsafe_allow_html=True)
    with st.container(key="workspace"):
        h1, h2 = st.container(key="whead").columns([5, 1], vertical_alignment="center")
        h1.markdown('<p class="s-h2">검색 결과</p><p class="s-caption">최근 결과가 맨 위에 와요. '
                    '맨 위 한 줄이 결론이고, 그 아래가 자세한 내용이에요.</p>', unsafe_allow_html=True)
        if h2.button("초기화", key="reset", use_container_width=True):
            st.session_state["history"], st.session_state["messages"] = [], []
            st.query_params.clear()
            st.rerun()

        if question:  # AI 질문: ② 질문 속 회사의 데이터 결론부터 바로 보여주고, AI 설명은 이어서
            msgs.append({"role": "user", "content": question})
            st.markdown(f'<div class="s-user"><b>나</b>{html.escape(question)}</div>', unsafe_allow_html=True)
            history = st.session_state["history"]
            before = len(history)
            i_new = len(msgs)
            with st.container(key=f"answer{i_new}"):
                st.markdown('<span class="s-who">회사 연봉 AI</span>', unsafe_allow_html=True)
                found = detect_companies(question)
                quick = [agent.tools.get_salary_estimate(h["company_key"]) for h in found]
                for r in quick:
                    st.markdown(f'<p class="s-concl">{conclusion({"kind": "single", "rows": [r]})}</p>',
                                unsafe_allow_html=True)
                out = None
                with st.status("AI가 자세한 설명을 쓰는 중이에요… (20초쯤 걸려요)", expanded=False) as status:
                    try:
                        if provider is None:
                            raise RuntimeError("이 실행 환경에 GEMINI_API_KEY가 없어 AI 설명을 쓸 수 없어요.")
                        out = agent.ask(question, provider, history=history, log=lambda s: status.write(s))
                        status.update(label="답을 찾았어요", state="complete")
                    except Exception as e:
                        del history[before:]
                        status.update(label="AI 설명은 받지 못했어요", state="error")
                        print("[AI 실패]", str(e)[:300], flush=True)
                if out:
                    tools = [t["tool"] for t in out["trace"]]
                    kind, rows = collect(out["trace"])
                    st.session_state.setdefault("tool_nums", set()).update(evaluate.tool_numbers(out["trace"]))
                    st.session_state.setdefault("main_nums", set()).update(main_salaries(out["trace"]))
                    unchecked = [a for a, tol in evaluate.amounts_in(out["answer"] or "")
                                 if not grounded(a, tol, st.session_state["tool_nums"], st.session_state["main_nums"])]
                    msg = {"role": "assistant", "mode": "ai", "content": out["answer"], "tools": tools,
                           "kind": kind, "rows": rows, "unchecked": unchecked}
                else:  # ⑩ AI가 안 되면 질문 속 회사의 데이터만이라도 보여준다
                    msg = {"role": "assistant", "mode": "ai", "fallback": True, "content": None,
                           "kind": ("single" if len(quick) == 1 else "compare") if quick else None, "rows": quick}
                    if not quick:
                        st.error("AI 서버가 바쁘거나 오늘 무료 사용량을 다 썼어요. 회사 이름만 넣으면 AI 없이 바로 볼 수 있어요.")
                msgs.append(msg)
            st.rerun()  # 결과를 위 '최근 결과' 자리에 같은 모양으로 다시 그린다

        for user, answer, i in reversed(pairs):
            show_pair(user, answer, i)

        st.markdown('<p class="s-caption" style="font-size:11px;margin-top:14px">회사 전체의 평균 추정치예요. '
                    '신입·직무·개인 연봉과 다르며, 오차 범위도 함께 확인해 주세요.</p>', unsafe_allow_html=True)


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
