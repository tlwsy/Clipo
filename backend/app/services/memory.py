# SPDX-License-Identifier: AGPL-3.0-or-later
import heapq
import math
import random
from collections.abc import Callable, Iterable
from datetime import datetime


def sample_memories(
    candidates: Iterable[tuple[int, datetime]],
    count: int,
    now: datetime,
    random_value: Callable[[], float] = random.random,
) -> list[int]:
    """Weighted sampling without replacement; retain only count identifiers in memory."""
    reservoir: list[tuple[float, int]] = []
    for note_id, created_at in candidates:
        weight = 1 + max(0, (now - created_at).total_seconds()) / 31536000
        score = math.log(max(random_value(), 1e-300)) / weight
        item = (score, note_id)
        if len(reservoir) < count:
            heapq.heappush(reservoir, item)
        elif item > reservoir[0]:
            heapq.heapreplace(reservoir, item)
    return [note_id for _, note_id in sorted(reservoir, reverse=True)]
