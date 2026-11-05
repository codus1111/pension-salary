#!/usr/bin/env bash
# macOS · Linux · WSL에서 웹 화면 실행:  bash run_app.sh
# 처음 한 번은 설치 때문에 몇 분 걸린다.
set -e
cd "$(dirname "$0")"

PY=$(command -v python3.12 || command -v python3 || command -v python)
if [ ! -x .venv/bin/python ]; then
  echo "[1/3] 가상환경을 만드는 중..."
  "$PY" -m venv .venv || { echo "Python 3.12 이상과 venv가 필요해요 (Ubuntu: sudo apt install python3-venv)"; exit 1; }
fi

echo "[2/3] 필요한 패키지를 확인하는 중..."
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo ".env 파일을 만들었어요. AI 질문을 쓰려면 .env 의 GEMINI_API_KEY 를 채우세요. 비워 둬도 회사 직접 찾기는 됩니다."
fi

echo "[3/3] 브라우저에서 http://localhost:8501 을 여세요. 끄려면 Ctrl+C"
# 브라우저가 있으면 잠시 뒤 자동으로 연다 (macOS: open, Linux: xdg-open)
( sleep 8; (command -v open >/dev/null && open http://localhost:8501) || (command -v xdg-open >/dev/null && xdg-open http://localhost:8501) ) >/dev/null 2>&1 &
exec .venv/bin/python -m streamlit run app/streamlit_app.py --server.port 8501
