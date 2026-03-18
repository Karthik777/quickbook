"""CaptureShell singleton + async run_cell() with variable inspection."""
import asyncio
from typing import Any

try:
    from execnb.shell import CaptureShell
    _shell = CaptureShell()
    HAS_SHELL = True
except ImportError:
    _shell = None
    HAS_SHELL = False

# Lock so only one cell runs at a time in the simple path
_lock = asyncio.Lock()


def _snapshot_ns() -> dict[str, int]:
    """Return {name: id(value)} for all non-private vars."""
    if not HAS_SHELL:
        return {}
    return {k: id(v) for k, v in _shell.user_ns.items() if not k.startswith("_")}


def _diff_ns(before: dict[str, int]) -> tuple[dict, dict]:
    """Return (new_vars, changed_vars) after execution."""
    if not HAS_SHELL:
        return {}, {}
    new_vars, changed_vars = {}, {}
    for k, v in _shell.user_ns.items():
        if k.startswith("_"):
            continue
        if k not in before:
            new_vars[k] = v
        elif id(v) != before[k]:
            changed_vars[k] = v
    return new_vars, changed_vars


async def run_cell(code: str) -> dict:
    """Execute code in CaptureShell; return outputs + var diffs."""
    if not HAS_SHELL:
        return {
            "outputs": [{"output_type": "stream", "name": "stderr",
                         "text": "execnb not installed. Run: pip install execnb\n"}],
            "new_vars": {}, "changed_vars": {}
        }

    async with _lock:
        before = _snapshot_ns()
        result = await asyncio.to_thread(_shell.run, code)
        new_vars, changed_vars = _diff_ns(before)

    outputs = _result_to_outputs(result)
    return {"outputs": outputs, "new_vars": new_vars, "changed_vars": changed_vars}


def _result_to_outputs(result) -> list:
    """Convert execnb result AttrDict to list of Jupyter output dicts."""
    outputs = []

    # stdout / stderr streams
    if result.stdout:
        outputs.append({"output_type": "stream", "name": "stdout",
                         "text": result.stdout})
    if result.stderr:
        outputs.append({"output_type": "stream", "name": "stderr",
                         "text": result.stderr})

    # display objects (images, HTML, DataFrames, etc.)
    for obj in (result.display_objects or []):
        if hasattr(obj, "data"):
            outputs.append({"output_type": "display_data", "data": obj.data,
                             "metadata": getattr(obj, "metadata", {})})

    # execute_result (last expression value)
    if result.result is not None and not result.quiet:
        exec_res = result.result
        if hasattr(exec_res, "data"):
            outputs.append({"output_type": "execute_result",
                             "data": exec_res.data,
                             "metadata": getattr(exec_res, "metadata", {}),
                             "execution_count": None})
        else:
            # Fallback: plain repr
            outputs.append({"output_type": "execute_result",
                             "data": {"text/plain": repr(exec_res)},
                             "metadata": {}, "execution_count": None})

    # exception
    if result.exc is not None:
        exc = result.exc
        import traceback
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        outputs.append({
            "output_type": "error",
            "ename": type(exc).__name__,
            "evalue": str(exc),
            "traceback": tb_lines,
        })

    return outputs


def get_var(name: str) -> Any:
    """Retrieve a variable from the kernel namespace."""
    if not HAS_SHELL:
        return None
    return _shell.user_ns.get(name)


def get_completions(prefix: str) -> list[str]:
    """Return variable/attr names matching prefix from kernel namespace."""
    if not HAS_SHELL:
        return []
    ns = _shell.user_ns
    matches = [k for k in ns if k.startswith(prefix) and not k.startswith("_")]
    # also include builtins
    import builtins
    matches += [k for k in dir(builtins) if k.startswith(prefix) and k not in matches]
    return sorted(matches)[:40]


def restart_kernel():
    """Reset the shell namespace."""
    global _shell
    if HAS_SHELL:
        _shell = CaptureShell()
