"""
Diff Viewer - Flask 기반 파일 비교 웹 애플리케이션

두 개의 디렉토리(00.WordBase, 01.CodeBase) 내 텍스트 파일을 비교하여
줄 단위 및 단어 단위의 차이점을 시각적으로 보여주는 웹 애플리케이션.

주요 기능:
  - 베이스라인별 파일 목록 관리
  - 줄 단위 diff (difflib.SequenceMatcher 기반)
  - 단어 단위 diff (토큰 분리 후 비교)
  - 공백/대소문자 변경 감지 및 시각적 구분
  - 유사도 기반 라인 매칭 (greedy + monotonic 순서 보장)
"""

import os      # 파일 시스템 경로 처리용
import re      # 정규표현식 (토큰 분리, 공백 제거 등)
import html    # HTML 이스케이프용
import difflib # 텍스트 비교 및 유사도 계산 라이브러리
import xml.etree.ElementTree as ET
from flask import Flask, render_template, abort, redirect, url_for, request, jsonify

# Flask 애플리케이션 인스턴스 생성
app = Flask(__name__)

# 프로젝트 루트 디렉토리 경로 (이 파일이 위치한 디렉토리)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 비교 대상 데이터가 저장된 디렉토리 (data/ 폴더)
DATA_DIR = os.path.join(BASE_DIR, "data")

# [H3] 두 줄이 같은 줄로 짝지어질 최소 유사도 임계값
# 0.55로 설정 — 기존 0.3은 너무 낮아 무관한 줄끼리 잘못 매칭되는 문제가 있었음
SIMILARITY_THRESHOLD = 0.55

# 편집 결과를 전송할 외부 서버 URL (추후 설정)
SUBMIT_SERVER_URL = ""


# ─────────────────────────────────────────
# 폴더 스캔: 베이스라인 및 파일 목록 관련 함수들
# ─────────────────────────────────────────

def get_baselines():
    """data/ 하위의 베이스라인 폴더 목록을 정렬하여 반환.

    Returns:
        list[str]: 베이스라인 폴더명 리스트 (예: ["baseline_v1", "baseline_v2"])
                   data/ 폴더가 없으면 빈 리스트 반환
    """
    # data/ 디렉토리가 존재하지 않으면 빈 리스트 반환
    if not os.path.isdir(DATA_DIR):
        return []
    # data/ 하위에서 디렉토리만 필터링하여 이름순 정렬 후 반환
    return sorted(
        name for name in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, name))
    )


def find_pair_dirs(baseline):
    """베이스라인 폴더 안에서 비교 대상이 되는 두 디렉토리를 찾아 반환.

    규칙:
      - "00"으로 시작하는 폴더 → word_dir (원본, 예: 00.WordBase)
      - "01"로 시작하는 폴더 → code_dir (수정본, 예: 01.CodeBase)

    Args:
        baseline (str): 베이스라인 폴더명

    Returns:
        tuple[str|None, str|None]: (word_dir 경로, code_dir 경로)
                                    찾지 못하면 해당 값은 None
    """
    base_path = os.path.join(DATA_DIR, baseline)
    word_dir = code_dir = None
    # 베이스라인 경로가 유효한 디렉토리인지 확인
    if not os.path.isdir(base_path):
        return None, None
    # 하위 디렉토리를 정렬하여 순회하며 00~/01~ 패턴 매칭
    for name in sorted(os.listdir(base_path)):
        full = os.path.join(base_path, name)
        if not os.path.isdir(full):
            continue
        # "00"으로 시작하는 첫 번째 디렉토리를 word_dir로 지정
        if name.startswith("00") and word_dir is None:
            word_dir = full
        # "01"로 시작하는 첫 번째 디렉토리를 code_dir로 지정
        elif name.startswith("01") and code_dir is None:
            code_dir = full
    return word_dir, code_dir


def file_has_diff(word_dir, code_dir, filename):
    """두 디렉토리의 동일 파일명에 대해 내용이 다른지 빠르게 확인.

    Args:
        word_dir (str): 원본 디렉토리 경로
        code_dir (str): 수정본 디렉토리 경로
        filename (str): 비교할 파일명

    Returns:
        bool: 파일 내용이 다르면 True, 같으면 False
              파일 읽기 실패 시에도 True 반환 (변경된 것으로 간주)
    """
    path_a = os.path.join(word_dir, filename)
    path_b = os.path.join(code_dir, filename)
    try:
        # 양쪽 파일을 읽어서 전체 내용을 문자열로 비교
        with open(path_a, "r", encoding="utf-8", errors="replace") as fa, \
             open(path_b, "r", encoding="utf-8", errors="replace") as fb:
            return fa.read() != fb.read()
    except OSError:
        # 파일 읽기 실패 시 변경된 것으로 간주
        return True


