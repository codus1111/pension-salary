#!/usr/bin/env bash
# 국민연금 가입 사업장 내역 2025년 1~12월분을 공공데이터포털에서 받는다 (파일마다 약 110MB).
# 각 파일은 등록일 전달의 자료다 (20250224 등록 = 2025-01분).
# 첨부파일 ID는 공공데이터포털 '주기성 과거 데이터' 목록에서 확인한 값 (2026-11-04).
# 사용법 (프로젝트 폴더에서): bash src/download_months.sh
set -u
mkdir -p data/raw/monthly
while read -r ym atch; do
  out="data/raw/monthly/nps_${ym}.csv"
  if [ -s "$out" ]; then echo "있음: $out"; continue; fi
  curl -sSL --fail -o "$out.part" "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=${atch}&fileDetailSn=1" \
    && mv "$out.part" "$out" && echo "받음: $out $(du -h "$out" | cut -f1)" \
    || { echo "실패: $ym"; rm -f "$out.part"; }
  sleep 5  # 서버에 부담을 주지 않도록 쉬어 간다
done <<'EOF'
2025-01 FILE_000000003102254
2025-02 FILE_000000003113171
2025-03 FILE_000000003125831
2025-04 FILE_000000003142010
2025-05 FILE_000000003167253
2025-06 FILE_000000003195518
2025-07 FILE_000000003225993
2025-08 FILE_000000003258024
2025-09 FILE_000000003508797
2025-10 FILE_000000003539630
2025-11 FILE_000000003569855
2025-12 FILE_000000003590996
EOF
echo 끝
