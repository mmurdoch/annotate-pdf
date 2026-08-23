import subprocess
import sys
from pathlib import Path

from src.pdf_utils import create_annotation, list_annotations, render_overlays


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
