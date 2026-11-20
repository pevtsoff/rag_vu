"""Which consumers (jobs) react to which event types."""

from collections.abc import Mapping

from app.application.dto.job_route import JobRoute


class EventRoutes:
    def __init__(self, routes: Mapping[str, tuple[JobRoute, ...]]) -> None:
        self._routes = {event_type: tuple(targets) for event_type, targets in routes.items()}
        self._by_consumer = {
            route.consumer: route for targets in self._routes.values() for route in targets
        }

    def routes_for(self, event_type: str) -> tuple[JobRoute, ...]:
        return self._routes.get(event_type, ())

    def route_for_consumer(self, consumer: str) -> JobRoute:
        try:
            return self._by_consumer[consumer]
        except KeyError as exc:
            raise LookupError(f"No route is registered for consumer {consumer!r}") from exc

    def consumers(self) -> frozenset[str]:
        return frozenset(self._by_consumer)
