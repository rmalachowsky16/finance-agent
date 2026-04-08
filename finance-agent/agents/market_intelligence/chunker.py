"""Transcript chunker: splits long text into overlapping token-bounded chunks."""

import logging
import re
from dataclasses import dataclass

import tiktoken

logger = logging.getLogger(__name__)

_DEFAULT_ENCODING = "cl100k_base"  # matches claude-sonnet-4-6's tokenizer family


@dataclass
class Chunk:
    """A single text chunk with its position metadata."""

    index: int
    text: str
    token_count: int
    char_start: int
    char_end: int


class TranscriptChunker:
    """
    Splits transcript text into overlapping chunks that fit within Claude's context.

    Strategy:
    1. Split on paragraph boundaries (double newline).
    2. If a paragraph is itself too large, split further on sentence boundaries.
    3. Greedily accumulate paragraphs until chunk_size is reached.
    4. Backtrack by overlap_size tokens before starting the next chunk.
    """

    def __init__(
        self,
        chunk_size: int = 3000,
        overlap_size: int = 200,
        encoding_name: str = _DEFAULT_ENCODING,
    ) -> None:
        """
        Args:
            chunk_size:    Maximum tokens per chunk (exclusive of overlap).
            overlap_size:  Tokens of context carried over from the previous chunk.
            encoding_name: tiktoken encoding to use for token counting.
        """
        if overlap_size >= chunk_size:
            raise ValueError("overlap_size must be less than chunk_size")
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self._enc = tiktoken.get_encoding(encoding_name)

    def chunk(self, text: str) -> list[Chunk]:
        """
        Split *text* into overlapping chunks.

        Args:
            text: Full transcript text to split.

        Returns:
            Ordered list of :class:`Chunk` objects. Empty list if text is blank.
        """
        if not text or not text.strip():
            return []

        segments = self._split_to_segments(text)
        if not segments:
            return []

        chunks: list[Chunk] = []
        current_segments: list[str] = []
        current_tokens: list[list[int]] = []
        chunk_index = 0

        for seg in segments:
            seg_tokens = self._encode(seg)

            # A single segment exceeds the chunk size — hard-split it
            if len(seg_tokens) > self.chunk_size:
                # Flush current buffer first
                if current_segments:
                    chunk = self._build_chunk(chunk_index, current_segments, text)
                    chunks.append(chunk)
                    chunk_index += 1
                    current_segments, current_tokens = self._trim_to_overlap(
                        current_segments, current_tokens
                    )

                # Hard-split the oversized segment
                for sub_chunk in self._hard_split(seg, seg_tokens):
                    chunks.append(Chunk(
                        index=chunk_index,
                        text=sub_chunk,
                        token_count=len(self._encode(sub_chunk)),
                        char_start=text.find(sub_chunk),
                        char_end=text.find(sub_chunk) + len(sub_chunk),
                    ))
                    chunk_index += 1
                continue

            # Would adding this segment exceed the limit?
            total = sum(len(t) for t in current_tokens) + len(seg_tokens)
            if total > self.chunk_size and current_segments:
                chunk = self._build_chunk(chunk_index, current_segments, text)
                chunks.append(chunk)
                chunk_index += 1
                current_segments, current_tokens = self._trim_to_overlap(
                    current_segments, current_tokens
                )

            current_segments.append(seg)
            current_tokens.append(seg_tokens)

        # Flush remainder
        if current_segments:
            chunk = self._build_chunk(chunk_index, current_segments, text)
            chunks.append(chunk)

        logger.info(
            "Split transcript (%d chars) into %d chunk(s) (~%d tokens each)",
            len(text),
            len(chunks),
            self.chunk_size,
        )
        return chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _encode(self, text: str) -> list[int]:
        return self._enc.encode(text)

    def _split_to_segments(self, text: str) -> list[str]:
        """Split on paragraph boundaries, then sentence boundaries for large paragraphs."""
        paragraphs = re.split(r"\n\s*\n", text)
        segments: list[str] = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(self._encode(para)) > self.chunk_size:
                # Break oversized paragraph into sentences
                sentences = re.split(r"(?<=[.!?])\s+", para)
                segments.extend(s.strip() for s in sentences if s.strip())
            else:
                segments.append(para)
        return segments

    def _trim_to_overlap(
        self,
        segments: list[str],
        tokens: list[list[int]],
    ) -> tuple[list[str], list[list[int]]]:
        """Drop leading segments until the retained tail is ≤ overlap_size tokens."""
        while segments and sum(len(t) for t in tokens) > self.overlap_size:
            segments.pop(0)
            tokens.pop(0)
        return segments, tokens

    def _build_chunk(self, index: int, segments: list[str], full_text: str) -> Chunk:
        text = "\n\n".join(segments)
        token_count = len(self._encode(text))
        char_start = full_text.find(segments[0])
        char_end = char_start + len(text)
        return Chunk(index=index, text=text, token_count=token_count, char_start=char_start, char_end=char_end)

    def _hard_split(self, text: str, tokens: list[int]) -> list[str]:
        """Token-boundary hard split for segments that exceed chunk_size on their own."""
        results: list[str] = []
        for i in range(0, len(tokens), self.chunk_size - self.overlap_size):
            window = tokens[max(0, i - self.overlap_size): i + self.chunk_size]
            results.append(self._enc.decode(window))
        return results
