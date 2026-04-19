"""Comprehensive tests for the oversized-chunk re-splitting logic.

Covers every helper function, edge case, and integration path introduced
to prevent chunks from exceeding the embedder's token budget.
"""

from __future__ import annotations

import pytest

from guru_core.types import ChunkingConfig, MatchConfig, Rule
from guru_server.ingestion import Chunk, MarkdownParser
from guru_server.ingestion.markdown import (
    DEFAULT_TOKEN_BUDGET,
    _estimate_tokens,
    _hard_split,
    _merge_segments,
    _resplit_chunk,
    _split_on_paragraphs,
    _split_on_sentences,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def parser() -> MarkdownParser:
    return MarkdownParser()


@pytest.fixture
def rule() -> Rule:
    return Rule(ruleName="test", match=MatchConfig(glob="**/*.md"), labels=["docs"])


def _make_chunk(
    content: str,
    *,
    breadcrumb: str = "Section",
    level: int = 2,
    chunk_id: str = "orig0000",
    frontmatter: dict | None = None,
    labels: list[str] | None = None,
    kind: str = "markdown_section",
    language: str = "markdown",
    artifact_qualname: str | None = "kb::doc::Section",
    parent_document_id: str | None = "kb::doc",
    parent_chunk_id: str | None = None,
) -> Chunk:
    """Factory for Chunk instances used in unit tests."""
    return Chunk(
        content=content,
        file_path="/test.md",
        header_breadcrumb=breadcrumb,
        chunk_level=level,
        chunk_id=chunk_id,
        frontmatter=frontmatter or {},
        labels=labels or ["docs"],
        kind=kind,
        language=language,
        artifact_qualname=artifact_qualname,
        parent_document_id=parent_document_id,
        parent_chunk_id=parent_chunk_id,
    )


# ============================================================================
# _estimate_tokens
# ============================================================================


class TestEstimateTokens:
    def test_empty_string(self):
        assert _estimate_tokens("") == 0

    def test_single_char(self):
        assert _estimate_tokens("a") == 0  # 1 // 4 = 0

    def test_three_chars(self):
        assert _estimate_tokens("abc") == 0  # 3 // 4 = 0

    def test_four_chars(self):
        assert _estimate_tokens("abcd") == 1

    def test_exact_multiple_of_four(self):
        assert _estimate_tokens("a" * 100) == 25

    def test_not_multiple_of_four_floors(self):
        assert _estimate_tokens("a" * 101) == 25  # 101 // 4 = 25

    def test_whitespace_only(self):
        assert _estimate_tokens("    ") == 1  # 4 spaces = 1 token

    def test_newlines_count(self):
        assert _estimate_tokens("\n\n\n\n") == 1

    def test_unicode_multibyte(self):
        # Python len() counts characters, not bytes.
        text = "日本語テスト"  # 6 chars
        assert _estimate_tokens(text) == 1  # 6 // 4 = 1

    def test_large_text(self):
        assert _estimate_tokens("x" * 8000) == 2000


# ============================================================================
# _split_on_paragraphs
# ============================================================================


class TestSplitOnParagraphs:
    def test_single_paragraph(self):
        result = _split_on_paragraphs("Hello world this is one paragraph.")
        assert result == ["Hello world this is one paragraph."]

    def test_two_paragraphs(self):
        result = _split_on_paragraphs("Para one.\n\nPara two.")
        assert result == ["Para one.", "Para two."]

    def test_triple_newlines(self):
        result = _split_on_paragraphs("A\n\n\nB")
        assert result == ["A", "B"]

    def test_many_blank_lines(self):
        result = _split_on_paragraphs("A\n\n\n\n\nB")
        assert result == ["A", "B"]

    def test_leading_blank_lines(self):
        result = _split_on_paragraphs("\n\nA\n\nB")
        assert result == ["A", "B"]

    def test_trailing_blank_lines(self):
        result = _split_on_paragraphs("A\n\nB\n\n")
        assert result == ["A", "B"]

    def test_empty_string(self):
        result = _split_on_paragraphs("")
        assert result == []

    def test_whitespace_only_paragraphs_filtered(self):
        result = _split_on_paragraphs("A\n\n   \n\nB")
        assert result == ["A", "B"]

    def test_single_newline_does_not_split(self):
        result = _split_on_paragraphs("Line one.\nLine two.")
        assert result == ["Line one.\nLine two."]

    def test_preserves_internal_single_newlines(self):
        text = "First line\nSecond line\n\nNew paragraph"
        result = _split_on_paragraphs(text)
        assert len(result) == 2
        assert result[0] == "First line\nSecond line"

    def test_code_block_stays_together(self):
        text = "```python\ndef foo():\n    pass\n```"
        result = _split_on_paragraphs(text)
        assert len(result) == 1


# ============================================================================
# _split_on_sentences
# ============================================================================


class TestSplitOnSentences:
    def test_period_space(self):
        result = _split_on_sentences("Hello. World.")
        assert result == ["Hello.", "World."]

    def test_exclamation(self):
        result = _split_on_sentences("Wow! Great.")
        assert result == ["Wow!", "Great."]

    def test_question_mark(self):
        result = _split_on_sentences("Why? Because.")
        assert result == ["Why?", "Because."]

    def test_no_sentence_boundary(self):
        result = _split_on_sentences("Hello world")
        assert result == ["Hello world"]

    def test_sentence_at_end_no_trailing_space(self):
        # Sentence ends at end of text — no space after punctuation.
        result = _split_on_sentences("One sentence.")
        assert result == ["One sentence."]

    def test_abbreviation_false_positive(self):
        # "e.g. something" may split — this is an accepted trade-off
        # The important thing is that the result stays under budget.
        result = _split_on_sentences("Use e.g. Python for scripting.")
        assert len(result) >= 1  # may split, but always non-empty

    def test_multiple_spaces_after_period(self):
        result = _split_on_sentences("Foo.  Bar.")
        # Regex splits on space(s) after punctuation
        assert "Foo." in result
        assert any("Bar." in s for s in result)

    def test_empty_string(self):
        result = _split_on_sentences("")
        assert result == []

    def test_whitespace_only_segments_filtered(self):
        result = _split_on_sentences("A.   ")
        # The trailing whitespace after split should be filtered
        assert all(s.strip() for s in result)

    def test_newline_after_period(self):
        # Newlines are whitespace but the regex uses \s+ after [.!?]
        result = _split_on_sentences("End.\nStart.")
        # \n is whitespace, so it should split
        assert len(result) == 2

    def test_many_sentences(self):
        text = " ".join(f"Sentence {i}." for i in range(20))
        result = _split_on_sentences(text)
        assert len(result) == 20


# ============================================================================
# _merge_segments
# ============================================================================


class TestMergeSegments:
    def test_empty_list(self):
        assert _merge_segments([], budget=100, separator="\n\n") == []

    def test_single_segment_under_budget(self):
        result = _merge_segments(["Hello"], budget=100, separator="\n\n")
        assert result == ["Hello"]

    def test_single_segment_over_budget(self):
        # A single oversized segment can't be split by merge — it stays as-is
        big = "A" * 800  # 200 tokens
        result = _merge_segments([big], budget=50, separator="\n\n")
        assert result == [big]

    def test_two_segments_fit_in_one(self):
        result = _merge_segments(["AA", "BB"], budget=100, separator="\n\n")
        assert result == ["AA\n\nBB"]

    def test_two_segments_dont_fit(self):
        a = "A" * 100  # 25 tokens
        b = "B" * 100  # 25 tokens
        result = _merge_segments([a, b], budget=30, separator="\n\n")
        assert result == [a, b]

    def test_three_segments_first_two_fit(self):
        a = "A" * 40  # 10 tokens
        b = "B" * 40  # 10 tokens
        c = "C" * 40  # 10 tokens
        result = _merge_segments([a, b, c], budget=25, separator="\n\n")
        assert len(result) == 2
        assert result[0] == f"{a}\n\n{b}"
        assert result[1] == c

    def test_separator_cost_affects_merge(self):
        # With a separator that costs tokens, two segments that would
        # fit without separator may not fit with it.
        a = "A" * 96  # 24 tokens
        b = "B" * 96  # 24 tokens
        sep = "X" * 20  # 5 tokens, so total would be 24+5+24 = 53
        result = _merge_segments([a, b], budget=50, separator=sep)
        assert result == [a, b]

    def test_empty_separator(self):
        a = "A" * 40  # 10 tokens
        b = "B" * 40  # 10 tokens
        result = _merge_segments([a, b], budget=25, separator="")
        assert result == [a + b]

    def test_many_small_segments_merge_greedily(self):
        segs = ["W" * 8 for _ in range(10)]  # each 2 tokens
        result = _merge_segments(segs, budget=15, separator=" ")
        # Segments are greedily merged. With ~2 tokens per segment and a
        # space separator that rounds to 0 by _estimate_tokens, merging is
        # approximate. Verify that merging actually happened.
        assert 1 < len(result) < 10

    def test_preserves_all_content(self):
        segs = ["alpha", "beta", "gamma"]
        result = _merge_segments(segs, budget=5, separator="|")
        combined = "|".join(result)
        for s in segs:
            assert s in combined

    def test_paragraph_separator(self):
        result = _merge_segments(["A", "B"], budget=100, separator="\n\n")
        assert result == ["A\n\nB"]

    def test_sentence_separator(self):
        result = _merge_segments(["A.", "B."], budget=100, separator=" ")
        assert result == ["A. B."]

    def test_exact_budget_boundary(self):
        # seg = 10 tokens exactly, budget = 10 → should fit alone
        seg = "A" * 40  # 10 tokens
        result = _merge_segments([seg], budget=10, separator="\n\n")
        assert result == [seg]

    def test_two_segments_exactly_at_budget_with_separator(self):
        # Each 4 tokens, separator 0 tokens (empty), budget = 8
        a = "A" * 16  # 4 tokens
        b = "B" * 16  # 4 tokens
        result = _merge_segments([a, b], budget=8, separator="")
        assert result == [a + b]


# ============================================================================
# _hard_split
# ============================================================================


class TestHardSplit:
    def test_text_under_budget(self):
        result = _hard_split("Hello", budget=100)
        assert result == ["Hello"]

    def test_text_exactly_at_budget(self):
        text = "A" * 400  # 100 tokens
        result = _hard_split(text, budget=100)
        assert result == [text]

    def test_text_over_budget(self):
        text = "A" * 800  # 200 tokens
        result = _hard_split(text, budget=100)
        assert len(result) == 2
        assert result[0] == "A" * 400
        assert result[1] == "A" * 400

    def test_text_not_even_multiple(self):
        text = "A" * 500  # 125 tokens
        result = _hard_split(text, budget=100)
        assert len(result) == 2
        assert len(result[0]) == 400
        assert len(result[1]) == 100

    def test_empty_text(self):
        result = _hard_split("", budget=100)
        # range(0, 0, 400) produces nothing
        assert result == []

    def test_large_text_many_pieces(self):
        text = "X" * 4000  # 1000 tokens
        result = _hard_split(text, budget=100)
        assert len(result) == 10
        for piece in result:
            assert len(piece) == 400

    def test_budget_one(self):
        text = "ABCD"  # 1 token
        result = _hard_split(text, budget=1)
        assert result == ["ABCD"]

    def test_preserves_all_content(self):
        text = "Hello World! This is a test."
        result = _hard_split(text, budget=3)  # 12 chars per piece
        assert "".join(result) == text


# ============================================================================
# _resplit_chunk — core logic
# ============================================================================


class TestResplitChunk:
    # --- passthrough cases ---

    def test_under_budget_returns_original(self):
        chunk = _make_chunk("Short text")
        result = _resplit_chunk(chunk, budget=1900)
        assert result == [chunk]
        assert result[0] is chunk

    def test_exactly_at_budget_returns_original(self):
        content = "A" * (1900 * 4)  # exactly 1900 tokens
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=1900)
        assert len(result) == 1
        assert result[0] is chunk

    def test_empty_content_returns_original(self):
        chunk = _make_chunk("")
        result = _resplit_chunk(chunk, budget=100)
        assert len(result) == 1
        assert result[0] is chunk

    # --- paragraph splitting ---

    def test_splits_on_paragraphs(self):
        para = "P" * 200  # 50 tokens
        content = f"{para}\n\n{para}\n\n{para}\n\n{para}"
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=60)
        assert len(result) >= 2
        for sub in result:
            assert _estimate_tokens(sub.content) <= 60

    def test_merges_small_paragraphs_together(self):
        # Each paragraph is 5 tokens, budget is 20 → multiple paras merge
        para = "P" * 20  # 5 tokens
        content = "\n\n".join([para] * 6)  # ~30 tokens total
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=20)
        # Some paragraphs should be merged together
        assert len(result) < 6

    def test_paragraph_split_preserves_content(self):
        paragraphs = [f"Paragraph {i} " + "x" * 100 for i in range(5)]
        content = "\n\n".join(paragraphs)
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=40)
        all_content = "\n\n".join(sub.content for sub in result)
        for p in paragraphs:
            assert p in all_content

    # --- sentence splitting ---

    def test_splits_on_sentences_when_paragraph_too_big(self):
        # One giant paragraph with many sentences
        sentences = [f"Sentence number {i} with some words." for i in range(40)]
        content = " ".join(sentences)
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=100)
        assert len(result) >= 2
        for sub in result:
            assert _estimate_tokens(sub.content) <= 100

    def test_mixed_paragraph_and_sentence_split(self):
        # Small paragraph (fits) + huge paragraph (needs sentence split)
        small = "Small paragraph here."
        big_sentences = " ".join(
            [f"This is sentence {i} in the big paragraph." for i in range(50)]
        )
        content = f"{small}\n\n{big_sentences}"
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=100)
        assert len(result) >= 2
        for sub in result:
            assert _estimate_tokens(sub.content) <= 100

    # --- hard cut ---

    def test_hard_cut_no_sentence_boundaries(self):
        content = "X" * 8000  # 2000 tokens, no spaces or periods
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=500)
        assert len(result) >= 2
        for sub in result:
            assert _estimate_tokens(sub.content) <= 500
        assert "".join(sub.content for sub in result) == content

    def test_hard_cut_after_sentence_split_still_too_big(self):
        # Single sentence that's massive — no sentence break inside
        content = "A" * 4000 + "."  # One huge "sentence"
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=200)
        assert len(result) >= 2
        for sub in result:
            assert _estimate_tokens(sub.content) <= 200

    # --- three-stage cascading ---

    def test_all_three_stages_in_one_chunk(self):
        # Multiple paragraphs: some fit, one huge paragraph with sentences,
        # one huge paragraph without sentence boundaries
        para_ok = "OK paragraph. " * 5  # small
        para_sentences = " ".join(
            [f"Sentence {i} has content." for i in range(40)]
        )  # needs sentence split
        para_hard = "Z" * 4000  # needs hard cut
        content = f"{para_ok}\n\n{para_sentences}\n\n{para_hard}"
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=200)
        assert len(result) >= 3
        for sub in result:
            assert _estimate_tokens(sub.content) <= 200

    # --- metadata preservation ---

    def test_preserves_file_path(self):
        chunk = _make_chunk("A" * 800 + "\n\n" + "B" * 800)
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.file_path == "/test.md"

    def test_preserves_chunk_level(self):
        chunk = _make_chunk("A" * 800 + "\n\n" + "B" * 800, level=3)
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.chunk_level == 3

    def test_preserves_frontmatter(self):
        fm = {"title": "Test", "version": "1.0"}
        chunk = _make_chunk(
            "A" * 800 + "\n\n" + "B" * 800,
            frontmatter=fm,
        )
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.frontmatter == fm

    def test_preserves_labels(self):
        chunk = _make_chunk(
            "A" * 800 + "\n\n" + "B" * 800,
            labels=["api", "docs"],
        )
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.labels == ["api", "docs"]

    def test_preserves_kind(self):
        chunk = _make_chunk("A" * 800 + "\n\n" + "B" * 800, kind="markdown_section")
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.kind == "markdown_section"

    def test_preserves_language(self):
        chunk = _make_chunk("A" * 800 + "\n\n" + "B" * 800, language="markdown")
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.language == "markdown"

    def test_preserves_parent_document_id(self):
        chunk = _make_chunk(
            "A" * 800 + "\n\n" + "B" * 800,
            parent_document_id="kb::readme.md",
        )
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.parent_document_id == "kb::readme.md"

    def test_preserves_parent_chunk_id(self):
        chunk = _make_chunk(
            "A" * 800 + "\n\n" + "B" * 800,
            parent_chunk_id="parent123",
        )
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.parent_chunk_id == "parent123"

    # --- breadcrumb numbering ---

    def test_breadcrumb_part_numbering_starts_at_1(self):
        content = "\n\n".join(["X" * 200] * 4)
        chunk = _make_chunk(content, breadcrumb="Doc > Sec")
        result = _resplit_chunk(chunk, budget=60)
        for i, sub in enumerate(result):
            assert sub.header_breadcrumb == f"Doc > Sec#part-{i + 1}"

    def test_breadcrumb_special_chars(self):
        content = "A" * 800 + "\n\n" + "B" * 800
        chunk = _make_chunk(content, breadcrumb="Root > Section (v2.0)")
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.header_breadcrumb.startswith("Root > Section (v2.0)")

    def test_breadcrumb_document_level(self):
        content = "A" * 800 + "\n\n" + "B" * 800
        chunk = _make_chunk(content, breadcrumb="Document")
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.header_breadcrumb.startswith("Document")

    # --- chunk ID ---

    def test_chunk_ids_are_unique(self):
        content = "\n\n".join(["X" * 200] * 6)
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=60)
        ids = [c.chunk_id for c in result]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_are_16_chars(self):
        content = "\n\n".join(["X" * 200] * 4)
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=60)
        for sub in result:
            assert len(sub.chunk_id) == 16

    def test_chunk_ids_deterministic(self):
        content = "\n\n".join(["X" * 200] * 4)
        chunk1 = _make_chunk(content, chunk_id="same_id")
        chunk2 = _make_chunk(content, chunk_id="same_id")
        r1 = _resplit_chunk(chunk1, budget=60)
        r2 = _resplit_chunk(chunk2, budget=60)
        assert [c.chunk_id for c in r1] == [c.chunk_id for c in r2]

    def test_chunk_ids_differ_for_different_originals(self):
        content = "\n\n".join(["X" * 200] * 4)
        chunk1 = _make_chunk(content, chunk_id="id_alpha")
        chunk2 = _make_chunk(content, chunk_id="id_beta")
        r1 = _resplit_chunk(chunk1, budget=60)
        r2 = _resplit_chunk(chunk2, budget=60)
        assert [c.chunk_id for c in r1] != [c.chunk_id for c in r2]

    # --- content_type detection on sub-chunks ---

    def test_content_type_text_on_plain_sub_chunks(self):
        content = "Plain text. " * 300
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=100)
        for sub in result:
            assert sub.content_type == "text"

    def test_content_type_code_on_code_sub_chunk(self):
        # First sub-chunk has code, second doesn't
        code_para = "```python\ndef foo():\n    pass\n```\n" + "x" * 600
        text_para = "Just plain text. " * 30
        content = f"{code_para}\n\n{text_para}"
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=100)
        code_subs = [s for s in result if "```" in s.content]
        text_subs = [s for s in result if "```" not in s.content and "|" not in s.content]
        for s in code_subs:
            assert s.content_type == "code"
        for s in text_subs:
            assert s.content_type == "text"

    def test_content_type_table_on_table_sub_chunk(self):
        table = "| Col1 | Col2 |\n|------|------|\n| a | b |\n" * 30
        text = "Just text. " * 100
        content = f"{table}\n\n{text}"
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=100)
        table_subs = [s for s in result if "|" in s.content]
        for s in table_subs:
            assert s.content_type in ("table", "mixed")

    # --- edge case: very small budget ---

    def test_very_small_budget(self):
        content = "Hello world. This is a test."
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk, budget=2)
        for sub in result:
            assert _estimate_tokens(sub.content) <= 2

    # --- default budget constant ---

    def test_default_budget_value(self):
        assert DEFAULT_TOKEN_BUDGET == 1900

    def test_resplit_uses_default_budget(self):
        # Content just over 1900 tokens
        content = "A" * (1901 * 4)
        chunk = _make_chunk(content)
        result = _resplit_chunk(chunk)  # uses default budget
        assert len(result) >= 2


