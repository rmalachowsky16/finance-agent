"""FastAPI route: POST /api/v1/intelligence/analyze"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agents.market_intelligence import TranscriptAnalysis
from agents.market_intelligence.downloader import (
    DownloaderError,
    NoTranscriptError,
    TickerNotFoundError,
    TranscriptDownloader,
)
from agents.market_intelligence.chunker import TranscriptChunker
from agents.market_intelligence.summarizer import TranscriptSummarizer
from core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/intelligence", tags=["market-intelligence"])


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. 'AAPL'", min_length=1, max_length=10)
    filing_type: str = Field("8-K", description="SEC filing type to fetch")
    limit: int = Field(1, ge=1, le=5, description="Number of most-recent filings to analyze")


@router.post(
    "/analyze",
    response_model=TranscriptAnalysis,
    summary="Analyze earnings call transcripts for a ticker",
    response_description="Structured transcript analysis with themes, tone, and guidance",
)
async def analyze_transcript(body: AnalyzeRequest) -> TranscriptAnalysis:
    """
    Download SEC 8-K earnings call transcript(s) for the given ticker and run
    Claude-powered analysis.

    Returns a :class:`TranscriptAnalysis` with:
    - Overall management tone
    - Top 3 themes
    - Guidance revision direction
    - Risk flags
    - Plain-English summary
    """
    settings = get_settings()
    ticker = body.ticker.upper().strip()
    logger.info("Analyze request: ticker=%s limit=%d", ticker, body.limit)

    # --- Download -----------------------------------------------------------
    downloader = TranscriptDownloader(
        company=settings.edgar_company_name,
        email=settings.edgar_email,
    )
    try:
        filings = downloader.fetch(ticker, limit=body.limit)
    except TickerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoTranscriptError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except DownloaderError as exc:
        logger.exception("EDGAR download error for %s", ticker)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    # Use the most recent filing only for the structured analysis
    filing = filings[0]

    # --- Analyze ------------------------------------------------------------
    chunker = TranscriptChunker(
        chunk_size=settings.chunk_size_tokens,
        overlap_size=settings.chunk_overlap_tokens,
    )
    summarizer = TranscriptSummarizer(chunker=chunker)

    try:
        analysis = await summarizer.analyze(
            ticker=ticker,
            text=filing["text"],
            filing_date=filing.get("filing_date"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Analysis failed for %s", ticker)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis error: {exc}",
        ) from exc

    return analysis
