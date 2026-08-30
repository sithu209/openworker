"""Runtime event compatibility layer.

H1 reuses OpenWorker's existing Event/EventType contract exactly. Harness event
translation will target these types in a later segment instead of changing the
UI/server event protocol.
"""

from ..events import Event, EventType

RuntimeEvent = Event
RuntimeEventType = EventType

__all__ = ["RuntimeEvent", "RuntimeEventType"]
