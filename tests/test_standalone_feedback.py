from __future__ import annotations

import pytest
from conftest import seed_corpus
from sqlalchemy import select
from test_workflow import HelpSeekingAgent, callback_update, handle, start_run

from opinions_agent.agent import AgentTurnOutput, TelegramMessageSpec
from opinions_agent.models import RunStatus, TelegramInteraction
from opinions_agent.telegram import FakeTelegramClient


class ProposalAgent(HelpSeekingAgent):
    async def run_turn(self, *, prompt_fragment, resume_state, **kwargs):
        if resume_state is None:
            return AgentTurnOutput(
                status="awaiting_user",
                telegram_messages=[
                    TelegramMessageSpec(
                        text=f"Proposal {i}",
                        buttons=[
                            {"text": "Approve", "callback_data": f"approve:{i}"},
                            {"text": "Reject", "callback_data": f"reject:{i}"},
                        ],
                    )
                    for i in (1, 2)
                ],
            ), {"conversation": "proposals"}
        return await super().run_turn(prompt_fragment=prompt_fragment, resume_state=resume_state, **kwargs)


def standalone(update_id, text, chat_id=12345):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id + 10000,
            "chat": {"id": chat_id},
            "text": text,
        },
    }


async def test_standalone_correction_includes_pending_rejection(session, settings, opinions_repo):
    seed_corpus(settings)
    agent = ProposalAgent()
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram, agent)
    outbound = session.scalar(
        select(TelegramInteraction)
        .where(
            TelegramInteraction.direction == "outbound",
            TelegramInteraction.opinion_run_id == run.id,
        )
        .order_by(TelegramInteraction.id)
    )
    assert await handle(session, settings, telegram, callback_update(701, outbound, "reject:1"), agent) == "recorded"
    assert run.status == RunStatus.AWAITING_USER.value
    update = standalone(702, "Wait, please propose the first opinion again.")
    assert await handle(session, settings, telegram, update, agent) == "resumed"
    assert agent.resumed_state == {"conversation": "proposals"}
    assert "reject:1" in agent.resumed_prompt
    assert "Wait, please propose the first opinion again." in agent.resumed_prompt
    assert await handle(session, settings, telegram, update, agent) == "duplicate"


@pytest.mark.parametrize("status", [RunStatus.RUNNING_AGENT.value, RunStatus.COMPLETED.value, None])
async def test_standalone_does_not_start_nonwaiting_run(session, settings, opinions_repo, status):
    seed_corpus(settings)
    agent = HelpSeekingAgent()
    telegram = FakeTelegramClient()
    if status:
        run = await start_run(session, settings, telegram, agent)
        run.status = status
        session.commit()
    assert await handle(session, settings, telegram, standalone(703, "Please reconsider."), agent) == "no_pending_run"
    assert agent.resumed_prompt is None


async def test_standalone_rejects_other_chat(session, settings, opinions_repo):
    seed_corpus(settings)
    agent = HelpSeekingAgent()
    telegram = FakeTelegramClient()
    run = await start_run(session, settings, telegram, agent)
    assert await handle(session, settings, telegram, standalone(704, "Please reconsider.", 999), agent) == "forbidden"
    assert run.status == RunStatus.AWAITING_USER.value
    assert agent.resumed_prompt is None
