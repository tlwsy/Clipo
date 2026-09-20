from app.extractors.base import Extractor
from app.extractors.generic import GenericExtractor


class ExtractorRegistry:
    def __init__(self, extractors: list[Extractor] | None = None):
        self.extractors = extractors or [GenericExtractor()]

    def get(self, url: str) -> Extractor:
        for extractor in self.extractors:
            if extractor.matches(url):
                return extractor
        raise ValueError("No matching extractor")