# ============================================================================
# MarkdownParser._resplit_oversized (static method)
# ============================================================================


class TestResplitOversized:
    def test_empty_list(self):
        result = MarkdownParser._resplit_oversized([])
        assert result == []

    def test_all_under_budget(self):
        chunks = [_make_chunk("short", chunk_id=f"id{i}") for i in range(3)]
        result = MarkdownParser._resplit_oversized(chunks, budget=1900)
        assert len(result) == 3
        for orig, res in zip(chunks, result, strict=True):
            assert res is orig

    def test_all_oversized(self):
        chunks = [
            _make_chunk("X" * 800 + "\n\n" + "Y" * 800, chunk_id=f"id{i}")
            for i in range(3)
        ]
        result = MarkdownParser._resplit_oversized(chunks, budget=100)
        assert len(result) > 3
        for sub in result:
            assert _estimate_tokens(sub.content) <= 100

    def test_mix_of_small_and_oversized(self):
        small = _make_chunk("Tiny", chunk_id="small")
        big = _make_chunk("X" * 800 + "\n\n" + "Y" * 800, chunk_id="big")
        result = MarkdownParser._resplit_oversized([small, big], budget=100)
        assert result[0] is small
        assert len(result) > 2

    def test_preserves_order(self):
        c1 = _make_chunk("First content", chunk_id="c1", breadcrumb="First")
        c2 = _make_chunk(
            "X" * 800 + "\n\n" + "Y" * 800, chunk_id="c2", breadcrumb="Second"
        )
        c3 = _make_chunk("Third content", chunk_id="c3", breadcrumb="Third")
        result = MarkdownParser._resplit_oversized([c1, c2, c3], budget=100)
        assert result[0] is c1
        assert result[-1] is c3
        middle = result[1:-1]
        for sub in middle:
            assert sub.header_breadcrumb.startswith("Second")

    def test_single_under_budget(self):
        chunk = _make_chunk("Just fine")
        result = MarkdownParser._resplit_oversized([chunk])
        assert result == [chunk]

    def test_single_oversized(self):
        chunk = _make_chunk("X" * 800 + "\n\n" + "Y" * 800, chunk_id="solo")
        result = MarkdownParser._resplit_oversized([chunk], budget=100)
        assert len(result) >= 2


