from __future__ import annotations

from typing import Any

import httpx

from opinions_agent.agent import TelegramMessageSpec


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"

    async def send_message(self, chat_id: int, spec: TelegramMessageSpec) -> int:
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        payload: dict[str, Any] = {"chat_id": chat_id, "text": spec.text, "parse_mode": "HTML"}
        if spec.reply_to_message_id is not None:
            payload["reply_to_message_id"] = spec.reply_to_message_id
        if spec.force_reply:
            payload["reply_markup"] = {"force_reply": True}
        elif spec.buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": button.text, "callback_data": button.callback_data} for button in spec.buttons]
                ]
            }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/sendMessage", json=payload)
            response.raise_for_status()
            data = response.json()
        return int(data["result"]["message_id"])

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/answerCallbackQuery", json=payload)
            response.raise_for_status()

    async def get_updates(self, offset: int | None = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 30}
        if offset is not None:
            payload["offset"] = offset
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(f"{self.base_url}/getUpdates", json=payload)
            response.raise_for_status()
            return list(response.json()["result"])


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, TelegramMessageSpec]] = []
        self.answered_callbacks: list[tuple[str, str | None]] = []
        self._next_message_id = 1000

    async def send_message(self, chat_id: int, spec: TelegramMessageSpec) -> int:
        self.sent.append((chat_id, spec))
        self._next_message_id += 1
        return self._next_message_id

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        self.answered_callbacks.append((callback_query_id, text))
