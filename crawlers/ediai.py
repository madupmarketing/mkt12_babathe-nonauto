"""
에디AI 크롤러 (console.aedi.ai 기반)
- 로그인: https://console.aedi.ai/en/login (국가: Korea)
- 리포트: https://advertiser.aedi.ai/advertisements/agency/report
- 광고주: 바바더닷컴(바바더닷컴), 캠페인 2종 순차 조회
- 반환: {"trendbox": {...}, "ai_matching": {...}}
"""

import logging
import os
import re
import time

from utils.dates import get_target_date

logger = logging.getLogger(__name__)

LOGIN_URL  = "https://console.aedi.ai/en/login"
REPORT_URL = "https://advertiser.aedi.ai/advertisements/agency/report"

ADVERTISER_NAME = "바바더닷컴"

# 캠페인 드롭다운에서 선택할 텍스트
CAMPAIGNS = {
    "ai_matching": "AI상품매칭",
    "trendbox":    "트렌드박스",
}


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise EnvironmentError(f"환경변수 {name}이 설정되지 않았습니다.")
    return val


def _clean_number(text: str) -> int:
    cleaned = re.sub(r"[^\d]", "", str(text).strip())
    return int(cleaned) if cleaned else 0


def build_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)


def login(driver):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    logger.info("[EdiAI] 로그인 시작")
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 20)

    # 1. 국가 드롭다운 → Korea 선택
    nation_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'input[name="nation"]')))
    nation_input.click()
    time.sleep(1)
    korea_option = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'li.kr')))
    korea_option.click()
    logger.info("[EdiAI] 국가 Korea 선택")
    time.sleep(0.5)

    # 2. Username / Password 입력
    driver.find_element(By.CSS_SELECTOR, 'input[name="username"]').send_keys(_require_env("EDIAI_ID"))
    driver.find_element(By.CSS_SELECTOR, 'input[name="password"]').send_keys(_require_env("EDIAI_PW"))
    time.sleep(0.3)

    # 3. Login 버튼 클릭 (type="button", class="btn_login")
    btn = driver.find_element(By.CSS_SELECTOR, 'button.btn_login')
    driver.execute_script("arguments[0].click();", btn)
    logger.info("[EdiAI] Login 버튼 클릭")
    time.sleep(6)

    try:
        driver.save_screenshot("/tmp/ediai_login.png")
    except Exception:
        pass

    current = driver.current_url
    logger.info(f"[EdiAI] 로그인 후 URL: {current}")
    if "/en/login" in current:
        raise RuntimeError(f"[EdiAI] 로그인 실패 — URL: {current}")

    logger.info("[EdiAI] 로그인 성공")


def _set_date_range(driver, target_date: str):
    """
    날짜 필터를 target_date로 설정.
    - target_date == KST 전일자: '어제' 단축 버튼 사용
    - 그 외: 날짜 텍스트 입력 필드 직접 설정 (YYYY-MM-DD 형식)
    """
    from datetime import datetime, timezone, timedelta as _td

    kst = timezone(_td(hours=9))
    yesterday = (datetime.now(kst) - _td(days=1)).strftime("%Y-%m-%d")

    if target_date == yesterday:
        clicked = driver.execute_script("""
            var tags = ['button', 'a', 'span', 'li', 'div'];
            for (var ti = 0; ti < tags.length; ti++) {
                var els = document.querySelectorAll(tags[ti]);
                for (var i = 0; i < els.length; i++) {
                    var t = (els[i].textContent || '').trim();
                    var st = window.getComputedStyle(els[i]);
                    if (t === '어제' && st.display !== 'none' && st.visibility !== 'hidden') {
                        els[i].click(); return true;
                    }
                }
            }
            return false;
        """)
        if clicked:
            logger.info("[EdiAI] '어제' 버튼 클릭")
            time.sleep(1)
        else:
            logger.warning("[EdiAI] '어제' 버튼 없음 — 날짜 직접 입력 시도")
            _set_date_direct(driver, target_date)
    else:
        logger.info(f"[EdiAI] target_date({target_date}) ≠ yesterday({yesterday}) — 날짜 직접 입력")
        _set_date_direct(driver, target_date)


def _set_date_direct(driver, target_date: str):
    """
    Flatpickr 라이브러리 API로 날짜 직접 설정.
    - EdiAI는 flatpickr-input 사용 → DOM 조작 불가, _flatpickr.setDate() 필요
    - id: default_start_picker / default_end_picker (진단 로그에서 확인)
    """
    result = driver.execute_script("""
        var d = arguments[0];
        var startEl = document.getElementById('default_start_picker');
        var endEl   = document.getElementById('default_end_picker');
        if (!startEl || !endEl) return 'no_elements';
        var fp0 = startEl._flatpickr;
        var fp1 = endEl._flatpickr;
        if (!fp0 || !fp1) return 'no_flatpickr_instance';
        fp0.setDate(d, true);
        fp1.setDate(d, true);
        return 'fp_set | start=' + startEl.value + ' end=' + endEl.value;
    """, target_date)
    logger.info(f"[EdiAI] Flatpickr 날짜 설정: {result}")
    time.sleep(1)


