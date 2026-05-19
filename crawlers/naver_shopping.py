"""
네이버 쇼핑파트너센터 크롤러
- PC: https://center.shopping.naver.com/report/order
- MO: https://center.shopping.naver.com/report/mobile/order
- 전일자 조회, 합계 행에서 노출수 / 클릭수 / 적용수수료 추출
- 반환: {"imps": N, "clicks": N, "cost": N}

※ 네이버 로그인은 보안이 강함.
  - user-agent 설정, 쿠키 재사용 등으로 안정성 확보
  - 첫 실행 시 SMS 인증이 요구될 수 있음 → NAVER_COOKIE 환경변수로 세션 쿠키 주입 가능
"""

import json
import logging
import os
import re
import time

from utils.dates import get_target_date

logger = logging.getLogger(__name__)

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
PC_REPORT_URL   = "https://center.shopping.naver.com/report/order"
MO_REPORT_URL   = "https://center.shopping.naver.com/report/mobile/order"


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
    # 네이버 봇 감지 회피용 user-agent
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


def _inject_cookies(driver, cookie_json: str):
    """NAVER_COOKIE 환경변수(JSON 배열)를 드라이버에 주입."""
    try:
        cookies = json.loads(cookie_json)
        # .naver.com 쿠키는 naver.com에서 주입
        driver.get("https://naver.com")
        time.sleep(1)
        for cookie in cookies:
            if ".naver.com" in cookie.get("domain", "") or cookie.get("domain", "").endswith("naver.com"):
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"쿠키 주입 실패 ({cookie.get('name')}): {e}")
        # center.shopping.naver.com 전용 쿠키 주입
        driver.get("https://center.shopping.naver.com")
        time.sleep(2)
        for cookie in cookies:
            domain = cookie.get("domain", "")
            if "center.shopping" in domain or "shopping.naver" in domain:
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"쿠키 주입 실패 ({cookie.get('name')}): {e}")
        logger.info(f"[NaverShopping] 쿠키 {len(cookies)}개 주입 완료")
    except Exception as e:
        logger.warning(f"[NaverShopping] 쿠키 주입 오류: {e}")


def login(driver):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    naver_id = _require_env("NAVER_ID")
    naver_pw = _require_env("NAVER_PW")

    logger.info("[NaverShopping] 네이버 로그인 시작")
    driver.get(NAVER_LOGIN_URL)
    time.sleep(2)

    wait = WebDriverWait(driver, 20)

    # ID 입력 — send_keys 방식 (JS 방식은 네이버 암호화 우회 안 됨)
    id_field = wait.until(EC.element_to_be_clickable((By.ID, "id")))
    id_field.click()
    id_field.clear()
    id_field.send_keys(naver_id)
    time.sleep(0.5)

    # PW 입력
    pw_field = wait.until(EC.element_to_be_clickable((By.ID, "pw")))
    pw_field.click()
    pw_field.clear()
    pw_field.send_keys(naver_pw)
    time.sleep(0.5)

    # 로그인 버튼 클릭
    try:
        login_btn = driver.find_element(By.CSS_SELECTOR, "#log\\.login, .btn_login, button[type='submit']")
        login_btn.click()
    except Exception:
        pw_field.submit()

    time.sleep(4)

    try:
        driver.save_screenshot("/tmp/naver_login.png")
    except Exception:
        pass

    current = driver.current_url
    logger.info(f"[NaverShopping] 로그인 후 URL: {current}")

    # SMS 인증 화면 감지
    if "sms" in current.lower() or "otp" in current.lower() or "auth" in current.lower():
        raise RuntimeError(
            "[NaverShopping] SMS/2단계 인증 화면 감지. "
            "NAVER_COOKIE 환경변수로 세션 쿠키를 주입하거나 "
            "계정의 2단계 인증을 해제해주세요."
        )

    if "nidlogin" in current:
        raise RuntimeError("[NaverShopping] 네이버 로그인 실패 — 아이디/비밀번호 확인 필요")

    logger.info("[NaverShopping] 로그인 성공")


