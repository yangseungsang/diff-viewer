# XML 데이터 포맷 & Edit 기능 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.txt` 파일을 `.xml` 포맷으로 교체하고, diff 화면에서 01.CodeBase 쪽 변경 라인에 Edit/Skip 기능을 추가하여 결과를 서버로 전송한다.

**Architecture:** 백엔드에서 XML을 파싱해 기존 텍스트 포맷으로 변환 후 기존 diff 엔진에 그대로 전달한다. diff 행(row)에 XML Item 메타데이터를 함께 전달하고, 프론트엔드 JS가 편집 상태를 관리한 뒤 완료 시 JSON으로 서버에 전송한다.

**Tech Stack:** Python 3 (xml.etree.ElementTree, Flask), pytest, Jinja2, Vanilla JS, CSS

---

## 변경 파일 목록

| 파일 | 역할 |
|------|------|
| `app.py` | XML 파서 추가, 파일 확장자 `.xml` 처리, `meta_b` 전달, submit 엔드포인트 |
| `templates/diff.html` | Edit/Skip 버튼, 진행 카운터, 전송 버튼, JS 상태 관리 |
| `static/style.css` | 편집됨/스킵됨 상태 스타일, 버튼 스타일, 카운터/전송 버튼 스타일 |
| `tests/test_xml_parser.py` | XML 파서 단위 테스트 |
| `data/baseline_v4/00.WordBase/sample.xml` | XML 테스트 데이터 (원본) |
| `data/baseline_v4/01.CodeBase/sample.xml` | XML 테스트 데이터 (수정본) |

---

## Task 1: XML 테스트 데이터 생성

**Files:**
- Create: `data/baseline_v4/00.WordBase/sample.xml`
- Create: `data/baseline_v4/01.CodeBase/sample.xml`

- [ ] **Step 1: 00.WordBase/sample.xml 생성**

```xml
<?xml version="1.0" encoding="utf-8"?>
<DiffPackage>
  <PackageName>TestPackage</PackageName>
  <DiffItems>
    <DiffItem>
      <SubTitle>섹션A</SubTitle>
      <Items>
        <Item>
          <ID>item_001</ID>
          <Value>안녕하세요 세계</Value>
          <LineNumber>1</LineNumber>
          <EditType>None</EditType>
        </Item>
        <Item>
          <ID>item_002</ID>
          <Value>동일한 라인입니다</Value>
          <LineNumber>2</LineNumber>
          <EditType>None</EditType>
        </Item>
      </Items>
    </DiffItem>
    <DiffItem>
      <SubTitle>섹션B</SubTitle>
      <Items>
        <Item>
          <ID>item_003</ID>
          <Value>변경될 내용 ABC</Value>
          <LineNumber>3</LineNumber>
          <EditType>None</EditType>
        </Item>
        <Item>
          <ID>item_004</ID>
          <Value>또 다른 동일 라인</Value>
          <LineNumber>4</LineNumber>
          <EditType>None</EditType>
        </Item>
      </Items>
    </DiffItem>
  </DiffItems>
</DiffPackage>
```

- [ ] **Step 2: 01.CodeBase/sample.xml 생성 (일부 다른 내용)**

```xml
<?xml version="1.0" encoding="utf-8"?>
<DiffPackage>
  <PackageName>TestPackage</PackageName>
  <DiffItems>
    <DiffItem>
      <SubTitle>섹션A</SubTitle>
      <Items>
        <Item>
          <ID>item_001</ID>
          <Value>안녕하세요 월드</Value>
          <LineNumber>1</LineNumber>
          <EditType>Modified</EditType>
        </Item>
        <Item>
          <ID>item_002</ID>
          <Value>동일한 라인입니다</Value>
          <LineNumber>2</LineNumber>
          <EditType>None</EditType>
        </Item>
      </Items>
    </DiffItem>
    <DiffItem>
      <SubTitle>섹션B</SubTitle>
      <Items>
        <Item>
          <ID>item_003</ID>
          <Value>변경된 내용 XYZ</Value>
          <LineNumber>3</LineNumber>
          <EditType>Modified</EditType>
        </Item>
        <Item>
          <ID>item_004</ID>
          <Value>또 다른 동일 라인</Value>
          <LineNumber>4</LineNumber>
          <EditType>None</EditType>
        </Item>
      </Items>
    </DiffItem>
  </DiffItems>
</DiffPackage>
```

