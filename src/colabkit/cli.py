"""Sync and async clients for the `colab` CLI.

Exit codes are unreliable (`exec` exits 0 when the code raises; `status` and `stop` exit 0 for
an unknown session), so results are judged from the output text. Each command is built once
(`_Commands`) and run by either client, which differ only in how they start the process.
"""

import asyncio
import logging
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from colabkit.errors import ColabAuthError, ColabError, ColabMissing, ColabNoGpu
from colabkit.parse import (
    SessionInfo,
    Usage,
    classify,
    is_auth_failure,
    parse_sessions,
    parse_usage,
    strip_ansi,
    tail,
)

log = logging.getLogger("colabkit")

EXEC_GRACE_S = 60  # how long the CLI may take beyond the code's own timeout


@dataclass(frozen=True)
class _Call[T]:
    args: tuple[str, ...]
    timeout: float
    interpret: Callable[[str], T]
    stdin: str | None = None
    check: bool = True  # a non-zero exit raises


def _text(out: str) -> str:
    return out


def _ignore(_out: str) -> None:
    return None


class _Commands:
    def __init__(self, binary: str = "colab", auth: str | None = None):
        self.binary = binary
        self.auth = auth

    def argv(self, *args: str) -> list[str]:
        return [self.binary, *(["--auth", self.auth] if self.auth else []), *args]

    def proxy_command(self, session: str, identity: str) -> str:
        """The `ssh -o ProxyCommand=` that reaches `session`'s VM (see `colabkit.ssh`)."""
        return " ".join(self.argv("ssh", "--proxy-mode", "-s", session, "-i", identity))

    def _finish[T](self, call: _Call[T], argv: list[str], code: int, raw: bytes, t0: float) -> T:
        out = strip_ansi(raw.decode(errors="replace"))
        log.debug(
            "colab %s", {"argv": argv, "exit": code, "duration_s": round(time.monotonic() - t0, 2)}
        )
        if call.check and code != 0:
            raise classify(call.args, out, code)
        return call.interpret(out)

    def _timed_out(self, call: _Call[object]) -> ColabError:
        log.warning("colab %s", {"argv": self.argv(*call.args), "timeout_s": call.timeout})
        return ColabError(f"`colab {call.args[0]}` timed out after {call.timeout:.0f} s.")

    # Commands --------------------------------------------------------------------------------

    def _usage(self) -> _Call[Usage]:
        return _Call(("usage",), 60, parse_usage)

    def _sessions(self) -> _Call[list[SessionInfo]]:
        return _Call(("sessions",), 60, parse_sessions)

    def _status(self, session: str) -> _Call[bool]:
        def alive(out: str) -> bool:
            if is_auth_failure(out) and "not found" not in out:
                raise ColabAuthError(tail(out))
            return any(s.name == session for s in parse_sessions(out))

        # `status` syncs with the backend first, so it prunes sessions whose VM was reclaimed.
        return _Call(("status", "-s", session), 60, alive, check=False)

    def _new(self, session: str, gpu: str | None, high_mem: bool) -> _Call[str | None]:
        """Interprets to None when the session is ready, else the output to judge it by."""
        args = ["new", "-s", session]
        if gpu:
            args += ["--gpu", gpu]
        if high_mem:
            args.append("--high-mem")
        return _Call(tuple(args), 600, lambda out: None if "Session READY" in out else out,
                     check=False)  # fmt: skip

    def _new_failed(self, gpu: str | None, out: str) -> ColabError:
        if is_auth_failure(out):
            return ColabAuthError(tail(out))
        return ColabNoGpu(gpu, tail(out))

    def _stop(self, session: str, check: bool) -> _Call[None]:
        return _Call(("stop", "-s", session), 180, _ignore, check=check)

    def _exec(
        self,
        session: str,
        code: str | None,
        file: Path | None,
        env: Mapping[str, str] | None,
        timeout: float,
    ) -> _Call[str]:
        if (code is None) == (file is None):
            raise ValueError("exec takes exactly one of `code` and `file`")
        args = ["exec", "-s", session]
        if file is not None:
            args += ["-f", str(file)]
        args += ["--timeout", f"{timeout:g}"]
        for k, v in (env or {}).items():
            args += ["--env", f"{k}={v}"]
        return _Call(tuple(args), timeout + EXEC_GRACE_S, _text, stdin=code)

    def _install(self, session: str, requirements: Path) -> _Call[str]:
        return _Call(("install", "-s", session, "-r", str(requirements)), 1200, _text)

    def _upload(self, session: str, local: Path, remote: str, timeout: float) -> _Call[None]:
        def uploaded(out: str) -> None:
            if "Uploaded" not in out:
                raise ColabError("Upload to Colab failed.", detail=tail(out))

        return _Call(("upload", "-s", session, str(local), remote), timeout, uploaded)

    def _download(self, session: str, remote: str, local: Path, timeout: float) -> _Call[None]:
        def downloaded(out: str) -> None:
            if "Downloaded" not in out or not local.exists():
                raise ColabError("Download from Colab failed.", detail=tail(out))

        local.parent.mkdir(parents=True, exist_ok=True)
        return _Call(("download", "-s", session, remote, str(local)), timeout, downloaded)

    def _save_log(self, session: str, out: Path) -> _Call[None]:
        out.parent.mkdir(parents=True, exist_ok=True)
        return _Call(("log", "-s", session, "-o", str(out)), 120, _ignore, check=False)


