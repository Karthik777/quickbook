"""quickbook — FastHTML async Jupyter notebook with inline vars, terminal, and LLM context."""
import asyncio
import json
import os
from pathlib import Path
from fasthtml.common import *

from notebook import get_or_create, list_notebooks, Cell
from kernel import run_cell, get_var, get_completions, restart_kernel
from render import render_outputs, render_vars, var_modal
from terminal import get_pty
from dialog import stream_prompt, add_to_context, get_context

# ---------------------------------------------------------------------------
# Styles & scripts (CDN)
# ---------------------------------------------------------------------------

_css = Style("""
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0d1117; color: #e6edf3; margin: 0; }
#app { display: flex; flex-direction: column; height: 100vh; }

/* Toolbar */
#toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 16px;
           background: #161b22; border-bottom: 1px solid #30363d; flex-shrink: 0; }
#toolbar h1 { font-size: 1rem; margin: 0; color: #58a6ff; font-weight: 600; }
.tb-sep { flex: 1; }
.tb-btn { background: #21262d; border: 1px solid #30363d; color: #e6edf3;
          padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: .85rem; }
.tb-btn:hover { background: #30363d; }
.tb-btn.danger { color: #f85149; }

/* Main layout */
#main { display: flex; flex: 1; overflow: hidden; }
#cells-panel { flex: 1; overflow-y: auto; padding: 16px; }
#terminal-panel { width: 45%; border-left: 1px solid #30363d; background: #0d1117;
                  display: none; flex-direction: column; }
#terminal-panel.open { display: flex; }
#terminal-header { padding: 6px 12px; background: #161b22; border-bottom: 1px solid #30363d;
                   display: flex; justify-content: space-between; align-items: center;
                   font-size: .8rem; color: #8b949e; }
#term-container { flex: 1; padding: 4px; }

/* Cells */
.cell { border: 1px solid #30363d; border-radius: 8px; margin-bottom: 12px;
        background: #161b22; transition: border-color .15s; }
.cell:focus-within { border-color: #388bfd; }
.cell.running { border-color: #d29922; }

.cell-header { display: flex; align-items: center; gap: 6px; padding: 6px 10px;
               border-bottom: 1px solid #21262d; }
.cell-type-badge { font-size: .7rem; padding: 2px 6px; border-radius: 4px;
                   background: #21262d; color: #8b949e; text-transform: uppercase; }
.cell-type-badge.code { color: #79c0ff; }
.cell-type-badge.markdown { color: #a371f7; }
.cell-type-badge.shell { color: #56d364; }
.cell-type-badge.prompt { color: #f0883e; }
.run-btn { background: #238636; border: none; color: #fff; padding: 3px 10px;
           border-radius: 5px; cursor: pointer; font-size: .8rem; }
.run-btn:hover { background: #2ea043; }
.run-btn:disabled { background: #21262d; color: #484f58; cursor: not-allowed; }
.cell-actions { margin-left: auto; display: flex; gap: 4px; }
.cell-act-btn { background: none; border: none; color: #8b949e; cursor: pointer;
                font-size: .85rem; padding: 2px 5px; border-radius: 4px; }
.cell-act-btn:hover { color: #e6edf3; background: #21262d; }

/* CodeMirror host */
.cm-host { min-height: 48px; }
.cm-editor { background: #0d1117 !important; }
.cm-editor.cm-focused { outline: none !important; }
.cm-content { font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: .9rem; }

/* Fallback textarea (when CM not loaded) */
.cell-source { width: 100%; min-height: 60px; background: #0d1117; color: #e6edf3;
               border: none; padding: 10px; font-family: monospace; font-size: .9rem;
               resize: vertical; outline: none; }

/* Outputs */
.cell-outputs { padding: 8px 12px; border-top: 1px solid #21262d; }
.output-stream { margin: 2px 0; white-space: pre-wrap; font-size: .85rem;
                 font-family: monospace; padding: 4px 8px; border-radius: 4px; }
.output-stdout { background: #0d1117; color: #c9d1d9; }
.output-stderr { background: #160d0d; color: #ffa198; }
.output-plain  { background: #0d1117; color: #c9d1d9; white-space: pre-wrap;
                 font-size: .85rem; font-family: monospace; padding: 4px 8px; }
.output-error  { background: #160d0d; padding: 8px; border-radius: 4px; }
.error-header  { color: #ffa198; display: block; margin-bottom: 4px; }
.error-traceback { color: #c9d1d9; font-size: .8rem; font-family: monospace;
                   white-space: pre-wrap; margin: 0; }
.output-html   { overflow-x: auto; }
.output-image  { max-width: 100%; }

/* Inline vars */
.inline-vars { padding: 4px 12px 6px; border-top: 1px dashed #21262d; }
.var-item summary { cursor: pointer; padding: 2px 4px; border-radius: 4px;
                    list-style: none; display: flex; align-items: baseline; gap: 6px; }
.var-item summary:hover { background: #21262d; }
.var-name    { color: #79c0ff; font-family: monospace; font-size: .85rem; font-weight: 600; }
.var-type    { color: #8b949e; font-size: .75rem; }
.var-preview { color: #c9d1d9; font-family: monospace; font-size: .8rem;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 40vw; }
.inspect-link { color: #388bfd; font-size: .75rem; text-decoration: none; margin-left: auto;
                cursor: pointer; }
.inspect-link:hover { text-decoration: underline; }
.var-item > pre { margin: 4px 0 4px 16px; font-size: .8rem; color: #c9d1d9;
                  background: #0d1117; padding: 6px; border-radius: 4px;
                  white-space: pre-wrap; max-height: 200px; overflow-y: auto; }

/* Running spinner */
.htmx-indicator { display: none; }
.htmx-request .htmx-indicator { display: inline; }
.spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid #d29922;
           border-top-color: transparent; border-radius: 50%;
           animation: spin .6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Modal */
#modal { position: fixed; inset: 0; z-index: 1000; }
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7);
                 display: flex; align-items: center; justify-content: center; }
.modal-content { background: #161b22; border: 1px solid #30363d; border-radius: 10px;
                 min-width: 400px; max-width: 80vw; max-height: 80vh;
                 display: flex; flex-direction: column; }
.modal-header  { display: flex; align-items: center; gap: 8px; padding: 12px 16px;
                 border-bottom: 1px solid #30363d; }
.modal-title   { margin: 0; font-size: 1rem; color: #79c0ff; font-family: monospace; }
.modal-type    { color: #8b949e; font-size: .8rem; }
.modal-close   { margin-left: auto; background: none; border: none; color: #8b949e;
                 cursor: pointer; font-size: 1.2rem; padding: 0 4px; }
.modal-close:hover { color: #e6edf3; }
.modal-body    { padding: 16px; overflow: auto; flex: 1; font-family: monospace;
                 font-size: .85rem; }
.df-table      { border-collapse: collapse; font-size: .8rem; }
.df-table th, .df-table td { border: 1px solid #30363d; padding: 4px 8px; }
.df-table th   { background: #21262d; }

/* Add cell bar */
.add-cell-bar  { display: flex; gap: 8px; margin-bottom: 16px; }
.add-cell-btn  { background: #21262d; border: 1px dashed #30363d; color: #8b949e;
                 padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: .85rem; }
.add-cell-btn:hover { border-color: #58a6ff; color: #58a6ff; }

/* Context panel */
#context-panel { padding: 8px 16px; background: #0d1117; border-top: 1px solid #30363d;
                 max-height: 200px; overflow-y: auto; display: none; }
#context-panel.open { display: block; }
.ctx-msg  { padding: 4px 8px; margin: 2px 0; border-radius: 4px;
            font-size: .8rem; font-family: monospace; }
.ctx-user { background: #122d4b; color: #79c0ff; }
.ctx-assistant { background: #1c2a1c; color: #56d364; }

/* Streaming prompt output */
.prompt-stream { white-space: pre-wrap; font-family: monospace; font-size: .85rem;
                 color: #c9d1d9; padding: 8px; }
""")