- [ ] **Step 3: 커밋**

```bash
git add data/baseline_v4/
git commit -m "test: add XML baseline_v4 test data"
```

---

## Task 2: XML 파서 구현 (TDD)

**Files:**
- Create: `tests/test_xml_parser.py`
- Modify: `app.py` (상단 import 및 `parse_xml_file` 함수 추가)

- [ ] **Step 1: tests/ 디렉토리 및 테스트 파일 생성**

```python
# tests/test_xml_parser.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import textwrap, tempfile, pytest
from app import parse_xml_file

XML_SAMPLE = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <DiffPackage>
      <PackageName>MyPkg</PackageName>
      <DiffItems>
        <DiffItem>
          <SubTitle>섹션1</SubTitle>
          <Items>
            <Item>
              <ID>id_001</ID>
              <Value>첫 번째 값</Value>
              <LineNumber>1</LineNumber>
              <EditType>None</EditType>
            </Item>
            <Item>
              <ID>id_002</ID>
              <Value>두 번째 값</Value>
              <LineNumber>2</LineNumber>
              <EditType>Modified</EditType>
            </Item>
          </Items>
        </DiffItem>
        <DiffItem>
          <SubTitle>섹션2</SubTitle>
          <Items>
            <Item>
              <ID>id_003</ID>
              <Value>세 번째 값</Value>
              <LineNumber>3</LineNumber>
              <EditType>None</EditType>
            </Item>
          </Items>
        </DiffItem>
      </DiffItems>
    </DiffPackage>
""")


@pytest.fixture
def xml_file(tmp_path):
    f = tmp_path / "sample.xml"
    f.write_text(XML_SAMPLE, encoding="utf-8")
    return str(f)


def test_parse_returns_tuple(xml_file):
    result = parse_xml_file(xml_file)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_lines_contain_package_header(xml_file):
    lines, _ = parse_xml_file(xml_file)
    assert any("MyPkg" in l for l in lines)


def test_lines_contain_all_item_values(xml_file):
    lines, _ = parse_xml_file(xml_file)
    assert "첫 번째 값" in lines
    assert "두 번째 값" in lines
    assert "세 번째 값" in lines


def test_meta_map_keys_are_int(xml_file):
    _, meta_map = parse_xml_file(xml_file)
    for k in meta_map:
        assert isinstance(k, int)


def test_meta_map_item_fields(xml_file):
    lines, meta_map = parse_xml_file(xml_file)
    # 첫 번째 값이 있는 라인의 인덱스 찾기
    idx = lines.index("첫 번째 값")
    meta = meta_map[idx]
    assert meta["item_id"] == "id_001"
    assert meta["value"] == "첫 번째 값"
    assert meta["line_number"] == 1
    assert meta["edit_type"] == "None"
    assert meta["sub_title"] == "섹션1"
    assert meta["package_name"] == "MyPkg"


def test_meta_map_second_diffitem(xml_file):
    lines, meta_map = parse_xml_file(xml_file)
    idx = lines.index("세 번째 값")
    meta = meta_map[idx]
    assert meta["item_id"] == "id_003"
    assert meta["sub_title"] == "섹션2"


def test_header_lines_not_in_meta_map(xml_file):
    lines, meta_map = parse_xml_file(xml_file)
    for idx, line in enumerate(lines):
        if "MyPkg" in line or line.strip() == "":
            assert idx not in meta_map, f"헤더/빈 줄(인덱스 {idx})이 meta_map에 포함됨"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```
cd /home/yangsm/Projects/diff-viewer
pip install pytest -q
pytest tests/test_xml_parser.py -v
```

Expected: FAIL (parse_xml_file not defined)

- [ ] **Step 3: app.py 상단에 ET import 추가**

`app.py` 15~18번째 줄 import 블록에 아래 추가:
```python
import xml.etree.ElementTree as ET
```

- [ ] **Step 4: parse_xml_file 함수 추가**

`app.py` 의 `read_file` 함수(594번째 줄) 바로 위에 추가:

```python
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

            idx = len(lines)
            meta_map[idx] = {
                'item_id': item_id,
                'value': value,
                'line_number': int(line_number_text),
                'edit_type': edit_type,
                'sub_title': sub_title,
                'package_name': package_name,
            }
            lines.append(value)

    return lines, meta_map
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```
pytest tests/test_xml_parser.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add app.py tests/test_xml_parser.py
git commit -m "feat: add parse_xml_file with tests"
```

