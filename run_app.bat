@echo off
rem 윈도우에서 웹 화면 실행: 이 파일을 더블클릭한다. 처음 한 번은 설치 때문에 몇 분 걸린다.
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 가상환경을 만드는 중...
    py -3.12 -m venv .venv 2>nul || python -m venv .venv
    if errorlevel 1 (
        echo Python 3.12 이상이 필요해요. https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행하세요.
        pause
        exit /b 1
    )
)

echo [2/3] 필요한 패키지를 확인하는 중...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo 패키지 설치에 실패했어요. 인터넷 연결을 확인하고 다시 실행하세요.
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo .env 파일을 만들었어요. AI 질문을 쓰려면 .env 의 GEMINI_API_KEY 를 채우세요. 비워 둬도 회사 직접 찾기는 됩니다.
)

echo [3/3] 잠시 뒤 브라우저에서 http://localhost:8501 이 열려요. 끄려면 이 창을 닫으세요.
rem 서버가 뜰 시간을 조금 준 뒤 브라우저를 연다
start "" /b cmd /c "timeout /t 8 >nul & start http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app\streamlit_app.py --server.port 8501
pause
