from dataclasses import dataclass


@dataclass(frozen=True)
class JobRoute:
    """The consumer that handles an event and the worker queue it runs on."""

    consumer: str
    queue: str
