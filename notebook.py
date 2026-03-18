"""In-memory notebook state + execnb nbio persistence."""
import uuid
from dataclasses import dataclass, field
from pathlib import Path

try:
    from execnb.nbio import read_nb, write_nb, mk_cell, new_nb, dict2nb, nb2dict
    HAS_EXECNB = True
except ImportError:
    HAS_EXECNB = False


@dataclass
class Cell:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    cell_type: str = "code"   # "code" | "markdown" | "shell" | "prompt"
    source: str = ""
    outputs: list = field(default_factory=list)
    running: bool = False
    new_vars: dict = field(default_factory=dict)
    changed_vars: dict = field(default_factory=dict)


@dataclass
class Notebook:
    path: str
    name: str = ""
    cells: list = field(default_factory=list)

    def __post_init__(self):
        if not self.name:
            self.name = Path(self.path).stem

    def add_cell(self, cell_type="code", source="", after_id=None) -> Cell:
        cell = Cell(cell_type=cell_type, source=source)
        if after_id:
            idx = next((i for i, c in enumerate(self.cells) if c.id == after_id), None)
            if idx is not None:
                self.cells.insert(idx + 1, cell)
                return cell
        self.cells.append(cell)
        return cell

    def get_cell(self, cell_id: str) -> Cell | None:
        return next((c for c in self.cells if c.id == cell_id), None)

    def delete_cell(self, cell_id: str):
        self.cells = [c for c in self.cells if c.id != cell_id]

    def move_cell(self, cell_id: str, direction: str):
        idx = next((i for i, c in enumerate(self.cells) if c.id == cell_id), None)
        if idx is None:
            return
        if direction == "up" and idx > 0:
            self.cells[idx], self.cells[idx - 1] = self.cells[idx - 1], self.cells[idx]
        elif direction == "down" and idx < len(self.cells) - 1:
            self.cells[idx], self.cells[idx + 1] = self.cells[idx + 1], self.cells[idx]

    def save(self):
        if not HAS_EXECNB:
            return
        nb_cells = []
        for c in self.cells:
            ct = "code" if c.cell_type in ("code", "shell", "prompt") else "markdown"
            nb_cells.append(mk_cell(c.source, ct))
            # store outputs back into nbformat cell
            if c.outputs:
                nb_cells[-1]["outputs"] = c.outputs
        nb = new_nb(nb_cells)
        write_nb(nb, self.path)

    def load(self):
        if not HAS_EXECNB or not Path(self.path).exists():
            return
        nb = read_nb(self.path)
        self.cells = []
        for nc in nb.cells:
            ct = nc.get("cell_type", "code")
            src = nc.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            outs = list(nc.get("outputs", []))
            cell = Cell(cell_type=ct, source=src, outputs=outs)
            self.cells.append(cell)


# Global notebook store: path -> Notebook
_notebooks: dict[str, Notebook] = {}


def get_or_create(path: str) -> Notebook:
    if path not in _notebooks:
        nb = Notebook(path=path)
        nb.load()
        if not nb.cells:
            nb.add_cell("code", "# Welcome to quickbook\nprint('Hello!')")
        _notebooks[path] = nb
    return _notebooks[path]


def list_notebooks(nb_dir: str = "notebooks") -> list[str]:
    p = Path(nb_dir)
    p.mkdir(exist_ok=True)
    return sorted(str(f) for f in p.glob("*.ipynb"))