def get_file_list(baseline):
    """해당 베이스라인의 전체 파일 목록과 변경 여부를 반환.

    Args:
        baseline (str): 베이스라인 폴더명

    Returns:
        dict: {
            "word_dir": str|None,      - 원본 디렉토리 경로
            "code_dir": str|None,      - 수정본 디렉토리 경로
            "files": list[dict],       - 파일 정보 리스트 [{name, changed}, ...]
            "changed_count": int,      - 변경된 파일 수
        }
    """
    word_dir, code_dir = find_pair_dirs(baseline)

    # [M2] 양쪽 디렉토리의 합집합으로 파일 목록 생성
    # 한쪽에만 있는 파일도 포함하기 위해 set 합집합(|=) 사용
    filenames = set()
    if word_dir:
        filenames |= {f for f in os.listdir(word_dir) if f.endswith(".xml")}
    if code_dir:
        filenames |= {f for f in os.listdir(code_dir) if f.endswith(".xml")}

    # 각 파일의 변경 여부를 확인하여 리스트 구성
    files = []
    for f in sorted(filenames):
        # 양쪽 디렉토리가 모두 존재할 때만 diff 비교, 아니면 변경 없음으로 처리
        changed = file_has_diff(word_dir, code_dir, f) if word_dir and code_dir else False
        files.append({"name": f, "changed": changed})

    # 변경된 파일 수 집계
    changed_count = sum(1 for f in files if f["changed"])

    return {
        "word_dir": word_dir,
        "code_dir": code_dir,
        "files":    files,
        "changed_count": changed_count,
    }


# ─────────────────────────────────────────
# 베이스라인 정보: info.md 읽기 및 마크다운 변환
# ─────────────────────────────────────────