class ColabCli(_Commands):
    """Blocking client; the session is named on each call."""

    def _run[T](self, call: _Call[T]) -> T:
        argv = self.argv(*call.args)
        t0 = time.monotonic()
        try:
            p = subprocess.run(
                argv,
                input=call.stdin.encode() if call.stdin is not None else None,
                stdin=subprocess.DEVNULL if call.stdin is None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=call.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise self._timed_out(call) from e
        except FileNotFoundError as e:
            raise ColabMissing(str(e)) from e
        return self._finish(call, argv, p.returncode, p.stdout, t0)

    def usage(self) -> Usage:
        return self._run(self._usage())

    def sessions(self) -> list[SessionInfo]:
        return self._run(self._sessions())

    def status(self, session: str) -> bool:
        """True while the backend still has the session's VM."""
        return self._run(self._status(session))

    def new(self, session: str, gpu: str | None = None, high_mem: bool = False) -> None:
        out = self._run(self._new(session, gpu, high_mem))
        if out is not None and not self.status(session):
            raise self._new_failed(gpu, out)

    def stop(self, session: str, check: bool = True) -> None:
        self._run(self._stop(session, check))

    def exec(
        self,
        session: str,
        code: str | None = None,
        *,
        file: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 120,
    ) -> str:
        """Run `code` (sent on stdin) or `file` in the session's kernel; returns its output."""
        return self._run(self._exec(session, code, file, env, timeout))

    def install(self, session: str, requirements: Path) -> str:
        return self._run(self._install(session, requirements))

    def upload(self, session: str, local: Path, remote: str, timeout: float = 3600) -> None:
        self._run(self._upload(session, local, remote, timeout))

    def download(self, session: str, remote: str, local: Path, timeout: float = 1800) -> None:
        self._run(self._download(session, remote, local, timeout))

    def save_log(self, session: str, out: Path) -> None:
        self._run(self._save_log(session, out))


class AsyncColabCli(_Commands):
    """asyncio client; the session is named on each call."""

    async def _run[T](self, call: _Call[T]) -> T:
        argv = self.argv(*call.args)
        t0 = time.monotonic()
        stdin = asyncio.subprocess.DEVNULL if call.stdin is None else asyncio.subprocess.PIPE
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdin=stdin, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
        except FileNotFoundError as e:
            raise ColabMissing(str(e)) from e
        try:
            async with asyncio.timeout(call.timeout):
                out, _ = await proc.communicate(
                    call.stdin.encode() if call.stdin is not None else None
                )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise self._timed_out(call) from None
        assert proc.returncode is not None
        return self._finish(call, argv, proc.returncode, out, t0)

    async def usage(self) -> Usage:
        return await self._run(self._usage())

    async def sessions(self) -> list[SessionInfo]:
        return await self._run(self._sessions())

    async def status(self, session: str) -> bool:
        """True while the backend still has the session's VM."""
        return await self._run(self._status(session))

    async def new(self, session: str, gpu: str | None = None, high_mem: bool = False) -> None:
        out = await self._run(self._new(session, gpu, high_mem))
        if out is not None and not await self.status(session):
            raise self._new_failed(gpu, out)

    async def stop(self, session: str, check: bool = True) -> None:
        await self._run(self._stop(session, check))

    async def exec(
        self,
        session: str,
        code: str | None = None,
        *,
        file: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 120,
    ) -> str:
        """Run `code` (sent on stdin) or `file` in the session's kernel; returns its output."""
        return await self._run(self._exec(session, code, file, env, timeout))

    async def install(self, session: str, requirements: Path) -> str:
        return await self._run(self._install(session, requirements))

    async def upload(self, session: str, local: Path, remote: str, timeout: float = 3600) -> None:
        await self._run(self._upload(session, local, remote, timeout))

    async def download(self, session: str, remote: str, local: Path, timeout: float = 1800) -> None:
        await self._run(self._download(session, remote, local, timeout))

    async def save_log(self, session: str, out: Path) -> None:
        await self._run(self._save_log(session, out))
