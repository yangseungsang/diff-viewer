import os
import re
import difflib
from flask import Flask, render_template, abort, redirect, url_for

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# [H3] 두 줄이 같은 줄로 짝지어질 최소 유사도 — 0.55 (기존 0.3은 너무 낮아 무관한 줄이 매칭됨)
SIMILARITY_THRESHOLD = 0.55


# ─────────────────────────────────────────
# 폴더 스캔
# ─────────────────────────────────────────

def get_baselines():
    """data/ 하위의 베이스라인 폴더 목록 반환"""
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(
        name for name in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, name))
    )


def find_pair_dirs(baseline):
    """baseline 폴더 안에서 00~/01~ 폴더를 찾아 반환"""
    base_path = os.path.join(DATA_DIR, baseline)
    word_dir = code_dir = None
    if not os.path.isdir(base_path):
        return None, None
    for name in sorted(os.listdir(base_path)):
        full = os.path.join(base_path, name)
        if not os.path.isdir(full):
            continue
        if name.startswith("00") and word_dir is None:
            word_dir = full
        elif name.startswith("01") and code_dir is None:
            code_dir = full
    return word_dir, code_dir


def file_has_diff(word_dir, code_dir, filename):
    """파일이 변경되었는지 빠르게 확인"""
    path_a = os.path.join(word_dir, filename)
    path_b = os.path.join(code_dir, filename)
    try:
        with open(path_a, "r", encoding="utf-8", errors="replace") as fa, \
             open(path_b, "r", encoding="utf-8", errors="replace") as fb:
            return fa.read() != fb.read()
    except OSError:
        return True


def get_file_list(baseline):
    """해당 베이스라인의 파일 목록 반환 (변경 여부 포함)"""
    word_dir, code_dir = find_pair_dirs(baseline)

    # [M2] 양쪽 디렉토리의 합집합으로 파일 목록 생성
    filenames = set()
    if word_dir:
        filenames |= {f for f in os.listdir(word_dir) if f.endswith(".txt")}
    if code_dir:
        filenames |= {f for f in os.listdir(code_dir) if f.endswith(".txt")}

    files = []
    for f in sorted(filenames):
        changed = file_has_diff(word_dir, code_dir, f) if word_dir and code_dir else False
        files.append({"name": f, "changed": changed})

    changed_count = sum(1 for f in files if f["changed"])

    return {
        "word_dir": word_dir,
        "code_dir": code_dir,
        "files":    files,
        "changed_count": changed_count,
    }


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def esc_ws(s):
    """공백 문자를 시각적 기호로 변환 (공백 diff 하이라이트용)"""
    out = ""
    for ch in s:
        if ch == " ":
            out += "·"
        elif ch == "\t":
            out += "→\t"
        else:
            out += esc(ch)
    return out


def line_similarity(a, b):
    """두 줄의 유사도 (0.0 ~ 1.0)"""
    # [H7] 빈 줄끼리는 0.0으로 처리해 greedy 매칭에서 의미 있는 줄을 방해하지 않도록
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# ─────────────────────────────────────────
# 단어 단위 diff
# ─────────────────────────────────────────

def tokenize(text):
    """공백 포함 단어 토큰 분리"""
    return re.findall(r'\S+|\s+', text) if text else []


def _classify_replace(seg_a, seg_b):
    """
    replace 세그먼트의 차이 유형을 분류.
    - "ws"   : 비공백 내용이 동일하고 공백 배치만 다름
    - "case" : 비공백 내용이 대소문자만 다름
    - "diff" : 내용이 다름
    """
    stripped_a = seg_a.strip()
    stripped_b = seg_b.strip()

    # 양쪽 다 공백만
    if stripped_a == "" and stripped_b == "":
        return "ws"

    # 비공백 내용이 동일 → 공백 배치만 다름
    # 예: "서울시 " vs " 서울시" → 공백 차이
    non_ws_a = re.sub(r'\s+', '', seg_a)
    non_ws_b = re.sub(r'\s+', '', seg_b)
    words_a = seg_a.split()
    words_b = seg_b.split()

    if non_ws_a == non_ws_b and len(words_a) == len(words_b):
        return "ws"

    # 대소문자만 다름 (단어 수가 같을 때만)
    if (non_ws_a.lower() == non_ws_b.lower()
            and len(words_a) == len(words_b)):
        return "case"

    return "diff"


