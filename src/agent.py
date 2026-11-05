"""직접 만든 회사 연봉 AI 에이전트.

Claude 앱 같은 완성된 에이전트에 MCP 도구를 붙이는 대신, 에이전트의 반복 구조를 직접 구현한다.

  질문 → 모델(도구 설명과 함께) → 모델이 도구 호출을 요청 → 우리 코드가 도구 실행
       → 결과를 모델에 돌려줌 → ... → 도구 호출 없이 답이 나오면 끝

- 도구: src/mcp_server.py의 함수 5개를 그대로 쓴다 (MCP 서버와 같은 코드, 같은 안내문)
- 모델 교체: 대화 기록을 공통 형식(Message)으로 저장하고, 모델별 변환은 Provider 클래스가 맡는다.
  지금은 Gemini(무료 한도)만 있고, 같은 형식으로 Claude·로컬 모델을 추가할 수 있다.
- 기록: 어떤 도구를 어떤 인자로 불렀는지, 몇 초 걸렸는지 trace로 남긴다 (평가에 쓴다)

사용법 (WSL)
  ~/venvs/pension/bin/python src/agent.py "토스 평균 연봉 어느 정도야?"
  ~/venvs/pension/bin/python src/agent.py --chat          # 대화 모드 (이어서 질문)
  ~/venvs/pension/bin/python src/agent.py --list-models
API 키는 .env 또는 .env.txt의 GEMINI_API_KEY에서 읽는다. 모델은 --model 또는 GEMINI_MODEL로 바꾼다
(지정하지 않으면 gemini-3.5-flash, 바쁘면 gemini-3.5-flash-lite).
"""
import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import mcp_server as tools  # noqa: E402

# 요청마다 찍히는 연결 로그("HTTP Request: ...", "AFC is enabled ...")를 끈다
for name in ("httpx", "google_genai", "google_genai.models"):
    logging.getLogger(name).setLevel(logging.WARNING)

# 2026-11 기준: 2.5-flash는 신규 사용자에게 제공되지 않고, 3.8-flash는 사용자가 몰려 503을 자주 돌려준다.
# 기본 모델이 바쁘면(503) 다음 모델로 넘어간다.
DEFAULT_GEMINI_MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
REQUEST_TIMEOUT_MS = 90_000
MAX_STEPS = 8

SYSTEM_PROMPT = tools.INSTRUCTIONS + (
    " 사용자가 묻는 말에는 항상 한국어로 답한다. 금액은 '1억 1,218만 원'처럼 읽기 쉽게 쓴다. "
    "도구 결과에 없는 숫자를 지어내지 않는다. 특히 보험료 상한 금액, 보험료율 같은 제도 숫자는 기억에 의존하지 말고 "
    "도구 결과(cap_monthly_won, method_and_limits)에 있는 값만 쓴다. 숫자의 뜻은 도구가 준 설명(*_meaning)대로 전한다. "
    "도구로 답할 수 없는 질문이면 그렇다고 말한다."
)

