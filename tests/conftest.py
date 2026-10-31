import asyncio
import json
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from colabkit import AsyncColabCli, ColabCli


class Fake:
    """The fake CLI's state, and a uniform blocking face for either client."""

    def __init__(self, root: Path, cli: ColabCli | AsyncColabCli) -> None:
        self.root = root
        self.cli = cli

    def __getattr__(self, name: str) -> Callable[..., Any]:
        method = getattr(self.cli, name)
        if isinstance(self.cli, AsyncColabCli):
            return lambda *a, **kw: asyncio.run(method(*a, **kw))
        return method  # type: ignore[no-any-return]

    def calls(self) -> list[dict[str, Any]]:
        path = self.root / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    root = tmp_path / "colab"
    root.mkdir()
    monkeypatch.setenv("FAKE_COLAB_DIR", str(root))
    script = root / "colab"
    fake = Path(__file__).with_name("fake_colab.py")
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" "$@"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture(params=["sync", "async"])
def fake(request: pytest.FixtureRequest, binary: str) -> Fake:
    cls = ColabCli if request.param == "sync" else AsyncColabCli
    return Fake(Path(binary).parent, cls(binary))
