# 어느 PC·서버에서든 같은 환경으로 웹 화면을 띄운다 (Python 버전·패키지가 고정됨)
#   docker build -t pension-salary .
#   docker run -p 8501:8501 --env-file .env pension-salary     → http://localhost:8501
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PENSION_DATA_DIR=/app/data/app \
    PYTHONUNBUFFERED=1
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
