"""MCP 서버의 도구들을 직접 불러 결과를 눈으로 확인한다.

1) 함수를 바로 호출  2) 실제 MCP 프로토콜(stdio)로 서버를 띄워 도구 목록과 호출 결과 확인
사용법 (WSL): ~/venvs/pension/bin/python src/try_tools.py
             ~/venvs/pension/bin/python src/try_tools.py search 토스 비바리퍼블리카   # 검색만
             ~/venvs/pension/bin/python src/try_tools.py call get_salary_estimate '{"company_key": "네이버|220816"}'
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def direct():
    t = time.time()
    import mcp_server as s
    print(f"서버 데이터 로드 {time.time() - t:.1f}초\n")
    for q in ["토스", "SK하이닉스", "카카오", "대신정보통신"]:
        print(f"== search_company({q!r})")
        for c in s.search_company(q, limit=4):
            print("  ", c)
    key = s.search_company("대신정보통신", 1)[0]["company_key"]
    print("\n== get_salary_estimate(대신정보통신)")
    print(json.dumps(s.get_salary_estimate(key), ensure_ascii=False, indent=2))
    keys = [s.search_company(q, 1)[0]["company_key"] for q in ["네이버", "카카오", "우아한형제들"]]
    print("\n== compare_companies(네이버, 카카오, 우아한형제들)")
    for r in s.compare_companies(keys):
        print("  ", {k: r[k] for k in ("name", "estimated_salary_manwon", "range_manwon",
                                       "dart_actual_salary_manwon", "monthly_exit_rate")})
    print("\n== industry_ranking('소프트웨어', limit=5)")
    print(json.dumps(s.industry_ranking("소프트웨어", limit=5), ensure_ascii=False, indent=2))


async def protocol(via_wsl_exe=False):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    if via_wsl_exe:  # Windows의 Claude가 .mcp.json대로 띄우는 것과 같은 경로
        cfg = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["company-salary"]
        params = StdioServerParameters(command="/mnt/c/Windows/System32/wsl.exe", args=cfg["args"])
    else:
        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "src/mcp_server.py")])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("\n== MCP 프로토콜로 본 도구 목록:", [t.name for t in tools.tools])
            res = await session.call_tool("search_company", {"query": "네이버", "limit": 2})
            print("== call_tool(search_company, 네이버):", res.content[0].text[:300])


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "call":  # 도구 하나를 JSON 인자로 호출
        import mcp_server as s
        print(json.dumps(getattr(s, sys.argv[2])(**json.loads(sys.argv[3] if len(sys.argv) > 3 else "{}")),
                         ensure_ascii=False, indent=1))
    elif len(sys.argv) > 1 and sys.argv[1] == "wsl":
        asyncio.run(asyncio.wait_for(protocol(via_wsl_exe=True), timeout=60))
    elif len(sys.argv) > 2 and sys.argv[1] == "search":
        import mcp_server as s
        for q in sys.argv[2:]:
            print(f"== {q}")
            for c in s.search_company(q, 3):
                print("  ", c)
    else:
        direct()
        asyncio.run(protocol())
