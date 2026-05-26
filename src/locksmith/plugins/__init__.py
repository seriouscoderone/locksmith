# -*- encoding: utf-8 -*-
"""
locksmith.plugins package

Plugin architecture for Locksmith wallet extensions.
"""
from locksmith.plugins.base import (
    PluginCore,
    AppPlugin,
    VaultPlugin,
    AccountProviderPlugin,
    IdentifierUploadProviderPlugin,
    WitnessProviderPlugin,
    WatcherProviderPlugin,
    CredentialProviderPlugin,
)

__all__ = [
    "PluginCore",
    "AppPlugin",
    "VaultPlugin",
    "AccountProviderPlugin",
    "IdentifierUploadProviderPlugin",
    "WitnessProviderPlugin",
    "WatcherProviderPlugin",
    "CredentialProviderPlugin",
]