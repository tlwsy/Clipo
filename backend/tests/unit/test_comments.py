# SPDX-FileCopyrightText: 2026 Clipo contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from app.extractors.base import CapturedComment
from app.services.comments import select_comments


def test_candidates_rank_by_likes_then_replies_deduplicate_and_keep_original_positions() -> None:
    comments = [
        CapturedComment(content="use this method", likes=2),
        CapturedComment(content="USE  THIS\nMETHOD", likes=20),
        CapturedComment(content="另一个具体建议", likes=20, replies=3),
        CapturedComment(content="还有一条不同建议", likes=20, replies=3),
        CapturedComment(content="最后一条详细评论", likes=1),
    ]
    selected = select_comments(comments, 3)
    assert [index for index, _ in selected] == [2, 3, 1]
    assert selected[2][1].content == "USE  THIS\nMETHOD"
    assert comments[0].content == "use this method"
    assert len(comments) == 5


def test_short_blank_symbol_and_emoji_comments_are_excluded() -> None:
    comments = [
        CapturedComment(content=value, likes=100)
        for value in [
            "",
            "   ",
            "谢谢",
            "👍👍👍👍👍",
            "👨‍👩‍👧‍👦",
            "[笑哭R][笑哭R]",
            "!!!???",
            "1️⃣2️⃣3️⃣4️⃣5️⃣",
        ]
    ]
    comments.append(CapturedComment(content="具体建议五个字", likes=0))
    assert [index for index, _ in select_comments(comments, 30)] == [8]


def test_unicode_normalization_deduplicates_full_width_text() -> None:
    comments = [CapturedComment(content="ＡＢＣＤＥ"), CapturedComment(content="abcde", likes=10)]
    assert [index for index, _ in select_comments(comments, 30)] == [1]