---

## Task 3: 파일 스캔 함수 XML 확장자 처리

**Files:**
- Modify: `app.py` (`get_file_list` 함수, 132~134번째 줄)

- [ ] **Step 1: 실패 테스트 추가 (tests/test_xml_parser.py 하단에 추가)**

```python
# tests/test_xml_parser.py 하단에 추가
from app import get_file_list

def test_get_file_list_finds_xml(tmp_path):
    # baseline 디렉토리 구조 생성
    word_dir = tmp_path / "00.WordBase"
    code_dir = tmp_path / "01.CodeBase"
    word_dir.mkdir(); code_dir.mkdir()
    (word_dir / "a.xml").write_text("<DiffPackage><PackageName>P</PackageName><DiffItems/></DiffPackage>")
    (code_dir / "a.xml").write_text("<DiffPackage><PackageName>P</PackageName><DiffItems/></DiffPackage>")

    import app as app_module
    original_data_dir = app_module.DATA_DIR

    # baseline 디렉토리를 tmp_path 기준으로 임시 교체
    baseline_name = tmp_path.name
    parent = str(tmp_path.parent)
    app_module.DATA_DIR = parent
    try:
        result = get_file_list(baseline_name)
        filenames = [f['name'] for f in result['files']]
        assert "a.xml" in filenames
    finally:
        app_module.DATA_DIR = original_data_dir
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```
pytest tests/test_xml_parser.py::test_get_file_list_finds_xml -v
```

Expected: FAIL (`.txt` 필터로 인해 `a.xml`을 찾지 못함)

- [ ] **Step 3: get_file_list 함수 수정 (app.py 132~134번째 줄)**

변경 전:
```python
    if word_dir:
        filenames |= {f for f in os.listdir(word_dir) if f.endswith(".txt")}
    if code_dir:
        filenames |= {f for f in os.listdir(code_dir) if f.endswith(".txt")}
```

변경 후:
```python
    if word_dir:
        filenames |= {f for f in os.listdir(word_dir) if f.endswith(".xml")}
    if code_dir:
        filenames |= {f for f in os.listdir(code_dir) if f.endswith(".xml")}
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```
pytest tests/test_xml_parser.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add app.py tests/test_xml_parser.py
git commit -m "feat: update file scanning to .xml extension"
```

---

## Task 4: make_row에 meta_b 필드 추가

**Files:**
- Modify: `app.py` (`make_row` 함수, 610~651번째 줄)

- [ ] **Step 1: make_row 시그니처 및 반환값 수정**

`app.py` 610번째 줄 `make_row` 함수 전체를 아래로 교체:

```python
def make_row(rtype, lineno_a, lineno_b, text_a, text_b, meta_b=None):
    """diff 테이블의 한 행(row) 데이터를 생성.

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
```

- [ ] **Step 2: 커밋**

```bash
git add app.py
git commit -m "feat: add meta_b field to make_row"
```

---

## Task 5: build_diff에 XML 파싱 연동

**Files:**
- Modify: `app.py` (`build_diff` 함수, 654~743번째 줄)

- [ ] **Step 1: 실패 테스트 추가 (tests/test_xml_parser.py 하단에 추가)**

