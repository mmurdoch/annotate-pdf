# PDF Annotation Toolkit

Minimal toolkit to add, edit, and remove text annotations on existing PDFs using PyMuPDF.

Install:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Quick CLI example:

```bash
python src/cli.py add "Playbook - The Ranger.pdf" --page 1 --x 100 --y 100 --text "Hello"
python src/cli.py export "Playbook - The Ranger.pdf" out/annotated.pdf
```

Start web UI:

```bash
python src/web_ui.py
# open http://127.0.0.1:5000
```
