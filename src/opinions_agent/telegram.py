from __future__ import annotations

from typing import Any

import httpx

from opinions_agent.agent import TelegramMessageSpec


class TelegramAPIError(RuntimeError):
    pass


def _telegram_result(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.is_success:
        return data
    description = str(data.get("description") or response.reason_phrase or "unknown error")
    raise TelegramAPIError(f"Telegram {operation} failed with HTTP {response.status_code}: {description}")


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
            data = _telegram_result(response, "sendMessage")
        return int(data["result"]["message_id"])

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/answerCallbackQuery", json=payload)
            _telegram_result(response, "answerCallbackQuery")

    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": []},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/editMessageText", json=payload)
            _telegram_result(response, "editMessageText")

    async def get_updates(self, offset: int | None = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 30}
        if offset is not None:
            payload["offset"] = offset
        async with httpx.AsyncClient(timeout=40) as client:
            response = await client.post(f"{self.base_url}/getUpdates", json=payload)
            return list(_telegram_result(response, "getUpdates")["result"])


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, TelegramMessageSpec]] = []
        self.answered_callbacks: list[tuple[str, str | None]] = []
        self.edited_messages: list[tuple[int, int, str]] = []
        self._next_message_id = 1000

    async def send_message(self, chat_id: int, spec: TelegramMessageSpec) -> int:
        self.sent.append((chat_id, spec))
        self._next_message_id += 1
        return self._next_message_id

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        self.answered_callbacks.append((callback_query_id, text))

    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        self.edited_messages.append((chat_id, message_id, text))