```python
# tests/test_xml_parser.py 하단에 추가
from app import build_diff

WORD_XML = """<?xml version="1.0" encoding="utf-8"?>
<DiffPackage>
  <PackageName>Pkg</PackageName>
  <DiffItems>
    <DiffItem>
      <SubTitle>S1</SubTitle>
      <Items>
        <Item><ID>a1</ID><Value>같은 내용</Value><LineNumber>1</LineNumber><EditType>None</EditType></Item>
        <Item><ID>a2</ID><Value>원본 값</Value><LineNumber>2</LineNumber><EditType>None</EditType></Item>
      </Items>
    </DiffItem>
  </DiffItems>
</DiffPackage>"""

CODE_XML = """<?xml version="1.0" encoding="utf-8"?>
<DiffPackage>
  <PackageName>Pkg</PackageName>
  <DiffItems>
    <DiffItem>
      <SubTitle>S1</SubTitle>
      <Items>
        <Item><ID>a1</ID><Value>같은 내용</Value><LineNumber>1</LineNumber><EditType>None</EditType></Item>
        <Item><ID>a2</ID><Value>수정된 값</Value><LineNumber>2</LineNumber><EditType>Modified</EditType></Item>
      </Items>
    </DiffItem>
  </DiffItems>
</DiffPackage>"""


def test_build_diff_xml_replace_has_meta_b(tmp_path):
    word_dir = tmp_path / "00.WordBase"
    code_dir = tmp_path / "01.CodeBase"
    word_dir.mkdir(); code_dir.mkdir()
    (word_dir / "t.xml").write_text(WORD_XML, encoding="utf-8")
    (code_dir / "t.xml").write_text(CODE_XML, encoding="utf-8")

    rows, total, changed = build_diff(str(word_dir), str(code_dir), "t.xml")
    replace_rows = [r for r in rows if r["type"] == "replace"]
    assert len(replace_rows) > 0
    for row in replace_rows:
        assert row["meta_b"] is not None
        assert "item_id" in row["meta_b"]
        assert "sub_title" in row["meta_b"]
        assert "package_name" in row["meta_b"]


def test_build_diff_xml_equal_has_no_meta_b(tmp_path):
    word_dir = tmp_path / "00.WordBase"
    code_dir = tmp_path / "01.CodeBase"
    word_dir.mkdir(); code_dir.mkdir()
    (word_dir / "t.xml").write_text(WORD_XML, encoding="utf-8")
    (code_dir / "t.xml").write_text(CODE_XML, encoding="utf-8")

    rows, _, _ = build_diff(str(word_dir), str(code_dir), "t.xml")
    equal_rows = [r for r in rows if r["type"] == "equal"]
    assert len(equal_rows) > 0
    for row in equal_rows:
        assert row["meta_b"] is None
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```
pytest tests/test_xml_parser.py::test_build_diff_xml_replace_has_meta_b tests/test_xml_parser.py::test_build_diff_xml_equal_has_no_meta_b -v
```

Expected: FAIL

- [ ] **Step 3: build_diff 함수 수정**

`app.py` `build_diff` 함수에서 파일 읽는 부분(677~679번째 줄)을 아래로 교체:

```python
    is_xml = filename.endswith(".xml")
    if is_xml:
        lines_a, _ = parse_xml_file(path_a)
        lines_b, meta_map_b = parse_xml_file(path_b)
    else:
        lines_a = [l.rstrip("\r\n") for l in read_file(path_a)]
        lines_b = [l.rstrip("\r\n") for l in read_file(path_b)]
        meta_map_b = {}
```

그리고 `build_diff` 내부 `replace` 블록 처리 부분(721~727번째 줄)을 수정:

```python
            for rtype, la, lb in matched:
                lna = lineno_a if la is not None else None
                lnb = lineno_b if lb is not None else None
                meta = meta_map_b.get(lineno_b - 1) if (is_xml and lb is not None and rtype in ("replace", "insert")) else None
                rows.append(make_row(rtype, lna, lnb, la, lb, meta_b=meta))
                if la is not None: lineno_a += 1
                if lb is not None: lineno_b += 1
```

그리고 `insert` 블록 처리 부분(735~738번째 줄)을 수정:

```python
        elif tag == "insert":
            for lb in lines_b[j1:j2]:
                meta = meta_map_b.get(lineno_b - 1) if is_xml else None
                rows.append(make_row("insert", None, lineno_b, None, lb, meta_b=meta))
                lineno_b += 1
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```
pytest tests/test_xml_parser.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add app.py tests/test_xml_parser.py
git commit -m "feat: connect build_diff with XML parser and meta_b"
```

---

## Task 6: diff_view 라우트 XML 확장자 처리

**Files:**
- Modify: `app.py` (`diff_view` 함수, 796~797번째 줄)