def _render_ws_diff(seg_a, seg_b):
    """
    공백/대소문자 차이를 문자 단위로 세밀하게 렌더링.
    - 삭제된 공백 → wd-ws-del (빨간, · / → 기호)
    - 추가된 공백 → wd-ws-add (초록, · / → 기호)
    - 변경된 공백 → wd-ws-del / wd-ws-add (탭↔스페이스 등)
    - 대소문자 차이 → wd-diff (파란색)
    """
    chars_a = list(seg_a)
    chars_b = list(seg_b)
    matcher = difflib.SequenceMatcher(None, chars_a, chars_b, autojunk=False)
    html_a, html_b = [], []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        ca = "".join(chars_a[i1:i2])
        cb = "".join(chars_b[j1:j2])
        if tag == "equal":
            html_a.append(esc(ca))
            html_b.append(esc(cb))
        elif tag == "replace":
            is_ws = (ca.strip() == "" or cb.strip() == "")
            is_case = (not is_ws and ca.lower() == cb.lower())
            if is_ws:
                html_a.append(f'<span class="wd-ws-del">{esc_ws(ca)}</span>')
                html_b.append(f'<span class="wd-ws-add">{esc_ws(cb)}</span>')
            elif is_case:
                html_a.append(f'<span class="wd-diff">{esc(ca)}</span>')
                html_b.append(f'<span class="wd-diff">{esc(cb)}</span>')
            else:
                html_a.append(f'<span class="wd-ws-del">{esc_ws(ca)}</span>')
                html_b.append(f'<span class="wd-ws-add">{esc_ws(cb)}</span>')
        elif tag == "delete":
            html_a.append(f'<span class="wd-ws-del">{esc_ws(ca)}</span>')
        elif tag == "insert":
            html_b.append(f'<span class="wd-ws-add">{esc_ws(cb)}</span>')

    return "".join(html_a), "".join(html_b)


def word_diff_html(text_a, text_b):
    """
    두 줄을 단어 단위로 비교해 HTML 문자열 쌍으로 반환.
    - 공백만 다름              → wd-ws (회색) — 문자 단위 diff
    - 한쪽에만 있는 단어       → wd-only (빨간색)
    - 완전히 다른 단어로 교체  → wd-only (빨간색)
    - 대소문자만 다름          → wd-diff (파란색)
    """
    # 줄 전체의 비공백 내용이 동일하면 공백 배치만 다른 것 → 문자 단위 diff
    non_ws_a = re.sub(r'\s+', '', text_a)
    non_ws_b = re.sub(r'\s+', '', text_b)
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

    tokens_a = tokenize(text_a)
    tokens_b = tokenize(text_b)
    matcher  = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)

    parts_a, parts_b = [], []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        seg_a = "".join(tokens_a[i1:i2])
        seg_b = "".join(tokens_b[j1:j2])

        if tag == "equal":
            parts_a.append(esc(seg_a))
            parts_b.append(esc(seg_b))

        elif tag == "replace":
            cls = _classify_replace(seg_a, seg_b)
            if cls == "ws":
                ha, hb = _render_ws_diff(seg_a, seg_b)
                parts_a.append(ha)
                parts_b.append(hb)
            elif cls == "case":
                ha, hb = _render_ws_diff(seg_a, seg_b)
                parts_a.append(ha)
                parts_b.append(hb)
            else:
                parts_a.append(f'<span class="wd-only">{esc(seg_a)}</span>')
                parts_b.append(f'<span class="wd-only">{esc(seg_b)}</span>')

        elif tag == "delete":
            parts_a.append(f'<span class="wd-only">{esc(seg_a)}</span>')

        elif tag == "insert":
            parts_b.append(f'<span class="wd-only">{esc(seg_b)}</span>')

    return "".join(parts_a), "".join(parts_b)


# ─────────────────────────────────────────
# 유사도 기반 라인 매칭
# ─────────────────────────────────────────

def match_blocks(block_a, block_b):
    """
    replace 블록 내에서 유사도 기반으로 라인을 최적 매칭.

    [C1] greedy 매칭 후 monotonic 순서를 강제하여 교차 매칭 방지.
    """
    n, m = len(block_a), len(block_b)

    # 유사도 행렬 계산
    sim = [[0.0] * m for _ in range(n)]
    for i, la in enumerate(block_a):
        for j, lb in enumerate(block_b):
            sim[i][j] = line_similarity(la, lb)

    # greedy 매칭: 유사도 높은 순으로 선택
    pairs = []
    for i in range(n):
        for j in range(m):
            if sim[i][j] >= SIMILARITY_THRESHOLD:
                pairs.append((sim[i][j], i, j))
    pairs.sort(key=lambda x: -x[0])

    matched_a = set()
    matched_b = set()
    matches   = {}

    for score, i, j in pairs:
        if i not in matched_a and j not in matched_b:
            matches[i] = j
            matched_a.add(i)
            matched_b.add(j)

    # [C1] monotonic 순서 강제 — 교차 매칭 제거
    ordered = sorted(matches.items())
    clean_matches = {}
    prev_j = -1
    for i, j in ordered:
        if j > prev_j:
            clean_matches[i] = j
            prev_j = j
    matches = clean_matches
    matched_a = set(matches.keys())
    matched_b = set(matches.values())

    # 결과를 원래 순서로 재구성
    unmatched_b = sorted(set(range(m)) - matched_b)

    events = []
    for i in range(n):
        if i in matches:
            events.append((i * 2 + 1, "replace", i, matches[i]))
        else:
            events.append((i * 2 + 1, "delete", i, None))

    matched_b_sorted = sorted((j, i) for i, j in matches.items())

    for bj in unmatched_b:
        inserted = False
        for match_bj, match_ai in matched_b_sorted:
            if match_bj > bj:
                events.append((match_ai * 2, "insert", None, bj))
                inserted = True
                break
        if not inserted:
            events.append((n * 2 + bj, "insert", None, bj))

    events.sort(key=lambda x: x[0])

    result = []
    for _, rtype, ai, bj in events:
        la = block_a[ai] if ai is not None else None
        lb = block_b[bj] if bj is not None else None
        result.append((rtype, la, lb))

    return result


