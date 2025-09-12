import statistics
from typing import Any, Dict, List, Optional


def _safe_bbox(item: Dict[str, Any]) -> Optional[Dict[str, float]]:
    geom = item.get("Geometry") or {}
    bbox = geom.get("BoundingBox") or {}
    top = bbox.get("Top")
    left = bbox.get("Left")
    width = bbox.get("Width")
    height = bbox.get("Height")
    if top is None or left is None or width is None or height is None:
        poly = geom.get("Polygon") or []
        if len(poly) == 4:
            xs = [p.get("X") for p in poly if p and "X" in p]
            ys = [p.get("Y") for p in poly if p and "Y" in p]
            if xs and ys and None not in xs and None not in ys:
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)
                left, top, width, height = (
                    min_x,
                    min_y,
                    max(1e-9, max_x - min_x),
                    max(1e-9, max_y - min_y),
                )
    if top is None:
        return None
    return {
        "top": float(top),
        "left": float(left),
        "width": float(width),
        "height": float(height),
        "bottom": float(top) + float(height),
        "center_y": float(top) + float(height) / 2.0,
        "right": float(left) + float(width),
    }


def _median(values: List[float], default: float) -> float:
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return default
    try:
        return statistics.median(vals)
    except:
        return default


def _extract_lines(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    for item in raw:
        if item.get("BlockType") != "LINE" or not item.get("Text"):
            continue
        bbox = _safe_bbox(item)
        if bbox:
            lines.append(
                {
                    "text": item["Text"].strip(),
                    **bbox,
                    "page": item.get("Page", 1),
                    "confidence": item.get("Confidence"),
                }
            )
    lines.sort(
        key=lambda line: (int(line.get("page", 1)), line["center_y"], line["left"])
    )
    return lines


def _rows_from_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not lines:
        return []
    lines = sorted(lines, key=lambda l: l["center_y"])
    median_height = _median([line["height"] for line in lines], default=0.012)
    y_tol = max(0.003, median_height * 0.5)
    rows: List[Dict[str, Any]] = []
    current_row_items: List[Dict[str, Any]] = []
    current_row_center: Optional[float] = None
    for ln in lines:
        if current_row_center is None:
            current_row_center = ln["center_y"]
            current_row_items = [ln]
            continue
        if abs(ln["center_y"] - current_row_center) <= y_tol:
            current_row_items.append(ln)
            current_row_center = sum(
                item["center_y"] for item in current_row_items
            ) / len(current_row_items)
        else:
            current_row_items.sort(key=lambda line: line["left"])
            row_text = " · ".join([line["text"] for line in current_row_items])
            row_top = min(line["top"] for line in current_row_items)
            row_bottom = max(line["bottom"] for line in current_row_items)
            rows.append(
                {
                    "text": row_text,
                    "left": min(l["left"] for l in current_row_items),
                    "top": row_top,
                    "bottom": row_bottom,
                    "height": row_bottom - row_top,
                    "center_y": (row_top + row_bottom) / 2.0,
                }
            )
            current_row_center, current_row_items = ln["center_y"], [ln]
    if current_row_items:
        current_row_items.sort(key=lambda line: line["left"])
        row_text = " · ".join([line["text"] for line in current_row_items])
        row_top = min(line["top"] for line in current_row_items)
        row_bottom = max(line["bottom"] for line in current_row_items)
        rows.append(
            {
                "text": row_text,
                "left": min(l["left"] for l in current_row_items),
                "top": row_top,
                "bottom": row_bottom,
                "height": row_bottom - row_top,
                "center_y": (row_top + row_bottom) / 2.0,
            }
        )
    rows.sort(key=lambda r: (r["center_y"], r["left"]))
    return rows


def _is_heading(row: Dict[str, Any], median_row_height: float) -> bool:
    txt = (row.get("text") or "").strip()
    if not txt:
        return False
    letters = [c for c in txt if c.isalpha()]
    if (
        letters
        and sum(1 for c in letters if c.isupper()) / len(letters) >= 0.7
        and 3 <= len(txt) <= 64
    ):
        return True
    heading_keywords = {
        "education",
        "skills",
        "projects",
        "experience",
        "work experience",
        "certifications",
        "summary",
        "objective",
        "profile",
        "contact",
    }
    if txt.lower() in heading_keywords:
        return True
    return False


def _group_rows(rows: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    if not rows:
        return {}
    median_row_height = _median([r["height"] for r in rows], default=0.012)
    groups: Dict[int, List[str]] = {}
    gidx = 0
    for i, cur in enumerate(rows):
        if _is_heading(cur, median_row_height) or gidx == 0:
            gidx += 1
            groups[gidx] = [cur["text"]]
        else:
            groups[gidx].append(cur["text"])
    return groups


def grouping(rawJsonData: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    lines = _extract_lines(rawJsonData)
    if not lines:
        return {}
    page_buckets: Dict[int, List[Dict[str, Any]]] = {}
    for ln in lines:
        page_buckets.setdefault(int(ln.get("page", 1)), []).append(ln)
    merged_groups: Dict[int, List[str]] = {}
    gidx = 1
    for page in sorted(page_buckets.keys()):
        rows = _rows_from_lines(page_buckets[page])
        page_groups = _group_rows(rows)
        for _, texts in sorted(page_groups.items(), key=lambda kv: int(kv[0])):
            merged_groups[gidx] = texts
            gidx += 1
    return {str(k): v for k, v in merged_groups.items()}
