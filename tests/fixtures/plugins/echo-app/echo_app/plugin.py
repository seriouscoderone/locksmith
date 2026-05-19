from __future__ import annotations

from keri import help

from locksmith.plugins.base import AppPlugin

logger = help.ogler.getLogger(__name__)


class EchoService:
    """Trivial AppService that logs start/stop for test assertions."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id

    def start(self) -> None:
        logger.info("plugin.service.started plugin_id=%s", self._plugin_id)

    def stop(self) -> None:
        logger.info("plugin.service.stopped plugin_id=%s", self._plugin_id)


class EchoAppPlugin(AppPlugin):
    """Minimal AppPlugin used by the Stage 1 integration tests."""

    @property
    def plugin_id(self) -> str:
        return "echo_app"

    def initialize(self, app) -> None:
        logger.info("plugin.initialize plugin_id=%s", self.plugin_id)

    def on_app_started(self, app, window) -> None:
        logger.info("plugin.on_app_started plugin_id=%s", self.plugin_id)

    def on_app_stopping(self, app) -> None:
        logger.info("plugin.on_app_stopping plugin_id=%s", self.plugin_id)

    def get_app_services(self):
        return [EchoService(self.plugin_id)]
