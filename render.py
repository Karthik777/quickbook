"""Render Jupyter output dicts and inline variables as FastHTML elements."""
import base64
from fasthtml.common import *


def render_output(out: dict) -> FT:
    """Convert one Jupyter output dict to a FastHTML element."""
    ot = out.get("output_type", "")

    if ot == "stream":
        text = out.get("text", "")
        if isinstance(text, list):
            text = "".join(text)
        cls = "output-stderr" if out.get("name") == "stderr" else "output-stdout"
        return Pre(text, cls=f"output-stream {cls}")

    if ot in ("execute_result", "display_data"):
        data = out.get("data", {})
        # Prefer rich formats first
        if "text/html" in data:
            html = data["text/html"]
            if isinstance(html, list):
                html = "".join(html)
            return Div(NotStr(html), cls="output-html")
        if "image/png" in data:
            img_b64 = data["image/png"]
            if isinstance(img_b64, list):
                img_b64 = "".join(img_b64)
            return Img(src=f"data:image/png;base64,{img_b64}", cls="output-image")
        if "image/jpeg" in data:
            img_b64 = data["image/jpeg"]
            if isinstance(img_b64, list):
                img_b64 = "".join(img_b64)
            return Img(src=f"data:image/jpeg;base64,{img_b64}", cls="output-image")
        if "text/plain" in data:
            text = data["text/plain"]
            if isinstance(text, list):
                text = "".join(text)
            return Pre(text, cls="output-plain")
        return Div()

    if ot == "error":
        ename = out.get("ename", "Error")
        evalue = out.get("evalue", "")
        tb = out.get("traceback", [])
        # Strip ANSI color codes for now
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_tb = "\n".join(ansi_escape.sub("", line) for line in tb)
        return Div(
            Strong(f"{ename}: {evalue}", cls="error-header"),
            Pre(clean_tb, cls="error-traceback"),
            cls="output-error"
        )

    return Div()


def render_outputs(outputs: list) -> FT:
    return Div(*[render_output(o) for o in outputs], cls="cell-outputs")


def _var_preview(v) -> str:
    try:
        r = repr(v)
        return r[:100] + ("…" if len(r) > 100 else "")
    except Exception:
        return "<error>"


def _var_detail(v) -> FT:
    """Rich representation for var inspector modal."""
    try:
        # pandas DataFrame
        import pandas as pd
        if isinstance(v, pd.DataFrame):
            return NotStr(v.to_html(max_rows=20, classes="df-table"))
    except ImportError:
        pass
    try:
        import numpy as np
        if isinstance(v, np.ndarray):
            return Pre(f"shape={v.shape} dtype={v.dtype}\n{repr(v)}")
    except ImportError:
        pass
    return Pre(repr(v), cls="var-full-repr")


def render_vars(new_vars: dict, changed_vars: dict) -> FT:
    """Inline var view — Details/Summary dropdowns at end of cell output."""
    items = []
    for k, v in {**new_vars, **changed_vars}.items():
        prefix = "★ " if k in new_vars else "↻ "
        preview = _var_preview(v)
        type_name = type(v).__name__
        items.append(
            Details(
                Summary(
                    Span(f"{prefix}{k}", cls="var-name"),
                    Span(f"  {type_name}  ", cls="var-type"),
                    Span(preview, cls="var-preview"),
                    A("⬡", hx_get=f"/inspect/{k}", hx_target="#modal",
                      hx_swap="innerHTML", cls="inspect-link", title="Inspect"),
                ),
                # Lazy-load detail on first open; cached in DOM after that
                hx_get=f"/inspect/{k}",
                hx_target="#modal",
                hx_swap="innerHTML",
                hx_trigger="toggle once",
                cls="var-item"
            )
        )
    if not items:
        return Div()
    return Div(*items, cls="inline-vars")


def var_modal(name: str, val) -> FT:
    """Full variable inspector modal."""
    return Div(
        Div(
            Div(
                H3(name, cls="modal-title"),
                Span(f"({type(val).__name__})", cls="modal-type"),
                Button("×", onclick="document.getElementById('modal').innerHTML=''",
                       cls="modal-close"),
                cls="modal-header"
            ),
            Div(_var_detail(val), cls="modal-body"),
            cls="modal-content"
        ),
        cls="modal-overlay",
        onclick="if(event.target===this)this.parentElement.innerHTML=''"
    )
