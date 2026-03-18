"""LLM context management using lisette + optional dialoghelper."""
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
# Used as fallback when dialoghelper is not installed.
_context: list[dict] = []

# msg_type values for dialoghelper: 'code', 'note', 'prompt'
_ROLE_TO_MSGTYPE = {"user": "note", "assistant": "note", "code": "code", "prompt": "prompt"}


async def add_to_context(role: str, content: str):
    """Add a message to the LLM conversation context."""
    if HAS_DIALOGHELPER:
        msg_type = _ROLE_TO_MSGTYPE.get(role, "note")
        await add_msg(content, msg_type=msg_type)
    else:
        _context.append({"role": role, "content": content})


async def update_context(msg_id: str, content: str):
    if HAS_DIALOGHELPER:
        await update_msg(id=msg_id, content=content)
    else:
        # fallback: no-op (no stable id in plain list)
        pass


async def delete_from_context(msg_id: str):
    if HAS_DIALOGHELPER:
        await del_msg(id=msg_id)
    else:
        pass


def get_context() -> list[dict]:
    return list(_context)


async def stream_prompt(prompt: str) -> AsyncIterator[str]:
    """Stream a Claude response for a prompt cell. Yields text chunks."""
    if not HAS_LISETTE:
        yield "[lisette not installed — run: pip install lisette]\n"
        return

    try:
        res = await _chat(prompt, stream=True)
        full = ""
        async for chunk in res:
            text = chunk if isinstance(chunk, str) else getattr(chunk, "text", "")
            full += text
            yield text
        # Persist to context after completion
        _context.append({"role": "user", "content": prompt})
        _context.append({"role": "assistant", "content": full})
    except Exception as e:
        yield f"\n[Error: {e}]\n"
