import pytest

from colabkit import ColabError, classify, marker_line, parse_sessions, parse_usage, strip_ansi
from colabkit.errors import ColabAuthError, SessionGone


def test_parse_sessions() -> None:
    out = (
        "[fh-a-0] gpu-t4-s-x | Hardware: T4 | Shape: Standard | Variant: GPU | Status: IDLE\n"
        "  Last Execution: stdin at 2026-10-15 12:00:00\n"
        "[?] gpu-l4-s-y | Hardware: L4 | Shape: Standard | Variant: GPU\n"
    )
    got = parse_sessions(out)
    assert [(s.name, s.hardware) for s in got] == [("fh-a-0", "T4"), ("?", "L4")]
    assert parse_sessions("[colab] No active sessions found on server.") == []


def test_parse_usage() -> None:
    u = parse_usage("Current balance: 255.61 compute units\nUsage rate: 1.76/hr\n"
                    "Active assignments: 1")  # fmt: skip
    assert (u.balance, u.rate_per_hour, u.assignments) == (255.61, 1.76, 1)
    assert parse_usage("Current balance: -0.5 compute units").balance == -0.5
    with pytest.raises(ColabError, match="balance"):
        parse_usage("[colab] A new version is available\n")


def test_marker_line() -> None:
    assert marker_line('noise\n@@poll {"a": 1}\n\x1b[0m@@poll 2\n', "@@poll") == "2"
    assert marker_line("noise", "@@poll") is None


def test_strip_ansi() -> None:
    assert strip_ansi("\x1b[1m[a] x\x1b[0m") == "[a] x"


def test_classify() -> None:
    lost = classify(("exec", "-s", "a"), "Session 'a' appears to be lost (404/401).")
    assert isinstance(lost, SessionGone)
    assert lost.session == "a"
    assert isinstance(classify(("usage",), "401 Client Error"), ColabAuthError)
    other = classify(("install", "-s", "a"), "boom", 3)
    assert (type(other), other.message, other.detail) == (
        ColabError,
        "`colab install` failed (exit 3).",
        "boom",
    )
