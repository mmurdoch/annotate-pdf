import subprocess
import sys
from typing import Any
from pathlib import Path

from src.pdf_utils import (
    accept_form_fields,
    create_annotation,
    detect_form_fields,
    list_annotations,
    list_form_fields,
    render_overlays,
    update_form_field,
)
from src.web_ui import app


def test_build_runs_pyright_with_warnings_as_errors():
    build_script = Path(__file__).parents[1] / "build.ps1"

    script = build_script.read_text(encoding="utf-8")

    assert "python -m pyright --warnings ." in script
    assert "python -m pytest -q -W error" in script


def test_web_ui_can_be_loaded_as_documented_script():
    project_root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import runpy, sys; "
                "sys.path = [p for p in sys.path if p != '']; "
                "sys.path.insert(0, 'src'); "
                "runpy.run_path('src/web_ui.py', run_name='not_main')"
            ),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_detected_field_actions_stack_above_field_overlays():
    from src.web_ui import TEMPLATE

    assert ".field-candidate-actions" in TEMPLATE
    assert "z-index: 2" in TEMPLATE


def test_clicking_page_background_does_not_prompt_for_annotation():
    from src.web_ui import TEMPLATE

    assert "prompt('Annotation text:')" not in TEMPLATE


def test_field_overlays_use_small_candidate_buffer_without_accepted_tooltips():
    from src.web_ui import TEMPLATE

    assert "const candidateBuffer = 2;" in TEMPLATE
    accepted_overlay = TEMPLATE.split("if (!candidate) {", 1)[1].split(
        "if (control.type === 'radio')", 1
    )[0]
    assert "control.title" not in accepted_overlay


def test_create_annotation_persists_annotation(tmp_path):
    pdf_path = tmp_path / "document.pdf"
    pdf_path.touch()

    annotation_id = create_annotation(
        str(pdf_path),
        {"page": 1, "x": 10, "y": 20, "text": "Review this"},
    )

    annotations = list_annotations(str(pdf_path))
    assert annotations[0]["id"] == annotation_id
    assert annotations[0]["text"] == "Review this"