def _switch_to_report_frame(driver) -> bool:
    """
    리포트 콘텐츠가 담긴 iframe으로 전환.
    Naver 쇼핑파트너센터는 메인 document에 nav만 있고,
    리포트 테이블/버튼은 iframe 안에 있음.
    """
    from selenium.webdriver.common.by import By

    driver.switch_to.default_content()
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    logger.info(f"[NaverShopping] iframe 수: {len(frames)}")

    for idx, frame in enumerate(frames):
        try:
            src = frame.get_attribute("src") or ""
            name = frame.get_attribute("name") or ""
            fid  = frame.get_attribute("id")   or ""
            logger.debug(f"[NaverShopping] iframe[{idx}] src={src[:80]} name={name} id={fid}")
            driver.switch_to.frame(frame)
            # 조회 버튼 또는 합계 텍스트가 있는 프레임인지 확인
            hit = driver.execute_script("""
                var els = document.querySelectorAll('*');
                for (var i = 0; i < els.length; i++) {
                    var t = (els[i].textContent || '').trim();
                    if ((t === '조회' || t.indexOf('합계') === 0) && els[i].children.length === 0)
                        return true;
                }
                return false;
            """)
            if hit:
                logger.info(f"[NaverShopping] 리포트 iframe 발견: idx={idx} src={src[:60]}")
                return True
            driver.switch_to.default_content()
        except Exception as e:
            logger.debug(f"[NaverShopping] iframe[{idx}] 전환 실패: {e}")
            driver.switch_to.default_content()

    logger.warning("[NaverShopping] 리포트 iframe을 찾지 못함 — 기본 document 유지")
    return False


def _click_search_btn(driver):
    """'조회' 버튼 클릭 — 직접 텍스트 노드 + 유연한 매칭."""
    clicked = driver.execute_script("""
        function directText(el) {
            var t = '';
            for (var i = 0; i < el.childNodes.length; i++) {
                if (el.childNodes[i].nodeType === 3) t += el.childNodes[i].nodeValue;
            }
            return t.replace(/\\s+/g, '').trim();
        }
        var tags = ['button', 'a', 'span', 'div'];
        for (var ti = 0; ti < tags.length; ti++) {
            var els = document.querySelectorAll(tags[ti]);
            for (var i = 0; i < els.length; i++) {
                var st = window.getComputedStyle(els[i]);
                if (st.display === 'none' || st.visibility === 'hidden') continue;
                var direct = directText(els[i]);
                var full = (els[i].textContent || '').replace(/\\s+/g, '').trim();
                if (direct === '조회' || full === '조회') {
                    els[i].click(); return '클릭:' + (els[i].textContent||'').trim().substring(0, 20);
                }
            }
        }
        return false;
    """)
    if clicked:
        logger.info(f"[NaverShopping] 조회 버튼 클릭: {clicked}")
    else:
        logger.warning("[NaverShopping] 조회 버튼 없음")
    time.sleep(4)


def _set_date_range(driver, target_date: str):
    """
    날짜 필터를 target_date로 설정 후 조회.
    - target_date == KST 전일자: '어제' 단축 버튼 사용
    - 그 외: 날짜 텍스트 입력 필드 직접 설정 (YYYY.MM.DD 형식)
    """
    from datetime import datetime, timezone, timedelta as _td

    kst = timezone(_td(hours=9))
    yesterday = (datetime.now(kst) - _td(days=1)).strftime("%Y-%m-%d")

    time.sleep(3)

    try:
        driver.save_screenshot("/tmp/naver_before_date.png")
    except Exception:
        pass

    if target_date == yesterday:
        # 어제 단축 버튼 클릭
        clicked = driver.execute_script("""
            function directText(el) {
                var t = '';
                for (var i = 0; i < el.childNodes.length; i++) {
                    if (el.childNodes[i].nodeType === 3) t += el.childNodes[i].nodeValue;
                }
                return t.trim();
            }
            var tags = ['button', 'a', 'span', 'li', 'div'];
            for (var ti = 0; ti < tags.length; ti++) {
                var els = document.querySelectorAll(tags[ti]);
                for (var i = 0; i < els.length; i++) {
                    var st = window.getComputedStyle(els[i]);
                    if (st.display === 'none' || st.visibility === 'hidden') continue;
                    var direct = directText(els[i]);
                    var full = (els[i].textContent || '').trim();
                    if (direct === '어제' || (full.indexOf('어제') >= 0 && full.length <= 15)) {
                        els[i].click(); return '클릭:' + full.substring(0, 20);
                    }
                }
            }
            return false;
        """)
        if clicked:
            logger.info(f"[NaverShopping] '어제' 버튼 클릭: {clicked}")
            time.sleep(2)
        else:
            logger.info("[NaverShopping] '어제' 단축 버튼 없음 — 기본값 사용")
    else:
        # 날짜 직접 입력 — ActionChains send_keys (React synthetic event 호환)
        # Naver 파트너센터: YYYY.MM.DD 형식
        date_naver = target_date.replace("-", ".")
        _set_date_by_sendkeys(driver, date_naver, "NaverShopping")

    _click_search_btn(driver)