# CodeMirror 6 + xterm.js via ESM CDN
_editor_script = Script("""
import {EditorView, basicSetup} from 'https://esm.sh/codemirror@6.0.1';
import {python} from 'https://esm.sh/@codemirror/lang-python@6.1.4';
import {autocompletion} from 'https://esm.sh/@codemirror/autocomplete@6.18.3';
import {keymap} from 'https://esm.sh/@codemirror/view@6.35.3';
import {defaultKeymap} from 'https://esm.sh/@codemirror/commands@6.7.1';

const editors = {};

function kernelComplete(context) {
  let word = context.matchBefore(/[\\w.]+/);
  if (!word || word.from === word.to) return null;
  return fetch('/completions?prefix=' + encodeURIComponent(word.text))
    .then(r => r.json())
    .then(items => ({from: word.from, options: items.map(l => ({label: l, type: 'variable'}))}));
}

function mountEditor(host) {
  if (host.dataset.mounted) return;
  host.dataset.mounted = '1';
  const cellId = host.dataset.cellId;
  const hidden = document.getElementById('src-' + cellId);
  const view = new EditorView({
    doc: hidden ? hidden.value : '',
    extensions: [
      basicSetup,
      python(),
      autocompletion({override: [kernelComplete]}),
      EditorView.updateListener.of(u => {
        if (u.docChanged && hidden) hidden.value = u.state.doc.toString();
      }),
      keymap.of([
        {key: 'Shift-Enter', run: (view) => {
          const cell = host.closest('.cell');
          if (cell) cell.querySelector('.run-btn')?.click();
          return true;
        }},
        ...defaultKeymap
      ]),
      EditorView.theme({'&': {background: '#0d1117'}, '.cm-content': {caretColor: '#e6edf3'}}),
    ],
    parent: host
  });
  editors[cellId] = view;
}

function mountAll() {
  document.querySelectorAll('.cm-host').forEach(mountEditor);
}

mountAll();
document.body.addEventListener('htmx:afterSettle', mountAll);
document.body.addEventListener('htmx:afterSwap', mountAll);

// Expose for terminal
window._editors = editors;
""", type="module")

