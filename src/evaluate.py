"""에이전트 자동 평가: eval/questions.json의 질문을 차례로 묻고, 답을 기준별로 채점한다.

채점 기준 (질문마다 적힌 것만 본다. 숫자 근거·한글·완료는 모든 질문에 적용)
- 올바른 회사  expect_key     : 도구 호출 인자(company_key)에 이 문자열이 모두 들어 있어야 한다
               expect_key_any : 이 중 하나라도 들어 있으면 된다
- 올바른 도구  expect_tools   : 이 도구를 불렀어야 한다
- 오차 범위    expect_range   : 답에 "A ~ B" 꼴의 금액 범위가 있어야 한다
- 꼭 할 말     answer_any     : 묶음마다 단어 하나 이상이 답에 있어야 한다
- 숫자 근거    (항상)          : 답에 나온 '…만 원' 금액이 모두 도구 결과에 있는 값이어야 한다 (±1만 원)
- 한글 답변    (항상)          : 답 글자의 절반 이상이 한글
- 완료         (항상)          : 도구 호출 한도 안에 답을 끝냈다

결과: reports/eval/<모델>.jsonl (질문별 원본), reports/eval.md (요약)
중간에 끊겨도 같은 명령으로 이어서 실행한다 (이미 답한 질문은 건너뛴다).
사용법 (WSL): ~/venvs/pension/bin/python src/evaluate.py [--model gemini-3.5-flash] [--only q01,q02]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agent import PROVIDERS, ask  # noqa: E402

QUESTIONS = ROOT / "eval/questions.json"
OUT_DIR = ROOT / "reports/eval"
PAUSE = 5  # 질문 사이 쉬는 시간(초). 무료 분당 한도를 피한다

AMOUNT_RE = re.compile(r"(?:(\d+(?:\.\d+)?)\s*억\s*)?(?:([\d,]+)\s*만)?\s*원")
RANGE_RE = re.compile(r"(?:\d+\s*억\s*)?[\d,]+\s*만?\s*원?\s*[~∼～\-–]\s*(?:\d+\s*억\s*)?[\d,]+\s*만\s*원")


def amounts_in(text):
    """'1억 4,096만 원', '6,030만 원', '1억 원', '약 1.41억 원' → [(만 원 단위 값, 허용 오차), ...].

    '1.41억'처럼 소수로 줄여 쓴 금액은 반올림만큼 허용 오차를 넓힌다 (1.41억 → 14,100 ± 50).
    """
    out = []
    for m in AMOUNT_RE.finditer(text):
        eok, man = m.group(1), m.group(2)
        if not eok and not man:
            continue
        # "1억 원이 넘는", "1억 원 이상", "1억 원대"처럼 딱 떨어지는 기준 금액은 데이터 주장이 아니라 표현이다
        after = text[m.end():m.end() + 4]
        if eok and not man and "." not in eok and re.match(r"\s*(이\s*넘|을\s*넘|이상|대|초|중반|후반|안팎|가까이)", after):
            continue
        tol = 1
        if eok and "." in eok:
            tol = max(1, int(0.5 * 10 ** (4 - len(eok.split(".")[1]))))
        # "약 1억 2,000만 원"(실제 1억 2,009만)처럼 '약'을 붙여 반올림한 금액은 반올림 단위의 절반까지 허용한다
        digits = (man or "").replace(",", "")
        if re.search(r"약\s*$", text[max(0, m.start() - 3):m.start()]) and digits and digits.strip("0"):
            zeros = len(digits) - len(digits.rstrip("0"))
            tol = max(tol, 10 ** zeros // 2)
        elif re.search(r"약\s*$", text[max(0, m.start() - 3):m.start()]) and eok and not man:
            tol = max(tol, 5000)  # "약 1억 원" → ±5,000만
        out.append((round(float(eok or 0) * 10_000) + int((man or "0").replace(",", "") or 0), tol))
    return out


def tool_numbers(trace):
    """도구 결과에 들어 있는 금액(만 원)을 모은다."""
    nums = set()

    def walk(v, key=""):
        if isinstance(v, dict):
            for k, x in v.items():
                walk(x, k)
        elif isinstance(v, list):
            for x in v:
                walk(x, key)
        elif isinstance(v, str):  # 설명 문장 속 금액도 근거로 인정한다 ("연 7,908만 원을 넘을 수 없다")
            nums.update(a for a, _ in amounts_in(v))
        elif isinstance(v, (int, float)) and v is not True and v is not False:
            if key.endswith("_manwon"):
                nums.add(int(round(v)))
            elif key == "cap_monthly_won":
                nums.add(int(round(v / 1e4)))
                nums.add(int(round(v * 12 / 1e4)))  # 연 단위 천장 (월 상한 × 12)
    for t in trace:
        walk(t.get("result"))
    return nums


def called_keys(trace, answer=""):
    """에이전트가 '다룬' 회사 키.

    1) 회사별 도구(추정·비교)에 넘긴 키
    2) 도구 결과(예: 업종 순위)에 나온 회사 중 답에 이름이 나온 회사
       — 게임 회사 질문에서 에이전트가 업종을 바꿔 다시 찾아 넥슨코리아로 답했는데 1)만 보면 실패로 잡혀서 추가
    """
    keys = []
    for t in trace:
        a = t.get("args", {})
        keys += [a["company_key"]] if "company_key" in a else []
        keys += list(a.get("company_keys", []))

    def walk(v):
        if isinstance(v, dict):
            k = v.get("company_key")
            if isinstance(k, str) and k.split("|")[0] and k.split("|")[0] in re.sub(r"\s", "", answer).lower():
                keys.append(k)
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    for t in trace:
        walk(t.get("result"))
    return keys


def grade(q, out):
    ans, trace = out["answer"] or "", out["trace"]
    keys, tools_used = called_keys(trace, ans), {t["tool"] for t in trace}
    checks = {}
    if "expect_key" in q:
        checks["올바른 회사"] = all(any(k in c for c in keys) for k in q["expect_key"])
    if "expect_key_any" in q:
        checks["올바른 회사"] = any(any(k in c for c in keys) for k in q["expect_key_any"])
    if "expect_tools" in q:
        checks["올바른 도구"] = all(t in tools_used for t in q["expect_tools"])
    if q.get("expect_range"):
        checks["오차 범위"] = bool(RANGE_RE.search(ans))
    if "answer_any" in q:
        checks["꼭 할 말"] = all(any(w in ans for w in group) for group in q["answer_any"])
    nums, found = tool_numbers(trace), amounts_in(ans)
    ungrounded = [a for a, tol in found if not any(abs(a - n) <= tol for n in nums)]
    checks["숫자 근거"] = not ungrounded
    letters = [ch for ch in ans if ch.isalpha()]
    checks["한글 답변"] = bool(letters) and sum("가" <= ch <= "힣" for ch in letters) / len(letters) >= 0.5
    checks["완료"] = out["finished"]
    return checks, ungrounded


def save(path, done):
    with path.open("w", encoding="utf-8") as f:
        for row in done.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_summary(model, rows, path=None):
    n = len(rows)
    passed = sum(all(r["checks"].values()) for r in rows)
    lines = [f"# 에이전트 평가 결과 ({model})\n",
             f"- 질문 {n}개 중 **모든 기준 통과 {passed}개 ({passed / n:.0%})**",
             f"- 평균 모델 호출 {sum(r['tokens']['model_calls'] for r in rows) / n:.1f}번, "
             f"평균 도구 호출 {sum(len(r['trace']) for r in rows) / n:.1f}번, "
             f"평균 소요 {sum(r['seconds'] for r in rows) / n:.0f}초, "
             f"질문당 평균 토큰 {sum(r['tokens']['input'] + r['tokens']['output'] for r in rows) / n:,.0f}\n",
             "## 기준별 통과율\n", "| 기준 | 해당 질문 | 통과 |", "|---|---|---|"]
    names = dict.fromkeys(k for r in rows for k in r["checks"])
    for c in names:
        vals = [r["checks"][c] for r in rows if c in r["checks"]]
        lines.append(f"| {c} | {len(vals)} | {sum(vals)} ({sum(vals) / len(vals):.0%}) |")
    lines += ["\n## 질문별 결과\n", "| 번호 | 유형 | 질문 | 결과 | 실패한 기준 | 지어낸 금액 |", "|---|---|---|---|---|---|"]
    for r in rows:
        fail = [k for k, v in r["checks"].items() if not v]
        lines.append(f"| {r['id']} | {r['type']} | {r['question']} | {'통과' if not fail else '실패'} | "
                     f"{', '.join(fail)} | {', '.join(f'{a:,}만' for a in r['ungrounded'])} |")
    (path or ROOT / f"reports/eval/{model}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--provider", default="gemini", choices=PROVIDERS)
    p.add_argument("--model")
    p.add_argument("--only", help="쉼표로 구분한 질문 번호만 실행 (예: q01,q02)")
    p.add_argument("--rerun", action="store_true", help="이미 답한 질문도 다시 실행")
    p.add_argument("--regrade", metavar="JSONL", help="모델을 다시 부르지 않고 저장된 답을 지금 채점 기준으로 다시 채점")
    a = p.parse_args()

    if a.regrade:
        qs = {q["id"]: q for q in json.loads(QUESTIONS.read_text(encoding="utf-8"))}
        path = Path(a.regrade)
        rows = [json.loads(line) for line in path.open(encoding="utf-8")]
        for r in rows:
            r["checks"], r["ungrounded"] = grade(qs[r["id"]], r)
        save(path, {r["id"]: r for r in rows})
        write_summary(path.stem, rows)
        return

    provider = PROVIDERS[a.provider](a.model)
    tag = (a.model or provider.models[0]).replace("/", "_")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{tag}.jsonl"
    done = {}
    if out_path.exists():
        done = {r["id"]: r for r in map(json.loads, out_path.open(encoding="utf-8"))}

    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    if a.only:
        questions = [q for q in questions if q["id"] in a.only.split(",")]
    if a.rerun:  # 이번에 실행할 질문만 기존 기록에서 지운다
        for q in questions:
            done.pop(q["id"], None)
    for i, q in enumerate(questions, 1):
        if q["id"] in done:
            continue
        print(f"\n=== [{i}/{len(questions)}] {q['id']} {q['question']}", flush=True)
        t0 = time.time()
        try:
            out = ask(q["question"], provider, log=lambda s: print("   " + s, flush=True))
        except Exception as e:  # 하루 한도 등으로 실패하면 기록하지 않고 멈춘다 → 다음에 이어서
            print(f"   실패: {str(e)[:200]}\n   여기서 멈춘다. 같은 명령으로 이어서 실행하면 된다.", flush=True)
            break
        checks, ungrounded = grade(q, out)
        row = {**q, **out, "model_used": provider.model, "seconds": round(time.time() - t0, 1),
               "checks": checks, "ungrounded": ungrounded}
        done[q["id"]] = row
        save(out_path, done)  # 질문마다 저장해서, 중간에 끊겨도 이어서 할 수 있게
        print(f"   → {'통과' if all(checks.values()) else '실패'} {checks}", flush=True)
        time.sleep(PAUSE)

    rows = [done[q["id"]] for q in json.loads(QUESTIONS.read_text(encoding="utf-8")) if q["id"] in done]
    if rows:
        write_summary(tag, rows)


if __name__ == "__main__":
    main()
