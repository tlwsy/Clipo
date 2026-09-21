from collections.abc import Callable

from pydantic import SecretStr

from app.extractors.base import Extractor
from app.extractors.generic import GenericExtractor
from app.extractors.xiaoheihe import XiaoheiheExtractor
from app.extractors.xiaohongshu import XiaohongshuExtractor


class ExtractorRegistry:
    def __init__(
        self,
        extractors: list[Extractor] | None = None,
        *,
        cookie_loader: Callable[[str], SecretStr | None] | None = None,
        max_comments: int = 100,
    ) -> None:
        self.extractors = extractors or [
            XiaohongshuExtractor(cookie_loader, max_comments=max_comments),
            XiaoheiheExtractor(cookie_loader, max_comments=max_comments),
            GenericExtractor(),
        ]

    def get(self, url: str) -> Extractor:
        for extractor in self.extractors:
            if extractor.matches(url):
                return extractor
        raise ValueError("No matching extractor")