_xterm_script = Script("""
import {Terminal} from 'https://esm.sh/@xterm/xterm@5.3.0';
import {FitAddon} from 'https://esm.sh/@xterm/addon-fit@0.10.0';
import {AttachAddon} from 'https://esm.sh/@xterm/addon-attach@0.11.0';

let termInstance = null;
let termWs = null;

window.openTerminal = function() {
  const panel = document.getElementById('terminal-panel');
  panel.classList.add('open');
  if (termInstance) { termInstance.focus(); return; }

  const container = document.getElementById('term-container');
  const term = new Terminal({cursorBlink: true, fontSize: 13,
    theme: {background: '#0d1117', foreground: '#c9d1d9', cursor: '#e6edf3'}});
  const fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(container);
  fitAddon.fit();

  const ws = new WebSocket('ws://' + location.host + '/terminal');
  term.loadAddon(new AttachAddon(ws));
  termWs = ws;
  termInstance = term;

  ws.addEventListener('open', () => {
    const dims = {cols: term.cols, rows: term.rows};
    ws.send(JSON.stringify({type: 'resize', ...dims}));
  });
  window.addEventListener('resize', () => fitAddon.fit());
};

window.closeTerminal = function() {
  document.getElementById('terminal-panel').classList.remove('open');
};
""", type="module")

# ---------------------------------------------------------------------------
# FastHTML app
# ---------------------------------------------------------------------------

app, rt = fast_app(
    exts="ws",
    hdrs=(
        _css,
        Link(rel="stylesheet",
             href="https://cdn.jsdelivr.net/npm/@xterm/xterm@5.3.0/css/xterm.css"),
        _editor_script,
        _xterm_script,
    ),
    live=False,
)

NB_DIR = "notebooks"
Path(NB_DIR).mkdir(exist_ok=True)
DEFAULT_NB = f"{NB_DIR}/untitled.ipynb"


# ---------------------------------------------------------------------------
# Cell rendering helpers
# ---------------------------------------------------------------------------

def _cell_type_selector(cell: Cell) -> FT:
    opts = [("code", "Code"), ("markdown", "Markdown"), ("shell", "Shell"), ("prompt", "AI Prompt")]
    return Select(
        *[Option(label, value=v, selected=(v == cell.cell_type)) for v, label in opts],
        hx_post=f"/cell/{cell.id}/type", hx_target=f"#cell-{cell.id}", hx_swap="outerHTML",
        name="cell_type", cls="tb-btn", style="padding:3px 6px; font-size:.8rem;"
    )


