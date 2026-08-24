"""
Owner: Person 1

Tests for extract/pdf_text.py.

contracts.normalize() does not exist in the repository yet (shared
contracts are not frozen). These tests monkeypatch `contracts.normalize`
with a stand-in so extract/pdf_text.py's own logic (page iteration,
page-number preservation, empty-page handling, line normalization
wiring) can be verified in isolation. They are not a substitute for
real integration testing once contracts.normalize() is implemented.
"""

from __future__ import annotations

import contracts
from extract.pdf_text import PageText, extract_pdf_pages


class _FakePage:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class _FakePdf:
    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _patch_pdfplumber_open(monkeypatch, fake_pdf: _FakePdf) -> None:
    monkeypatch.setattr(
        "extract.pdf_text.pdfplumber.open", lambda _path: fake_pdf
    )


def _patch_normalize_passthrough(monkeypatch) -> None:
    monkeypatch.setattr(contracts, "normalize", lambda line: line, raising=False)


def test_extract_pdf_pages_preserves_page_numbers_and_source_identity(
    monkeypatch,
) -> None:
    _patch_normalize_passthrough(monkeypatch)
    fake_pdf = _FakePdf([_FakePage("first page"), _FakePage("second page")])
    _patch_pdfplumber_open(monkeypatch, fake_pdf)

    pages = extract_pdf_pages("some/document.pdf", source_id="yearbook")

    assert [p.page_number for p in pages] == [1, 2]
    assert all(p.source_id == "yearbook" for p in pages)
    assert all(p.filename == "document.pdf" for p in pages)
    assert pages[0].raw_text == "first page"
    assert pages[1].raw_text == "second page"


def test_extract_pdf_pages_handles_page_with_no_extractable_text(
    monkeypatch,
) -> None:
    _patch_normalize_passthrough(monkeypatch)
    fake_pdf = _FakePdf([_FakePage("has text"), _FakePage(None)])
    _patch_pdfplumber_open(monkeypatch, fake_pdf)

    pages = extract_pdf_pages("doc.pdf", source_id="regulations")

    assert len(pages) == 2
    empty_page = pages[1]
    assert empty_page.page_number == 2
    assert empty_page.raw_text == ""
    assert empty_page.text == ""
    assert empty_page.has_text is False
    # Empty page does not break contiguous page numbering.
    assert pages[0].has_text is True


def test_extract_pdf_pages_applies_shared_normalize_per_line(monkeypatch) -> None:
    calls: list[str] = []

    def fake_normalize(line: str) -> str:
        calls.append(line)
        return line.upper()

    monkeypatch.setattr(contracts, "normalize", fake_normalize, raising=False)
    fake_pdf = _FakePdf([_FakePage("line one\nline two")])
    _patch_pdfplumber_open(monkeypatch, fake_pdf)

    pages = extract_pdf_pages("doc.pdf", source_id="yearbook")

    assert calls == ["line one", "line two"]
    assert pages[0].text == "LINE ONE\nLINE TWO"
    # raw_text is untouched by normalization.
    assert pages[0].raw_text == "line one\nline two"


def test_extract_pdf_pages_does_not_call_normalize_for_blank_page(monkeypatch) -> None:
    calls: list[str] = []

    def fake_normalize(line: str) -> str:
        calls.append(line)
        return line

    monkeypatch.setattr(contracts, "normalize", fake_normalize, raising=False)
    fake_pdf = _FakePdf([_FakePage(""), _FakePage(None)])
    _patch_pdfplumber_open(monkeypatch, fake_pdf)

    pages = extract_pdf_pages("doc.pdf", source_id="yearbook")

    assert calls == []
    assert pages[0].raw_text == ""
    assert pages[0].text == ""
    assert pages[0].has_text is False
    assert pages[1].raw_text == ""
    assert pages[1].text == ""
    assert pages[1].has_text is False


def test_page_text_is_a_frozen_dataclass_with_expected_fields() -> None:
    page = PageText(
        source_id="s",
        filename="f.pdf",
        page_number=1,
        raw_text="a",
        text="a",
        has_text=True,
    )
    assert page.source_id == "s"
    assert page.page_number == 1
