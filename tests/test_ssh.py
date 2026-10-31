from pathlib import Path

from colabkit import SshTunnel


def test_options_name_the_session_and_proxy() -> None:
    t = SshTunnel("colab ssh --proxy-mode -s s -i /k", Path("/k"), 8000, name="s")
    opts = t._opts()
    assert "ProxyCommand=colab ssh --proxy-mode -s s -i /k" in opts
    assert any(o.startswith("ControlPath=") and o.endswith("/s-%C") for o in opts)
    assert "IdentityFile=/k" in opts
