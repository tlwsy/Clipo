# SPDX-License-Identifier: AGPL-3.0-or-later
import random
from datetime import timedelta

from app.db.base import utcnow
from app.services.memory import sample_memories


def test_weighted_sampling_favors_older_notes_without_duplicates() -> None:
    now = utcnow()
    candidates = [(1, now), (2, now - timedelta(days=365 * 9))]
    rng = random.Random(42)
    older = sum(sample_memories(candidates, 1, now, rng.random) == [2] for _ in range(1000))
    assert 850 < older < 950
    assert set(sample_memories(candidates, 15, now)) == {1, 2}
    assert sample_memories([], 15, now) == []


def test_sampling_handles_zero_random_and_future_dates() -> None:
    now = utcnow()
    assert sample_memories([(1, now + timedelta(days=2))], 10, now, lambda: 0) == [1]
    rows = ((i, now) for i in range(10000))
    result = sample_memories(rows, 15, now)
    assert len(result) == len(set(result)) == 15
