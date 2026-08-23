"""PDF annotation utilities.

Provides simple sidecar-based annotation storage and rendering helpers.
"""

import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

import pymupdf as fitz


def _sidecar_path(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(pdf_path.suffix + ".annotations.json")


def _load_sidecar(pdf_path: Path):
    """Load annotations from the sidecar JSON file for ``pdf_path``.

    Returns an empty list when no sidecar exists.
    """
    p = _sidecar_path(pdf_path)
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


def list_annotations(pdf_path: str):
    """Return the list of annotations for ``pdf_path``."""
    p = Path(pdf_path)
    return _load_sidecar(p)


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
