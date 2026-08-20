"""Parse the canonical Telegram HTML proposal format out of agent messages."""

from __future__ import annotations

import html
import re
from collections.abc import Iterable

from pydantic import BaseModel, Field

from opinions_agent.agent import TelegramMessageSpec

EVIDENCE_ID_RE = re.compile(r"\b(?:rw|reader-note|reader-summary):[0-9a-z][0-9a-z-]*")
SECTION_RE = re.compile(r"<i>Section:</i>\s*(.+)")
OPINION_BLOCK_RE = re.compile(
    r"<b>(?:Proposed |Revised |Updated |New )?Opinion</b>\s*(.*?)\s*(?:<b>|<blockquote|\Z)", re.DOTALL
)
CURRENT_OPINION_BLOCK_RE = re.compile(
    r"<b>Current(?: Opinion)?</b>\s*(.*?)\s*<b>(?:Proposed |Revised |Updated |New )?Opinion</b>", re.DOTALL
)
HEADING_RE = re.compile(r"\A\s*<b>(.+?)</b>")

PROPOSAL_KINDS = {"add", "revise", "update", "remove", "merge", "discussion", "discuss"}


class ParsedProposal(BaseModel):
    proposal_id: str
    kind: str
    heading: str
    section: str | None = None
    opinion_text: str | None = None
    current_opinion_text: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    message_text: str


def extract_current_opinion_text(message_text: str) -> str | None:
    match = CURRENT_OPINION_BLOCK_RE.search(message_text)
    return html.unescape(match.group(1).strip()) if match else None


def parse_proposals(messages: Iterable[TelegramMessageSpec]) -> list[ParsedProposal]:
    """Extract proposals from Telegram messages; a proposal is any message with an Approve button."""
    proposals: list[ParsedProposal] = []
    for index, message in enumerate(messages):
        approve_data = next(
            (
                button.callback_data
                for button in message.buttons
                if (button.callback_data or "").startswith("approve:")
            ),
            None,
        )
        if approve_data is None:
            continue
        heading_match = HEADING_RE.search(message.text)
        heading = html.unescape(heading_match.group(1).strip()) if heading_match else ""
        first_word = heading.split(" ")[0].lower() if heading else ""
        section_match = SECTION_RE.search(message.text)
        opinion_match = OPINION_BLOCK_RE.search(message.text)
        proposals.append(
            ParsedProposal(
                proposal_id=approve_data.removeprefix("approve:") or f"message-{index}",
                kind=first_word if first_word in PROPOSAL_KINDS else "other",
                heading=heading,
                section=html.unescape(section_match.group(1).strip()) if section_match else None,
                opinion_text=html.unescape(opinion_match.group(1).strip()) if opinion_match else None,
                current_opinion_text=extract_current_opinion_text(message.text),
                evidence_ids=list(dict.fromkeys(EVIDENCE_ID_RE.findall(message.text))),
                message_text=message.text,
            )
        )
    return proposals