def render_cell(cell: Cell, nb_path: str) -> FT:
    is_running = cell.running
    cell_cls = f"cell cell-{cell.cell_type}" + (" running" if is_running else "")

    # Source input — hidden input updated by CodeMirror; visible as fallback
    hidden_src = Input(type="hidden", id=f"src-{cell.id}", name="source", value=cell.source)

    if cell.cell_type == "markdown":
        # Show rendered markdown or editor on click
        import re
        # Simple preview placeholder — real markdown via monsterui/mistletoe
        editor_area = Div(
            Div(id=f"cm-{cell.id}", cls="cm-host", **{"data-cell-id": cell.id}),
            hidden_src
        )
    else:
        editor_area = Div(
            Div(id=f"cm-{cell.id}", cls="cm-host", **{"data-cell-id": cell.id}),
            hidden_src
        )

    run_label = "▶ Run" if not is_running else "⏳"
    run_btn = Button(
        run_label,
        Span(cls="spinner htmx-indicator"),
        cls="run-btn",
        disabled=is_running,
        hx_post=f"/cell/{cell.id}/run",
        hx_include=f"#src-{cell.id}",
        hx_target=f"#out-{cell.id}",
        hx_swap="innerHTML",
        hx_indicator=f"#cell-{cell.id}",
    )

    header = Div(
        Span(cell.cell_type, cls=f"cell-type-badge {cell.cell_type}"),
        run_btn if cell.cell_type != "markdown" else Span(),
        Div(
            Button("↑", cls="cell-act-btn", title="Move up",
                   hx_post=f"/cell/{cell.id}/move/up",
                   hx_target="#cells", hx_swap="innerHTML"),
            Button("↓", cls="cell-act-btn", title="Move down",
                   hx_post=f"/cell/{cell.id}/move/down",
                   hx_target="#cells", hx_swap="innerHTML"),
            Button("→ ctx", cls="cell-act-btn", title="Add output to LLM context",
                   hx_post=f"/cell/{cell.id}/to-context",
                   hx_target="#ctx-status", hx_swap="innerHTML"),
            Button("✕", cls="cell-act-btn", title="Delete cell",
                   hx_delete=f"/cell/{cell.id}",
                   hx_target=f"#cell-{cell.id}", hx_swap="outerHTML",
                   hx_confirm="Delete this cell?"),
            cls="cell-actions"
        ),
        cls="cell-header"
    )

    output_div = Div(
        render_outputs(cell.outputs),
        render_vars(cell.new_vars, cell.changed_vars),
        id=f"out-{cell.id}"
    )

    return Div(header, editor_area, output_div, id=f"cell-{cell.id}", cls=cell_cls)


def render_all_cells(nb) -> FT:
    return Div(*[render_cell(c, nb.path) for c in nb.cells], id="cells")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@rt("/")
def get():
    nb = get_or_create(DEFAULT_NB)
    return full_page(nb)


@rt("/nb/{nb_name}")
def get(nb_name: str):
    path = f"{NB_DIR}/{nb_name}"
    if not path.endswith(".ipynb"):
        path += ".ipynb"
    nb = get_or_create(path)
    return full_page(nb)


def full_page(nb) -> FT:
    toolbar = Div(
        H1("⚡ quickbook"),
        Span(nb.name, style="color:#8b949e; font-size:.85rem;"),
        Div(cls="tb-sep"),
        Button("+ Code",    cls="tb-btn", hx_post="/cell/add",
               hx_vals='{"cell_type":"code"}',    hx_target="#cells", hx_swap="beforeend"),
        Button("+ Markdown", cls="tb-btn", hx_post="/cell/add",
               hx_vals='{"cell_type":"markdown"}', hx_target="#cells", hx_swap="beforeend"),
        Button("+ Shell",   cls="tb-btn", hx_post="/cell/add",
               hx_vals='{"cell_type":"shell"}',   hx_target="#cells", hx_swap="beforeend"),
        Button("+ AI",      cls="tb-btn", hx_post="/cell/add",
               hx_vals='{"cell_type":"prompt"}',  hx_target="#cells", hx_swap="beforeend"),
        Button("⌨ Terminal", cls="tb-btn", onclick="openTerminal()"),
        Button("💾 Save",    cls="tb-btn", hx_post="/save", hx_target="#ctx-status"),
        Button("↺ Restart", cls="tb-btn danger", hx_post="/restart",
               hx_target="#ctx-status", hx_confirm="Restart kernel? All variables will be lost."),
        Span(id="ctx-status", style="font-size:.8rem; color:#8b949e;"),
        id="toolbar"
    )

    cells_panel = Div(
        render_all_cells(nb),
        id="cells-panel"
    )

    terminal_panel = Div(
        Div(
            Span("Terminal"),
            Button("×", onclick="closeTerminal()", cls="cell-act-btn"),
            id="terminal-header"
        ),
        Div(id="term-container"),
        id="terminal-panel"
    )

    return Title("quickbook"), Div(
        toolbar,
        Div(cells_panel, terminal_panel, id="main"),
        Div(id="modal"),
        id="app"
    )


@rt("/cell/add")
async def post(cell_type: str = "code"):
    nb = get_or_create(DEFAULT_NB)
    cell = nb.add_cell(cell_type=cell_type)
    return render_cell(cell, nb.path)


