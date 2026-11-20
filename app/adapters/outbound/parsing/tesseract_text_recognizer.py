import subprocess

from app.adapters.outbound.parsing.image_text_recognizer import ImageTextRecognizer


class TesseractTextRecognizer(ImageTextRecognizer):
    """Runs the ``tesseract`` CLI installed in the worker image."""

    def __init__(self, languages: str = "rus+eng") -> None:
        self._languages = languages

    def recognize(self, png_bytes: bytes) -> str:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", self._languages],
            input=png_bytes,
            capture_output=True,
            check=True,
        )
        return result.stdout.decode("utf-8").strip()
