"""Server-side enforcement of rule 2 — every claim cites its source.

The rule is only real if it is checked here. A language model invents
plausible-looking encounter ids without effort, and a clinical claim that
cannot be traced back to a specific encounter is worse than no claim, so an
entry citing an id that is not in the request is dropped — never corrected,
never returned anyway.

Dropping everything is an acceptable outcome: rule 4 says an honestly empty
briefing beats invented content.
"""

import logging
from typing import Protocol, TypeVar

from app.models.briefing import BriefingRequest

logger = logging.getLogger(__name__)


class Sourced(Protocol):
    source_encounter_ids: list[str]


T = TypeVar("T", bound=Sourced)


def known_encounter_ids(dossier: BriefingRequest) -> set[str]:
    """Ids actually present in the request — the only citable universe."""
    return {encounter.id for encounter in dossier.encounters if encounter.id}


def keep_sourced(entries: list[T], known: set[str]) -> list[T]:
    """Keep only entries that cite at least one id, all of them real."""
    kept: list[T] = []

    for entry in entries:
        ids = entry.source_encounter_ids
        if ids and all(identifier in known for identifier in ids):
            kept.append(entry)
        else:
            logger.warning(
                "dropping briefing entry with unsourced ids: cited=%s known=%s",
                ids,
                sorted(known),
            )

    return kept