- [ ] **Step 1: diff_view 파일 확장자 체크 수정**

변경 전 (796~797번째 줄):
```python
    if not filename.endswith(".txt"):
        abort(400)
```

변경 후:
```python
    if not filename.endswith(".xml"):
        abort(400)
```

- [ ] **Step 2: Flask 서버 실행 후 브라우저에서 확인**

```
python app.py
```

브라우저에서 `http://localhost:5000/baseline_v4` 접속 → `sample.xml` 목록 확인 → 클릭하여 diff 화면 정상 표시 여부 확인.

- [ ] **Step 3: 커밋**

```bash
git add app.py
git commit -m "feat: update diff_view route to accept .xml files"
```

---

## Task 7: 서버 전송 엔드포인트 추가

**Files:**
- Modify: `app.py` (import 블록 및 `diff_view` 라우트 아래에 추가)

- [ ] **Step 1: Flask request, jsonify import 추가**

`app.py` 19번째 줄 import 수정:

```python
from flask import Flask, render_template, abort, redirect, url_for, request, jsonify
```

- [ ] **Step 2: 서버 전송 URL 상수 추가**

`app.py` `SIMILARITY_THRESHOLD` 상수(31번째 줄) 바로 아래에 추가:

```python
# 편집 결과를 전송할 외부 서버 URL (추후 설정)
SUBMIT_SERVER_URL = ""
```

- [ ] **Step 3: submit 엔드포인트 추가**

`app.py` 맨 끝 `if __name__ == "__main__":` 블록 바로 위에 추가:

```python
@app.route("/<baseline>/diff/<filename>/submit", methods=["POST"])
def submit_edits(baseline, filename):
    """편집/스킵 처리된 diff 라인 데이터를 외부 서버로 전송.

    Request body (JSON):
        [{"package_name": str, "sub_title": str,
          "item": {"id": str, "value": str, "line_number": int, "edit_type": str},
          "user_action": "edited"|"skipped"}, ...]

    Returns:
        JSON: {"status": "ok", "count": int} 또는
              {"status": "forwarded", "count": int} (서버 URL 설정 시)
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
        with urllib_req.urlopen(req, timeout=10) as resp:
            pass
        return jsonify({"status": "forwarded", "count": len(data)})

    return jsonify({"status": "ok", "count": len(data)})
```

- [ ] **Step 4: 커밋**

```bash
git add app.py
git commit -m "feat: add submit_edits endpoint for server forwarding"
```

---

## Task 8: diff.html 템플릿 수정 (Edit/Skip UI)

**Files:**
- Modify: `templates/diff.html`

- [ ] **Step 1: 헤더에 진행 카운터 및 전송 버튼 추가**

`diff.html` 26번째 줄 `{% if changed > 0 %}` 블록 안에, 네비게이션 버튼들 바로 앞에 추가:

```html
      <!-- XML 편집 진행 카운터 + 전송 버튼 (XML 파일이고 변경이 있을 때만) -->
      {% if rows and rows[0].meta_b is not none or rows | selectattr('meta_b') | list %}
      <span class="edit-progress" id="edit-progress">0 / 0 처리됨</span>
      <button class="send-btn" id="send-btn" disabled>서버로 전송</button>
      {% endif %}
```

실제로는 Jinja2에서 `rows|selectattr` 필터가 복잡하므로, `diff_view`에서 `has_editable` 변수를 전달하는 방식으로 변경. 먼저 `app.py`의 `diff_view` 반환값에 추가:

`app.py` `diff_view` 함수의 `render_template` 호출(823번째 줄)에 파라미터 추가:

```python
    has_editable = any(r.get("meta_b") for r in rows)

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
        has_editable=has_editable,
    )
```

그런 다음 `diff.html` 26번째 줄 `{% if changed > 0 %}` 안에 추가:

```html
      {% if has_editable %}
      <span class="edit-progress" id="edit-progress">0 / {{ changed }} 처리됨</span>
      <button class="send-btn" id="send-btn" disabled>서버로 전송</button>
      {% endif %}
```

- [ ] **Step 2: diff 테이블 replace/insert 행의 code-b 셀에 Edit/Skip 버튼 추가**

