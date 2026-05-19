"""
Google Sheets 업로더
- 대상: 버티컬_raw 탭, A~O열
- J열, K열은 수식으로 삽입
- 같은 날짜 행이 있으면 삭제 후 재삽입
"""

import json
import logging
import os

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# J열 수식 템플릿 (행 번호를 {n}으로 치환)
J_FORMULA_TEMPLATE = (
    '=IF(OR(B{n}="버즈빌",B{n}="버즈빌UA",B{n}="아크로스(ADN)",'
    'B{n}="네이버_브랜드검색",B{n}="NAP",B{n}="adpopcorn",'
    'B{n}="네이버GFA",B{n}="에디AI",B{n}="페이코",'
    'B{n}="네이버_보장형DA",B{n}="당근",B{n}="버즈빌_리뷰픽"),'
    'I{n},IF(B{n}="ive",I{n}/1.1*1.15,IF(B{n}="네이버쇼핑",I{n}/1.1,I{n}*1.15)))'
)

K_FORMULA_TEMPLATE = "=J{n}*1.1"


def get_client() -> gspread.Client:
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT", "").strip()
    if not sa_json:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT 환경변수가 비어있습니다. "
            "GitHub Secrets에서 서비스 계정 JSON을 다시 확인해주세요."
        )
    logger.info(f"[Sheets] 서비스 계정 JSON — 길이: {len(sa_json)}자, 시작: {sa_json[:5]!r}")
    try:
        sa_info = json.loads(sa_json)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"GOOGLE_SERVICE_ACCOUNT JSON 파싱 실패: {e}\n"
            f"값의 첫 30자: {sa_json[:30]!r}\n"
            "서비스 계정 JSON이 올바른 형식인지 확인해주세요."
        ) from e
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return gspread.authorize(creds)


def get_spreadsheet(client: gspread.Client, spreadsheet_id: str) -> gspread.Spreadsheet:
    return client.open_by_key(spreadsheet_id)


def load_dynamic_config(spreadsheet: gspread.Spreadsheet, config_sheet_name: str) -> dict:
    """설정 시트에서 키-값 쌍을 읽어 dict로 반환. 시트가 없으면 기본값으로 생성."""
    try:
        ws = spreadsheet.worksheet(config_sheet_name)
    except gspread.WorksheetNotFound:
        logger.warning(f"설정 탭 '{config_sheet_name}'이 없어 기본값으로 생성합니다.")
        ws = spreadsheet.add_worksheet(title=config_sheet_name, rows=20, cols=3)
        ws.update(
            "A1",
            [
                ["키", "값", "설명"],
                ["buzzvil_adgroup_ids", "55775,55776", "버즈빌 adgroup ID (쉼표 구분, 매달 업데이트)"],
            ],
            value_input_option="USER_ENTERED",
        )
        logger.info(f"설정 탭 '{config_sheet_name}' 생성 완료")

    rows = ws.get_all_values()
    cfg = {}
    for row in rows:
        if len(row) >= 2 and row[0].strip() and row[0].strip() != "키":
            cfg[row[0].strip()] = row[1].strip()
    logger.info(f"설정 탭 로드 완료: {list(cfg.keys())}")
    return cfg


def _make_row(target_date: str, media: str, campaign: str, device: str,
              imps: int, clicks: int, cost: int,
              purchase: int = 0, revenue: int = 0,
              install: int = 0, signup: int = 0,
              row_num: int = 1) -> list:
    """
    A~O 열 데이터 리스트 반환.
    J, K열은 수식 문자열.
    """
    return [
        target_date,          # A: 날짜
        media,                # B: 매체
        campaign,             # C: 캠페인
        "-",                  # D: 그룹
        "-",                  # E: 소재
        device,               # F: 디바이스
        imps,                 # G: 노출
        clicks,               # H: 클릭
        cost,                 # I: 광고비(대시보드)
        J_FORMULA_TEMPLATE.format(n=row_num),  # J: 광고비(+마크업) — 수식
        K_FORMULA_TEMPLATE.format(n=row_num),  # K: 광고비(VAT포함) — 수식
        purchase,             # L: 구매
        revenue,              # M: 매출
        install,              # N: 설치
        signup,               # O: 회원가입
    ]


def append_daily_rows(
    spreadsheet_id: str,
    data_sheet_name: str,
    config_sheet_name: str,
    rows_data: list[dict],
    target_date: str,
) -> list:
    """
    버티컬_raw 탭에 매일 데이터를 삽입.

    rows_data 형식:
    [
      {"media": "버즈빌UA", "campaign": "Buzzvil", "device": "M",
       "imps": 0, "clicks": 194, "cost": 76000,
       "purchase": 0, "revenue": 0, "install": 0, "signup": 0},
      ...
    ]
    """
    client = get_client()
    spreadsheet = get_spreadsheet(client, spreadsheet_id)
    ws = spreadsheet.worksheet(data_sheet_name)

    all_values = ws.get_all_values()
    header_row_count = 1  # 1행은 헤더

    # 같은 날짜 행 찾기 (A열 기준)
    rows_to_delete = []
    for i, row in enumerate(all_values):
        if i < header_row_count:
            continue
        if row and row[0] == target_date:
            rows_to_delete.append(i + 1)  # 1-indexed

    # 역순으로 삭제 (인덱스 밀림 방지)
    if rows_to_delete:
        logger.info(f"기존 {target_date} 데이터 {len(rows_to_delete)}행 삭제")
        for row_idx in reversed(rows_to_delete):
            ws.delete_rows(row_idx)

    # 삭제 후 최신 데이터 재조회
    all_values = ws.get_all_values()
    last_data_row = len(all_values)  # 마지막 데이터 행 번호 (1-indexed)
    insert_start = last_data_row + 1  # 다음 빈 행

    # 삽입할 행 목록 구성
    built_rows = []
    for offset, rd in enumerate(rows_data):
        row_num = insert_start + offset
        built_rows.append(
            _make_row(
                target_date=target_date,
                media=rd["media"],
                campaign=rd["campaign"],
                device=rd["device"],
                imps=rd.get("imps", 0),
                clicks=rd.get("clicks", 0),
                cost=rd.get("cost", 0),
                purchase=rd.get("purchase", 0),
                revenue=rd.get("revenue", 0),
                install=rd.get("install", 0),
                signup=rd.get("signup", 0),
                row_num=row_num,
            )
        )

    # 일괄 업데이트 (USER_ENTERED: 수식 그대로 처리)
    start_cell = f"A{insert_start}"
    ws.update(start_cell, built_rows, value_input_option="USER_ENTERED")

    # J, K열 회색 배경 적용 (수식 셀 시각적 구분)
    end_row = insert_start + len(built_rows) - 1
    ws.format(
        f"J{insert_start}:K{end_row}",
        {"backgroundColor": {"red": 0.851, "green": 0.851, "blue": 0.851}},
    )

    # 날짜(A열) 기준 오름차순 정렬 — 헤더(1행) 제외
    try:
        spreadsheet.batch_update({
            "requests": [{
                "sortRange": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,       # 0-indexed → 2행부터 (1행=헤더 제외)
                        "startColumnIndex": 0,
                    },
                    "sortSpecs": [{
                        "dimensionIndex": 0,      # A열 (0-indexed)
                        "sortOrder": "ASCENDING"
                    }]
                }
            }]
        })
        logger.info(f"날짜 기준 오름차순 정렬 완료")
    except Exception as e:
        logger.warning(f"정렬 실패 (업로드는 정상): {e}")

    logger.info(f"{target_date} 데이터 {len(built_rows)}행 삽입 완료 (A{insert_start}부터)")
    return built_rows
