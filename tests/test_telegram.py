from __future__ import annotations

from typing import Any

from opinions_agent.agent import TelegramButtonSpec, TelegramMessageSpec
from opinions_agent.telegram import TelegramClient


class FakeResponse:
    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return {"result": {"message_id": 42}}


class FakeAsyncClient:
    def __init__(self, **kwargs: Any) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
        self.posts.append((url, json))
        return FakeResponse()


async def test_telegram_messages_are_sent_as_html(monkeypatch) -> None:
    fake_client = FakeAsyncClient()
    monkeypatch.setattr("opinions_agent.telegram.httpx.AsyncClient", lambda **kwargs: fake_client)

    message_id = await TelegramClient("token").send_message(
        123,
        TelegramMessageSpec(
            text="<b>Add Opinion #1</b>",
            buttons=[TelegramButtonSpec(text="Approve", callback_data="approve:p1")],
        ),
    )

    assert message_id == 42
    assert fake_client.posts == [
        (
            "https://api.telegram.org/bottoken/sendMessage",
            {
                "chat_id": 123,
                "text": "<b>Add Opinion #1</b>",
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [[{"text": "Approve", "callback_data": "approve:p1"}]]
                },
            },
        )
    ]
