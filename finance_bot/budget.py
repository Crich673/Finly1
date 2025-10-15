import logging
from typing import Dict, Optional

try:
    from openai import AsyncOpenAI
    from openai.error import OpenAIError
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore
    OpenAIError = Exception  # type: ignore


class BudgetAdvisor:
    def __init__(self, openai_api_key: Optional[str]) -> None:
        self._client = AsyncOpenAI(api_key=openai_api_key) if openai_api_key and AsyncOpenAI else None

    async def generate_budget(self, income: float, summary: Dict[str, float]) -> str:
        if income <= 0:
            return "Укажите положительный доход, чтобы я мог рассчитать бюджет."

        if not self._client:
            return (
                "GPT недоступен. Рекомендуем распределить бюджет так: 50% на обязательные расходы, "
                "30% на цели и 20% на развлечения."
            )

        history_lines = [f"- {category}: {amount:.2f} ₽" for category, amount in summary.items()]
        history_text = "\n".join(history_lines) if history_lines else "нет данных"

        prompt = (
            "Составь персонализированный бюджет на месяц. Доход пользователя: "
            f"{income:.2f} ₽. Расходы по категориям:\n{history_text}. "
            "Предложи распределение средств по категориям и дай краткие советы по экономии."
        )

        try:
            response = await self._client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "system", "content": "Ты финансовый ассистент."}, {"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=400,
            )
            return response.choices[0].message.content.strip()
        except OpenAIError:
            logging.exception("OpenAI budget generation failed")
            return "Не удалось получить рекомендации от GPT. Попробуйте позже."
        except Exception:
            logging.exception("Unexpected error during budget generation")
            return "Произошла непредвиденная ошибка при расчёте бюджета."
