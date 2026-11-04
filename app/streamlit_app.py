"""회사 연봉 AI 에이전트 — 웹 화면 (Streamlit).

src/agent.py의 에이전트(직접 만든 반복 구조 + 도구 5개)를 그대로 쓰고, 화면만 붙인다.
- 비밀번호: 무료 AI 한도를 다른 사람이 다 쓰지 않도록 간단한 비밀번호를 건다
- 비밀 값(GEMINI_API_KEY, APP_PASSWORD)은 코드가 아니라 Streamlit의 secrets 설정에서 읽는다
로컬 실행 (WSL): ~/venvs/pension/bin/streamlit run app/streamlit_app.py
"""
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

st.set_page_config(page_title="회사 연봉 AI 에이전트", page_icon="💼", layout="centered")


def secret(name):
    try:
        return st.secrets[name]
    except Exception:  # secrets 파일이 없을 때 (로컬): 환경 변수나 .env에서 읽는다
        return os.environ.get(name)


# 비밀번호 확인
password = secret("APP_PASSWORD")
if password and not st.session_state.get("authed"):
    st.title("회사 연봉 AI 에이전트")
    typed = st.text_input("비밀번호", type="password")
    if typed:
        if typed == password:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("비밀번호가 맞지 않아요.")
    st.stop()

if secret("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = secret("GEMINI_API_KEY")


@st.cache_resource(show_spinner="데이터를 불러오는 중이에요 (처음 한 번만, 몇 초 걸려요)")
def load_agent():
    import agent  # 51만 개 회사 데이터를 불러온다
    return agent, agent.GeminiProvider()


agent, provider = load_agent()

st.title("회사 연봉 AI 에이전트")
st.caption("국민연금 공개 데이터로 회사 평균 연봉을 추정하고, 상장사 공시 연봉으로 검증한 결과를 바탕으로 답해요.")

with st.sidebar:
    st.subheader("이렇게 물어보세요")
    st.markdown("- 토스 평균 연봉 어느 정도야?\n- 네이버랑 카카오 비교해줘\n- 증권업계에서 연봉 높은 회사 어디야?\n- 이 추정 얼마나 정확해?")
    st.divider()
    st.markdown("**알아두세요**\n\n회사 전체 직원의 **평균 추정치**예요. 신입·직무·개인 연봉이 아니에요.")
    st.markdown("[프로젝트 코드와 검증 결과 (GitHub)](https://github.com/codus1111/pension-salary)")
    if st.button("대화 새로 시작"):
        st.session_state.pop("history", None)
        st.session_state.pop("messages", None)
        st.rerun()

if "history" not in st.session_state:
    st.session_state["history"] = []   # 에이전트가 기억하는 대화 (도구 호출 포함)
    st.session_state["messages"] = []  # 화면에 보이는 대화

for m in st.session_state["messages"]:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("tools"):
            st.caption("사용한 도구: " + " → ".join(m["tools"]))

question = st.chat_input("회사 이름이나 궁금한 점을 입력하세요")
if question:
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        history = st.session_state["history"]
        before = len(history)
        with st.status("생각하는 중이에요…", expanded=False) as status:
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
            st.markdown(out["answer"])
            if tools:
                st.caption("사용한 도구: " + " → ".join(tools))
            st.session_state["messages"].append({"role": "assistant", "content": out["answer"], "tools": tools})
