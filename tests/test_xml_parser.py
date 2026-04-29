# tests/test_xml_parser.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import textwrap
import pytest
from app import parse_xml_file, get_file_list, build_diff

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
    assert meta["package_name"] == "MyPkg"
    assert meta["value"] == "세 번째 값"


def test_header_lines_not_in_meta_map(xml_file):
    lines, meta_map = parse_xml_file(xml_file)
    for idx, line in enumerate(lines):
        if line.startswith("#########") or line.strip() == "":
            assert idx not in meta_map, f"헤더/빈 줄(인덱스 {idx})이 meta_map에 포함됨"


def test_empty_diffitems_returns_empty(tmp_path):
    empty_xml = '<?xml version="1.0" encoding="utf-8"?><DiffPackage><PackageName>P</PackageName><DiffItems/></DiffPackage>'
    f = tmp_path / "empty.xml"
    f.write_text(empty_xml, encoding="utf-8")
    lines, meta_map = parse_xml_file(str(f))
    assert lines == []
    assert meta_map == {}


def test_get_file_list_finds_xml(tmp_path):
    # baseline 디렉토리 구조 생성
    word_dir = tmp_path / "00.WordBase"
    code_dir = tmp_path / "01.CodeBase"
    word_dir.mkdir(); code_dir.mkdir()
    (word_dir / "a.xml").write_text('<DiffPackage><PackageName>P</PackageName><DiffItems/></DiffPackage>', encoding="utf-8")
    (code_dir / "a.xml").write_text('<DiffPackage><PackageName>P</PackageName><DiffItems/></DiffPackage>', encoding="utf-8")
    # .txt 파일도 생성 — 필터되어야 함
    (word_dir / "b.txt").write_text("should be ignored", encoding="utf-8")
    (code_dir / "b.txt").write_text("should be ignored", encoding="utf-8")

    import app as app_module
    original_data_dir = app_module.DATA_DIR

    baseline_name = tmp_path.name
    parent = str(tmp_path.parent)
    app_module.DATA_DIR = parent
    try:
        result = get_file_list(baseline_name)
        filenames = [f['name'] for f in result['files']]
        assert "a.xml" in filenames
        assert "b.txt" not in filenames
    finally:
        app_module.DATA_DIR = original_data_dir


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

    rows, _, _ = build_diff(str(word_dir), str(code_dir), "t.xml")
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
