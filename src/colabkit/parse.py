"""Reading the `colab` CLI's output (colab-cli 0.7.x)."""

import re
from dataclasses import dataclass

from colabkit.errors import ColabAuthError, ColabError, SessionGone

# `colab new --gpu X` silently falls back to A100 for an unknown name.
GPUS = ("T4", "L4", "G4", "H100", "A100")

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SESSION_LINE = re.compile(r"^\[([^\]]+)\] (\S+)(?: \| (.*))?$")
_GONE = re.compile(r"Session '[^']*' (not found|appears to be lost)")
_AUTH = re.compile(
    r"\b(401|403)\b|unauthenticated|invalid_grant|reauth|credentials|"
    r"permission denied|refresh token",
    re.IGNORECASE,
)
DETAIL_CHARS = 1500  # the tail of the output kept on an error


@dataclass(frozen=True)
class Usage:
    """The account's compute units (`colab usage`): every VM on it, not just ours."""

    balance: float
    rate_per_hour: float
    assignments: int  # VMs allocated


@dataclass(frozen=True)
class SessionInfo:
    name: str  # "?" for a server-side assignment with no local record
    endpoint: str
    hardware: str | None = None


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def tail(text: str) -> str:
    return text[-DETAIL_CHARS:]


def parse_usage(text: str) -> Usage:
    bal = re.search(r"Current balance:\s*(-?[\d.]+)", text)
    rate = re.search(r"Usage rate:\s*(-?[\d.]+)", text)
    n = re.search(r"Active assignments:\s*(\d+)", text)
    if not bal:
        raise ColabError("Couldn't read the Colab compute-unit balance.", detail=tail(text))
    return Usage(
        float(bal.group(1)), float(rate.group(1)) if rate else 0.0, int(n.group(1)) if n else 0
    )


def parse_sessions(text: str) -> list[SessionInfo]:
    out = []
    for line in text.splitlines():
        m = _SESSION_LINE.match(line.strip())
        if not m or m.group(1) == "colab":
            continue
        hw = re.search(r"Hardware: ([^|]+)", m.group(3) or "")
        out.append(SessionInfo(m.group(1), m.group(2), hw.group(1).strip() if hw else None))
    return out


def marker_line(text: str, marker: str) -> str | None:
    """The rest of the last line starting with `marker` (a script on the VM prints one)."""
    found = None
    for line in strip_ansi(text).splitlines():
        if line.startswith(marker):
            found = line[len(marker) :].strip()
    return found


def is_auth_failure(text: str) -> bool:
    return bool(_AUTH.search(text))


def session_gone(text: str) -> bool:
    return bool(_GONE.search(text))


def classify(args: tuple[str, ...], text: str, exit_code: int | None = None) -> ColabError:
    """The error a failed `colab <args>` call stands for, judged from its output."""
    # Checked first: "appears to be lost (404/401)" is not an auth problem.
    if session_gone(text):
        session = args[args.index("-s") + 1] if "-s" in args else "?"
        return SessionGone(session, tail(text))
    if is_auth_failure(text):
        return ColabAuthError(tail(text))
    code = f" (exit {exit_code})" if exit_code is not None else ""
    return ColabError(f"`colab {args[0]}` failed{code}.", detail=tail(text))
