# XML 데이터 포맷 & Edit 기능 추가 설계

**날짜**: 2026-04-29  
**이슈**: #10 — 데이터 포맷 및 기능 추가  
**방식**: 방식 A (백엔드 XML 파싱 + 프론트엔드 편집 상태 관리)

---

## 1. 배경 및 목표

- 기존 `.txt` 파일 포맷을 `.xml` 포맷으로 **완전 교체**
- `00.WordBase` / `01.CodeBase` 디렉토리 내 파일이 모두 XML로 변경됨
- 기존 diff 비교 로직은 그대로 유지하면서 XML을 텍스트로 변환하여 활용
- `01.CodeBase` 쪽의 diff 라인에 **Edit/Skip** 기능 추가
- 모든 diff 라인 처리 완료 시 서버로 JSON 전송

---

## 2. XML 데이터 구조

```xml
<DiffPackage>
  <PackageName>패키지명</PackageName>
  <DiffItems>
    <DiffItem>
      <SubTitle>소제목</SubTitle>
      <Items>
        <Item>
          <ID>아이템ID</ID>
          <Value>텍스트값</Value>
          <LineNumber>5</LineNumber>
          <EditType>None</EditType>
        </Item>
        ...
      </Items>
    </DiffItem>
    ...
  </DiffItems>
</DiffPackage>
```

- `EditType`은 XML 데이터가 가진 고유 필드이며, 사용자가 제어하는 값이 아님
- 모든 `Item`의 `Value`가 변환 대상 (EditType 무관)

---

## 3. 백엔드 설계 (app.py)

### 3-1. 파일 감지

- `get_file_list()`, `file_has_diff()`: `.txt` → `.xml` 확장자로 변경
- XML 파일 여부는 확장자로 판별

### 3-2. XML 파싱 함수 (`parse_xml_file`)

XML을 파싱하여 두 가지 결과물 반환:

**① 텍스트 라인 리스트** (기존 diff 엔진 입력용)

```
######### {PackageName} ##########

{Item.Value}
{Item.Value}
...
```

- PackageName 헤더 행 다음에 모든 Item의 Value를 순서대로 나열
- 기존 `read_file()` 역할을 대체

**② 메타데이터 맵**

```python
{
  라인인덱스(int): {
    "item_id": str,
    "value": str,
    "line_number": int,
    "edit_type": str,
    "sub_title": str,
    "package_name": str,
  }
}
```

- 텍스트 라인 인덱스 기준으로 Item 메타데이터를 조회할 수 있는 딕셔너리
- 헤더 행(PackageName 행)은 메타데이터 없음

### 3-3. diff 행(row) 확장

- `build_diff()` 로직 변경 없음 — 텍스트 라인만 받으므로 기존 그대로 동작
- `make_row()` 에서 XML 파일일 경우 `meta_b` 필드 추가:
  - `replace` / `insert` 타입 행에만 포함
  - `meta_b`: 해당 행의 01.CodeBase Item 메타데이터 딕셔너리
- 템플릿으로 전달 시 각 row에 `meta_b` 포함

---

## 4. 프론트엔드 설계 (diff.html + JS)

### 4-1. Edit/Skip 버튼

- `replace` 타입 행의 `01.CodeBase` 셀에 버튼 두 개 표시:
  - `[Edit]`: 클릭 시 셀 내용이 `<textarea>`로 전환 → 저장 시 "편집됨" 상태
  - `[Skip]`: 클릭 시 즉시 "스킵됨" 상태

### 4-2. 상태 시각화

| 상태 | 표시 |
|------|------|
| 미처리 | 기본 diff 스타일 |
| 편집됨 | 초록 테두리 + ✓ 뱃지 |
| 스킵됨 | 회색 테두리 + ⊘ 뱃지 |

- 두 상태 모두 다시 클릭(또는 버튼 재선택)하면 원래 상태로 되돌리기 가능

### 4-3. 진행 카운터 & 전송 버튼

- 헤더 영역에 `"3 / 7 처리됨"` 형태 카운터 표시
- 모든 diff 행이 편집됨 또는 스킵됨 상태가 되면 **"서버로 전송"** 버튼 활성화
- 버튼 활성화 전에는 비활성화(disabled) 처리

### 4-4. 상태 관리 (JS)

```javascript
// Map<rowIndex, { action: "edited"|"skipped", value: string }>
const editState = new Map();
```

- 페이지 새로고침 시 초기화 (의도된 트레이드오프)

### 4-5. 전송 데이터 (JSON)

변경된(다른) 라인만 전송:

```json
[
  {
    "package_name": "패키지명",
    "sub_title": "소제목",
    "item": {
      "id": "아이템ID",
      "value": "수정된값 또는 원래값",
      "line_number": 5,
      "edit_type": "None"
    },
    "user_action": "edited"
  },
  {
    "package_name": "패키지명",
    "sub_title": "소제목",
    "item": {
      "id": "아이템ID",
      "value": "원래값",
      "line_number": 8,
      "edit_type": "None"
    },
    "user_action": "skipped"
  }
]
```

- `edited` 행: `item.value`는 사용자가 수정한 값
- `skipped` 행: `item.value`는 원래 XML의 Value
- 전송 서버 URL은 추후 기입

---

## 5. 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `app.py` | XML 파싱 함수 추가, 파일 확장자 처리, row에 meta_b 추가 |
| `templates/diff.html` | Edit/Skip 버튼, 상태 뱃지, 진행 카운터, 전송 버튼 |
| `static/style.css` | 편집됨/스킵됨 상태 스타일 추가 |

---

## 6. 제약사항 및 트레이드오프

- 페이지 새로고침 시 편집 상태 초기화 (세션 저장 미구현)
- 서버 전송 URL은 추후 별도 설정
- `.txt` 파일 지원 완전 제거 (하위 호환 없음)
