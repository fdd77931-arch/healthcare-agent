"""Short-lived in-memory triage session storage."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock

from app.domain.triage import TriageSession


@dataclass
class _StoredSession:
    session: TriageSession
    expires_at: datetime


class SessionStore:
    def __init__(
        self,
        ttl: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl = ttl
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[str, _StoredSession] = {}
        self._lock = RLock()

    def create(self, session: TriageSession) -> TriageSession:
        with self._lock:
            stored = session.model_copy(deep=True)
            self._sessions[stored.session_id] = _StoredSession(
                session=stored,
                expires_at=self._clock() + self._ttl,
            )
            return stored.model_copy(deep=True)

    def get(self, session_id: str) -> TriageSession | None:
        with self._lock:
            stored = self._get_active(session_id)
            return (
                stored.session.model_copy(deep=True)
                if stored is not None
                else None
            )

    def _get_active(self, session_id: str) -> _StoredSession | None:
        stored = self._sessions.get(session_id)
        if stored is None:
            return None
        if stored.expires_at <= self._clock():
            del self._sessions[session_id]
            return None
        return stored

    def save(self, session: TriageSession) -> TriageSession | None:
        with self._lock:
            if self._get_active(session.session_id) is None:
                return None
            return self._save_active(session)

    def _save_active(self, session: TriageSession) -> TriageSession:
        stored = session.model_copy(deep=True)
        self._sessions[stored.session_id] = _StoredSession(
            session=stored,
            expires_at=self._clock() + self._ttl,
        )
        return stored.model_copy(deep=True)

    def update(
        self,
        session_id: str,
        updater: Callable[[TriageSession], TriageSession],
    ) -> TriageSession | None:
        with self._lock:
            stored = self._get_active(session_id)
            if stored is None:
                return None
            updated = updater(stored.session.model_copy(deep=True))
            if updated.session_id != session_id:
                raise ValueError("session updater cannot change session_id")
            return self._save_active(updated)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            if self._get_active(session_id) is None:
                return False
            return self._sessions.pop(session_id, None) is not None

    def purge_expired(self) -> int:
        with self._lock:
            now = self._clock()
            expired_ids = [
                session_id
                for session_id, stored in self._sessions.items()
                if stored.expires_at <= now
            ]
            for session_id in expired_ids:
                del self._sessions[session_id]
            return len(expired_ids)
