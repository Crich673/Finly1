import asyncio
import logging
import os
import re
import tempfile
from typing import List, Tuple

from aiogram.types import Message

try:
    import easyocr  # type: ignore
except ImportError:  # pragma: no cover
    easyocr = None

import pytesseract
from PIL import Image


class OCRService:
    def __init__(self) -> None:
        self._reader = None

    async def process_receipt(self, message: Message) -> List[Tuple[str, float]]:
        if not message.photo:
            return []

        photo = message.photo[-1]
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
            await photo.download(destination=tmp_path)

        try:
            text = await self._extract_text(tmp_path)
            items = self._parse_items(text)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                logging.warning("Failed to delete temp file %s", tmp_path)
        return items

    async def _extract_text(self, image_path: str) -> str:
        if easyocr is not None:
            text = await asyncio.to_thread(self._easyocr_read, image_path)
            if text:
                return text
        return await asyncio.to_thread(self._tesseract_read, image_path)

    def _easyocr_read(self, image_path: str) -> str:
        try:
            if self._reader is None:
                self._reader = easyocr.Reader(["ru", "en"], gpu=False)
            results = self._reader.readtext(image_path, detail=0)
            return "\n".join(results)
        except Exception:
            logging.exception("EasyOCR failed")
            return ""

    def _tesseract_read(self, image_path: str) -> str:
        try:
            image = Image.open(image_path)
            return pytesseract.image_to_string(image, lang="rus+eng")
        except Exception:
            logging.exception("Tesseract failed")
            return ""

    def _parse_items(self, text: str) -> List[Tuple[str, float]]:
        items: List[Tuple[str, float]] = []
        pattern = re.compile(r"^(?P<name>[\w\s\-\.,]+?)\s+(?P<amount>\d+[\.,]\d{2}|\d+)$")
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.isdigit():
                continue
            match = pattern.match(line)
            if not match:
                continue
            name = match.group("name").strip()
            amount_str = match.group("amount").replace(",", ".")
            try:
                amount = float(amount_str)
            except ValueError:
                continue
            if amount <= 0:
                continue
            items.append((name, amount))
        return items