# ============================================================================
# Integration: parse() with resplit
# ============================================================================


class TestParseIntegrationResplit:
    def test_all_sections_small_no_resplit(self, parser, tmp_path, rule):
        md = "# Title\n\nSmall content.\n\n## Sec\n\nAlso small.\n"
        p = tmp_path / "small.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            # No #part- suffix on small chunks
            assert "#part-" not in c.header_breadcrumb

    def test_one_oversized_others_small(self, parser, tmp_path, rule):
        big = "Word. " * 2000  # ~12000 chars
        md = f"# Title\n\nSmall.\n\n## Big\n\n{big}\n\n## Small\n\nTiny.\n"
        p = tmp_path / "mixed.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert _estimate_tokens(c.content) <= DEFAULT_TOKEN_BUDGET

    def test_multiple_oversized_sections(self, parser, tmp_path, rule):
        big1 = "Alpha. " * 2000
        big2 = "Beta. " * 2000
        md = f"# Title\n\n## One\n\n{big1}\n\n## Two\n\n{big2}\n"
        p = tmp_path / "multi.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert _estimate_tokens(c.content) <= DEFAULT_TOKEN_BUDGET
        one_chunks = [c for c in result.chunks if "One" in c.header_breadcrumb]
        two_chunks = [c for c in result.chunks if "Two" in c.header_breadcrumb]
        assert len(one_chunks) >= 2
        assert len(two_chunks) >= 2

    def test_oversized_after_h2_merge(self, parser, tmp_path):
        """When h2 merge produces an oversized chunk, resplit must fix it."""
        rule_h2 = Rule(
            ruleName="test",
            match=MatchConfig(glob="**/*.md"),
            labels=["docs"],
            chunking=ChunkingConfig(split_level="h2", max_tokens=800),
        )
        # Each h3 is small, but combined under h2 they exceed budget
        h3_content = "Content here. " * 300  # ~4200 chars = ~1050 tokens each
        md = (
            "# Title\n\n"
            "## Section A\n\nIntro.\n\n"
            f"### Sub 1\n\n{h3_content}\n\n"
            f"### Sub 2\n\n{h3_content}\n\n"
            "## Section B\n\nSmall.\n"
        )
        p = tmp_path / "merge_big.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule_h2, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert _estimate_tokens(c.content) <= DEFAULT_TOKEN_BUDGET

    def test_all_chunk_ids_unique_after_resplit(self, parser, tmp_path, rule):
        big = "Sentence here. " * 1500
        md = f"# Title\n\n{big}\n\n## Sec\n\n{big}\n"
        p = tmp_path / "ids.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        ids = [c.chunk_id for c in result.chunks]
        assert len(ids) == len(set(ids))

    def test_non_resplit_chunks_breadcrumb_unchanged(self, parser, tmp_path, rule):
        big = "Big text. " * 2000
        md = f"# Title\n\nSmall.\n\n## Big\n\n{big}\n\n## Tiny\n\nHello.\n"
        p = tmp_path / "bc.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        tiny_chunks = [c for c in result.chunks if "Tiny" in c.header_breadcrumb]
        assert tiny_chunks
        for c in tiny_chunks:
            assert "#part-" not in c.header_breadcrumb

    def test_oversized_with_code_blocks(self, parser, tmp_path, rule):
        code = "```python\n" + "x = 1\n" * 500 + "```\n"
        md = f"# Title\n\n## Code\n\n{code}\n\n## End\n\nDone.\n"
        p = tmp_path / "code.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert _estimate_tokens(c.content) <= DEFAULT_TOKEN_BUDGET

    def test_oversized_with_table(self, parser, tmp_path, rule):
        rows = "| Col1 | Col2 |\n|------|------|\n" + (
            "| data | val  |\n" * 500
        )
        md = f"# Title\n\n## Table\n\n{rows}\n\n## End\n\nDone.\n"
        p = tmp_path / "table.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert _estimate_tokens(c.content) <= DEFAULT_TOKEN_BUDGET

    def test_document_no_headings_oversized(self, parser, tmp_path, rule):
        """A document with no headings produces a single level-1 chunk."""
        big = "Word. " * 2000
        p = tmp_path / "noheading.md"
        p.write_text(big, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert _estimate_tokens(c.content) <= DEFAULT_TOKEN_BUDGET

    def test_only_h1_oversized(self, parser, tmp_path, rule):
        big = "Stuff. " * 2000
        md = f"# Big Heading\n\n{big}\n"
        p = tmp_path / "h1only.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert _estimate_tokens(c.content) <= DEFAULT_TOKEN_BUDGET
        # All sub-chunks carry the h1 breadcrumb
        for c in result.chunks:
            assert "Big Heading" in c.header_breadcrumb

    def test_frontmatter_preserved_on_resplit(self, parser, tmp_path, rule):
        big = "Word. " * 2000
        md = f"---\ntitle: My Doc\n---\n\n# Title\n\n{big}\n"
        p = tmp_path / "fm.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert c.frontmatter.get("title") == "My Doc"

    def test_labels_preserved_on_resplit(self, parser, tmp_path, rule):
        big = "Word. " * 2000
        md = f"# Title\n\n{big}\n"
        p = tmp_path / "labels.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert c.labels == ["docs"]

    def test_kind_and_language_preserved(self, parser, tmp_path, rule):
        big = "Word. " * 2000
        md = f"# Title\n\n{big}\n"
        p = tmp_path / "kind.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        for c in result.chunks:
            assert c.kind == "markdown_section"
            assert c.language == "markdown"

    def test_parent_document_id_preserved(self, parser, tmp_path, rule):
        big = "Word. " * 2000
        md = f"# Title\n\n{big}\n"
        p = tmp_path / "pdid.md"
        p.write_text(md, encoding="utf-8")
        result = parser.parse(p, rule, kb_name="test", rel_path=p.name)
        expected_doc_id = f"test::{p.name}"
        for c in result.chunks:
            assert c.parent_document_id == expected_doc_id


# ============================================================================
# OllamaEmbedder.max_input_tokens
# ============================================================================


class TestMaxInputTokens:
    def test_nomic_embed_text(self):
        from guru_server.embedding import OllamaEmbedder

        embedder = OllamaEmbedder(model="nomic-embed-text")
        assert embedder.max_input_tokens() == 2048

    def test_unknown_model_fallback(self):
        from guru_server.embedding import OllamaEmbedder

        embedder = OllamaEmbedder(model="some-future-model")
        assert embedder.max_input_tokens() == 2048