@rt("/cell/{cell_id}/run")
async def post(cell_id: str, source: str = ""):
    nb = get_or_create(DEFAULT_NB)
    cell = nb.get_cell(cell_id)
    if not cell:
        return Div("Cell not found", id=f"out-{cell_id}")

    cell.source = source
    cell.running = True

    if cell.cell_type == "prompt":
        # Stream AI response
        outputs = []
        full_text = ""
        async for chunk in stream_prompt(source):
            full_text += chunk
        outputs = [{"output_type": "stream", "name": "stdout", "text": full_text}]
        cell.outputs = outputs
        cell.new_vars = {}
        cell.changed_vars = {}
    else:
        result = await run_cell(source)
        cell.outputs = result["outputs"]
        cell.new_vars = result["new_vars"]
        cell.changed_vars = result["changed_vars"]

    cell.running = False

    return Div(
        render_outputs(cell.outputs),
        render_vars(cell.new_vars, cell.changed_vars),
        id=f"out-{cell_id}"
    )


@rt("/cell/{cell_id}/type")
async def post(cell_id: str, cell_type: str = "code"):
    nb = get_or_create(DEFAULT_NB)
    cell = nb.get_cell(cell_id)
    if not cell:
        return Div(id=f"cell-{cell_id}")
    cell.cell_type = cell_type
    return render_cell(cell, nb.path)


@rt("/cell/{cell_id}/move/{direction}")
async def post(cell_id: str, direction: str):
    nb = get_or_create(DEFAULT_NB)
    nb.move_cell(cell_id, direction)
    return render_all_cells(nb)


@rt("/cell/{cell_id}")
async def delete(cell_id: str):
    nb = get_or_create(DEFAULT_NB)
    nb.delete_cell(cell_id)
    return ""  # HTMX outerHTML swap removes the div


@rt("/cell/{cell_id}/to-context")
async def post(cell_id: str):
    nb = get_or_create(DEFAULT_NB)
    cell = nb.get_cell(cell_id)
    if not cell:
        return "Not found"
    content = "\n".join(
        o.get("data", {}).get("text/plain", o.get("text", ""))
        for o in cell.outputs if isinstance(o, dict)
    )
    await add_to_context("user", f"```\n{cell.source}\n```\nOutput:\n{content}")
    return "✓ Added to context"


@rt("/inspect/{var_name}")
def get(var_name: str):
    val = get_var(var_name)
    if val is None:
        return Div(f"Variable '{var_name}' not found", cls="modal-overlay",
                   onclick="document.getElementById('modal').innerHTML=''")
    return var_modal(var_name, val)


@rt("/completions")
def get(prefix: str = ""):
    return Response(
        content=json.dumps(get_completions(prefix)),
        media_type="application/json"
    )


@rt("/save")
async def post():
    nb = get_or_create(DEFAULT_NB)
    nb.save()
    return "✓ Saved"


@rt("/restart")
async def post():
    restart_kernel()
    nb = get_or_create(DEFAULT_NB)
    for cell in nb.cells:
        cell.outputs = []
        cell.new_vars = {}
        cell.changed_vars = {}
    return "↺ Kernel restarted"


# ---------------------------------------------------------------------------
# WebSocket terminal
# ---------------------------------------------------------------------------

async def _on_term_connect(send):
    """Subscribe this WS client to the shared PTY session on connect."""
    pty = await get_pty()
    pty.subscribe(send)
    # Nudge bash to emit its prompt
    await pty.write(b"\n")


async def _on_term_disconnect(ws):
    """Unsubscribe on disconnect (PTY session stays alive)."""
    pty = await get_pty()
    # find and remove the send callable bound to this ws
    # FastHTML passes the ws object; we stored send in subscribe — unsubscribe all
    # dead callables next time _on_readable fires (they'll raise & be removed)
    pass  # subscribers auto-clean on send failure in _on_readable


@app.ws("/terminal", conn=_on_term_connect, disconn=_on_term_disconnect)
async def ws_terminal(msg: str, send):
    """Route keystrokes and resize events from xterm.js to the PTY."""
    pty = await get_pty()
    if msg and msg[0] == "{":
        try:
            data = json.loads(msg)
            if data.get("type") == "resize":
                pty.resize(data.get("rows", 24), data.get("cols", 80))
            return
        except (json.JSONDecodeError, KeyError):
            pass
    await pty.write(msg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5001, reload=False)
