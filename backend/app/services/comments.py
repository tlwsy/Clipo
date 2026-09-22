# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import re
import unicodedata

from app.extractors.base import CapturedComment

MIN_COMMENT_CHARACTERS = 5


def select_comments(
    comments: list[CapturedComment], limit: int
) -> list[tuple[int, CapturedComment]]:
    """Select candidates without changing originals or their stable position identifiers."""
    ranked = sorted(
        enumerate(comments), key=lambda item: (-item[1].likes, -item[1].replies, item[0])
    )
    selected: list[tuple[int, CapturedComment]] = []
    seen: set[str] = set()
    for position, comment in ranked:
        normalized = " ".join(unicodedata.normalize("NFKC", comment.content).casefold().split())
        # Platforms also encode emoji as bracketed labels, such as [笑哭R].
        meaningful = re.sub(r"\[[^\[\]\n]{1,20}\]", "", normalized)
        meaningful = re.sub(r"[0-9#*]\ufe0f?\u20e3", "", meaningful)
        if sum(char.isalnum() for char in meaningful) < MIN_COMMENT_CHARACTERS:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        selected.append((position, comment))
        if len(selected) >= limit:
            break
    return selected
