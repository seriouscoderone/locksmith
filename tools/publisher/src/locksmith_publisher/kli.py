"""Thin subprocess wrappers over keripy `kli`. ALL receipt-collecting commands
force --receipt-endpoint (routes to Receiptor → /receipts; the default
WitnessReceiptor path hangs over HTTP)."""
import subprocess

KLI = "kli"  # resolved on PATH; tests/CI set kli.KLI = "<venv>/bin/kli"

_SECRET_FLAGS = {"--passcode", "-p", "--salt", "-s"}


def _redact(argv: list[str]) -> list[str]:
    """Return a copy of argv with values following secret flags replaced by ***."""
    out, redact_next = [], False
    for tok in argv:
        if redact_next:
            out.append("***")
            redact_next = False
        else:
            out.append(tok)
            redact_next = tok in _SECRET_FLAGS
    return out


def _run(argv: list[str], *, check: bool = True) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(_redact(argv))} failed ({proc.returncode}):\n{proc.stderr}")
    return proc.stdout


def kli_incept(*, name, alias, bran, base, wits: list[str], toad: int,
               transferable=True, icount=1, isith="1", ncount=1, nsith="1") -> str:
    argv = [KLI, "incept", "--name", name, "--alias", alias, "--base", base,
            "--passcode", bran, "--receipt-endpoint",
            "--transferable" if transferable else "--non-transferable",
            "--icount", str(icount), "--isith", str(isith),
            "--ncount", str(ncount), "--nsith", str(nsith), "--toad", str(toad)]
    for w in wits:
        argv += ["--wits", w]
    return _run(argv)


def kli_interact(*, name, alias, bran, base, data: str) -> str:
    argv = [KLI, "interact", "--name", name, "--alias", alias, "--base", base,
            "--passcode", bran, "--receipt-endpoint", "--data", data]
    return _run(argv)


def kli_init(*, name, base, bran, salt=None) -> str:
    """Create the keystore. `bran` is the passcode/seed; never logged.

    Pass `salt` (a qb64 string) to mint a deterministic AID reproducible from
    (salt + bran). The salt is a secret — read from an env var, never a CLI
    arg, never echoed. When `salt` is None or empty the keystore generates a
    random salt (the default / backward-compatible behaviour).
    """
    argv = [KLI, "init", "--name", name, "--base", base, "--passcode", bran]
    if salt:
        argv += ["--salt", salt]
    return _run(argv)


def kli_resolve_oobi(*, name, base, bran, oobi: str) -> str:
    """Resolve a witness OOBI into the keystore so incept can reach it."""
    return _run([KLI, "oobi", "resolve", "--name", name, "--base", base,
                 "--passcode", bran, "--oobi", oobi])
