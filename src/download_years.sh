#!/usr/bin/env bash
# 연봉 상승 추이용: 해마다 9월(가을) 국민연금 자료를 받는다 (파일마다 약 110MB).
# 기준소득월액은 매년 7월 전년도 소득으로 바뀌므로, 같은 9월끼리 비교하면 해마다 '전년도 소득' 기준이 같다.
# 2021년은 9월분 파일이 없어 10월분(20211118 등록)을 쓴다. 같은 7월~다음 6월 구간이라 소득 연도는 같다.
# 첨부파일 ID는 공공데이터포털 '주기성 과거 데이터' 목록에서 확인한 값 (2026-11-05).
# 사용법 (프로젝트 폴더에서): bash src/download_years.sh
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
2020-09 FILE_000000002460141
2021-10 FILE_000000002484364
2022-09 FILE_000000002642986
2023-09 FILE_000000002828788
2024-09 FILE_000000003045465
EOF
echo 끝
