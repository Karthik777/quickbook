"""LLM context management using lisette + optional dialoghelper."""
import asyncio
from typing import AsyncIterator

try:
    from lisette import AsyncChat
    _chat = AsyncChat("claude-sonnet-4-20250514")
    HAS_LISETTE = True
except ImportError:
    _chat = None
    HAS_LISETTE = False

try:
    from dialoghelper import add_msg, update_msg, del_msg
    HAS_DIALOGHELPER = True
except ImportError:
    HAS_DIALOGHELPER = False

# In-memory conversation context: list of {"role": ..., "content": ...}
_context: list[dict] = []


def add_to_context(role: str, content: str):
    """Add a message to the LLM conversation context."""
    if HAS_DIALOGHELPER:
        add_msg(content, role=role)
    else:
        _context.append({"role": role, "content": content})


def update_context(idx: int, content: str):
    if HAS_DIALOGHELPER:
        update_msg(idx, content)
    else:
        if 0 <= idx < len(_context):
            _context[idx]["content"] = content


def delete_from_context(idx: int):
    if HAS_DIALOGHELPER:
        del_msg(idx)
    else:
        if 0 <= idx < len(_context):
            _context.pop(idx)


def get_context() -> list[dict]:
    return list(_context)


async def stream_prompt(prompt: str) -> AsyncIterator[str]:
    """Stream a Claude response for a prompt cell. Yields text chunks."""
    if not HAS_LISETTE:
        yield "[lisette not installed — run: pip install lisette]\n"
        return

    # Build messages from context + new prompt
    messages = list(_context) + [{"role": "user", "content": prompt}]

    try:
        res = await _chat(prompt, stream=True)
        full = ""
        async for chunk in res:
            text = chunk if isinstance(chunk, str) else getattr(chunk, "text", "")
            full += text
            yield text
        # Add to context after completion
        _context.append({"role": "user", "content": prompt})
        _context.append({"role": "assistant", "content": full})
    except Exception as e:
        yield f"\n[Error: {e}]\n"
