"""Errors with a stable `code`, a short message, and the CLI output as `detail`."""


class ColabError(Exception):
    def __init__(self, message: str, detail: str | None = None, code: str = "colab_error"):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.code = code

    def __str__(self) -> str:
        return f"{self.message}\n{self.detail.strip()}" if self.detail else self.message


class ColabAuthError(ColabError):
    def __init__(self, detail: str | None = None):
        super().__init__(
            "Colab sign-in has expired. Sign the colab CLI in again (run any colab command, or"
            " `gcloud auth application-default login` with the Colab scopes for ADC), then retry.",
            detail,
            code="colab_auth",
        )


class SessionGone(ColabError):
    def __init__(self, session: str, detail: str | None = None):
        super().__init__(f"The Colab session {session} is gone.", detail, code="colab_lost")
        self.session = session


class ColabMissing(ColabError):
    def __init__(self, detail: str | None = None):
        super().__init__("The colab CLI isn't installed.", detail, code="colab_missing")


class ColabNoGpu(ColabError):
    def __init__(self, gpu: str | None, detail: str | None = None):
        what = f"a {gpu}" if gpu else "a"
        super().__init__(f"Colab wouldn't start {what} session.", detail, code="colab_no_gpu")
        self.gpu = gpu


class TunnelError(Exception):
    pass
