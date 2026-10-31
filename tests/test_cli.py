from pathlib import Path

import pytest

from colabkit import (
    AsyncColabCli,
    ColabAuthError,
    ColabCli,
    ColabError,
    ColabMissing,
    ColabNoGpu,
    SessionGone,
    SessionInfo,
    Usage,
)

from .conftest import Fake


def test_new_status_stop(fake: Fake) -> None:
    assert fake.status("a") is False
    fake.new("a", "L4", high_mem=True)
    assert fake.status("a") is True
    assert fake.calls()[1]["argv"] == ["new", "-s", "a", "--gpu", "L4", "--high-mem"]
    assert fake.sessions() == [SessionInfo("a", "gpu-l4-s-a", "L4")]
    fake.stop("a")
    assert fake.status("a") is False


def test_new_refused(fake: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_COLAB_REJECT", "H100")
    with pytest.raises(ColabNoGpu, match="H100") as e:
        fake.new("a", "H100")
    assert e.value.code == "colab_no_gpu"
    assert "rejected accelerator" in (e.value.detail or "")


def test_stop_unknown_session(fake: Fake) -> None:
    with pytest.raises(SessionGone) as e:
        fake.stop("nope")
    assert e.value.session == "nope"
    fake.stop("nope", check=False)


def test_exec_code_goes_on_stdin(fake: Fake) -> None:
    fake.new("a")
    assert "ran: print('hi')" in fake.exec("a", "print('hi')", timeout=30)
    call = fake.calls()[-1]
    assert call["argv"] == ["exec", "-s", "a", "--timeout", "30"]
    assert call["stdin"] == "print('hi')"


def test_exec_file_with_env(fake: Fake, tmp_path: Path) -> None:
    fake.new("a")
    script = tmp_path / "s.py"
    script.write_text("x = 1")
    assert "ran: x = 1" in fake.exec("a", file=script, env={"K": "v=1"}, timeout=5)
    argv = fake.calls()[-1]["argv"]
    assert argv == ["exec", "-s", "a", "-f", str(script), "--timeout", "5", "--env", "K=v=1"]


def test_exec_needs_code_or_file(fake: Fake) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        fake.exec("a")


def test_exec_on_a_lost_session(fake: Fake) -> None:
    with pytest.raises(SessionGone, match="session a is gone"):
        fake.exec("a", "pass")


def test_upload_download(fake: Fake, tmp_path: Path) -> None:
    fake.new("a")
    fake.upload("a", tmp_path / "x", "/content/x")
    local = tmp_path / "sub" / "y"
    fake.download("a", "/content/y", local)
    assert local.read_text() == "data"


def test_usage(fake: Fake) -> None:
    fake.new("a")
    assert fake.usage() == Usage(balance=198.67, rate_per_hour=1.5, assignments=1)


def test_auth_broken(fake: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_COLAB_AUTH_BROKEN", "1")
    for args in [("usage",), ("status", "a"), ("new", "a", "T4")]:
        with pytest.raises(ColabAuthError) as e:
            getattr(fake, args[0])(*args[1:])
        assert e.value.code == "colab_auth"


def test_unknown_failure(fake: Fake) -> None:
    fake.new("a")
    with pytest.raises(ColabError, match=r"`colab install` failed \(exit 3\)\.\nboom"):
        fake.install("a", Path("r.txt"))


def test_timeout(fake: Fake, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_COLAB_SLOW", "5")
    monkeypatch.setattr("colabkit.cli.EXEC_GRACE_S", 0)
    with pytest.raises(ColabError, match="timed out after 0 s"):
        fake.exec("a", "pass", timeout=0.3)


@pytest.mark.parametrize("cls", [ColabCli, AsyncColabCli])
def test_missing_binary(cls: type[ColabCli | AsyncColabCli], tmp_path: Path) -> None:
    fake = Fake(tmp_path, cls(str(tmp_path / "nope")))
    with pytest.raises(ColabMissing) as e:
        fake.usage()
    assert e.value.code == "colab_missing"


def test_auth_and_proxy_command() -> None:
    cli = ColabCli("colab", auth="adc")
    assert cli.argv("usage") == ["colab", "--auth", "adc", "usage"]
    assert cli.proxy_command("s", "/k") == "colab --auth adc ssh --proxy-mode -s s -i /k"
