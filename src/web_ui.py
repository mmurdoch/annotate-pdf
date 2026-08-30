"""Simple web UI for viewing and editing PDF annotations."""

import base64
from pathlib import Path

import pymupdf as fitz
from flask import Flask, jsonify, request, render_template_string

try:
    from src.pdf_utils import (
        list_annotations,
        list_form_fields,
        detect_form_fields,
        accept_form_fields,
        reject_form_fields,
        update_form_field,
        create_annotation,
        update_annotation,
        delete_annotation,
    )
except ModuleNotFoundError:
    from pdf_utils import (
        list_annotations,
        list_form_fields,
        detect_form_fields,
        accept_form_fields,
        reject_form_fields,
        update_form_field,
        create_annotation,
        update_annotation,
        delete_annotation,
    )

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>PDF Annotations</title>
    <style>
      img { max-width: 100%; height: auto; display: block; }
      .page { position: relative; display: inline-block; margin: 8px; }
      .ann {
        position: absolute;
        background: rgba(255,255,0,0.6);
        padding: 2px 4px;
        border: 1px solid #ccc;
        cursor: pointer;
      }
      .field-control {
        position: absolute;
        box-sizing: border-box;
        border: 1px solid #1976d2;
        background: rgba(255,255,255,0.85);
        color: #111;
        margin: 0;
      }
      .field-control[type="checkbox"], .field-control[type="radio"] {
        accent-color: #1976d2;
      }
      .field-candidate {
        position: absolute;
        box-sizing: border-box;
        border: 2px dashed #d97706;
        background: rgba(255, 237, 213, 0.45);
        z-index: 1;
        cursor: pointer;
        margin: 0;
        display: flex;
        flex-direction: row;
        align-items: flex-start;
      }
      .field-candidate:hover,
      .field-candidate:focus-within {
        z-index: 3;
      }
      .field-candidate button {
        margin: 2px;
        cursor: pointer;
        visibility: hidden;
      }
      .field-candidate:hover button,
      .field-candidate-actions:hover button,
      .field-candidate:focus-within button {
        visibility: visible;
      }
      .field-candidate-actions {
        position: relative;
        z-index: 2;
        display: flex;
        flex-direction: row;
        padding: 5px;
        margin: -5px;
      }
    </style>
  </head>
  <body>
    <h1>PDF Annotations</h1>
    <form id="open">
      <input name="pdf" placeholder="PDF file path" value="Playbook - The Ranger.pdf" size="60" />
      <button>Open</button>
    </form>
    <div id="viewer"></div>
    <script>
    async function load(pdf){
      const res = await fetch('/pages?pdf='+encodeURIComponent(pdf));
      const data = await res.json();
      const fieldsRes = await fetch('/fields/detect?pdf='+encodeURIComponent(pdf));
      const fieldsData = await fieldsRes.json();
      const viewer = document.getElementById('viewer');
      viewer.innerHTML = '';
      data.pages.forEach((p)=>{
        const div = document.createElement('div'); div.className='page';
        const img = document.createElement('img'); img.src = p.data; img.dataset.pageIndex = p.index;
        img.style.maxWidth = '600px';
        const syncPageSize = ()=>{
          div.style.width = img.clientWidth + 'px';
          div.style.height = img.clientHeight + 'px';
        };
        img.addEventListener('load', syncPageSize, {once: true});
        div.appendChild(img);
        if (img.complete) syncPageSize();
        const addFieldOverlay = (field, candidate)=>{
          const control = document.createElement(candidate ? 'div' : 'input');
          control.className = candidate ? 'field-candidate' : 'field-control';
          if (candidate) {
            const actions = document.createElement('div');
            actions.className = 'field-candidate-actions';
            control.appendChild(actions);
            const action = (text, endpoint)=>{
              const button = document.createElement('button');
              button.type = 'button';
              button.textContent = text;
              button.addEventListener('click', async (ev)=>{
                ev.stopPropagation();
                await fetch(endpoint, {
                  method: 'POST',
                  headers: {'Content-Type':'application/json'},
                  body: JSON.stringify({pdf: pdf, fields: [field]})
                });
                load(pdf);
              });
              actions.appendChild(button);
            };
            action('Accept', '/fields/accept');
            action('Reject', '/fields/reject');
            control.title = 'Review detected field';
          }
          if (!candidate) {
            control.type = field.type === 'checkbox' ? 'checkbox' :
              (field.type === 'radio' ? 'radio' : (field.type === 'integer' ? 'number' : 'text'));
          }
          const rect = field.rect;
          const render = ()=>{
            const scale = img.clientWidth / p.width;
            const candidateBuffer = 2;
            const buffer = candidate ? candidateBuffer : 0;
            control.style.left = (rect[0] * scale - buffer) + 'px';
            control.style.top = (rect[1] * scale - buffer) + 'px';
            control.style.width = ((rect[2] - rect[0]) * scale + buffer * 2) + 'px';
            control.style.height = ((rect[3] - rect[1]) * scale + buffer * 2) + 'px';
          };
          if (!candidate) {
            if (control.type === 'checkbox' || control.type === 'radio') {
              control.checked = Boolean(field.value);
            } else if (field.value !== null && field.value !== undefined) {
              control.value = field.value;
            }
            control.addEventListener('change', async ()=>{
              const value = control.type === 'checkbox' || control.type === 'radio'
                ? control.checked : control.value;
              await fetch('/fields/edit', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({pdf: pdf, id: field.id, props: {value: value}})
              });
            });
            if (control.type === 'radio') {
              let radioWasChecked = false;
              control.addEventListener('mousedown', ()=>{ radioWasChecked = control.checked; });
              control.addEventListener('click', ()=>{
                if (radioWasChecked) {
                  control.checked = false;
                  control.dispatchEvent(new Event('change'));
                }
              });
            }
          }
          img.addEventListener('load', render, {once: true});
          div.appendChild(control);
          if (img.complete) render();
        };
        fieldsData.accepted.filter((field)=>field.page===p.index).forEach((field)=>addFieldOverlay(field, false));
        fieldsData.fields.filter((field)=>field.page===p.index).forEach((field)=>addFieldOverlay(field, true));
        (data.annotations[p.index]||[]).forEach(a=>{
          const d = document.createElement('div'); d.className='ann'; d.textContent = a.text;
          d.style.left = (a.x)+'px'; d.style.top = (a.y)+'px'; d.dataset.id = a.id;
          d.addEventListener('click', async (ev)=>{
            ev.stopPropagation();
            const newText = prompt('Edit text (Cancel to keep):', a.text);
            if(newText===null) return;
            if(newText===''){
              await fetch('/annotations/delete', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ pdf: pdf, id: a.id })
              });
            } else {
              await fetch('/annotations/edit', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ pdf: pdf, id: a.id, props: { text: newText } })
              });
            }
            load(pdf);
          });
          div.appendChild(d);
        });
        viewer.appendChild(div);
      });
    }
    document.getElementById('open').addEventListener('submit', e=>{e.preventDefault(); load(e.target.pdf.value)});
    window.addEventListener('load', ()=>{ const f=document.getElementById('open'); load(f.pdf.value); });
    </script>
  </body>
