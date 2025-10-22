import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from openai import AsyncOpenAI
    from openai.error import OpenAIError
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore
    OpenAIError = Exception  # type: ignore


@dataclass
class CategorizedItem:
    name: str
    amount: float
    category: str
    confidence: float = 0.5


KEYWORD_CATEGORIES: Dict[str, str] = {
    "хлеб": "еда",
    "молоко": "еда",
    "сыр": "еда",
    "кофе": "еда",
    "чай": "еда",
    "ябл": "еда",
    "банан": "еда",
    "проезд": "транспорт",
    "метро": "транспорт",
    "такси": "транспорт",
    "билет": "транспорт",
    "бенз": "транспорт",
    "шампун": "покупки",
    "одеж": "покупки",
    "космет": "покупки",
    "меди": "здоровье",
    "апт": "здоровье",
    "лекар": "здоровье",
    "кино": "развлечения",
    "подпис": "развлечения",
    "игр": "развлечения",
}


class ExpenseCategorizer:
    def __init__(self, openai_api_key: Optional[str] = None) -> None:
        self._client = AsyncOpenAI(api_key=openai_api_key) if openai_api_key and AsyncOpenAI else None
        self._categories = {"еда", "транспорт", "покупки", "прочее", "здоровье", "развлечения"}

    async def classify_items(self, items: Iterable[Tuple[str, float]]) -> List[CategorizedItem]:
        categorized: List[CategorizedItem] = []
        for name, amount in items:
            category, confidence = self._classify_with_rules(name)
            if category is None:
                category = await self._classify_with_gpt(name)
                confidence = 0.6 if category != "прочее" else 0.3
            categorized.append(CategorizedItem(name=name, amount=amount, category=category, confidence=confidence))
        return categorized

    def _classify_with_rules(self, name: str) -> Tuple[Optional[str], float]:
        normalized = name.lower()
        for keyword, category in KEYWORD_CATEGORIES.items():
            if keyword in normalized:
                return category, 0.9
        return None, 0.0

    async def _classify_with_gpt(self, name: str) -> str:
        if not self._client:
            return "прочее"
        prompt = (
            "Ты — помощник по персональным финансам. Определи категорию покупки из списка: "
            "еда, транспорт, покупки, здоровье, развлечения, прочее. "
            "Ответь только названием категории в нижнем регистре. Покупка: "
            f"'{name}'."
        )
        try:
            response = await self._client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Ты классифицируешь расходы"}, {"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=8,
            )
            category = response.choices[0].message.content.strip().lower()
        except OpenAIError:
            logging.exception("OpenAI categorization failed")
            return "прочее"
        except Exception:
            logging.exception("Unexpected error during GPT categorization")
            return "прочее"

        if category not in self._categories:
            return "прочее"
        return category