`diff.html` 82번째 줄의 `code-b` 셀 부분을 아래로 교체:

```html
        <!-- 수정본 코드: 추가/변경 시 '+' 기호 표시 + 단어 단위 diff HTML -->
        <td class="code code-b">
          <span class="line-mark {% if row.type == "insert" or row.type == "replace" %}line-mark-add{% endif %}">{% if row.type == "insert" or row.type == "replace" %}+{% endif %}</span>
          <span class="line-text" id="line-text-{{ loop.index }}">{{ row.html_b|safe }}</span>
          {% if row.meta_b %}
          <span class="edit-actions">
            <button class="edit-action-btn edit-btn" data-row="{{ loop.index }}"
              data-meta="{{ row.meta_b | tojson | forceescape }}"
              data-original="{{ row.meta_b.value | e }}">수정</button>
            <button class="edit-action-btn skip-btn" data-row="{{ loop.index }}"
              data-meta="{{ row.meta_b | tojson | forceescape }}">스킵</button>
          </span>
          <span class="edit-status-badge" id="badge-{{ loop.index }}" style="display:none"></span>
          {% endif %}
        </td>
```

- [ ] **Step 3: JS 상태 관리 스크립트 추가**

`diff.html` 기존 `<script>` 블록 내부 맨 끝(`}());` 바로 뒤)에 추가:

```javascript
/* ── Edit/Skip 상태 관리 ── */
(function() {
  var editState = {};  // { rowIndex: { action: "edited"|"skipped", value: str, meta: obj } }
  var totalEditable = document.querySelectorAll('[data-meta]').length / 2;  // 버튼 쌍
  var progressEl = document.getElementById('edit-progress');
  var sendBtn = document.getElementById('send-btn');

  function updateProgress() {
    var done = Object.keys(editState).length;
    if (progressEl) progressEl.textContent = done + ' / ' + totalEditable + ' 처리됨';
    if (sendBtn) sendBtn.disabled = (done < totalEditable);
  }

  function setRowState(rowIdx, action, value, meta) {
    var row = document.querySelector('tr:nth-child(' + rowIdx + ')') ||
              document.querySelector('[data-row="' + rowIdx + '"]').closest('tr');
    var badge = document.getElementById('badge-' + rowIdx);
    var lineText = document.getElementById('line-text-' + rowIdx);

    // 기존 상태 초기화
    row.classList.remove('row-edited', 'row-skipped');
    if (badge) { badge.style.display = 'none'; badge.textContent = ''; }

    if (action === null) {
      delete editState[rowIdx];
    } else {
      editState[rowIdx] = { action: action, value: value, meta: meta };
      row.classList.add(action === 'edited' ? 'row-edited' : 'row-skipped');
      if (badge) {
        badge.textContent = action === 'edited' ? '✓ 수정됨' : '⊘ 스킵됨';
        badge.className = 'edit-status-badge badge-' + (action === 'edited' ? 'edited' : 'skipped');
        badge.style.display = 'inline';
      }
      if (action === 'edited' && lineText) lineText.textContent = value;
    }
    updateProgress();
  }

  // 수정 버튼 클릭
  document.querySelectorAll('.edit-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var rowIdx = this.getAttribute('data-row');
      var meta = JSON.parse(this.getAttribute('data-meta'));
      var original = this.getAttribute('data-original');

      if (editState[rowIdx] && editState[rowIdx].action === 'edited') {
        setRowState(rowIdx, null, null, null);
        return;
      }

      var newVal = prompt('값을 수정하세요:', original);
      if (newVal === null) return;  // 취소
      setRowState(rowIdx, 'edited', newVal, meta);
    });
  });

  // 스킵 버튼 클릭
  document.querySelectorAll('.skip-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var rowIdx = this.getAttribute('data-row');
      var meta = JSON.parse(this.getAttribute('data-meta'));
      var original = document.getElementById('line-text-' + rowIdx) ?
                     document.getElementById('line-text-' + rowIdx).textContent : '';

      if (editState[rowIdx] && editState[rowIdx].action === 'skipped') {
        setRowState(rowIdx, null, null, null);
        return;
      }
      setRowState(rowIdx, 'skipped', original, meta);
    });
  });

  // 서버 전송 버튼 클릭
  if (sendBtn) {
    sendBtn.addEventListener('click', function() {
      var payload = Object.values(editState).map(function(s) {
        return {
          package_name: s.meta.package_name,
          sub_title: s.meta.sub_title,
          item: {
            id: s.meta.item_id,
            value: s.value,
            line_number: s.meta.line_number,
            edit_type: s.meta.edit_type
          },
          user_action: s.action
        };
      });

      var url = window.location.pathname + '/submit';
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        alert('전송 완료: ' + data.count + '건');
      })
      .catch(function(err) {
        alert('전송 실패: ' + err.message);
      });
    });
  }

  updateProgress();
}());
```

