"""CursorStore adapter over Locksmith's db.tops (TopicsRecord keyed by (pre, eid))."""
from __future__ import annotations
from keri.db import basing


class DbTopsCursorStore:
    def __init__(self, db, pre):
        self.db = db
        self.pre = pre

    def get(self, eid, topic):
        rec = self.db.tops.get((self.pre, eid))
        if rec is None or topic not in rec.topics:
            return None
        return rec.topics[topic]

    def set(self, eid, topic, idx):
        rec = self.db.tops.get((self.pre, eid)) or basing.TopicsRecord(topics=dict())
        rec.topics[topic] = int(idx)
        self.db.tops.pin((self.pre, eid), rec)
