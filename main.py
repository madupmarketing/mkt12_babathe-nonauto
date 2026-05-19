"""
바바더닷컴 수기매체 자동화 메인 실행 스크립트
GitHub Actions 또는 수동 실행에서 호출됨.

실행 흐름:
1. 설정 파일 및 Google Sheets '설정' 탭에서 동적 설정(adgroup_id 등) 로드
2. 각 매체 크롤링 (버즈빌UA / ive / 네이버쇼핑 PC·MO / 에디AI)
3. Google Sheets '버티컬_raw' 탭에 6행 삽입 (중복 날짜 시 삭제 후 재삽입)
"""

import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from crawlers import buzzvil, iscreen, naver_shopping, ediai
from sheets import uploader
from utils.dates import get_target_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def load_static_config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def run(target_date: str | None = None) -> dict:
    target_date = target_date or get_target_date()
    logger.info(f"=== 자동화 시작 | 대상 날짜: {target_date} ===")

    static_cfg        = load_static_config()
    spreadsheet_id    = static_cfg["spreadsheet_id"]
    data_sheet_name   = static_cfg["data_sheet_name"]
    config_sheet_name = static_cfg["config_sheet_name"]

    # 설정 탭에서 동적 설정 로드
    client      = uploader.get_client()
    spreadsheet = uploader.get_spreadsheet(client, spreadsheet_id)
    dynamic_cfg = uploader.load_dynamic_config(spreadsheet, config_sheet_name)

    # 버즈빌 adgroup_id 목록 (쉼표 구분)
    bv_ids_raw = dynamic_cfg.get("buzzvil_adgroup_ids", "55775,55776")
    buzzvil_adgroup_ids = [x.strip() for x in bv_ids_raw.split(",") if x.strip()]

    # SKIP_CRAWLERS=naver_shopping,ediai 형태로 건너뛸 크롤러 지정
    skip = {s.strip() for s in os.environ.get("SKIP_CRAWLERS", "").split(",") if s.strip()}
    if skip:
        logger.info(f"건너뛸 크롤러: {skip}")

    errors = []
    rows_data = []  # 최종 업로드 행 목록

    # ── 버즈빌UA ─────────────────────────────────────────────
    logger.info("--- 버즈빌UA 크롤링 시작 ---")
    try:
        bv_data = buzzvil.scrape(adgroup_ids=buzzvil_adgroup_ids, target_date=target_date)
        if bv_data:
            rows_data.append({
                "media": "버즈빌UA", "campaign": "Buzzvil", "device": "M",
                "imps": bv_data["imps"], "clicks": bv_data["clicks"], "cost": bv_data["cost"],
            })
            logger.info(f"[버즈빌UA] 완료: {bv_data}")
        else:
            errors.append("버즈빌UA 데이터 없음")
            rows_data.append({"media": "버즈빌UA", "campaign": "Buzzvil", "device": "M",
                               "imps": 0, "clicks": 0, "cost": 0})
    except Exception as e:
        logger.error(f"버즈빌UA 크롤링 실패: {e}")
        errors.append(f"버즈빌UA 오류: {e}")
        rows_data.append({"media": "버즈빌UA", "campaign": "Buzzvil", "device": "M",
                           "imps": 0, "clicks": 0, "cost": 0})

    # ── ive (아이스크린) ──────────────────────────────────────
    logger.info("--- ive 크롤링 시작 ---")
    try:
        iv_data = iscreen.scrape(target_date=target_date)
        if iv_data:
            rows_data.append({
                "media": "ive", "campaign": "ive_cpa", "device": "M",
                "imps": iv_data["imps"], "clicks": iv_data["clicks"], "cost": iv_data["cost"],
            })
            logger.info(f"[ive] 완료: {iv_data}")
        else:
            errors.append("ive 데이터 없음")
            rows_data.append({"media": "ive", "campaign": "ive_cpa", "device": "M",
                               "imps": 0, "clicks": 0, "cost": 0})
    except Exception as e:
        logger.error(f"ive 크롤링 실패: {e}")
        errors.append(f"ive 오류: {e}")
        rows_data.append({"media": "ive", "campaign": "ive_cpa", "device": "M",
                           "imps": 0, "clicks": 0, "cost": 0})

    # ── 네이버쇼핑 PC / MO ───────────────────────────────────
    # config.json의 naver_shopping_static 값을 고정값으로 사용.
    # 크롤러가 안정화되면 아래 블록을 크롤링 방식으로 교체할 것.
    nv_static = static_cfg.get("naver_shopping_static", {})
    pc_s = nv_static.get("pc", {})
    mo_s = nv_static.get("mo", {})
    logger.info(f"--- 네이버쇼핑 고정값 사용: PC={pc_s}, MO={mo_s} ---")
    rows_data.append({
        "media": "네이버쇼핑", "campaign": "네이버쇼핑_PC", "device": "PC",
        "imps": pc_s.get("imps", 0), "clicks": pc_s.get("clicks", 0), "cost": pc_s.get("cost", 0),
    })
    rows_data.append({
        "media": "네이버쇼핑", "campaign": "네이버쇼핑_M", "device": "M",
        "imps": mo_s.get("imps", 0), "clicks": mo_s.get("clicks", 0), "cost": mo_s.get("cost", 0),
    })

    # ── 에디AI ───────────────────────────────────────────────
    if "ediai" in skip:
        logger.info("--- 에디AI 건너뜀 (SKIP_CRAWLERS) ---")
        rows_data.append({"media": "에디AI", "campaign": "AI상품매칭", "device": "M",
                           "imps": 0, "clicks": 0, "cost": 0})
        rows_data.append({"media": "에디AI", "campaign": "트렌드박스", "device": "M",
                           "imps": 0, "clicks": 0, "cost": 0})
    else:
        logger.info("--- 에디AI 크롤링 시작 ---")
        try:
            edi_data = ediai.scrape(target_date=target_date)
            for key, campaign in [("ai_matching", "AI상품매칭"), ("trendbox", "트렌드박스")]:
                d = edi_data.get(key)
                if d:
                    rows_data.append({
                        "media": "에디AI", "campaign": campaign, "device": "M",
                        "imps": d["imps"], "clicks": d["clicks"], "cost": d["cost"],
                        "purchase": d.get("purchase", 0), "revenue": d.get("revenue", 0),
                    })
                    logger.info(f"[에디AI/{campaign}] 완료: {d}")
                else:
                    errors.append(f"에디AI {campaign} 데이터 없음")
                    rows_data.append({"media": "에디AI", "campaign": campaign, "device": "M",
                                       "imps": 0, "clicks": 0, "cost": 0})
        except Exception as e:
            logger.error(f"에디AI 크롤링 실패: {e}")
            errors.append(f"에디AI 오류: {e}")
            rows_data.append({"media": "에디AI", "campaign": "AI상품매칭", "device": "M",
                               "imps": 0, "clicks": 0, "cost": 0})
            rows_data.append({"media": "에디AI", "campaign": "트렌드박스", "device": "M",
                               "imps": 0, "clicks": 0, "cost": 0})

    # ── Google Sheets 업로드 ─────────────────────────────────
    allow_partial = os.environ.get("ALLOW_PARTIAL_UPLOAD", "0") == "1"
    if errors and not allow_partial:
        logger.warning(f"크롤링 오류 있음, 업로드 건너뜀: {errors}")
        return {"date": target_date, "errors": errors, "uploaded": False}

    logger.info("--- Google Sheets 업로드 시작 ---")
    try:
        uploader.append_daily_rows(
            spreadsheet_id=spreadsheet_id,
            data_sheet_name=data_sheet_name,
            config_sheet_name=config_sheet_name,
            rows_data=rows_data,
            target_date=target_date,
        )
        logger.info(f"업로드 완료: {len(rows_data)}행")
    except Exception as e:
        logger.error(f"Google Sheets 업로드 실패: {e}")
        errors.append(f"Sheets 업로드 오류: {e}")

    logger.info("=== 실행 완료 ===")
    if errors:
        logger.warning(f"경고/오류: {errors}")
    else:
        logger.info("모든 매체 정상 처리 완료")

    return {"date": target_date, "errors": errors, "uploaded": True}


def get_dates_to_process() -> list[str]:
    date_from = os.environ.get("DATE_FROM", "").strip()
    date_to   = os.environ.get("DATE_TO",   "").strip()
    if date_from and date_to:
        from_d, to_d = date.fromisoformat(date_from), date.fromisoformat(date_to)
        dates, cur = [], from_d
        while cur <= to_d:
            dates.append(str(cur))
            cur += timedelta(days=1)
        return dates
    return [get_target_date()]


if __name__ == "__main__":
    dates = get_dates_to_process()
    all_errors: list[str] = []
    for d in dates:
        result = run(target_date=d)
        all_errors.extend(result.get("errors", []))
    sys.exit(1 if all_errors else 0)
