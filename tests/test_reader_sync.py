from __future__ import annotations

import pytest

from opinions_agent.corpus import CorpusPaths, init_data_dirs, load_state, read_documents, read_highlights
from opinions_agent.html_to_markdown import html_to_markdown
from opinions_agent.reader import sync_reader


def doc_row(reader_id: str = "doc1", **overrides) -> dict:
    row = {
        "id": reader_id,
        "category": "article",
        "title": "Example Article",
        "author": "Jane Doe",
        "source_url": "https://example.com/article",
        "summary": "Reader generated summary.",
        "tags": {"ai": {}, "writing": {}},
        "saved_at": "2026-06-01T12:00:00Z",
        "updated_at": "2026-06-10T09:00:00Z",
        "html_content": "<h1>Example</h1><p>Body &amp; text.</p>",
        "parent_id": None,
    }
    row.update(overrides)
    return row


def highlight_row(reader_id: str = "hl1", parent_id: str = "doc1", **overrides) -> dict:
    row = {
        "id": reader_id,
        "category": "highlight",
        "content": "Highlight text here.",
        "parent_id": parent_id,
        "created_at": "2026-06-10T14:00:00Z",
        "updated_at": "2026-06-10T14:03:00Z",
    }
    row.update(overrides)
    return row


def note_row(reader_id: str = "note1", parent_id: str = "hl1", text: str = "My note.") -> dict:
    return {
        "id": reader_id,
        "category": "note",
        "content": text,
        "parent_id": parent_id,
        "created_at": "2026-06-10T14:05:00Z",
        "updated_at": "2026-06-10T14:05:00Z",
    }


class FakeReaderClient:
    def __init__(self, batches: list[list[dict]]) -> None:
        self.batches = batches
        self.calls: list[str | None] = []

    async def list_documents(self, *, updated_after: str | None = None) -> list[dict]:
        self.calls.append(updated_after)
        return self.batches.pop(0) if self.batches else []


class FailingReaderClient:
    async def list_documents(self, *, updated_after: str | None = None) -> list[dict]:
        raise RuntimeError("readwise unavailable")


@pytest.fixture
def paths(tmp_path) -> CorpusPaths:
    corpus = CorpusPaths(tmp_path / "data")
    init_data_dirs(corpus)
    return corpus


async def test_sync_creates_expected_corpus_files(paths: CorpusPaths) -> None:
    client = FakeReaderClient([[doc_row(), highlight_row(), note_row()]])

    result = await sync_reader(client, paths)

    assert result.new_documents == 1
    assert result.new_highlights == 1
    documents = read_documents(paths)
    highlights = read_highlights(paths)
    assert documents[0].document_id == "reader:doc1"
    assert documents[0].tags == ["ai", "writing"]
    assert highlights[0].highlight_id == "rw:hl1"
    assert highlights[0].document_title == "Example Article"
    assert highlights[0].document_summary == "Reader generated summary."
    assert highlights[0].note == "My note."
    assert highlights[0].highlighted_date == "2026-06-10"
    assert highlights[0].highlighted_week == "2026-W24"
    content_path = paths.data_dir / documents[0].content_path
    assert content_path == paths.document_md("doc1")
    assert "Body & text." in content_path.read_text(encoding="utf-8")
    assert paths.raw_json("doc1").exists()
    assert paths.raw_json("hl1").exists()
    state = load_state(paths)
    assert state.sync.reader_updated_after == "2026-06-10T14:05:00+00:00"
    assert state.sync.last_success_at is not None


async def test_rerunning_sync_does_not_duplicate_rows(paths: CorpusPaths) -> None:
    batch = [doc_row(), highlight_row()]
    await sync_reader(FakeReaderClient([list(batch)]), paths)
    result = await sync_reader(FakeReaderClient([list(batch)]), paths)

    assert result.new_documents == 0
    assert result.new_highlights == 0
    assert len(read_documents(paths)) == 1
    assert len(read_highlights(paths)) == 1


async def test_failed_sync_does_not_advance_state(paths: CorpusPaths) -> None:
    await sync_reader(FakeReaderClient([[doc_row()]]), paths)
    before = load_state(paths)

    with pytest.raises(RuntimeError, match="readwise unavailable"):
        await sync_reader(FailingReaderClient(), paths)

    assert load_state(paths) == before


async def test_sync_uses_state_watermark_for_updated_after(paths: CorpusPaths) -> None:
    client = FakeReaderClient([[doc_row()], []])
    await sync_reader(client, paths)
    await sync_reader(client, paths)
    assert client.calls == [None, "2026-06-10T09:00:00+00:00"]


async def test_highlight_synced_without_parent_in_batch_joins_existing_document(paths: CorpusPaths) -> None:
    await sync_reader(FakeReaderClient([[doc_row()]]), paths)
    await sync_reader(FakeReaderClient([[highlight_row()]]), paths)

    highlight = read_highlights(paths)[0]
    assert highlight.document_title == "Example Article"
    assert highlight.source_url == "https://example.com/article"
    assert highlight.content_path == "documents/reader_doc1.md"


async def test_document_update_refreshes_denormalized_highlight_fields(paths: CorpusPaths) -> None:
    await sync_reader(FakeReaderClient([[doc_row(), highlight_row()]]), paths)
    await sync_reader(FakeReaderClient([[doc_row(title="Renamed Article", updated_at="2026-06-11T09:00:00Z")]]), paths)

    highlight = read_highlights(paths)[0]
    assert highlight.document_title == "Renamed Article"


async def test_late_note_attaches_to_existing_highlight(paths: CorpusPaths) -> None:
    await sync_reader(FakeReaderClient([[doc_row(), highlight_row()]]), paths)
    await sync_reader(FakeReaderClient([[note_row(text="Late note.")]]), paths)

    assert read_highlights(paths)[0].note == "Late note."


def test_html_to_markdown_handles_headings_lists_and_entities() -> None:
    markdown = html_to_markdown(
        "<h2>Title</h2><p>One &amp; two.</p><ul><li>first</li><li>second</li></ul>"
        "<script>ignored()</script><pre>code block</pre>"
    )
    assert "## Title" in markdown
    assert "One & two." in markdown
    assert "- first" in markdown
    assert "ignored()" not in markdown
    assert "code block" in markdown