def test_render_overlays_preserves_all_pages(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "document.pdf"
    output_path = tmp_path / "rendered.pdf"
    document = pymupdf.open()
    document.new_page()
    document.new_page()
    document.save(pdf_path)
    document.close()

    create_annotation(
        str(pdf_path), {"page": 2, "x": 10, "y": 20, "text": "Second page"}
    )
    render_overlays(str(pdf_path), str(output_path), flatten=True)

    rendered = pymupdf.open(output_path)
    assert rendered.page_count == 2
    rendered.close()


def test_detect_form_fields_finds_native_widget(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "widget.pdf"
    document = pymupdf.open()
    page = document.new_page(width=400, height=300)
    widget: Any = pymupdf.Widget()
    widget.field_name = "Strength"
    widget.field_type = getattr(pymupdf, "PDF_WIDGET_TYPE_TEXT")
    widget.rect = pymupdf.Rect(100, 80, 160, 105)
    page.add_widget(widget)
    document.save(pdf_path)
    document.close()

    fields = detect_form_fields(str(pdf_path))

    assert len(fields) == 1
    assert fields[0]["type"] == "integer"
    assert fields[0]["label"] == "Strength"
    assert fields[0]["page"] == 1
    assert fields[0]["rect"] == [100.0, 80.0, 160.0, 105.0]
    assert fields[0]["source"] == "widget"


def test_detect_form_fields_finds_bounded_text_region(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "regions.pdf"
    document = pymupdf.open()
    page = document.new_page(width=400, height=300)
    page.insert_text((100, 70), "Damage", fontsize=12)
    page.draw_rect(pymupdf.Rect(100, 80, 170, 110), color=(0, 0, 0), width=1)
    page.draw_rect(
        pymupdf.Rect(220, 80, 225, 85), color=(0, 0, 0), fill=(0, 0, 0), width=1
    )
    document.save(pdf_path)
    document.close()

    fields = detect_form_fields(str(pdf_path))

    assert len(fields) == 1
    assert fields[0]["type"] == "integer"
    assert fields[0]["label"] == "Damage"
    assert fields[0]["source"] == "detected"


def test_detect_form_fields_classifies_square_and_circle_controls(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "controls.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.draw_rect(pymupdf.Rect(30, 30, 48, 48), color=(0, 0, 0), width=1)
    page.draw_circle(pymupdf.Point(90, 39), 9, color=(0, 0, 0), width=1)
    document.save(pdf_path)
    document.close()

    fields = detect_form_fields(str(pdf_path))

    assert [field["type"] for field in fields] == ["checkbox", "radio"]


def test_detect_form_fields_finds_small_square_and_circle_controls(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "small-controls.pdf"
    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    page.draw_rect(pymupdf.Rect(30, 30, 36, 36), color=(0, 0, 0), width=1)
    page.draw_circle(pymupdf.Point(70, 33), 3, color=(0, 0, 0), width=1)
    document.save(pdf_path)
    document.close()

    fields = detect_form_fields(str(pdf_path))

    assert [field["type"] for field in fields] == ["checkbox", "radio"]


def test_detect_form_fields_does_not_classify_diamond_as_checkbox(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "diamond.pdf"
    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    page.draw_polyline(
        [
            pymupdf.Point(50, 30),
            pymupdf.Point(60, 40),
            pymupdf.Point(50, 50),
            pymupdf.Point(40, 40),
            pymupdf.Point(50, 30),
        ],
        color=(0, 0, 0),
        width=1,
    )
    document.save(pdf_path)
    document.close()

    fields = detect_form_fields(str(pdf_path))

    assert len(fields) == 1
    assert fields[0]["type"] == "text"


def test_accept_form_fields_persists_fields_separately(tmp_path):
    pdf_path = tmp_path / "fields.pdf"
    pdf_path.touch()
    candidate = {
        "id": "candidate-1",
        "page": 1,
        "rect": [10, 20, 80, 45],
        "type": "integer",
        "label": "XP",
        "value": None,
        "confidence": 0.8,
        "source": "detected",
    }

    field_id = accept_form_fields(str(pdf_path), [candidate])[0]

    fields = list_form_fields(str(pdf_path))
    assert field_id == fields[0]["id"]
    assert fields[0]["type"] == "integer"
    assert fields[0]["value"] is None
    assert not list_annotations(str(pdf_path))


def test_detect_fields_route_returns_candidates(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "route.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.insert_text((40, 40), "XP", fontsize=12)
    page.draw_rect(pymupdf.Rect(40, 50, 90, 75), color=(0, 0, 0), width=1)
    document.save(pdf_path)
    document.close()

    response = app.test_client().get(
        "/fields/detect", query_string={"pdf": str(pdf_path)}
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["fields"][0]["label"] == "XP"
    assert data["accepted"] == []


def test_accept_fields_route_persists_candidate(tmp_path):
    pdf_path = tmp_path / "accept-route.pdf"
    pdf_path.touch()
    candidate = {
        "page": 1,
        "rect": [10, 20, 80, 45],
        "type": "text",
        "label": "Name",
        "value": None,
        "confidence": 0.8,
        "source": "detected",
    }

    response = app.test_client().post(
        "/fields/accept", json={"pdf": str(pdf_path), "fields": [candidate]}
    )

    assert response.status_code == 200
    assert len(list_form_fields(str(pdf_path))) == 1


def test_update_form_field_persists_value(tmp_path):
    pdf_path = tmp_path / "update-field.pdf"
    pdf_path.touch()
    field_id = accept_form_fields(
        str(pdf_path),
        [
            {
                "page": 1,
                "rect": [10, 20, 80, 45],
                "type": "integer",
                "label": "XP",
                "value": None,
            }
        ],
    )[0]

    update_form_field(str(pdf_path), field_id, {"value": 12})

    assert list_form_fields(str(pdf_path))[0]["value"] == 12


def test_edit_fields_route_persists_value(tmp_path):
    pdf_path = tmp_path / "edit-route.pdf"
    pdf_path.touch()
    field_id = accept_form_fields(
        str(pdf_path),
        [
            {
                "page": 1,
                "rect": [10, 20, 80, 45],
                "type": "checkbox",
                "label": None,
                "value": False,
            }
        ],
    )[0]

    response = app.test_client().post(
        "/fields/edit",
        json={"pdf": str(pdf_path), "id": field_id, "props": {"value": True}},
    )

    assert response.status_code == 200
    assert list_form_fields(str(pdf_path))[0]["value"] is True


def test_web_ui_includes_editable_field_workflow():
    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"/fields/detect" in response.data
    assert b"/fields/edit" in response.data
    assert b"field-control" in response.data


def test_web_ui_positions_fields_relative_to_page_image():
    response = app.test_client().get("/")

    assert b"position: relative;" in response.data
    assert b"div.style.width = img.clientWidth + 'px'" in response.data
    assert b"div.style.height = img.clientHeight + 'px'" in response.data
    assert b"min-width: 12px" not in response.data
    assert b"min-height: 12px" not in response.data
    assert response.data.count(b"margin: 0;") >= 2


def test_detect_fields_route_excludes_accepted_region(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "accepted-region.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.draw_rect(pymupdf.Rect(40, 50, 90, 75), color=(0, 0, 0), width=1)
    document.save(pdf_path)
    document.close()
    candidate = detect_form_fields(str(pdf_path))[0]
    accept_form_fields(str(pdf_path), [candidate])

    response = app.test_client().get(
        "/fields/detect", query_string={"pdf": str(pdf_path)}
    )

    assert response.status_code == 200
    assert response.get_json()["fields"] == []


def test_reject_fields_route_excludes_candidate_and_persists_rejection(tmp_path):
    import pymupdf

    pdf_path = tmp_path / "rejected-region.pdf"
    document = pymupdf.open()
    page = document.new_page(width=300, height=200)
    page.draw_rect(pymupdf.Rect(40, 50, 90, 75), color=(0, 0, 0), width=1)
    document.save(pdf_path)
    document.close()
    candidate = detect_form_fields(str(pdf_path))[0]

    response = app.test_client().post(
        "/fields/reject", json={"pdf": str(pdf_path), "fields": [candidate]}
    )

    assert response.status_code == 200
    assert response.get_json()["ids"]
    assert (
        app.test_client()
        .get("/fields/detect", query_string={"pdf": str(pdf_path)})
        .get_json()["fields"]
        == []
    )


def test_web_ui_supports_deselecting_radio_and_rejecting_candidates():
    response = app.test_client().get("/")

    assert b"radioWasChecked" in response.data
    assert b"/fields/reject" in response.data


def test_web_ui_hides_candidate_actions_until_hover():
    response = app.test_client().get("/")

    assert b".field-candidate button {" in response.data
    assert b"visibility: hidden;" in response.data
    assert b".field-candidate:hover button" in response.data
    assert b"visibility: visible;" in response.data
    assert b"action('Accept', '/fields/accept')" in response.data
    assert b"display: flex;" in response.data
    assert b"flex-direction: row;" in response.data
    assert b"field-candidate-actions" in response.data
    assert b".field-candidate-actions:hover button" in response.data
    assert b"padding: 5px;" in response.data
    assert b"const candidateBuffer = 2" in response.data