# 도구 설명 (모델에게 보여주는 JSON 스키마). 실제 실행은 tools의 같은 이름 함수가 한다.
TOOL_SPECS = [
    {"name": "search_company",
     "description": tools.search_company.__doc__,
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string", "description": "회사 이름 (법인명 또는 브랜드명)"},
         "limit": {"type": "integer", "description": "최대 후보 수, 기본 8"}},
         "required": ["query"]}},
    {"name": "get_salary_estimate",
     "description": tools.get_salary_estimate.__doc__,
     "parameters": {"type": "object", "properties": {
         "company_key": {"type": "string", "description": "search_company 결과의 company_key"},
         "region": {"type": "string", "description": "사용자가 지역을 말했을 때만: 시·도 이름 (예: 부산, 경기)"}},
         "required": ["company_key"]}},
    {"name": "similar_companies",
     "description": tools.similar_companies.__doc__,
     "parameters": {"type": "object", "properties": {
         "company_key": {"type": "string", "description": "기준 회사의 company_key"},
         "limit": {"type": "integer", "description": "최대 회사 수, 기본 5"}},
         "required": ["company_key"]}},
    {"name": "compare_companies",
     "description": tools.compare_companies.__doc__,
     "parameters": {"type": "object", "properties": {
         "company_keys": {"type": "array", "items": {"type": "string"},
                          "description": "search_company 결과의 company_key 목록 (최대 5개)"}},
         "required": ["company_keys"]}},
    {"name": "industry_ranking",
     "description": tools.industry_ranking.__doc__,
     "parameters": {"type": "object", "properties": {
         "industry_keyword": {"type": "string", "description": "업종 이름에 들어갈 키워드 (예: 증권, 소프트웨어)"},
         "min_members": {"type": "integer", "description": "최소 가입자 수, 기본 100"},
         "limit": {"type": "integer", "description": "최대 회사 수, 기본 10"}},
         "required": ["industry_keyword"]}},
    {"name": "method_and_limits",
     "description": tools.method_and_limits.__doc__,
     "parameters": {"type": "object", "properties": {}}},
]
TOOL_FUNCS = {s["name"]: getattr(tools, s["name"]) for s in TOOL_SPECS}


@dataclass
class Message:
    """모델에 상관없는 공통 대화 기록 한 줄."""
    role: str                      # "user" | "assistant" | "tool"
    text: str = ""
    tool_calls: list = field(default_factory=list)   # assistant: [{"id", "name", "args"}]
    tool_name: str = ""            # tool: 어떤 도구의 결과인지
    tool_call_id: str = ""
    result: object = None          # tool: 도구가 돌려준 값
    raw: object = None             # assistant: 모델 원본 응답 (같은 모델에 되돌려줄 때 필요한 정보 보존)


def load_env(name):
    if os.environ.get(name):
        return os.environ[name]
    for fname in (".env", ".env.txt"):
        p = ROOT / fname
        if p.exists():
            m = re.search(rf"^\s*{name}\s*=\s*['\"]?([^\s'\"#]+)", p.read_text(encoding="utf-8-sig"), re.M)
            if m and m.group(1) != "여기에_키":  # .env.example을 복사만 하고 안 채운 경우는 없는 것으로 본다
                return m.group(1)
    sys.exit(f"{name}를 환경 변수나 .env / .env.txt에서 찾지 못했다.")