</html>
"""


def _render_page_image(pdf_path: Path, page_index: int) -> bytes:
    """Return PNG bytes for ``page_index`` of ``pdf_path``."""
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_index]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        return pix.tobytes("png")
    finally:
        doc.close()


@app.route("/")
def index():
    """Render main viewer template."""
    return render_template_string(TEMPLATE)


@app.route("/pages")
def pages():
    """Return rendered page images and annotations for the requested PDF."""
    pdf = request.args.get("pdf")
    if not pdf:
        return jsonify({"error": "missing pdf"}), 400
    p = Path(pdf)
    if not p.exists():
        return jsonify({"error": "file not found"}), 404
    doc = fitz.open(str(p))
    pages_list = []
    for i in range(len(doc)):  # pylint: disable=consider-using-enumerate
        page = doc[i]
        img = _render_page_image(p, i)
        b64 = "data:image/png;base64," + base64.b64encode(img).decode("ascii")
        pages_list.append(
            {
                "data": b64,
                "index": i + 1,
                "width": page.rect.width,
                "height": page.rect.height,
            }
        )
    doc.close()
    anns = list_annotations(str(p))
    by_page = {}
    for a in anns:
        by_page.setdefault(int(a["page"]), []).append(a)
    return jsonify({"pages": pages_list, "annotations": by_page})


@app.route("/fields/detect")
def detect_fields_route():
    """Return detected candidates and accepted fields for a PDF."""
    pdf = request.args.get("pdf")
    if not pdf:
        return jsonify({"error": "missing pdf"}), 400
    path = Path(pdf)
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    accepted = list_form_fields(str(path))
    candidates = detect_form_fields(str(path))
    accepted_regions = {(field["page"], tuple(field["rect"])) for field in accepted}
    candidates = [
        field
        for field in candidates
        if (field["page"], tuple(field["rect"])) not in accepted_regions
    ]
    return jsonify({"fields": candidates, "accepted": accepted})


@app.route("/fields/accept", methods=["POST"])
def accept_fields_route():
    """Persist reviewed field candidates for a PDF."""
    data = request.get_json() or {}
    pdf = data.get("pdf")
    if not pdf:
        return jsonify({"error": "missing pdf"}), 400
    path = Path(pdf)
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    try:
        ids = accept_form_fields(str(path), data.get("fields", []))
    except (KeyError, TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"ids": ids})


@app.route("/fields/reject", methods=["POST"])
def reject_fields_route():
    """Persist reviewed field candidates that should be ignored."""
    data = request.get_json() or {}
    pdf = data.get("pdf")
    if not pdf:
        return jsonify({"error": "missing pdf"}), 400
    path = Path(pdf)
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    try:
        ids = reject_form_fields(str(path), data.get("fields", []))
    except (KeyError, TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"ids": ids})


@app.route("/fields/edit", methods=["POST"])
def edit_fields_route():
    """Update an accepted field's value or properties."""
    data = request.get_json() or {}
    pdf = data.get("pdf")
    field_id = data.get("id")
    if not pdf or not field_id:
        return jsonify({"error": "missing pdf or field id"}), 400
    path = Path(pdf)
    if not path.exists():
        return jsonify({"error": "file not found"}), 404
    try:
        update_form_field(str(path), field_id, data.get("props", {}))
    except (KeyError, TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"ok": True})


@app.route("/annotations/add", methods=["POST"])
def add_annotation():
    """Create an annotation from posted JSON and return its id."""
    data = request.get_json()
    pdf = data.get("pdf")
    page = int(data.get("page", 1))
    x = float(data.get("x", 0))
    y = float(data.get("y", 0))
    text = data.get("text", "")
    size = int(data.get("size", 12))
    aid = create_annotation(
        str(pdf), {"page": page, "x": x, "y": y, "text": text, "size": size}
    )
    return jsonify({"id": aid})


@app.route("/annotations/edit", methods=["POST"])
def edit_annotation_route():
    """Edit an existing annotation's properties via POSTed JSON."""
    data = request.get_json()
    pdf = data.get("pdf")
    aid = data.get("id")
    props = data.get("props", {})
    update_annotation(str(pdf), aid, props)
    return jsonify({"ok": True})


@app.route("/annotations/delete", methods=["POST"])
def delete_annotation_route():
    """Delete an annotation specified in the POSTed JSON payload."""
    data = request.get_json()
    pdf = data.get("pdf")
    aid = data.get("id")
    delete_annotation(str(pdf), aid)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True)
