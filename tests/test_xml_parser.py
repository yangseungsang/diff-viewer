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