# ─────────────────────────────────────────
# 파일 전체 diff
# ─────────────────────────────────────────

# [H6] UnicodeDecodeError 방지 — errors="replace"로 안전하게 읽기
def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def make_row(rtype, lineno_a, lineno_b, text_a, text_b):
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
    }


def build_diff(word_dir, code_dir, filename):
    path_a = os.path.join(word_dir, filename)
    path_b = os.path.join(code_dir, filename)

    # [H1] Windows 줄바꿈(\r\n) 처리
    lines_a = [l.rstrip("\r\n") for l in read_file(path_a)]
    lines_b = [l.rstrip("\r\n") for l in read_file(path_b)]

    # [H2] 빈 파일 처리 — 한쪽이 비어있으면 표시
    if not lines_a and not lines_b:
        return [make_row("empty-file", None, None, None, None)], 0, 0

    if not lines_a:
        rows = [make_row("empty-file", None, None, None, None)]
        for idx, lb in enumerate(lines_b, 1):
            rows.append(make_row("insert", None, idx, None, lb))
        return rows, len(lines_b), len(lines_b)

    if not lines_b:
        rows = [make_row("empty-file", None, None, None, None)]
        for idx, la in enumerate(lines_a, 1):
            rows.append(make_row("delete", idx, None, la, None))
        return rows, len(lines_a), len(lines_a)

    matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    rows = []
    lineno_a = 1
    lineno_b = 1

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():

        if tag == "equal":
            for la, lb in zip(lines_a[i1:i2], lines_b[j1:j2]):
                rows.append(make_row("equal", lineno_a, lineno_b, la, lb))
                lineno_a += 1
                lineno_b += 1

        elif tag == "replace":
            block_a = lines_a[i1:i2]
            block_b = lines_b[j1:j2]
            matched = match_blocks(block_a, block_b)
            for rtype, la, lb in matched:
                lna = lineno_a if la is not None else None
                lnb = lineno_b if lb is not None else None
                rows.append(make_row(rtype, lna, lnb, la, lb))
                if la is not None: lineno_a += 1
                if lb is not None: lineno_b += 1

        elif tag == "delete":
            for la in lines_a[i1:i2]:
                rows.append(make_row("delete", lineno_a, None, la, None))
                lineno_a += 1

        elif tag == "insert":
            for lb in lines_b[j1:j2]:
                rows.append(make_row("insert", None, lineno_b, None, lb))
                lineno_b += 1

    total   = len(rows)
    changed = sum(1 for r in rows if r["type"] != "equal")
    return rows, total, changed


# ─────────────────────────────────────────
# 라우트
# ─────────────────────────────────────────

@app.route("/")
def index():
    baselines = get_baselines()
    if baselines:
        return redirect(url_for("baseline_view", baseline=baselines[0]))
    return render_template("index.html", baselines=[], files=None, current_baseline=None)


@app.route("/<baseline>")
def baseline_view(baseline):
    baselines = get_baselines()
    if baseline not in baselines:
        abort(404)
    files = get_file_list(baseline)
    return render_template("index.html", baselines=baselines, files=files, current_baseline=baseline)


@app.route("/<baseline>/diff/<filename>")
def diff_view(baseline, filename):
    if not filename.endswith(".txt"):
        abort(400)

    baselines = get_baselines()
    if baseline not in baselines:
        abort(404)

    word_dir, code_dir = find_pair_dirs(baseline)
    if not word_dir or not code_dir:
        abort(404)

    path_a = os.path.join(word_dir, filename)
    path_b = os.path.join(code_dir, filename)
    if not os.path.isfile(path_a) or not os.path.isfile(path_b):
        abort(404)

    files = get_file_list(baseline)
    rows, total, changed = build_diff(word_dir, code_dir, filename)
    word_dir_name = os.path.basename(word_dir)
    code_dir_name = os.path.basename(code_dir)

    return render_template(
        "diff.html",
        baselines=baselines,
        current_baseline=baseline,
        filename=filename,
        word_dir_name=word_dir_name,
        code_dir_name=code_dir_name,
        rows=rows,
        total=total,
        changed=changed,
        files=files,
    )


if __name__ == "__main__":
    app.run(debug=True)
