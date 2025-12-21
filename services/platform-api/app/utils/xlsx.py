import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass


_NS_WB = {
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wb": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
}
_NS_REL = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


@dataclass(frozen=True)
class SheetRef:
    name: str
    path: str


def _colrow(a1: str) -> tuple[str, int | None]:
    col = "".join([c for c in a1 if c.isalpha()])
    row = "".join([c for c in a1 if c.isdigit()])
    return col, int(row) if row else None


def _a1col_index(col: str) -> int:
    n = 0
    for c in col:
        n = n * 26 + (ord(c.upper()) - ord("A") + 1)
    return n


def list_sheets(xlsx_path: str) -> list[SheetRef]:
    with zipfile.ZipFile(xlsx_path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {rel.attrib["Id"]: "xl/" + rel.attrib["Target"] for rel in rels.findall("pr:Relationship", _NS_REL)}

        sheets: list[SheetRef] = []
        for s in wb.findall("wb:sheets/wb:sheet", _NS_WB):
            name = s.attrib.get("name") or "Sheet"
            rid = s.attrib.get("{%s}id" % _NS_WB["r"])
            target = rid_to_target.get(rid)
            if target:
                sheets.append(SheetRef(name=name, path=target))
        return sheets


def _read_shared_strings(z: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    shared: list[str] = []
    for si in root.findall("wb:si", _NS_WB):
        texts: list[str] = []
        for t in si.findall(".//wb:t", _NS_WB):
            texts.append(t.text or "")
        shared.append("".join(texts))
    return shared


def read_sheet_as_rows(xlsx_path: str, sheet_name: str = "Sheet1", max_rows: int | None = None) -> list[list[str]]:
    """
    Reads an XLSX sheet into a dense 2D array of strings.
    - Cell values are returned as strings (numbers are stringified).
    - Missing cells are returned as empty strings.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        shared = _read_shared_strings(z)
        sheets = list_sheets(xlsx_path)
        sheet = next((s for s in sheets if s.name == sheet_name), None)
        if sheet is None:
            raise ValueError(f"sheet not found: {sheet_name}")

        root = ET.fromstring(z.read(sheet.path))
        cells_by_row: dict[int, dict[int, str]] = defaultdict(dict)

        for c in root.findall(".//wb:sheetData/wb:row/wb:c", _NS_WB):
            r = c.attrib.get("r")
            if not r:
                continue
            col, row = _colrow(r)
            if row is None:
                continue
            if max_rows is not None and row > max_rows:
                continue

            t = c.attrib.get("t")
            v_el = c.find("wb:v", _NS_WB)
            if v_el is None:
                val = ""
            else:
                raw = v_el.text or ""
                if t == "s":
                    try:
                        val = shared[int(raw)]
                    except Exception:
                        val = raw
                else:
                    val = raw
            cells_by_row[row][_a1col_index(col)] = val

        if not cells_by_row:
            return []

        max_r = max(cells_by_row.keys())
        if max_rows is not None:
            max_r = min(max_r, max_rows)
        max_c = max((max(cols.keys()) for cols in cells_by_row.values()), default=0)

        rows: list[list[str]] = []
        for r in range(1, max_r + 1):
            cols = cells_by_row.get(r, {})
            if not cols:
                rows.append([])
                continue
            rows.append([cols.get(c, "") for c in range(1, max_c + 1)])
        return rows


