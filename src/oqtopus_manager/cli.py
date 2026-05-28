"""Wrapper for invoking the oqtopus CLI as a subprocess."""

import asyncio
import pathlib
from collections.abc import AsyncGenerator


async def _stream_command(
    argv: list[str],
    cwd: pathlib.Path,
) -> AsyncGenerator[str, None]:
    """Run *argv* in *cwd* and yield SSE-formatted strings."""
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        yield "data: oqtopus command not found. Please install oqtopus-cli first.\n\n"
        yield "event: done\ndata: error\n\n"
        return

    assert process.stdout is not None

    # Feed stdout into a queue from a background task so we can stop reading
    # when the parent process exits, even if a spawned daemon keeps the pipe open.
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def _reader() -> None:
        try:
            async for raw in process.stdout:  # type: ignore[union-attr]
                await queue.put(raw)
        finally:
            await queue.put(None)

    reader_task = asyncio.create_task(_reader())

    while True:
        try:
            raw = await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            if process.returncode is not None:
                reader_task.cancel()
                break
            continue
        if raw is None:
            break
        yield f"data: {raw.decode(errors='replace').rstrip()}\n\n"

    await process.wait()
    if process.returncode == 0:
        yield "event: done\ndata: success\n\n"
    else:
        yield "event: done\ndata: error\n\n"


async def stream_oqtopus_init(
    name: str, template: str, cwd: pathlib.Path
) -> AsyncGenerator[str, None]:
    """Run ``oqtopus init <name> --template <template>`` in *cwd*."""
    async for chunk in _stream_command(
        ["oqtopus", "init", name, "--template", template], cwd
    ):
        yield chunk


async def stream_log_tail(
    log_path: pathlib.Path, tail_lines: int
) -> AsyncGenerator[str, None]:
    """Stream *log_path* via ``tail -f -n tail_lines``, yielding SSE data lines."""
    try:
        process = await asyncio.create_subprocess_exec(
            "tail", "-f", "-n", str(tail_lines), str(log_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        yield "data: 'tail' command not found.\n\n"
        return

    assert process.stdout is not None
    try:
        async for raw in process.stdout:
            yield f"data: {raw.decode(errors='replace').rstrip()}\n\n"
    finally:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        await process.wait()


async def stream_oqtopus_backend(
    args: list[str], cwd: pathlib.Path
) -> AsyncGenerator[str, None]:
    """Run ``oqtopus backend <args>`` in *cwd*."""
    async for chunk in _stream_command(["oqtopus", "backend", *args], cwd):
        yield chunk
