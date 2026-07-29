"""Optional slot-parser boundary with an offline demo fallback."""

from collections.abc import Mapping
from typing import Protocol

from app.domain.models import TriageSlots


class SlotParser(Protocol):
    def parse(self, text: str, current: TriageSlots) -> TriageSlots: ...


class DemoSlotParser:
    def parse(self, text: str, current: TriageSlots) -> TriageSlots:
        return current.model_copy(
            update={"main_symptom": current.main_symptom or text.strip()}
        )


def build_slot_parser(
    environment: Mapping[str, str] | None = None,
) -> SlotParser:
    """Return the local parser unless a future configured provider is available."""
    _ = environment
    return DemoSlotParser()
