"""Tests for the Market Intelligence Agent pipeline."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from agents.market_intelligence.chunker import TranscriptChunker
from agents.market_intelligence.downloader import (
    NoTranscriptError,
    TickerNotFoundError,
    TranscriptDownloader,
)
from agents.market_intelligence.models import (
    GuidanceRevision,
    ManagementTone,
    TranscriptAnalysis,
)
from agents.market_intelligence.summarizer import TranscriptSummarizer

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TRANSCRIPT = """
Good morning, everyone, and welcome to Apple's fiscal Q3 2024 earnings call.

We had a strong quarter driven by continued Services growth and robust iPhone demand
in emerging markets. Revenue came in at $85.8 billion, up 5% year-over-year.

Looking ahead, we expect continued momentum in Services, which grew 14% this quarter.
We are raising our full-year guidance and now anticipate revenue growth in the high
single digits for fiscal 2024.

On the supply chain front, we have largely resolved the constraints we saw in prior
quarters and feel confident about our production capacity heading into the holiday season.

Analyst: Can you elaborate on the China market dynamics?

Management: We saw stabilization in China revenue after two challenging quarters. We
remain cautious but optimistic about the trajectory there. Regulatory risks persist,
but we believe our brand strength is resilient.
""" * 3  # repeat to ensure multiple chunks


_MOCK_CHUNK_TOOL_RESPONSE = MagicMock(
    stop_reason="tool_use",
    content=[
        MagicMock(
            type="tool_use",
            name="extract_chunk_analysis",
            input={
                "key_themes": ["Services growth", "iPhone demand", "China market"],
                "sentiment_signals": ["strong quarter", "robust demand", "optimistic"],
                "forward_guidance_mentions": ["raising our full-year guidance"],
                "tone": "bullish",
            },
        )
    ],
)

_MOCK_SYNTHESIS_TOOL_RESPONSE = MagicMock(
    stop_reason="tool_use",
    content=[
        MagicMock(
            type="tool_use",
            name="synthesize_transcript_analysis",
            input={
                "overall_tone": "bullish",
                "top_themes": ["Services growth", "iPhone demand", "China market"],
                "guidance_revision": "raised",
                "guidance_summary": "Apple raised full-year guidance to high single-digit revenue growth.",
                "risk_flags": ["China regulatory risk"],
                "human_readable_summary": (
                    "Apple reported a strong Q3 with 5% revenue growth driven by Services. "
                    "Management raised full-year guidance and expressed cautious optimism about China."
                ),
            },
        )
    ],
)


# ---------------------------------------------------------------------------
# Downloader tests
# ---------------------------------------------------------------------------

class TestTranscriptDownloader:
    def test_ticker_not_found_raises(self, tmp_path):
        """fetch() should raise TickerNotFoundError when EDGAR returns nothing."""
        with patch("agents.market_intelligence.downloader.Downloader") as MockDL:
            instance = MockDL.return_value
            instance.get.return_value = None  # simulates no download

            downloader = TranscriptDownloader(download_dir=str(tmp_path))
            with pytest.raises(TickerNotFoundError):
                downloader.fetch("ZZZZ")

    def test_no_transcript_raises_when_files_too_short(self, tmp_path):
        """fetch() should raise NoTranscriptError if all filing files are below the minimum."""
        ticker = "AAPL"
        filing_dir = tmp_path / "sec-edgar-filings" / ticker / "8-K" / "accession-001"
        filing_dir.mkdir(parents=True)
        (filing_dir / "full-submission.txt").write_text("Too short.", encoding="utf-8")

        with patch("agents.market_intelligence.downloader.Downloader") as MockDL:
            instance = MockDL.return_value
            instance.get.return_value = None

            downloader = TranscriptDownloader(download_dir=str(tmp_path))
            with pytest.raises(NoTranscriptError):
                downloader.fetch(ticker)

    def test_successful_extraction(self, tmp_path):
        """fetch() returns text and filing_date when transcript file is valid."""
        ticker = "AAPL"
        filing_dir = tmp_path / "sec-edgar-filings" / ticker / "8-K" / "2024-01-15"
        filing_dir.mkdir(parents=True)
        (filing_dir / "full-submission.txt").write_text(SAMPLE_TRANSCRIPT, encoding="utf-8")

        with patch("agents.market_intelligence.downloader.Downloader") as MockDL:
            instance = MockDL.return_value
            instance.get.return_value = None

            downloader = TranscriptDownloader(download_dir=str(tmp_path))
            results = downloader.fetch(ticker)

        assert len(results) == 1
        assert "2024-01-15" in (results[0]["filing_date"] or "")
        assert len(results[0]["text"]) > 100


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

class TestTranscriptChunker:
    def test_empty_text_returns_empty(self):
        chunker = TranscriptChunker()
        assert chunker.chunk("") == []
        assert chunker.chunk("   ") == []

    def test_short_text_is_single_chunk(self):
        chunker = TranscriptChunker(chunk_size=3000, overlap_size=200)
        chunks = chunker.chunk("Hello world. This is a short transcript.")
        assert len(chunks) == 1
        assert chunks[0].index == 0

    def test_long_text_produces_multiple_chunks(self):
        chunker = TranscriptChunker(chunk_size=300, overlap_size=50)
        chunks = chunker.chunk(SAMPLE_TRANSCRIPT)
        assert len(chunks) > 1

    def test_chunk_indices_are_sequential(self):
        chunker = TranscriptChunker(chunk_size=300, overlap_size=50)
        chunks = chunker.chunk(SAMPLE_TRANSCRIPT)
        indices = [c.index for c in chunks]
        assert indices == list(range(len(chunks)))


# ---------------------------------------------------------------------------
# Summarizer tests (mocked Claude API)
# ---------------------------------------------------------------------------

class TestTranscriptSummarizer:
    @pytest.fixture(autouse=True)
    def mock_claude(self):
        """Patch Anthropic client so no real API calls are made."""
        with patch("agents.market_intelligence.summarizer.get_claude_client") as mock_get:
            client = MagicMock()
            client.messages.create.side_effect = (
                # First N calls are chunk analyses, last call is synthesis
                lambda **kw: (
                    _MOCK_CHUNK_TOOL_RESPONSE
                    if kw.get("tools", [{}])[0].get("name") == "extract_chunk_analysis"
                    else _MOCK_SYNTHESIS_TOOL_RESPONSE
                )
            )
            mock_get.return_value = client
            yield client

    def test_analyze_returns_transcript_analysis(self):
        """analyze() should return a valid TranscriptAnalysis for AAPL."""
        summarizer = TranscriptSummarizer()
        result: TranscriptAnalysis = asyncio.run(
            summarizer.analyze(ticker="AAPL", text=SAMPLE_TRANSCRIPT, filing_date="2024-01-15")
        )

        assert isinstance(result, TranscriptAnalysis)
        assert result.ticker == "AAPL"
        assert result.filing_date == "2024-01-15"
        assert result.overall_tone == ManagementTone.bullish
        assert result.guidance_revision == GuidanceRevision.raised
        assert len(result.top_themes) <= 3
        assert len(result.chunk_summaries) > 0
        assert result.human_readable_summary != ""

    def test_chunk_summaries_have_correct_structure(self):
        """Each ChunkSummary should pass Pydantic validation."""
        summarizer = TranscriptSummarizer()
        result = asyncio.run(
            summarizer.analyze(ticker="AAPL", text=SAMPLE_TRANSCRIPT)
        )
        for cs in result.chunk_summaries:
            assert isinstance(cs.tone, ManagementTone)
            assert isinstance(cs.key_themes, list)
            assert cs.chunk_index >= 0
