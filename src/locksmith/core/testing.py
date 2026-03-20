# -*- encoding: utf-8 -*-
"""
locksmith.core.testing module

Test doers for verifying hio integration
"""
from hio.base import doing
from keri import help

logger = help.ogler.getLogger(__name__)


class TestDoer(doing.Doer):
    """
    Test doer that logs a message every second to verify hio integration.
    Can emit signals via a signal bridge when count reaches a threshold.
    """

    def __init__(self, signal_bridge=None, **kwa):
        """
        Initialize the test doer.

        Args:
            signal_bridge: Optional DoerSignalBridge instance for emitting Qt signals
        """
        super().__init__(tock=1.0, **kwa)  # Run every 1 second
        self.count = 0
        self.signal_bridge = signal_bridge

    def enter(self, **kwa):
        """Called when doer starts."""
        logger.info("TestDoer: Entering")
        self.count = 0

    def recur(self, tyme):
        """Called every tock (1 second)."""
        self.count += 1
        logger.info(f"TestDoer: Running (count: {self.count}, tyme: {tyme:.2f})")

        # Emit signal if bridge is available
        if self.signal_bridge:
            self.signal_bridge.emit_test_count(self.count)

            # Emit special event when count reaches 10
            if self.count >= 10:
                logger.info("TestDoer: Count reached 10, emitting doer_event")
                self.signal_bridge.emit_doer_event(
                    doer_name="TestDoer",
                    event_type="count_threshold_reached",
                    data={"count": self.count, "threshold": 10}
                )
                # Stop the doer after reaching threshold
                return True

        # Return False to keep running (or True to stop)
        return False

    def exit(self):
        """Called when doer exits."""
        logger.info(f"TestDoer: Exiting (ran {self.count} times)")