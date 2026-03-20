# -*- encoding: utf-8 -*-
"""
locksmith.plugins package

Plugin architecture for Locksmith wallet extensions.
"""
from locksmith.plugins.base import (
    PluginBase,
    AccountProviderPlugin,
    IdentifierUploadProviderPlugin,
    WitnessProviderPlugin,
    WatcherProviderPlugin,
    CredentialProviderPlugin,
)

__all__ = [
    "PluginBase",
    "AccountProviderPlugin",
    "IdentifierUploadProviderPlugin",
    "WitnessProviderPlugin",
    "WatcherProviderPlugin",
    "CredentialProviderPlugin",
]