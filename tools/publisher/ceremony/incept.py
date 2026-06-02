#!/usr/bin/env python3.14
"""Interactive entry-point for the publisher AID inception ceremony.

Read `docs/governance/publisher-ceremony.md` before running. The script supports
two modes:

- `--dry-run` (default): targets staging witnesses, uses fake signing devices,
  writes outputs to `--output-dir`. Used to rehearse the ceremony. Defaults to
  `--no-submit`.
- `--production`: targets api.keri.host witnesses, opens real YubiKey devices,
  signs the inception event, submits it to the witness pool, and persists
  receipts. Defaults to `--submit`. This is the step that makes the publisher
  AID live (see Task B9).

Always commit the resulting `publisher_anchor.json` to
`src/locksmith/release/publisher_anchor.json` after the ceremony completes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from locksmith_publisher.incept import run_inception_ceremony


def _collect_software_passphrases(*, count: int, env_prefix: str | None) -> list[bytes]:
    """Collect N passphrases either from env vars or interactive prompt."""
    import os
    if env_prefix:
        passphrases: list[bytes] = []
        for i in range(1, count + 1):
            var = f"{env_prefix}_{i}"
            value = os.environ.get(var)
            if value is None:
                print(f"ERROR: environment variable {var} not set", file=sys.stderr)
                sys.exit(1)
            passphrases.append(value.encode("utf-8"))
        return passphrases

    import getpass
    passphrases = []
    for i in range(1, count + 1):
        while True:
            pw1 = getpass.getpass(f"Passphrase for key {i}: ")
            pw2 = getpass.getpass(f"Confirm passphrase for key {i}: ")
            if pw1 == pw2:
                if len(pw1) < 12:
                    print("Passphrase too short (minimum 12 chars). Try again.", file=sys.stderr)
                    continue
                passphrases.append(pw1.encode("utf-8"))
                break
            print("Passphrases don't match. Try again.", file=sys.stderr)
    return passphrases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publisher AID inception ceremony")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--witness-oobi",
        action="append",
        dest="witness_oobis",
        default=None,
        help="Repeat for each witness (>=toad required). "
             "If omitted, uses the KERI.host 5-witness federation.",
    )
    parser.add_argument("--toad", type=int, default=3)
    parser.add_argument("--quorum", type=int, default=2)
    parser.add_argument("--signers", type=int, default=3)
    parser.add_argument(
        "--yubikey-slot",
        action="append",
        dest="yubikey_slots",
        default=None,
        help="PIV slot per device; defaults to 9c for each.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--production", action="store_true")
    parser.add_argument(
        "--submit",
        dest="submit",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Submit the signed inception event to the witness pool and "
             "persist receipts. Defaults to --submit in --production and "
             "--no-submit in --dry-run.",
    )
    parser.add_argument("--non-interactive", action="store_true",
                        help="Skip confirmation prompts. Required for automated tests.")
    parser.add_argument(
        "--software-keys",
        type=Path,
        default=None,
        help="Use software-backed Ed25519 keys persisted to encrypted PEM "
             "files in this directory (instead of YubiKey hardware). "
             "BOOTSTRAP ONLY — rotate to hardware later via Phase 4 flow.",
    )
    parser.add_argument(
        "--passphrase-env-prefix",
        default=None,
        help="If set, read software-key passphrases from environment variables "
             "{prefix}_1, {prefix}_2, {prefix}_3 (for automated tests). "
             "Otherwise prompts interactively.",
    )
    args = parser.parse_args(argv)

    dry_run = not args.production
    slots = args.yubikey_slots or ["9c"] * args.signers

    passphrases: list[bytes] | None = None
    if args.software_keys is not None:
        passphrases = _collect_software_passphrases(
            count=args.signers,
            env_prefix=args.passphrase_env_prefix,
        )

    if not args.non_interactive:
        print("\n=== Locksmith Publisher AID Inception Ceremony ===")
        print(f"Mode: {'DRY-RUN' if dry_run else 'PRODUCTION'}")
        witness_count = len(args.witness_oobis) if args.witness_oobis else 5
        print(f"Witnesses: {witness_count} ({'explicit' if args.witness_oobis else 'KERI.host federation'})")
        print(f"Signer quorum: {args.quorum} of {args.signers}")
        print(f"toad (witness receipts required): {args.toad}")
        print(f"Output directory: {args.output_dir}")
        confirm = input("Type CONTINUE to proceed: ")
        if confirm.strip() != "CONTINUE":
            print("Aborted.", file=sys.stderr)
            return 1

    if args.submit is None:
        submit = not dry_run
    else:
        submit = args.submit

    run_inception_ceremony(
        witness_oobis=args.witness_oobis or [],
        toad=args.toad,
        quorum=args.quorum,
        signers=args.signers,
        dry_run=dry_run,
        submit=submit,
        output_dir=args.output_dir,
        yubikey_slots=slots,
        software_key_dir=args.software_keys,
        software_passphrases=passphrases,
    )
    print(f"Ceremony complete. Outputs in {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
