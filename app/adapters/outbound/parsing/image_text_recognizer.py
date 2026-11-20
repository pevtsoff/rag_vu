"""OCR of a single image."""

from abc import ABC, abstractmethod


class ImageTextRecognizer(ABC):
    @abstractmethod
    def recognize(self, png_bytes: bytes) -> str: ...