def _set_yesterday(driver, target_date: str | None = None):
    """하위호환 — target_date 미전달 시 어제 버튼만 시도."""
    if target_date is None:
        from utils.dates import get_target_date
        target_date = get_target_date()
    _set_date_range(driver, target_date)


def _select_advertiser(driver):
    """광고주 드롭다운 (React-Select, .report_SelectAuid) — Selenium으로 직접 조작."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    time.sleep(1)
    wait = WebDriverWait(driver, 10)
    try:
        # React-Select control 클릭으로 드롭다운 열기
        control = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, '.report_SelectAuid [class*="-control"]')
        ))
        control.click()
        time.sleep(1)
        # 열린 메뉴에서 ADVERTISER_NAME 포함 옵션 클릭
        options = driver.find_elements(By.CSS_SELECTOR, '[class*="-option"]')
        for opt in options:
            if ADVERTISER_NAME in (opt.text or ""):
                opt.click()
                logger.info("[EdiAI] 광고주 선택 완료")
                time.sleep(1)
                return
        logger.warning("[EdiAI] 광고주 옵션 없음 — 기본값 유지")
    except Exception as e:
        logger.warning(f"[EdiAI] 광고주 선택 오류: {e}")


def _select_campaign(driver, campaign_keyword: str):
    """
    캠페인 드롭다운 (#selectBoxWrap 체크박스 멀티셀렉트).
    keyword 포함 캠페인만 체크, 나머지 해제.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    time.sleep(1)
    wait = WebDriverWait(driver, 10)
    try:
        # 드롭다운 열기
        wrap = wait.until(EC.element_to_be_clickable((By.ID, "selectBoxWrap")))
        wrap.click()
        time.sleep(1.5)

        # JS: getComputedStyle로 가시성 확인 (headless에서 getBoundingClientRect는 0을 반환할 수 있음)
        # 레이블 자체 textContent 먼저 확인, 없으면 부모 최대 4단계 탐색
        actions = driver.execute_script("""
            var kw = arguments[0];
            var done = [];
            var labels = document.querySelectorAll('label[for^="ckb_"]');
            for (var i = 0; i < labels.length; i++) {
                var forId = labels[i].getAttribute('for');
                if (forId === 'ckb_all') continue;
                // ckb_0~99: 컬럼 필터 체크박스(날짜·노출수 등) — 건너뜀
                // 실제 캠페인 ID는 대형 숫자 (예: ckb_7385, ckb_7386)
                var numMatch = forId.match(/^ckb_(\d+)$/);
                if (numMatch && parseInt(numMatch[1]) < 100) continue;
                // getComputedStyle로 숨겨진 레이블 제외 (headless에서 안정적)
                var st = window.getComputedStyle(labels[i]);
                if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') continue;
                var chk = document.getElementById(forId);
                if (!chk) continue;
                // 레이블 자체 텍스트 먼저, 없으면 부모 탐색
                var text = (labels[i].textContent || '').replace(/\\s+/g, ' ').trim();
                if (!text || text.length < 2) {
                    var node = labels[i];
                    for (var d = 0; d < 4; d++) {
                        node = node.parentElement;
                        if (!node) break;
                        var tc = (node.textContent || '').replace(/\\s+/g, ' ').trim();
                        if (tc.length > 1 && tc.length < 100) { text = tc; break; }
                    }
                }
                var isTarget = text.indexOf(kw) >= 0;
                // XOR: 상태 불일치할 때만 클릭
                if (isTarget !== chk.checked) {
                    labels[i].click();
                    done.push(forId + ':' + (isTarget ? 'on' : 'off') + ':' + text.substring(0, 15));
                }
            }
            return done.join(',') || 'no_change';
        """, campaign_keyword)

        logger.info(f"[EdiAI] 캠페인 '{campaign_keyword}' 설정: {actions}")
        time.sleep(0.5)
        # 드롭다운 닫기
        driver.find_element(By.TAG_NAME, "body").click()
        time.sleep(0.5)
    except Exception as e:
        logger.warning(f"[EdiAI] 캠페인 선택 오류: {e}")


def _click_search(driver):
    """'조회' 버튼 클릭 — 가시성 확인 후 클릭."""
    clicked = driver.execute_script("""
        var tags = ['button', 'a', 'span', 'div'];
        for (var ti = 0; ti < tags.length; ti++) {
            var els = document.querySelectorAll(tags[ti]);
            for (var i = 0; i < els.length; i++) {
                var t = (els[i].textContent || '').trim();
                var st = window.getComputedStyle(els[i]);
                if (t === '조회' && st.display !== 'none' && st.visibility !== 'hidden') {
                    els[i].click(); return true;
                }
            }
        }
        return false;
    """)
    if clicked:
        logger.info("[EdiAI] 조회 버튼 클릭")
    else:
        logger.warning("[EdiAI] 조회 버튼 없음")
    time.sleep(5)


def _extract_data(driver, label: str) -> dict | None:
    """
    JS로 '합계' 행을 찾아 컬럼 위치 기준으로 데이터 추출.
    컬럼 순서(0-indexed): 날짜|노출수|클릭수|클릭률|전환수|전환율|광고비|전환금액|ROAS|...
    """
    try:
        driver.save_screenshot(f"/tmp/ediai_{label}.png")
    except Exception:
        pass

    # JS로 '합계' 행 찾아 전체 셀 텍스트 반환 (숫자/기호만)
    cells = driver.execute_script("""
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            var t = (all[i].innerText || '').trim();
            if (t === '합계' && all[i].children.length === 0) {
                var row = all[i].parentElement;
                while (row && row.children.length < 5) {
                    row = row.parentElement;
                }
                if (!row) return null;
                var result = [];
                for (var j = 0; j < row.children.length; j++) {
                    result.push((row.children[j].innerText || '').trim());
                }
                return result;
            }
        }
        return null;
    """)

    if not cells:
        # 합계 행 없으면 날짜 행 직접 탐색
        logger.warning(f"[EdiAI/{label}] 합계 행 없음 — 날짜 행 탐색")
        cells = driver.execute_script("""
            var all = document.querySelectorAll('*');
            for (var i = 0; i < all.length; i++) {
                var t = (all[i].innerText || '').trim();
                if (/^\\d{4}-\\d{2}-\\d{2}$/.test(t) && all[i].children.length === 0) {
                    var row = all[i].parentElement;
                    while (row && row.children.length < 5) {
                        row = row.parentElement;
                    }
                    if (!row) return null;
                    var result = [];
                    for (var j = 0; j < row.children.length; j++) {
                        result.push((row.children[j].innerText || '').trim());
                    }
                    return result;
                }
            }
            return null;
        """)

    if not cells:
        logger.error(f"[EdiAI/{label}] 데이터 행을 찾을 수 없음")
        return None

    logger.info(f"[EdiAI/{label}] 셀 수: {len(cells)}, 내용: {cells}")

    # '합계' 셀 위치를 동적으로 탐지 — 셀 구조가 달라져도 안전
    try:
        base = next(i for i, c in enumerate(cells) if c.strip() == "합계")
    except StopIteration:
        base = -1  # '합계' 없으면 0-indexed 직접 사용

    # 합계 이후: 노출(+1), 클릭(+2), 클릭률(+3), 전환수(+4), 전환율(+5), 광고비(+6), 전환금액(+7)
    def _get(offset):
        idx = base + offset if base >= 0 else offset
        return _clean_number(cells[idx]) if 0 <= idx < len(cells) else 0

    result = {
        "imps":     _get(1),
        "clicks":   _get(2),
        "cost":     _get(6),
        "purchase": _get(4),
        "revenue":  _get(7),
    }
    logger.info(f"[EdiAI/{label}] 결과: {result}")
    return result


def scrape(target_date: str | None = None) -> dict:
    """
    에디AI 대행사 리포트 — AI상품매칭 + 트렌드박스 순차 조회.
    반환: {
      "ai_matching": {"imps": N, "clicks": N, "cost": N, "purchase": N, "revenue": N},
      "trendbox":    {"imps": N, "clicks": N, "cost": N, "purchase": N, "revenue": N},
    }
    """
    target_date = target_date or get_target_date()
    driver = build_driver()

    try:
        login(driver)

        logger.info(f"[EdiAI] 리포트 페이지 이동: {REPORT_URL}")
        driver.get(REPORT_URL)
        time.sleep(8)  # React 앱 초기 렌더링 충분히 대기

        # 광고주 먼저 선택 → 날짜 피커가 광고주 선택 후 렌더링됨
        _select_advertiser(driver)
        _set_yesterday(driver, target_date)

        results = {}

        for key, campaign_keyword in CAMPAIGNS.items():
            logger.info(f"[EdiAI] '{campaign_keyword}' 캠페인 조회 시작")
            _select_campaign(driver, campaign_keyword)
            _click_search(driver)
            data = _extract_data(driver, key)
            results[key] = data

        return results
    finally:
        driver.quit()