- [ ] **Step 4: 커밋**

```bash
git add templates/diff.html app.py
git commit -m "feat: add Edit/Skip UI and server submit to diff.html"
```

---

## Task 9: CSS 스타일 추가

**Files:**
- Modify: `static/style.css` (파일 끝에 추가)

- [ ] **Step 1: style.css 파일 끝에 스타일 추가**

```css
/* ── Edit/Skip 기능 스타일 ── */

.edit-actions {
  display: inline-flex;
  gap: 4px;
  margin-left: 8px;
  vertical-align: middle;
}

.edit-action-btn {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 3px;
  border: 1px solid currentColor;
  cursor: pointer;
  background: transparent;
  line-height: 1.4;
}

.edit-btn {
  color: #2563eb;
  border-color: #93c5fd;
}
.edit-btn:hover { background: #eff6ff; }

.skip-btn {
  color: #6b7280;
  border-color: #d1d5db;
}
.skip-btn:hover { background: #f9fafb; }

/* 수정됨 상태 행 */
tr.row-edited td { background: #f0fdf4 !important; }
tr.row-edited td.code-b { outline: 2px solid #22c55e; outline-offset: -2px; }

/* 스킵됨 상태 행 */
tr.row-skipped td { background: #f9fafb !important; opacity: 0.7; }
tr.row-skipped td.code-b { outline: 2px solid #9ca3af; outline-offset: -2px; }

/* 상태 뱃지 */
.edit-status-badge {
  font-size: 11px;
  font-weight: 600;
  margin-left: 6px;
  padding: 1px 5px;
  border-radius: 3px;
  vertical-align: middle;
}
.badge-edited  { color: #15803d; background: #dcfce7; }
.badge-skipped { color: #6b7280; background: #f3f4f6; }

/* 진행 카운터 */
.edit-progress {
  font-size: 12px;
  color: #6b7280;
  margin-right: 6px;
}

/* 서버 전송 버튼 */
.send-btn {
  font-size: 12px;
  padding: 3px 12px;
  border-radius: 4px;
  border: 1px solid #2563eb;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}
.send-btn:disabled {
  background: #9ca3af;
  border-color: #9ca3af;
  cursor: not-allowed;
}
.send-btn:not(:disabled):hover { background: #1d4ed8; }
```

- [ ] **Step 2: 커밋**

```bash
git add static/style.css
git commit -m "feat: add CSS styles for Edit/Skip feature"
```

---

## Task 10: 최종 통합 테스트

- [ ] **Step 1: 전체 테스트 실행**

```
pytest tests/ -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 2: Flask 서버 실행 후 브라우저 E2E 테스트**

```
python app.py
```

체크리스트:
- `http://localhost:5000/baseline_v4` → `sample.xml` 목록 표시 확인
- `sample.xml` 클릭 → diff 화면 표시 확인
- 변경된 행에 [수정] / [스킵] 버튼 표시 확인
- [수정] 클릭 → 프롬프트 입력 → 행이 초록 테두리 + ✓ 수정됨 뱃지로 변경 확인
- [스킵] 클릭 → 행이 회색 테두리 + ⊘ 스킵됨 뱃지로 변경 확인
- 버튼 재클릭 → 원래 상태로 복귀 확인
- 모든 diff 행 처리 후 "서버로 전송" 버튼 활성화 확인
- 전송 버튼 클릭 → "전송 완료: N건" 알림 확인

- [ ] **Step 3: 최종 커밋 (필요 시)**

```bash
git add -A
git commit -m "chore: finalize XML format and edit feature implementation"
```
