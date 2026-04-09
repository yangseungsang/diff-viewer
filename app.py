import os
import re
import difflib
from flask import Flask, render_template, abort

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 두 줄이 같은 줄로 짝지어질 최소 유사도 (0.0 ~ 1.0)
SIMILARITY_THRESHOLD = 0.3


# ─────────────────────────────────────────
# 폴더 스캔
# ─────────────────────────────────────────

def find_pair_dirs(exam_dir):
    """exam_dir 안에서 00으로 시작하는 폴더와 01로 시작하는 폴더를 찾아 반환"""
    word_dir = code_dir = None
    if not os.path.isdir(exam_dir):
        return None, None
    for name in sorted(os.listdir(exam_dir)):
        full = os.path.join(exam_dir, name)
        if not os.path.isdir(full):
            continue
        if name.startswith("00") and word_dir is None:
            word_dir = full
        elif name.startswith("01") and code_dir is None:
            code_dir = full
    return word_dir, code_dir


def get_all_exams():
    """
    data/ 하위의 모든 폴더를 탐색해 시험 목록 반환.
    각 폴더 안에서 00~/01~ 하위폴더를 자동으로 찾음.
    """
    result = []
    if not os.path.isdir(DATA_DIR):
        return result

    for exam_id in sorted(os.listdir(DATA_DIR)):
        exam_path = os.path.join(DATA_DIR, exam_id)
        if not os.path.isdir(exam_path):
            continue
        word_dir, code_dir = find_pair_dirs(exam_path)

        word_files = set()
        code_files = set()
        if word_dir:
            word_files = {f for f in os.listdir(word_dir) if f.endswith(".txt")}
        if code_dir:
            code_files = {f for f in os.listdir(code_dir) if f.endswith(".txt")}

        result.append({
            "exam_id":   exam_id,
            "word_dir":  word_dir,
            "code_dir":  code_dir,
            "common":    sorted(word_files & code_files),
            "only_word": sorted(word_files - code_files),
            "only_code": sorted(code_files - word_files),
        })
    return result


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def line_similarity(a, b):
    """두 줄의 유사도 (0.0 ~ 1.0)"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# ─────────────────────────────────────────
# 단어 단위 diff
# ─────────────────────────────────────────

def tokenize(text):
    """공백 포함 단어 토큰 분리"""
    return re.findall(r'\S+|\s+', text) if text else []


def word_diff_html(text_a, text_b):
    """
    두 줄을 단어 단위로 비교해 HTML 문자열 쌍으로 반환.
    - 한쪽에만 있는 단어  → wd-only (빨간색)
    - 대소문자/철자 차이  → wd-diff  (파란색)
    """
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
            if seg_a.strip() == "" and seg_b.strip() == "":
                parts_a.append(esc(seg_a))
                parts_b.append(esc(seg_b))
            elif seg_a.lower() == seg_b.lower():
                # 대소문자만 다름
                parts_a.append(f'<span class="wd-diff">{esc(seg_a)}</span>')
                parts_b.append(f'<span class="wd-diff">{esc(seg_b)}</span>')
            else:
                # 철자 차이
                parts_a.append(f'<span class="wd-diff">{esc(seg_a)}</span>')
                parts_b.append(f'<span class="wd-diff">{esc(seg_b)}</span>')

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

    알고리즘:
    1. 각 (a_line, b_line) 쌍의 유사도를 계산
    2. 유사도가 THRESHOLD 이상인 쌍 중 greedy하게 최적 쌍을 선택
       (유사도 높은 순으로 매칭, 한 번 매칭된 라인은 재사용 안 함)
    3. 매칭된 쌍 → replace 행
       매칭 안 된 a → delete 행
       매칭 안 된 b → insert 행
    4. 최종 순서는 원래 줄 번호 순서대로 재정렬

    반환: list of ("replace"|"delete"|"insert", la_or_None, lb_or_None)
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
    matches   = {}  # a_idx -> b_idx

    for score, i, j in pairs:
        if i not in matched_a and j not in matched_b:
            matches[i] = j
            matched_a.add(i)
            matched_b.add(j)

    # 결과를 원래 순서로 재구성
    # 매칭된 쌍은 a의 줄 번호 기준으로 배치
    # 매칭 안 된 b는 가장 가까운 위치의 a 뒤에 삽입

    # a_idx별 이후에 삽입될 b들 정리
    # 매칭 안 된 b를 순서대로 배치하기 위해
    # 매칭된 a 중 b_idx 기준으로 앞에 있는 미매칭 b를 앞에 배치

    unmatched_b = sorted(set(range(m)) - matched_b)

    # (position_key, type, a_idx_or_None, b_idx_or_None)
    events = []
    for i in range(n):
        if i in matches:
            events.append((i * 2 + 1, "replace", i, matches[i]))
        else:
            events.append((i * 2 + 1, "delete", i, None))

    # 미매칭 b를 적절한 위치에 삽입
    # 방법: 매칭된 b_idx보다 작은 미매칭 b는 그 매칭 쌍 앞에, 나머지는 뒤에
    matched_b_sorted = sorted((j, i) for i, j in matches.items())  # (b_idx, a_idx)

    for bj in unmatched_b:
        # bj보다 큰 b_idx 중 최소 매칭 쌍을 찾음
        inserted = False
        for match_bj, match_ai in matched_b_sorted:
            if match_bj > bj:
                # match_ai 앞에 삽입
                events.append((match_ai * 2, "insert", None, bj))
                inserted = True
                break
        if not inserted:
            # 모든 매칭 쌍보다 뒤에
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

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
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

    lines_a = [l.rstrip("\n") for l in read_file(path_a)]
    lines_b = [l.rstrip("\n") for l in read_file(path_b)]

    # 라인 전체 SequenceMatcher
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

            # 유사도 기반 매칭
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
    exams = get_all_exams()
    return render_template("index.html", exams=exams)


@app.route("/diff/<exam_id>/<filename>")
def diff_view(exam_id, filename):
    if not filename.endswith(".txt"):
        abort(400)

    exam_path = os.path.join(DATA_DIR, exam_id)
    word_dir, code_dir = find_pair_dirs(exam_path)

    if not word_dir or not code_dir:
        abort(404)

    path_a = os.path.join(word_dir, filename)
    path_b = os.path.join(code_dir, filename)
    if not os.path.isfile(path_a) or not os.path.isfile(path_b):
        abort(404)

    exams = get_all_exams()
    rows, total, changed = build_diff(word_dir, code_dir, filename)
    word_dir_name = os.path.basename(word_dir)
    code_dir_name = os.path.basename(code_dir)

    return render_template(
        "diff.html",
        exam_id=exam_id,
        filename=filename,
        word_dir_name=word_dir_name,
        code_dir_name=code_dir_name,
        rows=rows,
        total=total,
        changed=changed,
        exams=exams,
    )


if __name__ == "__main__":
    app.run(debug=True)
