"""Minimal Word (.docx) export for subtitle tables."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

from .models import SubtitleSegment

WORD_EXPORT_MODE_BILINGUAL_TABLE = "bilingualTable"
WORD_EXPORT_MODE_TRANSCRIPT = "transcript"
SUPPORTED_WORD_EXPORT_MODES = {
    WORD_EXPORT_MODE_BILINGUAL_TABLE,
    WORD_EXPORT_MODE_TRANSCRIPT,
}

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
DC_NS = "http://purl.org/dc/elements/1.1/"
DCTERMS_NS = "http://purl.org/dc/terms/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
EP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
VT_NS = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

ET.register_namespace("w", WORD_NS)
ET.register_namespace("r", DOC_REL_NS)
ET.register_namespace("cp", CORE_NS)
ET.register_namespace("dc", DC_NS)
ET.register_namespace("dcterms", DCTERMS_NS)
ET.register_namespace("xsi", XSI_NS)
ET.register_namespace("ep", EP_NS)
ET.register_namespace("vt", VT_NS)


class WordExportError(RuntimeError):
    """Raised when LinguaSub cannot generate a valid Word document."""


def _w(tag: str) -> str:
    return f"{{{WORD_NS}}}{tag}"


def _rel(tag: str) -> str:
    return f"{{{REL_NS}}}{tag}"


def _core(tag: str) -> str:
    return f"{{{CORE_NS}}}{tag}"


def _dc(tag: str) -> str:
    return f"{{{DC_NS}}}{tag}"


def _dcterms(tag: str) -> str:
    return f"{{{DCTERMS_NS}}}{tag}"


def _ep(tag: str) -> str:
    return f"{{{EP_NS}}}{tag}"


def _vt(tag: str) -> str:
    return f"{{{VT_NS}}}{tag}"


def _xml_bytes(element: ET.Element) -> bytes:
    return ET.tostring(element, encoding="utf-8", xml_declaration=True)


def _format_word_timestamp(value_ms: object) -> str:
    if not isinstance(value_ms, (int, float)) or not math.isfinite(value_ms):
        return "--"

    normalized = int(round(float(value_ms)))
    if normalized < 0:
        return "--"

    total_seconds, milliseconds = divmod(normalized, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def _normalize_cell_text(text: str) -> str:
    lines = [line.strip() for line in str(text).splitlines()]
    return "\n".join(line for line in lines if line)


def _append_run(paragraph: ET.Element, text: str, *, bold: bool = False) -> None:
    run = ET.SubElement(paragraph, _w("r"))
    if bold:
        run_properties = ET.SubElement(run, _w("rPr"))
        ET.SubElement(run_properties, _w("b"))

    normalized_text = text if text else ""
    text_element = ET.SubElement(run, _w("t"))
    if normalized_text[:1].isspace() or normalized_text[-1:].isspace():
        text_element.set(XML_SPACE, "preserve")
    text_element.text = normalized_text


def _append_paragraph(
    parent: ET.Element,
    text: str,
    *,
    bold: bool = False,
    alignment: str | None = None,
    spacing_after: int | None = None,
) -> ET.Element:
    paragraph = ET.SubElement(parent, _w("p"))
    paragraph_properties = ET.SubElement(paragraph, _w("pPr"))
    if alignment:
        alignment_element = ET.SubElement(paragraph_properties, _w("jc"))
        alignment_element.set(_w("val"), alignment)
    if spacing_after is not None:
        spacing_element = ET.SubElement(paragraph_properties, _w("spacing"))
        spacing_element.set(_w("after"), str(spacing_after))

    _append_run(paragraph, text, bold=bold)
    return paragraph


def _append_labeled_paragraph(
    parent: ET.Element,
    label: str,
    text: str,
    *,
    spacing_after: int | None = None,
) -> ET.Element:
    paragraph = ET.SubElement(parent, _w("p"))
    paragraph_properties = ET.SubElement(paragraph, _w("pPr"))
    if spacing_after is not None:
        spacing_element = ET.SubElement(paragraph_properties, _w("spacing"))
        spacing_element.set(_w("after"), str(spacing_after))

    _append_run(paragraph, f"{label}: ", bold=True)
    _append_run(paragraph, _normalize_cell_text(text))
    return paragraph


def _append_table_cell(
    row: ET.Element,
    text: str,
    *,
    width: int,
    bold: bool = False,
) -> None:
    cell = ET.SubElement(row, _w("tc"))
    cell_properties = ET.SubElement(cell, _w("tcPr"))
    cell_width = ET.SubElement(cell_properties, _w("tcW"))
    cell_width.set(_w("w"), str(width))
    cell_width.set(_w("type"), "dxa")
    vertical_alignment = ET.SubElement(cell_properties, _w("vAlign"))
    vertical_alignment.set(_w("val"), "top")

    normalized_text = _normalize_cell_text(text)
    if not normalized_text:
        _append_paragraph(cell, "", spacing_after=80)
        return

    lines = normalized_text.splitlines()
    for index, line in enumerate(lines):
        _append_paragraph(
            cell,
            line,
            bold=bold,
            spacing_after=80 if index < len(lines) - 1 else 40,
        )


def _build_bilingual_table_document(segments: list[SubtitleSegment]) -> bytes:
    document = ET.Element(_w("document"))
    body = ET.SubElement(document, _w("body"))

    _append_paragraph(
        body,
        "LinguaSub Bilingual Subtitle Export",
        bold=True,
        spacing_after=160,
    )
    _append_paragraph(
        body,
        "Each subtitle segment is listed with start time, end time, source text, and translated text.",
        spacing_after=200,
    )

    table = ET.SubElement(body, _w("tbl"))
    table_properties = ET.SubElement(table, _w("tblPr"))
    table_width = ET.SubElement(table_properties, _w("tblW"))
    table_width.set(_w("w"), "0")
    table_width.set(_w("type"), "auto")
    table_layout = ET.SubElement(table_properties, _w("tblLayout"))
    table_layout.set(_w("type"), "fixed")
    table_borders = ET.SubElement(table_properties, _w("tblBorders"))
    for border_name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = ET.SubElement(table_borders, _w(border_name))
        border.set(_w("val"), "single")
        border.set(_w("sz"), "4")
        border.set(_w("space"), "0")
        border.set(_w("color"), "C8D0DA")

    grid_widths = [1700, 1700, 3600, 3600]
    table_grid = ET.SubElement(table, _w("tblGrid"))
    for width in grid_widths:
        grid_column = ET.SubElement(table_grid, _w("gridCol"))
        grid_column.set(_w("w"), str(width))

    header_row = ET.SubElement(table, _w("tr"))
    for title, width in zip(
        ["Start Time", "End Time", "Source Text", "Translated Text"],
        grid_widths,
        strict=True,
    ):
        _append_table_cell(header_row, title, width=width, bold=True)

    for segment in segments:
        row = ET.SubElement(table, _w("tr"))
        _append_table_cell(row, _format_word_timestamp(segment.start), width=grid_widths[0])
        _append_table_cell(row, _format_word_timestamp(segment.end), width=grid_widths[1])
        _append_table_cell(row, segment.sourceText, width=grid_widths[2])
        _append_table_cell(row, segment.translatedText, width=grid_widths[3])

    _append_section_properties(body)
    return _package_document(document)


def _build_transcript_document(segments: list[SubtitleSegment]) -> bytes:
    document = ET.Element(_w("document"))
    body = ET.SubElement(document, _w("body"))

    _append_paragraph(
        body,
        "LinguaSub Transcript Export",
        bold=True,
        spacing_after=160,
    )
    _append_paragraph(
        body,
        "Each subtitle segment is written as a readable bilingual transcript with timestamps.",
        spacing_after=220,
    )

    for segment in segments:
        time_range = (
            f"{_format_word_timestamp(segment.start)} -> "
            f"{_format_word_timestamp(segment.end)}"
        )
        _append_paragraph(body, time_range, bold=True, spacing_after=60)
        _append_labeled_paragraph(
            body,
            "Source",
            segment.sourceText,
            spacing_after=70 if segment.translatedText.strip() else 180,
        )
        if segment.translatedText.strip():
            _append_labeled_paragraph(
                body,
                "Translation",
                segment.translatedText,
                spacing_after=180,
            )

    _append_section_properties(body)
    return _package_document(document)


def _safe_text(value: object) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)) and math.isfinite(value):
        return int(round(float(value)))
    return 0


def _safe_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _normalize_content_summary(summary: dict[str, object]) -> dict[str, object]:
    one_sentence_summary = _safe_text(summary.get("oneSentenceSummary"))
    chapters: list[dict[str, object]] = []
    for item in _safe_list(summary.get("chapters")):
        if not isinstance(item, dict):
            continue
        chapters.append(
            {
                "start": _safe_int(item.get("start")),
                "end": _safe_int(item.get("end")),
                "title": _safe_text(item.get("title")),
                "summary": _safe_text(item.get("summary")),
            }
        )

    keywords: list[dict[str, str]] = []
    for item in _safe_list(summary.get("keywords")):
        if not isinstance(item, dict):
            continue
        keywords.append(
            {
                "term": _safe_text(item.get("term")),
                "translation": _safe_text(item.get("translation")),
                "explanation": _safe_text(item.get("explanation")),
            }
        )

    study_notes = _safe_text(summary.get("studyNotes"))
    has_content = bool(
        one_sentence_summary
        or study_notes
        or any(
            chapter["title"] or chapter["summary"]
            for chapter in chapters
        )
        or any(
            keyword["term"] or keyword["translation"] or keyword["explanation"]
            for keyword in keywords
        )
    )
    if not has_content:
        raise WordExportError("Content summary is empty. Generate a content summary before exporting.")

    return {
        "oneSentenceSummary": one_sentence_summary,
        "chapters": chapters,
        "keywords": keywords,
        "studyNotes": study_notes,
    }


def _append_content_summary_section(
    body: ET.Element,
    title: str,
    fallback_text: str,
    content: str,
) -> None:
    _append_paragraph(body, title, bold=True, spacing_after=80)
    _append_paragraph(
        body,
        content if content else fallback_text,
        spacing_after=180,
    )


def _build_content_summary_document(summary: dict[str, object]) -> bytes:
    normalized_summary = _normalize_content_summary(summary)
    document = ET.Element(_w("document"))
    body = ET.SubElement(document, _w("body"))

    _append_paragraph(body, "Content Summary", bold=True, spacing_after=140)
    _append_labeled_paragraph(
        body,
        "Generated at",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        spacing_after=200,
    )
    _append_content_summary_section(
        body,
        "One-sentence Summary",
        "No one-sentence summary returned.",
        str(normalized_summary["oneSentenceSummary"]),
    )

    _append_paragraph(body, "Chapter Summaries", bold=True, spacing_after=80)
    chapters = normalized_summary["chapters"]
    if isinstance(chapters, list) and chapters:
        for index, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, dict):
                continue
            time_range = (
                f"{_format_word_timestamp(chapter.get('start'))} -> "
                f"{_format_word_timestamp(chapter.get('end'))}"
            )
            chapter_title = _safe_text(chapter.get("title")) or f"Chapter {index}"
            _append_paragraph(
                body,
                f"{index}. {chapter_title}",
                bold=True,
                spacing_after=40,
            )
            _append_labeled_paragraph(body, "Time", time_range, spacing_after=40)
            _append_labeled_paragraph(
                body,
                "Summary",
                _safe_text(chapter.get("summary")) or "No chapter summary returned.",
                spacing_after=150,
            )
    else:
        _append_paragraph(body, "No chapter summaries returned.", spacing_after=180)

    _append_paragraph(body, "Keywords / Terms", bold=True, spacing_after=80)
    keywords = normalized_summary["keywords"]
    if isinstance(keywords, list) and keywords:
        for index, keyword in enumerate(keywords, start=1):
            if not isinstance(keyword, dict):
                continue
            term = _safe_text(keyword.get("term")) or f"Keyword {index}"
            translation = _safe_text(keyword.get("translation")) or "--"
            explanation = _safe_text(keyword.get("explanation")) or "--"
            _append_paragraph(body, f"{index}. {term}", bold=True, spacing_after=40)
            _append_labeled_paragraph(
                body,
                "Translation",
                translation,
                spacing_after=40,
            )
            _append_labeled_paragraph(
                body,
                "Explanation",
                explanation,
                spacing_after=150,
            )
    else:
        _append_paragraph(body, "No keywords returned.", spacing_after=180)

    _append_content_summary_section(
        body,
        "Study Notes",
        "No study notes returned.",
        str(normalized_summary["studyNotes"]),
    )

    _append_section_properties(body)
    return _package_document(document)


def _append_section_properties(body: ET.Element) -> None:
    section_properties = ET.SubElement(body, _w("sectPr"))
    page_size = ET.SubElement(section_properties, _w("pgSz"))
    page_size.set(_w("w"), "11906")
    page_size.set(_w("h"), "16838")
    page_margin = ET.SubElement(section_properties, _w("pgMar"))
    for key, value in {
        "top": "1440",
        "right": "1080",
        "bottom": "1440",
        "left": "1080",
        "header": "708",
        "footer": "708",
        "gutter": "0",
    }.items():
        page_margin.set(_w(key), value)


def _package_document(document: ET.Element) -> bytes:
    package = BytesIO()
    with ZipFile(package, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _build_content_types_xml())
        archive.writestr("_rels/.rels", _build_root_relationships_xml())
        archive.writestr("docProps/core.xml", _build_core_properties_xml())
        archive.writestr("docProps/app.xml", _build_app_properties_xml())
        archive.writestr("word/document.xml", _xml_bytes(document))

    return package.getvalue()


def _build_content_types_xml() -> bytes:
    root = ET.Element(
        "Types",
        xmlns="http://schemas.openxmlformats.org/package/2006/content-types",
    )
    ET.SubElement(
        root,
        "Default",
        Extension="rels",
        ContentType="application/vnd.openxmlformats-package.relationships+xml",
    )
    ET.SubElement(root, "Default", Extension="xml", ContentType="application/xml")
    ET.SubElement(
        root,
        "Override",
        PartName="/word/document.xml",
        ContentType=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        ),
    )
    ET.SubElement(
        root,
        "Override",
        PartName="/docProps/core.xml",
        ContentType="application/vnd.openxmlformats-package.core-properties+xml",
    )
    ET.SubElement(
        root,
        "Override",
        PartName="/docProps/app.xml",
        ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml",
    )
    return _xml_bytes(root)


def _build_root_relationships_xml() -> bytes:
    root = ET.Element(_rel("Relationships"))
    relationships = [
        (
            "rId1",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
            "word/document.xml",
        ),
        (
            "rId2",
            "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
            "docProps/core.xml",
        ),
        (
            "rId3",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties",
            "docProps/app.xml",
        ),
    ]
    for relationship_id, relationship_type, target in relationships:
        relationship = ET.SubElement(root, _rel("Relationship"))
        relationship.set("Id", relationship_id)
        relationship.set("Type", relationship_type)
        relationship.set("Target", target)
    return _xml_bytes(root)


def _build_core_properties_xml() -> bytes:
    root = ET.Element(_core("coreProperties"))
    ET.SubElement(root, _dc("title")).text = "LinguaSub Subtitle Export"
    ET.SubElement(root, _dc("creator")).text = "LinguaSub"
    ET.SubElement(root, _core("lastModifiedBy")).text = "LinguaSub"
    created_value = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    created = ET.SubElement(root, _dcterms("created"))
    created.set(f"{{{XSI_NS}}}type", "dcterms:W3CDTF")
    created.text = created_value
    modified = ET.SubElement(root, _dcterms("modified"))
    modified.set(f"{{{XSI_NS}}}type", "dcterms:W3CDTF")
    modified.text = created_value
    return _xml_bytes(root)


def _build_app_properties_xml() -> bytes:
    root = ET.Element(_ep("Properties"))
    ET.SubElement(root, _ep("Application")).text = "LinguaSub"
    ET.SubElement(root, _ep("DocSecurity")).text = "0"
    ET.SubElement(root, _ep("ScaleCrop")).text = "false"
    heading_pairs = ET.SubElement(root, _ep("HeadingPairs"))
    heading_vector = ET.SubElement(
        heading_pairs,
        _vt("vector"),
        size="2",
        baseType="variant",
    )
    variant_heading = ET.SubElement(heading_vector, _vt("variant"))
    ET.SubElement(variant_heading, _vt("lpstr")).text = "Title"
    variant_count = ET.SubElement(heading_vector, _vt("variant"))
    ET.SubElement(variant_count, _vt("i4")).text = "1"
    titles = ET.SubElement(root, _ep("TitlesOfParts"))
    titles_vector = ET.SubElement(titles, _vt("vector"), size="1", baseType="lpstr")
    ET.SubElement(titles_vector, _vt("lpstr")).text = "Document"
    ET.SubElement(root, _ep("Company")).text = "LinguaSub"
    ET.SubElement(root, _ep("LinksUpToDate")).text = "false"
    ET.SubElement(root, _ep("SharedDoc")).text = "false"
    ET.SubElement(root, _ep("HyperlinksChanged")).text = "false"
    ET.SubElement(root, _ep("AppVersion")).text = "1.0"
    return _xml_bytes(root)


def validate_word_export_mode(mode: str | None) -> str:
    normalized = (mode or WORD_EXPORT_MODE_BILINGUAL_TABLE).strip()
    if normalized in SUPPORTED_WORD_EXPORT_MODES:
        return normalized

    supported = ", ".join(sorted(SUPPORTED_WORD_EXPORT_MODES))
    raise WordExportError(
        f"Unsupported Word export mode '{mode}'. Use one of: {supported}."
    )


def generate_word_document(
    segments: list[SubtitleSegment],
    *,
    mode: str = WORD_EXPORT_MODE_BILINGUAL_TABLE,
) -> bytes:
    normalized_mode = validate_word_export_mode(mode)
    if normalized_mode == WORD_EXPORT_MODE_BILINGUAL_TABLE:
        return _build_bilingual_table_document(segments)
    if normalized_mode == WORD_EXPORT_MODE_TRANSCRIPT:
        return _build_transcript_document(segments)

    raise WordExportError(f"Unsupported Word export mode '{mode}'.")


def generate_content_summary_word_document(summary: dict[str, object]) -> bytes:
    if not isinstance(summary, dict):
        raise WordExportError("Content summary is empty. Generate a content summary before exporting.")

    return _build_content_summary_document(summary)
