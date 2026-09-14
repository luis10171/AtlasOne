"""Keep provider status separate from text used as conversation context."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AdvisorReply:
    text: str
    snapshot: dict
    api_failed: bool = False
