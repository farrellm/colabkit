"""A fake `colab` CLI with colab-cli 0.7.4's messages.

State lives in `$FAKE_COLAB_DIR`: `sessions.json` (name -> GPU) and `calls.jsonl` (each argv,
with the stdin it was given). Knobs (env): `FAKE_COLAB_AUTH_BROKEN` (every call fails with a
401), `FAKE_COLAB_REJECT` (GPUs `new` refuses), `FAKE_COLAB_SLOW` (seconds every call sleeps).
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ["FAKE_COLAB_DIR"])
STATE = ROOT / "sessions.json"


def main(argv: list[str]) -> int:
    stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
    with (ROOT / "calls.jsonl").open("a") as fh:
        fh.write(json.dumps({"argv": argv, "stdin": stdin}) + "\n")
    time.sleep(float(os.environ.get("FAKE_COLAB_SLOW") or 0))
    if argv[:1] == ["--auth"]:
        argv = argv[2:]
    if os.environ.get("FAKE_COLAB_AUTH_BROKEN"):
        print("[colab] Warning: failed to fetch compute-unit info: 401 Client Error: Unauthorized")
        return 1
    sessions: dict[str, str] = json.loads(STATE.read_text()) if STATE.exists() else {}
    cmd, rest = argv[0], argv[1:]
    name = rest[rest.index("-s") + 1] if "-s" in rest else ""
    if cmd == "usage":
        print(
            f"Current balance: 198.67 compute units\nUsage rate: {1.5 * len(sessions):.2f}/hr\n"
            f"Active assignments: {len(sessions)}"
        )
    elif cmd == "sessions":
        if not sessions:
            print("[colab] No active sessions found on server.")
        for n, gpu in sessions.items():
            print(f"[{n}] gpu-{gpu.lower()}-s-{n} | Hardware: {gpu} | Shape: Standard")
    elif cmd == "status":
        if name in sessions:
            print(f"\x1b[1m[{name}] 10.0.0.1 | Hardware: {sessions[name]} | Status: IDLE\x1b[0m")
        else:
            print(f"[colab] Session '{name}' not found.")
    elif cmd == "new":
        gpu = rest[rest.index("--gpu") + 1] if "--gpu" in rest else "CPU"
        print(f"[colab] Creating session '{name}'...")
        if gpu in os.environ.get("FAKE_COLAB_REJECT", "").split(","):
            print(f"[colab] Backend rejected accelerator '{gpu}'.")
            return 1
        sessions[name] = gpu
        STATE.write_text(json.dumps(sessions))
        print("[colab] Session READY.")
    elif cmd == "stop":
        if name not in sessions:
            print(f"[colab] Session '{name}' not found.")
            return 3
        del sessions[name]
        STATE.write_text(json.dumps(sessions))
        print("[colab] Session terminated.")
    elif name not in sessions:
        print(f"[colab] Session '{name}' appears to be lost (404/401). Cleaning up.")
        return 1
    elif cmd == "exec":
        code = Path(rest[rest.index("-f") + 1]).read_text() if "-f" in rest else stdin
        print(f"ran: {code}")
    elif cmd == "upload":
        print(f"[colab] Uploaded '{rest[-2]}' to '{rest[-1]}'")
    elif cmd == "download":
        Path(rest[-1]).write_text("data")
        print(f"[colab] Downloaded '{rest[-2]}' to '{rest[-1]}'")
    else:
        print(f"boom: {cmd}")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
