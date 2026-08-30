"""PDF annotation utilities.

Provides simple sidecar-based annotation storage and rendering helpers.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, cast

import pymupdf as fitz


def _sidecar_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(pdf_path.suffix + ".annotations.json")


def _fields_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(pdf_path.suffix + ".fields.json")


def _rejected_fields_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(pdf_path.suffix + ".rejected-fields.json")


def _load_sidecar(pdf_path: Path):
    """Load annotations from the sidecar JSON file for ``pdf_path``.

    Returns an empty list when no sidecar exists.
    """
    p = _sidecar_path(pdf_path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_fields(pdf_path: Path):
    p = _fields_path(pdf_path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_rejected_fields(pdf_path: Path):
    p = _rejected_fields_path(pdf_path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_sidecar(pdf_path: Path, annotations):
    """Atomically save ``annotations`` to the PDF sidecar file."""
    p = _sidecar_path(pdf_path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(annotations, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def _save_fields(pdf_path: Path, fields):
    p = _fields_path(pdf_path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(fields, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def _save_rejected_fields(pdf_path: Path, fields):
    p = _rejected_fields_path(pdf_path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(fields, f, indent=2, ensure_ascii=False)
    tmp.replace(p)


def list_annotations(pdf_path: str):
    """Return the list of annotations for ``pdf_path``."""
    p = Path(pdf_path)
    return _load_sidecar(p)


def list_form_fields(pdf_path: str):
    """Return accepted editable fields for ``pdf_path``."""
    return _load_fields(Path(pdf_path))


def _validate_field(field):
    field_type = field.get("type")
    if field_type not in {"checkbox", "radio", "integer", "text"}:
        raise ValueError("unsupported field type")
    rect = field.get("rect")
    if not isinstance(rect, list) or len(rect) != 4:
        raise ValueError("field rect must contain four values")
    if rect[2] <= rect[0] or rect[3] <= rect[1]:
        raise ValueError("field rect must have positive dimensions")
    if int(field.get("page", 0)) < 1:
        raise ValueError("field page must be positive")


def accept_form_fields(pdf_path: str, candidates):
    """Accept detected field candidates and persist them separately."""
    path = Path(pdf_path)
    fields = _load_fields(path)
    accepted_ids = []
    for candidate in candidates:
        field = dict(candidate)
        field["id"] = str(uuid.uuid4())
        field["rect"] = [float(value) for value in field["rect"]]
        _validate_field(field)
        field["source"] = field.get("source", "detected")
        fields.append(field)
        accepted_ids.append(field["id"])
    _save_fields(path, fields)
    return accepted_ids


def reject_form_fields(pdf_path: str, candidates):
    """Persist detected field regions that should not be offered again."""
    path = Path(pdf_path)
    rejected = _load_rejected_fields(path)
    rejected_ids = []
    existing_regions = {(field["page"], tuple(field["rect"])) for field in rejected}
    for candidate in candidates:
        field = dict(candidate)
        field["id"] = str(uuid.uuid4())
        field["rect"] = [float(value) for value in field["rect"]]
        _validate_field(field)
        region = (field["page"], tuple(field["rect"]))
        if region not in existing_regions:
            rejected.append(
                {"id": field["id"], "page": field["page"], "rect": field["rect"]}
            )
            existing_regions.add(region)
        rejected_ids.append(field["id"])
    _save_rejected_fields(path, rejected)
    return rejected_ids


def update_form_field(pdf_path: str, field_id: str, new_props: dict):
    """Update an accepted field and persist its value or metadata."""
    path = Path(pdf_path)
    fields = _load_fields(path)
    for field in fields:
        if field["id"] != field_id:
            continue
        updated = dict(field)
        updated.update(new_props)
        if updated["type"] == "integer" and updated.get("value") is not None:
            try:
                updated["value"] = int(updated["value"])
            except (TypeError, ValueError) as error:
                raise ValueError("integer field value must be an integer") from error
        elif updated["type"] in {"checkbox", "radio"}:
            updated["value"] = bool(updated.get("value", False))
        _validate_field(updated)
        field.update(updated)
        _save_fields(path, fields)
        return
    raise KeyError("field not found")


_INTEGER_LABELS = {"strength", "dexterity", "damage", "armor", "xp"}


def _rect_as_list(rect):
    return [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]


def _field_type_for_label(label):
    if label and label.strip().lower() in _INTEGER_LABELS:
        return "integer"
    return "text"


def _nearby_label(words, rect):
    candidates = []
    for word in words:
        word_rect = fitz.Rect(word[:4])
        if word_rect.y1 <= rect.y0 and word_rect.x1 >= rect.x0 - 100:
            distance = rect.y0 - word_rect.y1
            candidates.append((distance, word[4]))
    if not candidates:
        return None
    candidates.sort(key=lambda candidate: candidate[0])
    return candidates[0][1]


def _widget_field_type(widget):
    widget_types = {
        getattr(fitz, "PDF_WIDGET_TYPE_CHECKBOX", -1): "checkbox",
        getattr(fitz, "PDF_WIDGET_TYPE_RADIOBUTTON", -1): "radio",
        getattr(fitz, "PDF_WIDGET_TYPE_TEXT", -1): "text",
    }
    return widget_types.get(widget.field_type, "text")


def _drawing_field_type(drawing, rect, label):
    items = drawing.get("items", [])
    if items and all(item[0] == "c" for item in items):
        return "radio"
    if (
        items
        and all(item[0] == "re" for item in items)
        and rect.width <= 30
        and rect.height <= 30
        and abs(rect.width - rect.height) <= 4
    ):
        return "checkbox"
    return _field_type_for_label(label)


def detect_form_fields(pdf_path: str):  # pylint: disable=too-many-locals
    """Detect native widgets and conservative vector form regions.

    Returned rectangles use PDF points and page numbers start at one.
    """
    document = fitz.open(str(Path(pdf_path)))
    fields = []
    rejected_regions = {
        (field["page"], tuple(field["rect"]))
        for field in _load_rejected_fields(Path(pdf_path))
    }
    try:
        for page_number, page_index in enumerate(range(len(document)), start=1):
            page = document[page_index]
            words = page.get_text("words")
            widgets = page.widgets()
            if widgets:
                for widget in widgets:
                    widget = cast(Any, widget)
                    label = widget.field_name or None
                    field_type = _widget_field_type(widget)
                    if field_type == "text":
                        field_type = _field_type_for_label(label)
                    if (
                        page_number,
                        tuple(_rect_as_list(widget.rect)),
                    ) in rejected_regions:
                        continue
                    fields.append(
                        {
                            "id": str(uuid.uuid4()),
                            "page": page_number,
                            "rect": _rect_as_list(widget.rect),
                            "type": field_type,
                            "label": label,
                            "value": widget.field_value,
                            "confidence": 1.0,
                            "source": "widget",
                        }
                    )

            for drawing in page.get_drawings():
                rect = drawing.get("rect")
                if rect is None or drawing.get("fill") is not None:
                    continue
                width = rect.width
                height = rect.height
                if width < 4 or height < 4 or width > 500 or height > 200:
                    continue
                if width / height > 12 or height / width > 12:
                    continue
                label = _nearby_label(words, rect)
                if (page_number, tuple(_rect_as_list(rect))) in rejected_regions:
                    continue
                fields.append(
                    {
                        "id": str(uuid.uuid4()),
                        "page": page_number,
                        "rect": _rect_as_list(rect),
                        "type": _drawing_field_type(drawing, rect, label),
                        "label": label,
                        "value": None,
                        "confidence": 0.8,
                        "source": "detected",
                    }
                )
    finally:
        document.close()
    return fields


def create_annotation(pdf_path: str, annotation: dict):
    """Create an annotation for ``pdf_path`` from an ``annotation`` dict.

    The annotation dict should contain at least: ``page``, ``x``, ``y``, ``text``.
    Optional keys: ``font``, ``size``, ``color``.
    Returns the created annotation id.
    """
    p = Path(pdf_path)
    annotations = _load_sidecar(p)
    ann = {
        "id": str(uuid.uuid4()),
        "page": int(annotation.get("page", 1)),
        "x": float(annotation.get("x", 0)),
        "y": float(annotation.get("y", 0)),
        "text": str(annotation.get("text", "")),
        "font": annotation.get("font", "helv"),
        "size": int(annotation.get("size", 12)),
        "color": list(annotation.get("color", (0, 0, 0))),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "modified_at": None,
    }
    annotations.append(ann)
    _save_sidecar(p, annotations)
    return ann["id"]


def update_annotation(pdf_path: str, annotation_id: str, new_props: dict):
    """Update an existing annotation by ``annotation_id`` with ``new_props``."""
    p = Path(pdf_path)
    annotations = _load_sidecar(p)
    found = False
    for a in annotations:
        if a["id"] == annotation_id:
            a.update(new_props)
            a["modified_at"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            found = True
            break
    if not found:
        raise KeyError("annotation not found")
    _save_sidecar(p, annotations)


def delete_annotation(pdf_path: str, annotation_id: str):
    """Delete the annotation with ``annotation_id`` from the sidecar."""
    p = Path(pdf_path)
    annotations = _load_sidecar(p)
    new = [a for a in annotations if a["id"] != annotation_id]
    if len(new) == len(annotations):
        raise KeyError("annotation not found")
    _save_sidecar(p, new)


def render_overlays(pdf_path: str, out_path: str, flatten: bool = False):
    """Render saved annotations onto the PDF and write to ``out_path``.

    When ``flatten`` is True the text is drawn into the page content; otherwise
    a freetext annotation is added.
    """
    p = Path(pdf_path)
    doc = fitz.open(str(p))
    annotations = _load_sidecar(p)
    # create a mapping by page
    by_page = {}
    for a in annotations:
        by_page.setdefault(int(a["page"]), []).append(a)

    def _draw_annotation(page_obj, ann):
        """Draw a single annotation dict onto ``page_obj``."""
        x = ann["x"]
        y = ann["y"]
        text = ann["text"]
        size = ann.get("size", 12)
        font = ann.get("font", "helv")
        color = ann.get("color", [0, 0, 0])
        w = max(50, int(size * len(text) * 0.6))
        h = int(size * 1.6)
        rect = fitz.Rect(x, y, x + w, y + h)
        if flatten:
            page_obj.insert_textbox(
                rect, text, fontsize=size, fontname=font, color=tuple(color)
            )
        else:
            annot = page_obj.add_freetext_annot(
                rect, text, fontsize=size, fontname=font, text_color=tuple(color)
            )
            try:
                annot.update()
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    for page_index in range(1, len(doc) + 1):
        page = doc.load_page(page_index - 1)
        anns = by_page.get(page_index, [])
        for a in anns:
            _draw_annotation(page, a)

    # save
    doc.save(out_path)
    doc.close()
