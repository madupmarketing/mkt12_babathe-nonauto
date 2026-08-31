/**
 * 바바더닷컴 수기매체 — 매일 08:00 KST GitHub 크롤링 자동 실행 트리거
 *
 * [목적] GitHub 예약(cron)은 정시 보장이 안 되어 수시간 지연됨.
 *        GAS 시간트리거(정시성 높음)가 매일 08:00 KST에 GitHub workflow_dispatch를
 *        호출 → dispatch는 즉시 실행되므로 약 08:05경 시트 적재 완료.
 *
 * [세팅 순서]
 *  1) script.google.com → 새 프로젝트 (performance_team12 계정으로 로그인 상태)
 *  2) 이 코드 전체 붙여넣기
 *  3) 프로젝트 설정(톱니바퀴) → 스크립트 속성 → 속성 추가
 *        이름 : GITHUB_TOKEN
 *        값   : (GitHub Personal Access Token — 아래 [토큰] 참고)
 *  4) 함수 선택 → installTrigger → 실행 (최초 1회, 권한 승인)
 *  5) 함수 선택 → triggerDailyCrawl → 실행 (테스트: Actions에 dispatch 실행 뜨는지 확인)
 *
 * [토큰] 다음 중 하나 (GAS 스크립트 속성에만 저장, 코드/채팅에 남기지 말 것)
 *   · Fine-grained PAT — Repository: madupmarketing/mkt12_babathe-nonauto,
 *                        Permissions > Actions: Read and write
 *   · Classic PAT — scope: repo, workflow
 */

var GITHUB_REPO   = "madupmarketing/mkt12_babathe-nonauto";
var WORKFLOW_FILE = "daily_crawl.yml";

/** 매일 트리거가 호출하는 본체: GitHub 크롤링 워크플로우를 전일자로 실행 */
function triggerDailyCrawl() {
  var token = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  if (!token) {
    throw new Error("스크립트 속성에 GITHUB_TOKEN이 없습니다. 세팅 3번 참고.");
  }

  var url = "https://api.github.com/repos/" + GITHUB_REPO
          + "/actions/workflows/" + WORKFLOW_FILE + "/dispatches";

  var res = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      "Authorization": "Bearer " + token,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28"
    },
    // target_date 비움 → main.py가 전일자(KST 어제)를 자동 적용
    payload: JSON.stringify({ ref: "main", inputs: { target_date: "" } }),
    muteHttpExceptions: true
  });

  var code = res.getResponseCode();
  Logger.log("workflow_dispatch 응답 코드: " + code + "  (204 = 성공)");
  if (code !== 204) {
    Logger.log("실패 본문: " + res.getContentText());
    throw new Error("dispatch 실패 (코드 " + code + ") — 토큰 권한/레포명 확인");
  }
}

/** 최초 1회 실행: 매일 08:00 KST 시간트리거 등록 (중복 자동 제거) */
function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "triggerDailyCrawl") ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger("triggerDailyCrawl")
    .timeBased()
    .atHour(8)            // 08시대 (KST)
    .everyDays(1)
    .inTimezone("Asia/Seoul")
    .create();
  Logger.log("트리거 등록 완료: 매일 08:00 KST → triggerDailyCrawl");
}
