/**
 * 👍👎 피드백을 구글 시트에 모으는 Apps Script (웹 화면 app/streamlit_app.py의 save_feedback이 여기로 보낸다).
 *
 * 연결 방법 (한 번만, 5분)
 * 1. 구글 시트를 새로 만든다 (이름 예: 회사 연봉 AI 피드백).
 * 2. 메뉴 [확장 프로그램] → [Apps Script]를 열고, 기본 코드를 지운 뒤 이 파일 내용을 붙여 넣는다.
 * 3. 아래 TOKEN의 값을 아무도 모를 긴 글자로 바꾼다 (예: 키보드로 막 친 20자). 저장.
 * 4. [배포] → [새 배포] → 유형 '웹 앱' → 실행 사용자 '나', 액세스 권한 '모든 사용자' → 배포.
 *    (처음에 권한 허용 화면이 나오면 본인 계정으로 허용)
 * 5. 나온 웹 앱 URL(…/exec)과 3번의 글자를 Streamlit Cloud의 앱 Settings → Secrets에 넣는다:
 *      FEEDBACK_URL = "https://script.google.com/macros/s/…/exec"
 *      FEEDBACK_TOKEN = "3번에서 정한 글자"
 *    로컬 PC에서는 .env 파일에 같은 두 줄을 넣는다 (따옴표 없이).
 * 6. 사이트에서 👍를 눌러 시트에 줄이 생기면 끝.
 *
 * TOKEN이 맞는 요청만 받아서, URL을 누가 알아도 시트에 아무거나 쓰지 못한다.
 */
const TOKEN = '여기를_긴_글자로_바꾸세요';
const HEADER = ['시간', '투표', '질문', '답 앞부분', '회사', '사용한 도구', '아쉬운 점'];

function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  if (d.token !== TOKEN) {
    return ContentService.createTextOutput('forbidden');
  }
  const book = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = book.getSheetByName('feedback') || book.insertSheet('feedback');
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADER);
    sheet.setFrozenRows(1);
  }
  // 수식으로 해석되지 않게 '=' 등으로 시작하는 글은 앞에 ' 를 붙인다
  const safe = (v) => {
    const s = String(v == null ? '' : v);
    return /^[=+\-@]/.test(s) ? "'" + s : s;
  };
  sheet.appendRow([d.time, d.vote, d.question, d.answer, d.companies, d.tools, d.comment].map(safe));
  return ContentService.createTextOutput('ok');
}