def _inline_md(text):
    """인라인 마크다운(굵게, 기울임, 코드)을 HTML로 변환."""
    text = html.escape(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text


def _simple_markdown(text):
    """간단한 마크다운을 HTML로 변환 (제목, 목록, 단락, 구분선, 인라인 스타일)."""
    lines = text.split('\n')
    result = []
    in_list = False

    for line in lines:
        line = line.rstrip()
        if line.startswith('### '):
            if in_list: result.append('</ul>'); in_list = False
            result.append(f'<h5 class="info-h">{html.escape(line[4:])}</h5>')
        elif line.startswith('## '):
            if in_list: result.append('</ul>'); in_list = False
            result.append(f'<h4 class="info-h">{html.escape(line[3:])}</h4>')
        elif line.startswith('# '):
            if in_list: result.append('</ul>'); in_list = False
            result.append(f'<h3 class="info-h">{html.escape(line[2:])}</h3>')
        elif line.strip() in ('---', '***', '___'):
            if in_list: result.append('</ul>'); in_list = False
            result.append('<hr class="info-hr">')
        elif line.startswith('- ') or line.startswith('* '):
            if not in_list: result.append('<ul class="info-list">'); in_list = True
            result.append(f'<li>{_inline_md(line[2:])}</li>')
        elif line.strip() == '':
            if in_list: result.append('</ul>'); in_list = False
        else:
            if in_list: result.append('</ul>'); in_list = False
            result.append(f'<p class="info-p">{_inline_md(line)}</p>')

    if in_list:
        result.append('</ul>')

    return '\n'.join(result)


def get_baseline_info(baseline):
    """베이스라인 폴더의 info.md를 읽어 HTML로 반환. 파일이 없으면 None."""
    info_path = os.path.join(DATA_DIR, baseline, 'info.md')
    if not os.path.isfile(info_path):
        return None
    try:
        with open(info_path, 'r', encoding='utf-8', errors='replace') as f:
            return _simple_markdown(f.read())
    except OSError:
        return None


# ─────────────────────────────────────────
# 유틸: HTML 이스케이프 및 공백 시각화 함수
# ─────────────────────────────────────────

def esc(s):
    """HTML 특수문자를 이스케이프 처리.

    XSS 방지를 위해 &, <, > 문자를 HTML 엔티티로 변환.

    Args:
        s (str): 원본 문자열

    Returns:
        str: 이스케이프된 문자열
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_ws(s):
    """공백 문자를 시각적 기호로 변환 (공백 diff 하이라이트 표시용).

    변환 규칙:
      - 스페이스(' ') → 가운뎃점('·')
      - 탭('\\t') → 화살표 + 탭('→\\t')
      - 그 외 문자 → HTML 이스케이프 처리

    Args:
        s (str): 원본 문자열

    Returns:
        str: 공백이 시각적 기호로 변환된 HTML 문자열
    """
    out = ""
    for ch in s:
        if ch == " ":
            out += "·"       # 스페이스를 가운뎃점으로 시각화
        elif ch == "\t":
            out += "→\t"     # 탭을 화살표 기호 + 탭으로 시각화
        else:
            out += esc(ch)   # 일반 문자는 HTML 이스케이프만 적용
    return out


def line_similarity(a, b):
    """두 줄의 텍스트 유사도를 0.0 ~ 1.0 사이 값으로 계산.

    difflib.SequenceMatcher.ratio()를 사용하여 유사도를 측정.

    Args:
        a (str): 비교 대상 줄 A
        b (str): 비교 대상 줄 B

    Returns:
        float: 유사도 (0.0 = 완전히 다름, 1.0 = 완전히 같음)
    """
    # [H7] 빈 줄끼리는 0.0으로 처리해 greedy 매칭에서 의미 있는 줄을 방해하지 않도록
    # 빈 줄끼리 높은 유사도로 매칭되면 실제 의미 있는 줄의 매칭이 방해받음
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    # autojunk=False: 자동 junk 감지 비활성화 (짧은 텍스트에서 더 정확)
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# ─────────────────────────────────────────
# 단어 단위 diff: 두 줄을 단어/문자 단위로 비교하여 HTML 생성
# ─────────────────────────────────────────

def tokenize(text):
    """텍스트를 공백 포함 단어 토큰으로 분리.

    정규표현식으로 비공백 연속 문자(\\S+)와 공백 연속 문자(\\s+)를
    각각 별도 토큰으로 분리하여 단어 단위 diff에 활용.

    Args:
        text (str): 분리할 텍스트

    Returns:
        list[str]: 토큰 리스트 (예: ["hello", " ", "world"])
    """
    return re.findall(r'\S+|\s+', text) if text else []


def _classify_replace(seg_a, seg_b):
    """replace 세그먼트(변경 구간)의 차이 유형을 분류.

    두 텍스트 조각의 차이가 공백 배치, 대소문자, 또는 내용 차이인지 판별.

    Args:
        seg_a (str): 원본 세그먼트
        seg_b (str): 수정본 세그먼트

    Returns:
        str: 차이 유형
             - "ws"   : 비공백 내용이 동일하고 공백 배치만 다름
             - "case" : 비공백 내용이 대소문자만 다름
             - "diff" : 실질적 내용이 다름
    """
    # 양쪽 텍스트에서 앞뒤 공백 제거
    stripped_a = seg_a.strip()
    stripped_b = seg_b.strip()

    # 양쪽 다 공백만으로 이루어진 경우 → 공백 차이
    if stripped_a == "" and stripped_b == "":
        return "ws"

    # 모든 공백을 제거한 순수 텍스트끼리 비교
    # 예: "서울시 " vs " 서울시" → 공백을 제거하면 동일
    non_ws_a = re.sub(r'\s+', '', seg_a)
    non_ws_b = re.sub(r'\s+', '', seg_b)
    # 공백 기준으로 분리한 단어 리스트
    words_a = seg_a.split()
    words_b = seg_b.split()

    # 공백 제거 후 내용이 동일하고 단어 수도 같으면 → 공백 배치만 다른 것
    if non_ws_a == non_ws_b and len(words_a) == len(words_b):
        return "ws"

    # 대소문자만 다른 경우 (단어 수가 같을 때만 인정)
    # 단어 수가 다르면 구조적 변경이므로 "diff"로 분류
    if (non_ws_a.lower() == non_ws_b.lower()
            and len(words_a) == len(words_b)):
        return "case"

    # 위 조건에 해당하지 않으면 실질적인 내용 변경
    return "diff"


def _render_ws_diff(seg_a, seg_b):
    """공백/대소문자 차이를 문자 단위로 세밀하게 HTML 렌더링.

    문자 하나하나를 비교하여 공백 삭제/추가, 대소문자 차이 등을
    각각 다른 CSS 클래스로 표시.

    CSS 클래스 매핑:
      - wd-ws-del : 삭제된 공백 (빨간색 배경, ·/→ 기호로 시각화)
      - wd-ws-add : 추가된 공백 (초록색 배경, ·/→ 기호로 시각화)
      - wd-diff   : 대소문자 차이 (파란색 배경)

    Args:
        seg_a (str): 원본 텍스트
        seg_b (str): 수정본 텍스트

    Returns:
        tuple[str, str]: (원본 HTML, 수정본 HTML)
    """
    # 문자 단위 리스트로 변환하여 SequenceMatcher로 비교
    chars_a = list(seg_a)
    chars_b = list(seg_b)
    matcher = difflib.SequenceMatcher(None, chars_a, chars_b, autojunk=False)
    html_a, html_b = [], []

    # 각 opcode(equal/replace/delete/insert)에 따라 HTML 생성
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        ca = "".join(chars_a[i1:i2])  # 원본 쪽 문자열 조각
        cb = "".join(chars_b[j1:j2])  # 수정본 쪽 문자열 조각
        if tag == "equal":
            # 동일한 부분 → 이스케이프만 적용
            html_a.append(esc(ca))
            html_b.append(esc(cb))
        elif tag == "replace":
            # 변경된 부분 → 공백 차이인지 대소문자 차이인지 구분
            is_ws = (ca.strip() == "" or cb.strip() == "")    # 한쪽이 공백만
            is_case = (not is_ws and ca.lower() == cb.lower()) # 대소문자만 다름
            if is_ws:
                # 공백 차이 → 공백 시각화 기호 사용
                html_a.append(f'<span class="wd-ws-del">{esc_ws(ca)}</span>')
                html_b.append(f'<span class="wd-ws-add">{esc_ws(cb)}</span>')
            elif is_case:
                # 대소문자 차이 → 파란색 하이라이트
                html_a.append(f'<span class="wd-diff">{esc(ca)}</span>')
                html_b.append(f'<span class="wd-diff">{esc(cb)}</span>')
            else:
                # 그 외 차이 → 공백 시각화로 표시 (혼합 차이)
                html_a.append(f'<span class="wd-ws-del">{esc_ws(ca)}</span>')
                html_b.append(f'<span class="wd-ws-add">{esc_ws(cb)}</span>')
        elif tag == "delete":
            # 원본에만 있는 문자 → 삭제 표시
            html_a.append(f'<span class="wd-ws-del">{esc_ws(ca)}</span>')
        elif tag == "insert":
            # 수정본에만 있는 문자 → 추가 표시
            html_b.append(f'<span class="wd-ws-add">{esc_ws(cb)}</span>')

    return "".join(html_a), "".join(html_b)


def word_diff_html(text_a, text_b):
    """두 줄을 단어 단위로 비교해 HTML 문자열 쌍으로 반환.

    비교 결과에 따라 다른 CSS 클래스가 적용됨:
      - 공백만 다름              → _render_ws_diff 호출 (문자 단위 diff)
      - 대소문자만 다름          → _render_ws_diff 호출 (wd-diff 파란색)
      - 한쪽에만 있는 단어       → wd-only (빨간색)
      - 완전히 다른 단어로 교체  → wd-only (빨간색)

    Args:
        text_a (str): 원본 줄 텍스트
        text_b (str): 수정본 줄 텍스트

    Returns:
        tuple[str, str]: (원본 HTML, 수정본 HTML)
    """
    # 먼저 줄 전체 레벨에서 차이 유형을 빠르게 판별
    # 모든 공백을 제거한 순수 텍스트 비교
    non_ws_a = re.sub(r'\s+', '', text_a)
    non_ws_b = re.sub(r'\s+', '', text_b)
    # 공백 제거 후 동일하면 공백 배치만 다른 것 → 문자 단위 세밀 비교
    if non_ws_a == non_ws_b:
        return _render_ws_diff(text_a, text_b)

    # 대소문자만 다른 경우도 줄 전체 레벨에서 먼저 체크
    # 단, 단어 수가 같아야 함 — "foo BAR" vs "foobar" 같은 단어 구조 변경은 제외
    words_a = text_a.split()
    words_b = text_b.split()
    if (non_ws_a.lower() == non_ws_b.lower()
            and non_ws_a != non_ws_b
            and len(words_a) == len(words_b)):
        return _render_ws_diff(text_a, text_b)

    # 줄 전체 레벨에서 빠른 판별이 안 되면 → 단어 토큰 단위로 비교
    tokens_a = tokenize(text_a)  # 원본을 토큰으로 분리
    tokens_b = tokenize(text_b)  # 수정본을 토큰으로 분리
    # SequenceMatcher로 토큰 시퀀스 비교
    matcher  = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)

    parts_a, parts_b = [], []  # 각 쪽의 HTML 조각 리스트

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        # 현재 opcode 범위의 토큰들을 합쳐서 세그먼트 문자열 생성
        seg_a = "".join(tokens_a[i1:i2])
        seg_b = "".join(tokens_b[j1:j2])

        if tag == "equal":
            # 동일한 부분 → 이스케이프만 적용
            parts_a.append(esc(seg_a))
            parts_b.append(esc(seg_b))

        elif tag == "replace":
            # 변경된 부분 → 세부 분류하여 적절한 스타일 적용
            cls = _classify_replace(seg_a, seg_b)
            if cls == "ws":
                # 공백만 다름 → 문자 단위 세밀 렌더링
                ha, hb = _render_ws_diff(seg_a, seg_b)
                parts_a.append(ha)
                parts_b.append(hb)
            elif cls == "case":
                # 대소문자만 다름 → 문자 단위 세밀 렌더링 (파란색)
                ha, hb = _render_ws_diff(seg_a, seg_b)
                parts_a.append(ha)
                parts_b.append(hb)
            else:
                # 내용이 다름 → 빨간색 하이라이트 (wd-only)
                parts_a.append(f'<span class="wd-only">{esc(seg_a)}</span>')
                parts_b.append(f'<span class="wd-only">{esc(seg_b)}</span>')

        elif tag == "delete":
            # 원본에만 있는 토큰 → 삭제된 단어 표시 (빨간색)
            parts_a.append(f'<span class="wd-only">{esc(seg_a)}</span>')

        elif tag == "insert":
            # 수정본에만 있는 토큰 → 추가된 단어 표시 (빨간색)
            parts_b.append(f'<span class="wd-only">{esc(seg_b)}</span>')

    return "".join(parts_a), "".join(parts_b)


# ─────────────────────────────────────────
# 유사도 기반 라인 매칭: replace 블록 내 줄 최적 짝짓기
# ─────────────────────────────────────────

def match_blocks(block_a, block_b):
    """replace 블록 내에서 유사도 기반으로 라인을 최적 매칭.

    [C1] greedy 매칭 후 monotonic 순서를 강제하여 교차 매칭 방지.

    알고리즘:
      1. 모든 (i, j) 쌍의 유사도 행렬 계산
      2. 유사도가 임계값 이상인 쌍을 높은 순으로 greedy 선택
      3. 교차 매칭 제거 (j값이 단조 증가하도록 필터링)
      4. 매칭되지 않은 줄은 delete/insert로 처리

    Args:
        block_a (list[str]): 원본 줄 리스트
        block_b (list[str]): 수정본 줄 리스트

    Returns:
        list[tuple]: [(type, line_a, line_b), ...] 형태의 결과
                     type은 "replace", "delete", "insert" 중 하나
    """
    n, m = len(block_a), len(block_b)

    # 1단계: 유사도 행렬 계산 — 모든 (i, j) 조합의 유사도를 미리 계산
    sim = [[0.0] * m for _ in range(n)]
    for i, la in enumerate(block_a):
        for j, lb in enumerate(block_b):
            sim[i][j] = line_similarity(la, lb)

    # 2단계: greedy 매칭 — 유사도가 임계값 이상인 쌍을 높은 순으로 선택
    pairs = []
    for i in range(n):
        for j in range(m):
            if sim[i][j] >= SIMILARITY_THRESHOLD:
                pairs.append((sim[i][j], i, j))
    # 유사도 내림차순 정렬 → 가장 유사한 쌍부터 선택
    pairs.sort(key=lambda x: -x[0])

    matched_a = set()  # 이미 매칭된 원본 줄 인덱스
    matched_b = set()  # 이미 매칭된 수정본 줄 인덱스
    matches   = {}     # {원본 인덱스: 수정본 인덱스} 매핑

    for score, i, j in pairs:
        # 양쪽 모두 아직 매칭되지 않은 경우에만 선택
        if i not in matched_a and j not in matched_b:
            matches[i] = j
            matched_a.add(i)
            matched_b.add(j)

    # 3단계: [C1] monotonic 순서 강제 — 교차 매칭 제거
    # 원본 줄 순서대로 정렬한 뒤, 수정본 인덱스(j)가 단조 증가하지 않는 매칭 제거
    # 이렇게 하면 줄 순서가 뒤바뀌는 교차 매칭을 방지
    ordered = sorted(matches.items())  # 원본 인덱스 기준 정렬
    clean_matches = {}
    prev_j = -1
    for i, j in ordered:
        if j > prev_j:
            clean_matches[i] = j
            prev_j = j
        # j <= prev_j인 경우 교차 매칭이므로 제외
    matches = clean_matches
    matched_a = set(matches.keys())
    matched_b = set(matches.values())

    # 4단계: 결과를 원래 순서로 재구성
    # 매칭되지 않은 수정본 줄 (insert로 처리)
    unmatched_b = sorted(set(range(m)) - matched_b)

    # 이벤트 리스트 생성: 정렬 키를 사용해 올바른 위치에 배치
    events = []
    for i in range(n):
        if i in matches:
            # 매칭된 줄 → replace (단어 단위 diff 표시)
            events.append((i * 2 + 1, "replace", i, matches[i]))
        else:
            # 매칭 안 된 원본 줄 → delete
            events.append((i * 2 + 1, "delete", i, None))

    # 매칭된 수정본 줄의 (j, i) 쌍 — insert 위치 결정에 사용
    matched_b_sorted = sorted((j, i) for i, j in matches.items())

    # 매칭 안 된 수정본 줄을 적절한 위치에 insert로 삽입
    for bj in unmatched_b:
        inserted = False
        for match_bj, match_ai in matched_b_sorted:
            if match_bj > bj:
                # 이 매칭 쌍 바로 앞에 삽입
                events.append((match_ai * 2, "insert", None, bj))
                inserted = True
                break
        if not inserted:
            # 모든 매칭 쌍 뒤에 삽입 (끝에 추가)
            events.append((n * 2 + bj, "insert", None, bj))

    # 정렬 키 기준으로 이벤트를 순서대로 정렬
    events.sort(key=lambda x: x[0])

    # 최종 결과 리스트 생성
    result = []
    for _, rtype, ai, bj in events:
        la = block_a[ai] if ai is not None else None  # 원본 줄 (없으면 None)
        lb = block_b[bj] if bj is not None else None  # 수정본 줄 (없으면 None)
        result.append((rtype, la, lb))

    return result


# ─────────────────────────────────────────
# 파일 전체 diff: 두 파일을 비교하여 HTML 행 데이터 생성
# ─────────────────────────────────────────

def parse_xml_file(path):
    """XML 파일을 파싱해 텍스트 라인 리스트와 Item 메타데이터 맵을 반환.

    Returns:
        tuple[list[str], dict[int, dict]]:
            - lines: 기존 diff 엔진에 전달할 텍스트 라인 리스트
              형식: ["######### {PackageName} ##########", "", "{Value}", ...]
            - meta_map: {0-based 라인 인덱스: item 메타데이터 딕셔너리}
              헤더/빈 줄은 meta_map에 포함되지 않음
    """
    tree = ET.parse(path)
    root = tree.getroot()
    package_name = root.findtext('PackageName') or ''

    lines = []
    meta_map = {}

    for diff_item in root.findall('.//DiffItem'):
        sub_title = diff_item.findtext('SubTitle') or ''
        lines.append(f"######### {package_name} ##########")
        lines.append("")

        for item_el in diff_item.findall('Items/Item'):
            item_id = item_el.findtext('ID') or ''
            value = item_el.findtext('Value') or ''
            line_number_text = item_el.findtext('LineNumber') or '0'
            edit_type = item_el.findtext('EditType') or 'None'

            try:
                line_number = int(line_number_text)
            except ValueError:
                line_number = 0

            idx = len(lines)
            meta_map[idx] = {
                'item_id': item_id,
                'value': value,
                'line_number': line_number,
                'edit_type': edit_type,
                'sub_title': sub_title,
                'package_name': package_name,
            }
            lines.append(value)

    return lines, meta_map


def read_file(path):
    """파일을 UTF-8로 읽어 줄 리스트로 반환.

    [H6] UnicodeDecodeError 방지를 위해 errors="replace" 옵션 사용.
    디코딩 불가능한 바이트는 유니코드 대체 문자(U+FFFD)로 치환됨.

    Args:
        path (str): 읽을 파일 경로

    Returns:
        list[str]: 줄 바꿈 포함한 각 줄의 리스트
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def make_row(rtype, lineno_a, lineno_b, text_a, text_b, meta_b=None):
    """diff 테이블의 한 행(row) 데이터를 생성.

    행 유형에 따라 적절한 HTML을 생성:
      - equal     : 양쪽 동일 → 이스케이프만 적용
      - replace   : 내용 변경 → 단어 단위 diff HTML 생성
      - delete    : 원본에만 있음 → 원본만 이스케이프
      - insert    : 수정본에만 있음 → 수정본만 이스케이프
      - empty-file: 빈 파일 → 빈 문자열

    Args:
        rtype (str): 행 유형 ("equal", "replace", "delete", "insert", "empty-file")
        lineno_a (int|None): 원본 줄 번호
        lineno_b (int|None): 수정본 줄 번호
        text_a (str|None): 원본 줄 텍스트
        text_b (str|None): 수정본 줄 텍스트
        meta_b (dict|None): XML Item 메타데이터 (XML 파일의 replace/insert 행만 해당)

    Returns:
        dict: {type, lineno_a, lineno_b, html_a, html_b, meta_b}
    """
    if rtype == "equal":
        ha = esc(text_a)
        hb = esc(text_b)
    elif rtype == "replace":
        ha, hb = word_diff_html(text_a or "", text_b or "")
    elif rtype == "delete":
        ha = esc(text_a or "")
        hb = ""
    elif rtype == "empty-file":
        ha = ""
        hb = ""
    else:  # insert
        ha = ""
        hb = esc(text_b or "")
    return {
        "type": rtype,
        "lineno_a": lineno_a,
        "lineno_b": lineno_b,
        "html_a": ha,
        "html_b": hb,
        "meta_b": meta_b,
    }


def build_diff(word_dir, code_dir, filename):
    """두 파일을 비교하여 diff 테이블 행 데이터 리스트를 생성.

    처리 과정:
      1. 양쪽 파일을 읽어서 줄 리스트로 변환
      2. difflib.SequenceMatcher로 줄 단위 비교
      3. replace 블록은 match_blocks()로 유사도 기반 세밀 매칭
      4. 각 줄을 make_row()로 HTML 행 데이터로 변환

    Args:
        word_dir (str): 원본 디렉토리 경로
        code_dir (str): 수정본 디렉토리 경로
        filename (str): 비교할 파일명

    Returns:
        tuple: (rows, total, changed)
               - rows: 행 데이터 리스트
               - total: 전체 행 수
               - changed: 변경된 행 수 (equal이 아닌 행)
    """
    path_a = os.path.join(word_dir, filename)
    path_b = os.path.join(code_dir, filename)

    is_xml = filename.endswith(".xml")
    if is_xml:
        lines_a, _ = parse_xml_file(path_a)
        lines_b, meta_map_b = parse_xml_file(path_b)
    else:
        # [H1] Windows 줄바꿈(\r\n) 처리 — 통일된 비교를 위해 줄 끝 문자 제거
        lines_a = [l.rstrip("\r\n") for l in read_file(path_a)]
        lines_b = [l.rstrip("\r\n") for l in read_file(path_b)]
        meta_map_b = {}

    # [H2] 빈 파일 처리 — 양쪽 모두 비어있거나 한쪽만 빈 경우
    if not lines_a and not lines_b:
        # 양쪽 모두 빈 파일
        return [make_row("empty-file", None, None, None, None)], 0, 0

    if not lines_a:
        # 원본만 빈 파일 → 수정본의 모든 줄이 추가된 것으로 표시
        rows = [make_row("empty-file", None, None, None, None)]
        for idx, lb in enumerate(lines_b, 1):
            rows.append(make_row("insert", None, idx, None, lb))
        return rows, len(lines_b), len(lines_b)

    if not lines_b:
        # 수정본만 빈 파일 → 원본의 모든 줄이 삭제된 것으로 표시
        rows = [make_row("empty-file", None, None, None, None)]
        for idx, la in enumerate(lines_a, 1):
            rows.append(make_row("delete", idx, None, la, None))
        return rows, len(lines_a), len(lines_a)

    # difflib.SequenceMatcher로 줄 단위 비교 수행
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    rows = []
    lineno_a = 1  # 원본 줄 번호 카운터
    lineno_b = 1  # 수정본 줄 번호 카운터

    # 각 opcode별로 행 데이터 생성
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == "equal":
            # 동일한 줄 블록 — 양쪽 동시에 줄 번호 증가
            for la, lb in zip(lines_a[i1:i2], lines_b[j1:j2]):
                rows.append(make_row("equal", lineno_a, lineno_b, la, lb))
                lineno_a += 1
                lineno_b += 1

        elif tag == "replace":
            # 변경된 줄 블록 — 유사도 기반 매칭으로 세밀하게 비교
            block_a = lines_a[i1:i2]
            block_b = lines_b[j1:j2]
            if is_xml:
                # XML 모드: 구조화된 항목은 위치 기준으로 강제 replace 매칭
                matched = list(zip(["replace"] * max(len(block_a), len(block_b)),
                                   block_a + [None] * (max(len(block_a), len(block_b)) - len(block_a)),
                                   block_b + [None] * (max(len(block_a), len(block_b)) - len(block_b))))
            else:
                matched = match_blocks(block_a, block_b)
            for rtype, la, lb in matched:
                # 해당 줄이 있을 때만 줄 번호 부여
                lna = lineno_a if la is not None else None
                lnb = lineno_b if lb is not None else None
                meta = meta_map_b.get(lineno_b - 1) if (is_xml and lb is not None and rtype in ("replace", "insert")) else None
                rows.append(make_row(rtype, lna, lnb, la, lb, meta_b=meta))
                if la is not None: lineno_a += 1
                if lb is not None: lineno_b += 1

        elif tag == "delete":
            # 삭제된 줄 블록 — 원본에만 존재하는 줄
            for la in lines_a[i1:i2]:
                rows.append(make_row("delete", lineno_a, None, la, None))
                lineno_a += 1

        elif tag == "insert":
            # 추가된 줄 블록 — 수정본에만 존재하는 줄
            for lb in lines_b[j1:j2]:
                meta = meta_map_b.get(lineno_b - 1) if is_xml else None
                rows.append(make_row("insert", None, lineno_b, None, lb, meta_b=meta))
                lineno_b += 1

    total   = len(rows)                                      # 전체 행 수
    changed = sum(1 for r in rows if r["type"] != "equal")   # 변경된 행 수
    return rows, total, changed


# ─────────────────────────────────────────
# 라우트: Flask URL 라우팅 핸들러
# ─────────────────────────────────────────

@app.route("/")
def index():
    """메인 페이지 — 첫 번째 베이스라인으로 자동 리다이렉트.

    베이스라인이 하나도 없으면 빈 상태의 index.html 렌더링.
    """
    baselines = get_baselines()
    if baselines:
        # 베이스라인이 있으면 첫 번째 베이스라인 페이지로 리다이렉트
        return redirect(url_for("baseline_view", baseline=baselines[0]))
    # 베이스라인이 없으면 빈 상태로 메인 페이지 렌더링
    return render_template("index.html", baselines=[], files=None, current_baseline=None)


@app.route("/<baseline>")
def baseline_view(baseline):
    """베이스라인별 파일 목록 페이지.

    해당 베이스라인의 모든 파일과 변경 여부를 표시.
    존재하지 않는 베이스라인 접근 시 404 반환.

    Args:
        baseline (str): URL에서 전달된 베이스라인 폴더명
    """
    baselines = get_baselines()
    # 유효하지 않은 베이스라인이면 404 에러
    if baseline not in baselines:
        abort(404)
    # 파일 목록 및 info.md 조회 후 템플릿 렌더링
    files = get_file_list(baseline)
    baseline_info = get_baseline_info(baseline)
    return render_template("index.html", baselines=baselines, files=files,
                           current_baseline=baseline, baseline_info=baseline_info)


@app.route("/<baseline>/diff/<filename>")
def diff_view(baseline, filename):
    """파일 diff 비교 페이지.

    두 디렉토리의 파일을 줄 단위/단어 단위로 비교한 결과를 표시.
    잘못된 파일명, 베이스라인, 또는 파일 미존재 시 적절한 HTTP 에러 반환.

    Args:
        baseline (str): URL에서 전달된 베이스라인 폴더명
        filename (str): 비교할 파일명 (.xml만 허용)
    """
    # .xml 확장자가 아닌 파일은 400 Bad Request
    if not filename.endswith(".xml"):
        abort(400)

    baselines = get_baselines()
    # 유효하지 않은 베이스라인이면 404
    if baseline not in baselines:
        abort(404)

    # 비교 대상 디렉토리 쌍 조회
    word_dir, code_dir = find_pair_dirs(baseline)
    if not word_dir or not code_dir:
        abort(404)

    # 양쪽 디렉토리에 해당 파일이 존재하는지 확인
    path_a = os.path.join(word_dir, filename)
    path_b = os.path.join(code_dir, filename)
    if not os.path.isfile(path_a) or not os.path.isfile(path_b):
        abort(404)

    # 파일 목록 및 diff 데이터 생성
    files = get_file_list(baseline)
    rows, total, changed = build_diff(word_dir, code_dir, filename)
    has_editable = any(r.get("meta_b") for r in rows)
    # 디렉토리 이름만 추출 (헤더 표시용)
    word_dir_name = os.path.basename(word_dir)
    code_dir_name = os.path.basename(code_dir)

    return render_template(
        "diff.html",
        baselines=baselines,
        current_baseline=baseline,
        filename=filename,
        word_dir_name=word_dir_name,   # 원본 디렉토리명 (예: 00.WordBase)
        code_dir_name=code_dir_name,   # 수정본 디렉토리명 (예: 01.CodeBase)
        rows=rows,                     # diff 행 데이터 리스트
        total=total,                   # 전체 행 수
        changed=changed,               # 변경된 행 수
        files=files,                   # 사이드바용 파일 목록
        has_editable=has_editable,
    )


@app.route("/<baseline>/diff/<filename>/submit", methods=["POST"])
def submit_edits(baseline, filename):
    """편집/스킵 처리된 diff 라인 데이터를 외부 서버로 전송.

    Request body (JSON):
        [{"package_name": str, "sub_title": str,
          "item": {"id": str, "value": str, "line_number": int, "edit_type": str},
          "user_action": "edited"|"skipped"}, ...]

    Returns:
        JSON: {"status": "ok", "count": int}
    """
    if baseline not in get_baselines():
        abort(404)
    if not filename.endswith(".xml"):
        abort(400)

    data = request.get_json()
    if not isinstance(data, list):
        abort(400)

    if SUBMIT_SERVER_URL:
        import urllib.request as urllib_req
        import json as json_mod
        payload = json_mod.dumps(data).encode("utf-8")
        req = urllib_req.Request(
            SUBMIT_SERVER_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_req.urlopen(req, timeout=10):
            pass
        return jsonify({"status": "forwarded", "count": len(data)})

    return jsonify({"status": "ok", "count": len(data)})


# 직접 실행 시 Flask 개발 서버 시작 (디버그 모드)
if __name__ == "__main__":
    app.run(debug=True)
