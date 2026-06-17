"""Trust anchor metadata for KERI release verification.

The real ``publisher_anchor.json`` is the trust root embedded into PyInstaller
builds; it bootstraps update verification on first install. Per the project's
privacy rule, the real anchor (real publisher AID + real witness OOBI domains)
is NOT committed: it is gitignored and build-injected, either via the
``LOCKSMITH_PUBLISHER_ANCHOR`` env var (a file path) or by placing the file at
``locksmith/release/publisher_anchor.json`` before the build.

The committed ``publisher_anchor.example.json`` is a placeholder template with
``example.com`` witnesses and a placeholder AID — same schema, no real values.

See ``locksmith.update.cli._load_publisher_anchor`` for the resolution order
and docs/superpowers/specs/2026-05-28-locksmith-deploy-update-design.md §7.7.

The federation/CDN DOMAINS (witness hosts/AIDs + release CDN base/bucket/
appcast URLs) follow the same de-commit pattern but live in a separate config:
the gitignored ``deploy_config.json`` with committed ``deploy_config.example.json``
template. See ``locksmith.release.deploy.load_deploy_config``.
"""
from locksmith.release.deploy import (
    DEPLOY_CONFIG_ENV_VAR,
    load_deploy_config,
)

__all__ = ["DEPLOY_CONFIG_ENV_VAR", "load_deploy_config"]
