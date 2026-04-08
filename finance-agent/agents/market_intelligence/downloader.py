"""SEC EDGAR downloader for 8-K earnings call transcripts."""

import logging
import re
from pathlib import Path
from typing import Optional

from sec_edgar_downloader import Downloader

logger = logging.getLogger(__name__)

# 8-K items that commonly contain earnings call transcripts
_TRANSCRIPT_ITEM_PATTERN = re.compile(
    r"item\s+(?:2\.02|7\.01|9\.01)",
    re.IGNORECASE,
)

# Rough heuristic: a real transcript has substantial Q&A dialogue
_MIN_TRANSCRIPT_CHARS = 2000


class DownloaderError(Exception):
    """Base error for downloader failures."""


class TickerNotFoundError(DownloaderError):
    """Raised when no filings are found for the given ticker."""


class NoTranscriptError(DownloaderError):
    """Raised when filings exist but contain no usable transcript text."""


class TranscriptDownloader:
    """Downloads and extracts earnings call transcript text from SEC EDGAR 8-K filings."""

    def __init__(self, download_dir: str = "/tmp/sec_filings", company: str = "FinanceAgent", email: str = "agent@example.com") -> None:
        """
        Args:
            download_dir: Local directory where SEC filings are saved.
            company:      Company name sent to EDGAR as part of the user-agent.
            email:        Contact email sent to EDGAR as part of the user-agent.
        """
        self._download_dir = Path(download_dir)
        self._downloader = Downloader(company, email, self._download_dir)

    def fetch(self, ticker: str, limit: int = 1) -> list[dict]:
        """
        Download the most recent 8-K filings for *ticker* and extract transcript text.

        Args:
            ticker: Stock ticker symbol (e.g. "AAPL").
            limit:  Maximum number of filings to retrieve.

        Returns:
            List of dicts with keys ``filing_date`` (str | None) and ``text`` (str).

        Raises:
            TickerNotFoundError: If no 8-K filings exist for the ticker.
            NoTranscriptError:   If filings were found but no transcript text could be extracted.
            DownloaderError:     For unexpected EDGAR / filesystem errors.
        """
        ticker = ticker.upper().strip()
        logger.info("Fetching %d 8-K filing(s) for %s", limit, ticker)

        try:
            self._downloader.get("8-K", ticker, limit=limit)
        except Exception as exc:
            raise DownloaderError(f"EDGAR download failed for {ticker}: {exc}") from exc

        filing_root = self._download_dir / "sec-edgar-filings" / ticker / "8-K"
        if not filing_root.exists():
            raise TickerNotFoundError(f"No 8-K filings found for ticker '{ticker}'")

        filing_dirs = sorted(filing_root.iterdir(), reverse=True)
        if not filing_dirs:
            raise TickerNotFoundError(f"No 8-K filing directories for '{ticker}'")

        results: list[dict] = []
        for filing_dir in filing_dirs[:limit]:
            entry = self._extract_from_dir(filing_dir, ticker)
            if entry:
                results.append(entry)

        if not results:
            raise NoTranscriptError(
                f"Downloaded {len(filing_dirs)} 8-K filing(s) for '{ticker}' "
                "but could not extract usable transcript text."
            )

        logger.info("Extracted %d transcript(s) for %s", len(results), ticker)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_from_dir(self, filing_dir: Path, ticker: str) -> Optional[dict]:
        """Return a single filing dict, or None if no transcript text found."""
        filing_date = self._parse_filing_date(filing_dir)

        # Prefer full-submission text file; fall back to any .txt / .htm
        candidates = list(filing_dir.glob("full-submission.txt"))
        if not candidates:
            candidates = list(filing_dir.glob("*.txt")) + list(filing_dir.glob("*.htm"))

        for path in candidates:
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Could not read %s: %s", path, exc)
                continue

            text = self._clean_text(raw)
            if len(text) >= _MIN_TRANSCRIPT_CHARS:
                return {"filing_date": filing_date, "text": text}

        logger.debug("No usable transcript in %s", filing_dir)
        return None

    @staticmethod
    def _clean_text(raw: str) -> str:
        """Strip HTML tags and collapse whitespace."""
        # Remove HTML/XML tags
        text = re.sub(r"<[^>]+>", " ", raw)
        # Collapse runs of whitespace to single space, preserve paragraph breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _parse_filing_date(filing_dir: Path) -> Optional[str]:
        """
        Attempt to extract the filing date from the directory name or metadata.
        EDGAR directories are often named with the accession number; we look for
        a YYYY-MM-DD pattern anywhere in the path.
        """
        match = re.search(r"(\d{4}-\d{2}-\d{2})", str(filing_dir))
        return match.group(1) if match else None
