from __future__ import annotations

from typing import Any

import pytest

from opinions_agent.agent import TelegramButtonSpec, TelegramMessageSpec
from opinions_agent.telegram import TelegramAPIError, TelegramClient


class FakeResponse:
    status_code = 200
    is_success = True
    reason_phrase = "OK"

    def json(self) -> dict[str, Any]:
        return {"result": {"message_id": 42}}


class FakeAsyncClient:
    def __init__(self, response: FakeResponse | None = None, **kwargs: Any) -> None:
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.response = response or FakeResponse()

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass

    async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
        self.posts.append((url, json))
        return self.response


class FailedResponse(FakeResponse):
    status_code = 400
    is_success = False
    reason_phrase = "Bad Request"

    def json(self) -> dict[str, Any]:
        return {"ok": False, "description": "Bad Request: message is not modified"}


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


async def test_telegram_message_edit_marks_callbacks_and_removes_buttons(monkeypatch) -> None:
    fake_client = FakeAsyncClient()
    monkeypatch.setattr("opinions_agent.telegram.httpx.AsyncClient", lambda **kwargs: fake_client)

    await TelegramClient("token").edit_message_text(123, 42, "<b>✅ Approved - Add Opinion #1</b>")

    assert fake_client.posts == [
        (
            "https://api.telegram.org/bottoken/editMessageText",
            {
                "chat_id": 123,
                "message_id": 42,
                "text": "<b>✅ Approved - Add Opinion #1</b>",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": []},
            },
        )
    ]


async def test_telegram_api_errors_include_detail_without_exposing_the_request_url(monkeypatch) -> None:
    fake_client = FakeAsyncClient(FailedResponse())
    monkeypatch.setattr("opinions_agent.telegram.httpx.AsyncClient", lambda **kwargs: fake_client)

    with pytest.raises(TelegramAPIError) as error:
        await TelegramClient("secret-token").edit_message_text(123, 42, "text")

    assert str(error.value) == (
        "Telegram editMessageText failed with HTTP 400: Bad Request: message is not modified"
    )
    assert "secret-token" not in str(error.value)
    assert "api.telegram.org" not in str(error.value)
