# 바바더닷컴 수기매체 자동화 — 인수인계 (2026-08-31)

> 전임자 퇴사에 따른 인수인계 문서. 새 담당자 또는 새 Claude 세션이 그대로 이어받도록 작성.
> 이 문서는 레포(`madupmarketing/mkt12_babathe-nonauto`)에도 `HANDOFF.md`로 커밋되어 있음.

---

## 0. 30초 요약

- **하는 일**: 매일 아침 버즈빌·ive·네이버쇼핑·에디AI 광고 데이터를 자동 수집 → Google Sheets `버티컬_raw`에 6행 적재.
- **어디서 도나**: GitHub Actions (레포 `madupmarketing/mkt12_babathe-nonauto`, 공개, 매드업 org 소유).
- **지금 상태**: **정상 작동 중.** 매일 예약 실행 + keepalive로 자동 유지됨. 담당자 없어도 계속 돎.
- **최근 이슈**: 예약이 아침에 지연되던 문제 → 예약 시각을 05:50 KST로 앞당겨 버퍼 확보(해결). 
- **미완(선택)**: "매일 9시 전 100% 보장"을 원하면 GAS 트리거 추가 필요(아래 6번). 안 해도 평상시 8시대 도착.

---

## 1. 접근 권한 (인수 시 가장 먼저 확인)

| 자원 | 무엇 | 인수 시 조치 |
|------|------|-------------|
| **GitHub org** | `madupmarketing` (레포 소유) | 새 담당자를 org 멤버(write)로 추가 |
| **GitHub 계정(현재 사용)** | `performanceteam12-sketch` — 이 계정으로 커밋/실행해 왔음 (scope: repo, workflow) | 이 팀 계정 자격증명 인수 **또는** 새 담당자 개인 계정을 org에 추가 |
| **전임자 개인 계정** | `youngjookang-md` | 이제 아무것도 여기 의존 안 함(레포 org 이전 완료). 정리 가능 |
| **Google Sheet** | ID `1ks8wr3Rh8HeJG5bIwfAUlZ1PLsUB_aeDp3GBzmCckY4`, 탭 `버티컬_raw` | 새 담당자에게 편집 권한 공유 확인 |
| **Google 서비스계정** | 시트에 편집자로 공유된 기계 계정 (`GOOGLE_SERVICE_ACCOUNT` 시크릿) | 시트 공유 유지되는지만 확인 |

> ⚠️ 전임자 개인 GitHub(`youngjookang-md`)와 로컬 PC의 파일에 의존하지 말 것. 필요한 건 전부 org 레포 안에 있음.

---

## 2. 자동화 동작 방식

- 진입점: `main.py` — 크롤러 4종 실행 후 `sheets/uploader.py`로 `버티컬_raw`에 6행 적재(중복 날짜는 삭제 후 재삽입 = idempotent).
- 크롤러: `crawlers/buzzvil.py`, `iscreen.py`(ive), `naver_shopping.py`, `ediai.py`.
- 각 실행은 **전일자(KST 어제)** 데이터를 채움. (예: 8/31 실행 → 8/30 데이터)
- 하루 6행: 버즈빌UA / ive / 네이버쇼핑_PC / 네이버쇼핑_M / 에디AI(AI상품매칭) / 에디AI(트렌드박스).

### 스케줄
- GitHub Actions cron: `50 20 * * *` (UTC) = **KST 05:50**. `.github/workflows/daily_crawl.yml`
- `keepalive.yml`: 12일마다 작은 커밋 → 레포 "활성" 유지 → GitHub이 예약을 자동정지시키지 않게 함.

### 시크릿 (레포 Settings → Secrets and variables → Actions)
`BUZZVIL_EMAIL/PASSWORD`, `ISCREEN_ID/PW`, `NAVER_ID/PW/COOKIE`, `EDIAI_ID/PW`, `GOOGLE_SERVICE_ACCOUNT`, (선택) `SLACK_WEBHOOK_URL`, 변수 `GAS_RERUN_URL`.
> 코드엔 값이 없고 전부 Secrets에서 주입됨. **매체 비번이 바뀌면 여기서 해당 Secret만 갱신**하면 됨.

---