class GeminiProvider:
    """Google Gemini API. 무료 한도 안에서 쓴다."""

    def __init__(self, model=None):
        from google import genai
        from google.genai import types
        self.types = types
        # SDK의 숨은 재시도를 끄고(attempts=1) 재시도는 step()에서 직접 한다. 그래야 멈춘 것처럼 안 보인다.
        self.client = genai.Client(api_key=load_env("GEMINI_API_KEY"), http_options=types.HttpOptions(
            timeout=REQUEST_TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1)))
        chosen = model or os.environ.get("GEMINI_MODEL")
        self.models = [chosen] if chosen else list(DEFAULT_GEMINI_MODELS)
        self.model = self.models[0]
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=s["name"], description=s["description"],
                                          parameters_json_schema=s["parameters"]) for s in TOOL_SPECS])],
            # 도구 실행은 SDK에 맡기지 않고 우리 반복 구조에서 직접 한다
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )

    def _contents(self, history):
        t, contents = self.types, []
        for m in history:
            if m.role == "user":
                contents.append(t.Content(role="user", parts=[t.Part(text=m.text)]))
            elif m.role == "assistant":
                contents.append(m.raw)  # 원본을 그대로 돌려줘야 모델 내부 정보(사고 서명 등)가 유지된다
            elif m.role == "tool":
                part = t.Part.from_function_response(name=m.tool_name, response={"result": m.result})
                if contents and contents[-1].role == "user" and contents[-1].parts[0].function_response:
                    contents[-1].parts.append(part)  # 연속된 도구 결과는 한 묶음으로
                else:
                    contents.append(t.Content(role="user", parts=[part]))
        return contents

    def step(self, history, log=None):
        contents = self._contents(history)
        for attempt in range(6):
            try:
                resp = self.client.models.generate_content(model=self.model, contents=contents, config=self.config)
                break
            except Exception as e:
                msg = str(e)
                busy = "503" in msg
                daily_quota_out = "429" in msg and "PerDay" in msg  # 하루 한도는 기다려도 안 풀린다
                if (busy or daily_quota_out) and self.model != self.models[-1]:  # 다음 모델로
                    nxt = self.models[self.models.index(self.model) + 1]
                    why = "바빠서(503)" if busy else "하루 무료 한도를 다 써서(429)"
                    log and log(f"  {self.model}이 {why} {nxt}로 바꾼다")
                    self.model = nxt
                    continue
                if daily_quota_out:
                    raise
                if ("429" in msg or "503" in msg) and attempt < 5:  # 분당 한도·일시 과부하면 기다렸다 다시
                    wait = 10 * (attempt + 1)
                    log and log(f"  {msg[:3]} 응답, {wait}초 뒤 다시 시도")
                    time.sleep(wait)
                    continue
                raise
        content = resp.candidates[0].content
        calls = [{"id": f"call_{i}", "name": c.name, "args": dict(c.args or {})}
                 for i, c in enumerate(resp.function_calls or [])]
        text = "".join(p.text for p in (content.parts or []) if getattr(p, "text", None) and not p.thought) \
            if content and content.parts else ""
        usage = resp.usage_metadata
        tokens = {"input": getattr(usage, "prompt_token_count", 0) or 0,
                  "output": getattr(usage, "candidates_token_count", 0) or 0}
        return Message(role="assistant", text=text, tool_calls=calls, raw=content), tokens

    def list_models(self):
        return [m.name for m in self.client.models.list()
                if "generateContent" in (getattr(m, "supported_actions", None) or [])]


PROVIDERS = {"gemini": GeminiProvider}


