# colabkit

Typed sync and async clients for Google's [`colab` CLI](https://pypi.org/project/google-colab-cli/)
(0.7.x), plus an SSH tunnel to a session's VM through `colab ssh --proxy-mode`.
Used by [degas](https://github.com/farrellm/degas) and
[FrameHound](https://github.com/farrellm/FrameHound).

The CLI's exit codes are unreliable (`exec` exits 0 when the code raises; `status` and `stop`
exit 0 for an unknown session), so results are judged from its output, and failures become
`ColabError`s with a stable `code`:

| Error            | `code`          | When                                       |
| ---------------- | --------------- | ------------------------------------------ |
| `ColabError`     | `colab_error`   | anything else (the output is in `detail`)  |
| `ColabAuthError` | `colab_auth`    | the CLI's sign-in has expired              |
| `SessionGone`    | `colab_lost`    | the session's VM was reclaimed or unknown  |
| `ColabMissing`   | `colab_missing` | the `colab` binary isn't installed         |
| `ColabNoGpu`     | `colab_no_gpu`  | `new` couldn't get the requested GPU       |

```python
from colabkit import AsyncColabCli, ColabCli, SshTunnel

cli = ColabCli()  # or ColabCli("colab", auth="adc")
cli.new("job-1", "L4")
print(cli.exec("job-1", "import torch; print(torch.cuda.is_available())", timeout=60))
cli.exec("job-1", file=Path("launch.py"), env={"JOB": "/content/job.json"})
cli.stop("job-1")

acli = AsyncColabCli()
tunnel = SshTunnel(
    acli.proxy_command("job-1", "/path/to/key"),
    Path("/path/to/key"),
    remote_port=8000,
    name="job-1",
)
await tunnel.open()  # localhost:tunnel.local_port -> the VM's port 8000
```

Install from a release tarball:

```toml
dependencies = ["colabkit @ https://github.com/farrellm/colabkit/archive/refs/tags/v0.1.0.tar.gz"]
```

Development: `make fmt`, `make check` (ruff, mypy strict, pytest).
