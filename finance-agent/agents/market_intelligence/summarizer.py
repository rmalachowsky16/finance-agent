"""Map-reduce transcript summarizer using Claude's tool_use for structured extraction."""

import asyncio
import logging
from typing import Any

import anthropic

from core.claude_client import get_claude_client
from .chunker import Chunk, TranscriptChunker
from .models import (
    ChunkSummary,
    GuidanceRevision,
    ManagementTone,
    TranscriptAnalysis,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas passed to Claude for structured extraction
# ---------------------------------------------------------------------------

_CHUNK_TOOL: dict[str, Any] = {
    "name": "extract_chunk_analysis",
    "description": (
        "Extract structured analysis from a single earnings call transcript chunk. "
        "Call this tool with the analysis results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key_themes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Up to 5 key topics discussed in this chunk.",
                "maxItems": 5,
            },
            "sentiment_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Phrases indicating positive or negative management sentiment.",
            },
            "forward_guidance_mentions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paraphrases or direct quotes where management discusses future outlook.",
            },
            "tone": {
                "type": "string",
                "enum": ["bullish", "neutral", "cautious", "defensive"],
                "description": "Overall tone of this chunk.",
            },
        },
        "required": ["key_themes", "sentiment_signals", "forward_guidance_mentions", "tone"],
    },
}

_SYNTHESIS_TOOL: dict[str, Any] = {
    "name": "synthesize_transcript_analysis",
    "description": (
        "Synthesize the full-transcript analysis from per-chunk summaries. "
        "Call this tool with the consolidated results."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "overall_tone": {
                "type": "string",
                "enum": ["bullish", "neutral", "cautious", "defensive"],
                "description": "Aggregate management tone across the full call.",
            },
            "top_themes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Top 3 themes ordered by prominence.",
                "maxItems": 3,
            },
            "guidance_revision": {
                "type": "string",
                "enum": ["raised", "maintained", "lowered", "none"],
                "description": "Whether forward guidance was raised, maintained, lowered, or not provided.",
            },
            "guidance_summary": {
                "type": "string",
                "description": "One-sentence summary of guidance, or empty string if none.",
            },
            "risk_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Notable risks or concerns raised during the call.",
            },
            "human_readable_summary": {
                "type": "string",
                "description": "2-4 sentence plain-English summary for a financial dashboard.",
            },
        },
        "required": [
            "overall_tone",
            "top_themes",
            "guidance_revision",
            "guidance_summary",
            "risk_flags",
            "human_readable_summary",
        ],
    },
}