def chat(provider, quiet=False):
    """터미널에서 질문을 이어서 주고받는다. 앞의 대화를 기억한다."""
    print("회사 연봉 에이전트입니다. 회사 이름이나 비교하고 싶은 회사를 물어보세요.")
    print("예: 토스 평균 연봉 어느 정도야? / 네이버랑 카카오 비교해줘 / 이 추정 얼마나 정확해?")
    print("끝내려면 '끝'이나 exit를 입력하세요. 처음부터 다시 하려면 '새로'를 입력하세요.\n")
    history = []
    while True:
        try:
            q = input("질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q in ("끝", "exit", "quit", "q"):
            break
        if q == "새로":
            history = []
            print("대화를 새로 시작합니다.\n")
            continue
        t0, before = time.time(), len(history)
        try:
            out = ask(q, provider, history=history, log=None if quiet else (lambda s: print("  " + s, flush=True)))
        except Exception as e:  # 한도 초과 등: 대화는 끝내지 않고 알려준다
            print(f"\n잠시 답을 받지 못했어요: {str(e)[:150]}\n")
            del history[before:]  # 답을 못 받은 질문과 그 도중 기록은 뺀다
            continue
        tools_used = " → ".join(t["tool"] for t in out["trace"]) or "없음"
        print(f"\n{out['answer']}\n")
        print(f"  (사용한 도구: {tools_used} | {time.time() - t0:.0f}초 | 모델 {provider.model})\n")
    print("대화를 마칩니다.")


def run_tool(name, args):
    if name not in TOOL_FUNCS:
        return {"error": f"없는 도구: {name}"}
    try:
        result = TOOL_FUNCS[name](**args)
    except Exception as e:  # 도구 오류도 모델에게 알려서 스스로 고치게 한다 (예: 잘못된 company_key)
        return {"error": str(e)}
    # pandas·numpy 값을 일반 JSON 값으로 바꿔 모델 API로 보낼 수 있게 한다.
    # NaN은 JSON에 없는 값이라 그대로 보내면 400 오류가 난다 ("현대자동차" 검색 결과의 빈 업종명) → None으로
    return _clean(json.loads(json.dumps(result, ensure_ascii=False,
                                        default=lambda o: o.item() if hasattr(o, "item") else str(o))))


def _clean(v):
    if isinstance(v, float) and v != v:  # NaN
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def ask(question, provider, max_steps=MAX_STEPS, log=None, history=None):
    """질문 하나를 끝까지 처리한다. 답, 도구 호출 기록, 사용 토큰을 돌려준다.

    log를 주면 단계마다 진행 상황을 바로 알린다 (예: log=print).
    history에 이전 대화 목록을 주면 이어서 묻는다 ("그럼 카카오는?"). 목록은 이 함수 안에서 늘어난다.
    """
    history = history if history is not None else []
    history.append(Message(role="user", text=question))
    trace, tokens = [], {"input": 0, "output": 0, "model_calls": 0}
    for step in range(1, max_steps + 1):
        t0 = time.time()
        msg, used = provider.step(history, log=log)
        log and log(f"[{step}단계] {provider.model} 응답 {time.time() - t0:.1f}초, "
                    f"도구 요청 {[c['name'] for c in msg.tool_calls] or '없음'}")
        tokens["input"] += used["input"]
        tokens["output"] += used["output"]
        tokens["model_calls"] += 1
        history.append(msg)
        if not msg.tool_calls:
            return {"question": question, "answer": msg.text, "trace": trace, "tokens": tokens, "finished": True}
        for call in msg.tool_calls:
            t0 = time.time()
            result = run_tool(call["name"], call["args"])
            trace.append({"tool": call["name"], "args": call["args"],
                          "ok": not (isinstance(result, dict) and "error" in result),
                          "seconds": round(time.time() - t0, 2),
                          "result": result})  # 평가에서 답의 숫자가 도구 결과에 있는지 대조한다
            history.append(Message(role="tool", tool_name=call["name"], tool_call_id=call["id"], result=result))
    return {"question": question, "answer": "도구 호출 횟수 한도에 걸려 답을 끝내지 못했다.",
            "trace": trace, "tokens": tokens, "finished": False}


def main():
    p = argparse.ArgumentParser(description="회사 연봉 AI 에이전트")
    p.add_argument("question", nargs="?")
    p.add_argument("--provider", default="gemini", choices=PROVIDERS)
    p.add_argument("--model")
    p.add_argument("--list-models", action="store_true")
    p.add_argument("--chat", action="store_true", help="대화 모드: 질문을 이어서 할 수 있다")
    p.add_argument("--quiet", action="store_true", help="단계별 진행 상황을 숨긴다")
    a = p.parse_args()

    provider = PROVIDERS[a.provider](a.model)
    if a.list_models:
        print("\n".join(provider.list_models()))
        return
    if a.chat:
        chat(provider, quiet=a.quiet)
        return
    if not a.question:
        p.error("질문을 입력하세요")

    out = ask(a.question, provider, log=lambda s: print(s, flush=True))
    print(f"\n[모델] {a.provider} / {provider.model}")
    for i, t in enumerate(out["trace"], 1):
        print(f"[도구 {i}] {t['tool']}({json.dumps(t['args'], ensure_ascii=False)}) "
              f"{'성공' if t['ok'] else '오류'} {t['seconds']}초")
    print(f"[토큰] 입력 {out['tokens']['input']:,} / 출력 {out['tokens']['output']:,}, "
          f"모델 호출 {out['tokens']['model_calls']}번\n")
    print(out["answer"])


if __name__ == "__main__":
    main()
