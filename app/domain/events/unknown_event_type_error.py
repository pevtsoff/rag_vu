"""Raised when an envelope names an event type that is not registered."""


class UnknownEventTypeError(LookupError):
    """No event class is registered for an envelope's ``event_type``."""