def _set_date_by_sendkeys(driver, date_str: str, label: str) -> bool:
    """
    실제 키 입력(send_keys)으로 날짜 필드 설정.
    JS setter는 React state를 못 건드리는 경우가 있어 send_keys 사용.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    # 1단계: value가 날짜 형식인 input 탐색 (YYYY.MM.DD 또는 YYYY-MM-DD)
    date_inputs = driver.execute_script("""
        var els = document.querySelectorAll('input[type="text"], input:not([type])');
        var result = [];
        for (var i = 0; i < els.length; i++) {
            var v = (els[i].value || '').trim();
            if (/^\\d{4}[.\\-]\\d{2}[.\\-]\\d{2}$/.test(v)) result.push(els[i]);
        }
        return result;
    """)

    if not date_inputs:
        # 2단계: placeholder / class / id에 date 관련 키워드 포함 input
        date_inputs = driver.execute_script("""
            var els = document.querySelectorAll('input');
            var result = [];
            for (var i = 0; i < els.length; i++) {
                var ph = (els[i].placeholder || '').toLowerCase();
                var cl = (els[i].className  || '').toLowerCase();
                var id = (els[i].id         || '').toLowerCase();
                var nm = (els[i].name       || '').toLowerCase();
                if (ph.indexOf('yyyy') >= 0 || ph.indexOf('날짜') >= 0 ||
                    cl.indexOf('date')  >= 0 || cl.indexOf('calendar') >= 0 ||
                    id.indexOf('date')  >= 0 || nm.indexOf('date')     >= 0) {
                    result.push(els[i]);
                }
            }
            return result;
        """)

    if not date_inputs:
        # 3단계: 진단 — iframe 내 모든 input 속성 로그
        all_inputs_info = driver.execute_script("""
            var els = document.querySelectorAll('input');
            var result = [];
            for (var i = 0; i < els.length; i++) {
                result.push(els[i].type + '|' + els[i].id + '|' +
                            els[i].name + '|' + els[i].className.substring(0,30) +
                            '|val=' + (els[i].value || '').substring(0, 20));
            }
            return result.join(' // ');
        """)
        logger.info(f"[{label}] iframe 내 모든 input: {all_inputs_info}")
        # 날짜처럼 보이는 text 요소도 탐색
        date_text_els = driver.execute_script("""
            var all = document.querySelectorAll('*');
            var result = [];
            for (var i = 0; i < all.length; i++) {
                var t = (all[i].textContent || '').trim();
                if (/^\\d{4}[.\\-]\\d{2}[.\\-]\\d{2}$/.test(t) && all[i].children.length === 0) {
                    var st = window.getComputedStyle(all[i]);
                    if (st.display !== 'none' && st.visibility !== 'hidden')
                        result.push(all[i].tagName + ':' + t);
                }
            }
            return result.slice(0, 10).join(' | ');
        """)
        logger.info(f"[{label}] 날짜 텍스트 요소: {date_text_els}")
        logger.warning(f"[{label}] 날짜 입력 필드를 찾을 수 없음 — 기본값 유지")
        return False

    # 시작·종료 날짜 모두 설정 (2개 이상이면 첫·마지막)
    targets = [date_inputs[0], date_inputs[-1]] if len(date_inputs) >= 2 else [date_inputs[0]]
    logger.info(f"[{label}] 날짜 입력 필드 {len(date_inputs)}개 발견, {len(targets)}개 설정 → {date_str}")

    for inp in targets:
        try:
            inp.click()
            time.sleep(0.2)
            inp.send_keys(Keys.CONTROL + "a")
            time.sleep(0.1)
            inp.send_keys(date_str)
            time.sleep(0.2)
            inp.send_keys(Keys.TAB)
            time.sleep(0.3)
        except Exception as e:
            logger.debug(f"[{label}] send_keys 실패: {e}")

    time.sleep(0.5)
    return True


# 하위호환 alias
def _set_date_yesterday(driver, target_date: str):
    _set_date_range(driver, target_date)


def _find_col_idx(headers: list[str], keywords: list[str]) -> int | None:
    """헤더 목록에서 키워드와 매칭되는 컬럼 인덱스 반환."""
    for i, h in enumerate(headers):
        h_norm = h.replace(" ", "").lower()
        for kw in keywords:
            if kw in h_norm:
                return i
    return None


def _extract_summary(driver, label: str) -> dict | None:
    """
    JS로 '합계' 행을 찾아 노출수/클릭수/적용수수료 추출.
    div 기반 레이아웃 대응 (table 없음).
    합계 행 구조: [합계텍스트, 노출수, 클릭수, 클릭율, 적용수수료, ...]
    """
    try:
        driver.save_screenshot(f"/tmp/naver_{label}_report.png")
    except Exception:
        pass

    cells = driver.execute_script("""
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            var t = (all[i].textContent || '').trim();
            // "합계" 또는 "합계 (데이터수 : N건)" 형태 모두 매칭
            if (t.indexOf('합계') === 0 && all[i].children.length === 0) {
                var row = all[i].parentElement;
                // 최소 7개 셀(합계|노출|클릭|클릭률|구매건수|구매금액|적용수수료)이 있는 행까지 올라감
                while (row && row.children.length < 7) {
                    row = row.parentElement;
                }
                // 7개 미만이면 4개 이상인 행으로 fallback
                if (!row) {
                    var row2 = all[i].parentElement;
                    while (row2 && row2.children.length < 4) row2 = row2.parentElement;
                    row = row2;
                }
                if (!row) return null;
                var result = [];
                for (var j = 0; j < row.children.length; j++) {
                    result.push((row.children[j].textContent || '').replace(/\\s+/g, ' ').trim());
                }
                return result;
            }
        }
        return null;
    """)

    if not cells:
        logger.error(f"[NaverShopping/{label}] 합계 행을 찾을 수 없음")
        return None

    logger.info(f"[NaverShopping/{label}] 합계 행 전체: {cells}")

    # 로그 확인된 실제 컬럼 구조 (7열):
    # [합계텍스트, 노출수, 클릭수, 클릭률('-'), 빈칸(''), 적용수수료, '-']
    # → imps=1, clicks=2, cost=5
    imps   = _clean_number(cells[1]) if len(cells) > 1 else 0
    clicks = _clean_number(cells[2]) if len(cells) > 2 else 0

    # 적용수수료: 확인된 인덱스 5 우선, fallback으로 5→6→4 순서로 탐색
    cost = 0
    for ci in (5, 6, 4):
        if len(cells) > ci:
            v = _clean_number(cells[ci])
            if v > 0:
                cost = v
                logger.info(f"[NaverShopping/{label}] cost at cells[{ci}]={cells[ci]!r} → {v}")
                break

    logger.info(f"[NaverShopping/{label}] imps={imps}, clicks={clicks}, cost={cost}")
    return {"imps": imps, "clicks": clicks, "cost": cost}


def scrape(target_date: str | None = None) -> dict:
    """
    PC, MO 리포트를 각각 조회하여 반환.
    반환: {"pc": {...}, "mo": {...}}
    각 값: {"imps": N, "clicks": N, "cost": N}
    """
    target_date = target_date or get_target_date()

    # NAVER_COOKIE가 있으면 쿠키 방식 우선
    cookie_json = os.environ.get("NAVER_COOKIE", "").strip()

    driver = build_driver()
    try:
        if cookie_json:
            logger.info("[NaverShopping] 쿠키 기반 로그인 시도")
            _inject_cookies(driver, cookie_json)
        else:
            login(driver)

        results = {}

        for label, url in [("PC", PC_REPORT_URL), ("MO", MO_REPORT_URL)]:
            logger.info(f"[NaverShopping/{label}] 리포트 페이지 이동: {url}")
            driver.get(url)
            time.sleep(3)
            current = driver.current_url
            logger.info(f"[NaverShopping/{label}] 현재 URL: {current}")
            if "login" in current or "nidlogin" in current:
                logger.error(f"[NaverShopping/{label}] 세션 만료 — 로그인 페이지로 리다이렉트됨")
                results[label.lower()] = None
                continue
            # 리포트 콘텐츠 iframe으로 전환
            _switch_to_report_frame(driver)
            _set_date_range(driver, target_date)
            data = _extract_summary(driver, label)
            driver.switch_to.default_content()
            results[label.lower()] = data
            if data:
                logger.info(f"[NaverShopping/{label}] 완료: {data}")
            else:
                logger.warning(f"[NaverShopping/{label}] 수집 실패")

        return results
    finally:
        driver.quit()
