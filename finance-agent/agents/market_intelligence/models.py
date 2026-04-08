"""Pydantic v2 schemas for Market Intelligence Agent outputs."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ManagementTone(str, Enum):
    """Overall tone inferred from management's language and framing."""

    bullish = "bullish"
    neutral = "neutral"
    cautious = "cautious"
    defensive = "defensive"


class GuidanceRevision(str, Enum):
    """Direction of forward guidance relative to prior period."""

    raised = "raised"
    maintained = "maintained"
    lowered = "lowered"
    none = "none"


class ChunkSummary(BaseModel):
    """Claude's analysis of a single transcript chunk."""

    chunk_index: int = Field(..., description="Zero-based position of this chunk in the transcript")
    key_themes: list[str] = Field(
        ...,
        description="Up to 5 key topics or themes discussed in this chunk",
        max_length=5,
    )
    sentiment_signals: list[str] = Field(
        ...,
        description="Phrases or signals indicating management sentiment (positive or negative)",
    )
    forward_guidance_mentions: list[str] = Field(
        ...,
        description="Direct quotes or paraphrases where management discusses future outlook or guidance",
    )
    tone: ManagementTone = Field(
        ..., description="Tone inferred from this chunk's language"
    )


class TranscriptAnalysis(BaseModel):
    """Final synthesized analysis of a full earnings call transcript."""

    ticker: str = Field(..., description="Stock ticker symbol")
    filing_date: Optional[str] = Field(None, description="Date of the 8-K filing (YYYY-MM-DD)")
    overall_tone: ManagementTone = Field(
        ..., description="Aggregate management tone across the full transcript"
    )
    top_themes: list[str] = Field(
        ...,
        description="Top 3 themes across the entire transcript, ordered by prominence",
        max_length=3,
    )
    guidance_revision: GuidanceRevision = Field(
        ..., description="Whether guidance was raised, maintained, lowered, or not given"
    )
    guidance_summary: Optional[str] = Field(
        None, description="One-sentence summary of guidance if provided"
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="Notable risk factors or concerns raised by management or analysts",
    )
    human_readable_summary: str = Field(
        ..., description="2-4 sentence plain-English summary suitable for a financial dashboard"
    )
    chunk_count: int = Field(..., description="Number of chunks the transcript was split into")
    chunk_summaries: list[ChunkSummary] = Field(
        ..., description="Per-chunk analysis results"
    )