class TranscriptSummarizer:
    """
    Map-reduce summarizer: each transcript chunk is analyzed independently,
    then a synthesis step merges all chunk results into a final TranscriptAnalysis.
    """

    def __init__(self, chunker: TranscriptChunker | None = None) -> None:
        """
        Args:
            chunker: Optional pre-configured :class:`TranscriptChunker`.
                     Defaults to standard settings (3000 tokens / 200 overlap).
        """
        self._chunker = chunker or TranscriptChunker()

    async def analyze(
        self,
        ticker: str,
        text: str,
        filing_date: str | None = None,
    ) -> TranscriptAnalysis:
        """
        Full map-reduce analysis of a transcript.

        Args:
            ticker:      Stock ticker symbol.
            text:        Full transcript text.
            filing_date: Optional ISO date string of the filing.

        Returns:
            A validated :class:`TranscriptAnalysis` instance.
        """
        chunks = self._chunker.chunk(text)
        if not chunks:
            raise ValueError(f"No chunks produced for ticker '{ticker}' — transcript may be empty")

        logger.info("Analyzing %d chunk(s) for %s", len(chunks), ticker)

        # MAP: analyze all chunks concurrently (bounded to avoid rate limits)
        chunk_summaries = await self._map_chunks(chunks)

        # REDUCE: synthesize into a single analysis
        synthesis = await self._synthesize(ticker, chunk_summaries)

        return TranscriptAnalysis(
            ticker=ticker,
            filing_date=filing_date,
            overall_tone=ManagementTone(synthesis["overall_tone"]),
            top_themes=synthesis["top_themes"][:3],
            guidance_revision=GuidanceRevision(synthesis["guidance_revision"]),
            guidance_summary=synthesis["guidance_summary"] or None,
            risk_flags=synthesis["risk_flags"],
            human_readable_summary=synthesis["human_readable_summary"],
            chunk_count=len(chunks),
            chunk_summaries=chunk_summaries,
        )

    # ------------------------------------------------------------------
    # Map phase
    # ------------------------------------------------------------------

    async def _map_chunks(self, chunks: list[Chunk]) -> list[ChunkSummary]:
        """Analyze chunks concurrently with a concurrency cap of 5."""
        semaphore = asyncio.Semaphore(5)

        async def bounded(chunk: Chunk) -> ChunkSummary:
            async with semaphore:
                return await self._analyze_chunk(chunk)

        return await asyncio.gather(*[bounded(c) for c in chunks])

    async def _analyze_chunk(self, chunk: Chunk) -> ChunkSummary:
        """Send one chunk to Claude and return a ChunkSummary."""
        client = get_claude_client()
        prompt = (
            "You are a financial analyst. Analyze the following earnings call transcript excerpt.\n\n"
            f"<transcript_chunk index='{chunk.index}'>\n{chunk.text}\n</transcript_chunk>\n\n"
            "Use the extract_chunk_analysis tool to return your structured findings."
        )

        response = await asyncio.to_thread(
            client.messages.create,
            model="claude-sonnet-4-6",
            max_tokens=1024,
            tools=[_CHUNK_TOOL],
            tool_choice={"type": "tool", "name": "extract_chunk_analysis"},
            messages=[{"role": "user", "content": prompt}],
        )

        tool_input = self._extract_tool_input(response, "extract_chunk_analysis")
        return ChunkSummary(
            chunk_index=chunk.index,
            key_themes=tool_input["key_themes"],
            sentiment_signals=tool_input["sentiment_signals"],
            forward_guidance_mentions=tool_input["forward_guidance_mentions"],
            tone=ManagementTone(tool_input["tone"]),
        )

    # ------------------------------------------------------------------
    # Reduce phase
    # ------------------------------------------------------------------

    async def _synthesize(
        self, ticker: str, summaries: list[ChunkSummary]
    ) -> dict[str, Any]:
        """Send all chunk summaries to Claude and synthesize a final analysis."""
        client = get_claude_client()

        summaries_text = "\n\n".join(
            f"[Chunk {s.chunk_index}]\n"
            f"Tone: {s.tone}\n"
            f"Key themes: {', '.join(s.key_themes)}\n"
            f"Sentiment signals: {'; '.join(s.sentiment_signals)}\n"
            f"Forward guidance: {'; '.join(s.forward_guidance_mentions)}"
            for s in summaries
        )

        prompt = (
            f"You are a senior financial analyst reviewing an earnings call for {ticker}.\n"
            "Below are per-section analyses of the transcript. Synthesize them into a "
            "comprehensive overall assessment.\n\n"
            f"<chunk_summaries>\n{summaries_text}\n</chunk_summaries>\n\n"
            "Use the synthesize_transcript_analysis tool to return your structured findings."
        )

        response = await asyncio.to_thread(
            client.messages.create,
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=[_SYNTHESIS_TOOL],
            tool_choice={"type": "tool", "name": "synthesize_transcript_analysis"},
            messages=[{"role": "user", "content": prompt}],
        )

        return self._extract_tool_input(response, "synthesize_transcript_analysis")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tool_input(
        response: anthropic.types.Message, tool_name: str
    ) -> dict[str, Any]:
        """Pull the input dict from the first matching tool_use block."""
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input  # type: ignore[return-value]
        raise RuntimeError(
            f"Claude did not call the '{tool_name}' tool. "
            f"Stop reason: {response.stop_reason}. Content: {response.content}"
        )
