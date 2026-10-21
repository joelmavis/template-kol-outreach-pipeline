#!/usr/bin/env python3
"""Read the first table from a local CSV or XLSX file using the standard library."""
from __future__ import annotations

import csv
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile


def _unique_headers(values, path):
    headers = [str(value or "").strip() for value in values]
    if not headers or not any(headers) or len(headers) != len(set(headers)):
        raise ValueError(f"{path}: missing or duplicate table headers")
    return headers


def read_csv_table(path):
    path = Path(path)
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with path.open(encoding=encoding, newline="") as stream:
                reader = csv.reader(stream)
                values = list(reader)
            break
        except UnicodeDecodeError as error:
            last_error = error
    else:
        raise ValueError(f"{path}: unsupported CSV encoding") from last_error
    if not values:
        raise ValueError(f"{path}: empty table")
    headers = _unique_headers(values[0], path)
    rows = []
    for row_number, values_row in enumerate(values[1:], 2):
        if not any(str(value).strip() for value in values_row):
            continue
        if len(values_row) > len(headers):
            raise ValueError(f"{path}: row {row_number} has more cells than the header")
        values_row += [""] * (len(headers) - len(values_row))
        rows.append({header: str(value).strip() for header, value in zip(headers, values_row)})
    return headers, rows


def _column_index(reference):
    letters = re.match(r"[A-Z]+", reference or "")
    if not letters:
        return 0
    value = 0
    for char in letters.group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def read_xlsx_table(path):
    path = Path(path)
    with ZipFile(path) as archive:
        namespaces = {
            "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
            "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
        }
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("main:si", namespaces):
                shared.append("".join(node.text or "" for node in item.iterfind(".//main:t", namespaces)))
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = workbook.find(".//main:sheets/main:sheet", namespaces)
        if sheet is None:
            raise ValueError(f"{path}: workbook has no worksheet")
        relation_id = sheet.attrib.get(f"{{{namespaces['rel']}}}id")
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = None
        for relation in relations:
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            raise ValueError(f"{path}: cannot locate first worksheet")
        worksheet_path = target.lstrip("/")
        if not worksheet_path.startswith("xl/"):
            worksheet_path = "xl/" + worksheet_path
        worksheet = ET.fromstring(archive.read(worksheet_path))
        grid = []
        for row in worksheet.findall(".//main:sheetData/main:row", namespaces):
            values = []
            for cell in row.findall("main:c", namespaces):
                index = _column_index(cell.attrib.get("r", ""))
                while len(values) <= index:
                    values.append("")
                cell_type = cell.attrib.get("t")
                if cell_type == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iterfind(".//main:t", namespaces))
                else:
                    node = cell.find("main:v", namespaces)
                    value = node.text if node is not None and node.text is not None else ""
                    if cell_type == "s" and value:
                        value = shared[int(value)]
                values[index] = str(value).strip()
            if any(values):
                grid.append(values)
    if not grid:
        raise ValueError(f"{path}: empty worksheet")
    headers = _unique_headers(grid[0], path)
    rows = []
    for row_number, values in enumerate(grid[1:], 2):
        if len(values) > len(headers) and any(values[len(headers):]):
            raise ValueError(f"{path}: row {row_number} has more cells than the header")
        values = values[:len(headers)] + [""] * max(0, len(headers) - len(values))
        rows.append({header: value for header, value in zip(headers, values)})
    return headers, rows


def read_local_table(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return read_csv_table(path)
    if path.suffix.lower() == ".xlsx":
        return read_xlsx_table(path)
    raise ValueError(f"{path}: expected a CSV or XLSX file")