## 3. 자주 하는 작업

**특정 날짜 수동 재수집 (백필)**
- GitHub → 레포 → **Actions → Daily Media Crawl → Run workflow** → `target_date`에 `YYYY-MM-DD` 입력 → 실행.
- CLI: `gh workflow run daily_crawl.yml --repo madupmarketing/mkt12_babathe-nonauto -f target_date=2026-08-27`

**실행 상태/로그 확인**
- Actions 탭에서 초록불/빨간불 확인. 빨간불이면 로그에서 어떤 매체가 실패했는지 확인.
- CLI: `gh run list --repo madupmarketing/mkt12_babathe-nonauto --workflow daily_crawl.yml -L 10`

---

## 4. 알려진 특성 (버그 아님 — 오해 방지)

- **버즈빌은 노출(imps)이 항상 0.** 설계상 클릭·광고비만 수집(README 명세). 노출 칸이 비어보여도 정상.
- **네이버쇼핑은 크롤링이 아니라 `config.json`의 고정값** 사용. 실제 값이 바뀌면 `naver_shopping_static`을 수동 수정해야 함. (`main.py` 주석: "크롤러 안정화되면 교체할 것")
- **GitHub 예약은 정시 보장이 안 됨(best-effort).** 보통 수십 분~2시간 지연. 그래서 05:50으로 앞당겨 버퍼를 둠.

---

## 5. 최근 변경 이력 (2026-08-28~31, `performanceteam12-sketch` 커밋)

| 커밋 | 내용 |
|------|------|
| `e69b9cb` | cron 08:00→07:40 (정각 혼잡 회피) |
| `f3a7f01` | `keepalive.yml` 추가 (예약 자동정지 방지) |
| `490541c` | cron 07:40→05:50 (예약 지연 버퍼로 9시 전 도착 목표) |
| (수동) | 8/27 데이터 백필 실행 |

---

## 6. 미완 과제 (선택) — 매일 9시 전 100% 보장

GitHub 예약 지연을 완전히 없애려면 **GAS 시간트리거가 08:00 KST에 GitHub을 호출**하게 하면 됨(즉시 실행 → 08:05 도착).
- 코드: 레포 `handoff/babathe_gas_trigger.gs` (또는 전임자 전달본).
- 순서: script.google.com에서 새 프로젝트 → 코드 붙여넣기 → 스크립트 속성에 `GITHUB_TOKEN`(fine-grained PAT, Actions: RW) 입력 → `installTrigger` 1회 실행.
- 완료 후 GitHub cron은 백업용(예: 11:30 KST)으로 옮기면 이중 안전망.
- **주의**: GAS는 구글 로그인 + 트리거 권한 승인 + 토큰 입력이 필요해 사람이 직접 세팅해야 함(자동화 불가). 안 해도 현재 버퍼로 평상시 8시대 도착.

---

## 7. 관련 자동화 (같은 시트, 다른 스크립트)

- **네이버브검_raw 자동화** (Apps Script, `performance_team12@madup.com` 계정): 매일 전일자 행 복사. 
  - 하루 블록을 4행 고정 → **"마지막 날짜와 같은 행 전체"로 동적 인식**하도록 개선한 v2 코드가 준비돼 있음(전임자 전달본 `브랜드검색_자동화_인수인계_v2.md`). 적용 여부 확인 필요.
- 기타 백업 레포(롯데ON 등)는 `madup-repos-backup.zip` 참고. 이 인수인계의 범위는 **바바더닷컴**만.

---

## 8. 새 Claude 세션에서 이어받는 법

1. 새 담당자가 자기 PC에서 `gh auth login` → 매드업 org 접근 되는 GitHub 계정으로 로그인.
2. 이 레포를 clone 또는 GitHub 웹에서 열기: `madupmarketing/mkt12_babathe-nonauto`.
3. Claude에게 이 `HANDOFF.md`를 읽히고 "바바더닷컴 수기매체 자동화 이어받을게" 라고 시작.
4. 상태 점검: `gh run list ...`로 최근 실행이 매일 초록불인지 확인.

---

문의 지점: 매드업 퍼포먼스 12팀. 이 문서 최신본은 레포 `HANDOFF.md`.
