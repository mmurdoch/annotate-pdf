"""Small example showing how to create and render an annotation."""

from pathlib import Path
from src.pdf_utils import create_annotation, render_overlays

PDF = Path("Playbook - The Ranger.pdf")


def main():
    """Create one annotation and write an annotated PDF to ``out/annotated.pdf``."""
    if not PDF.exists():
        print(
            "Place 'Playbook - The Ranger.pdf' in the workspace root to run this example."
        )
        return
    aid = create_annotation(
        str(PDF),
        {"page": 1, "x": 100, "y": 100, "text": "Example annotation", "size": 14},
    )
    print("created", aid)
    out = Path("out")
    out.mkdir(exist_ok=True)
    render_overlays(str(PDF), str(out / "annotated.pdf"), flatten=False)
    print("wrote", out / "annotated.pdf")


if __name__ == "__main__":
    main()
