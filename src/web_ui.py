"""Simple web UI for viewing and editing PDF annotations."""

import base64
from pathlib import Path

import pymupdf as fitz
from flask import Flask, jsonify, request, render_template_string

try:
    from src.pdf_utils import (
        list_annotations,
        create_annotation,
        update_annotation,
        delete_annotation,
    )
except ModuleNotFoundError:
    from pdf_utils import (
        list_annotations,
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
      const viewer = document.getElementById('viewer');
      viewer.innerHTML = '';
      data.pages.forEach((p)=>{
        const div = document.createElement('div'); div.className='page';
        const img = document.createElement('img'); img.src = p.data; img.dataset.pageIndex = p.index;
        img.style.maxWidth = '600px';
        img.addEventListener('click', async (ev)=>{
          const rect = ev.target.getBoundingClientRect();
          const x = Math.round(ev.clientX - rect.left);
          const y = Math.round(ev.clientY - rect.top);
          const text = prompt('Annotation text:');
          if(!text) return;
          await fetch('/annotations/add', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
              pdf: pdf,
              page: p.index,
              x: x,
              y: y,
              text: text
            })
          });
          load(pdf);
        });
        div.appendChild(img);
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
    for i in range(len(doc)):
        img = _render_page_image(p, i)
        b64 = "data:image/png;base64," + base64.b64encode(img).decode("ascii")
        pages_list.append({"data": b64, "index": i + 1})
    doc.close()
    anns = list_annotations(str(p))
    by_page = {}
    for a in anns:
        by_page.setdefault(int(a["page"]), []).append(a)
    return jsonify({"pages": pages_list, "annotations": by_page})


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
