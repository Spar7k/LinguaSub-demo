"""Tests for subtitle export outputs."""

from __future__ import annotations

import unittest
from pathlib import Path
from zipfile import ZipFile

from backend.app.export_service import (
    EmptySubtitleExportError,
    ExportServiceError,
    MissingTranslationExportError,
    export_srt,
    export_subtitles,
    export_word,
)
from backend.app.models import SubtitleSegment
from backend.app.srt_service import SrtGenerationError

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class ExportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tearDown()

    def tearDown(self) -> None:
        for file_name in (
            "subtitle-file.bilingual.srt",
            "subtitle-file.single.srt",
            "custom-export.srt",
            "long-range.srt",
            "subtitle-file.recognition.txt",
            "custom-recognition.txt",
            "subtitle-file_bilingual.docx",
            "subtitle-file_transcript.docx",
            "custom-review.docx",
            "long-range.docx",
            "unicode-export.docx",
            "unsafe_name_.srt",
            "unsafe_name_(1).srt",
            "subtitle-file.bilingual(1).srt",
        ):
            output_path = FIXTURE_DIR / file_name
            if output_path.exists():
                output_path.unlink()

    def test_export_srt_writes_bilingual_file_with_auto_name(self) -> None:
        result = export_srt(
            [
                SubtitleSegment(
                    id="seg-001",
                    start=0,
                    end=1200,
                    sourceText="Hello there.",
                    translatedText="[CN] Hello there.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            bilingual=True,
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
        )

        output_path = Path(result.path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.fileName, "subtitle-file.bilingual.srt")
        self.assertEqual(result.format, "srt")
        self.assertIn("Hello there.", output_path.read_text(encoding="utf-8-sig"))

    def test_export_srt_raises_when_segments_are_empty(self) -> None:
        with self.assertRaises(EmptySubtitleExportError):
            export_srt([], bilingual=True, source_file_path=FIXTURE_DIR / "subtitle-file.srt")

    def test_export_srt_requires_translations_for_bilingual_mode(self) -> None:
        with self.assertRaises(MissingTranslationExportError):
            export_srt(
                [
                    SubtitleSegment(
                        id="seg-002",
                        start=0,
                        end=1000,
                        sourceText="Need translation.",
                        translatedText="",
                        sourceLanguage="en",
                        targetLanguage="zh-CN",
                    )
                ],
                bilingual=True,
                source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            )

    def test_export_srt_supports_custom_file_name_for_single_mode(self) -> None:
        result = export_srt(
            [
                SubtitleSegment(
                    id="seg-003",
                    start=0,
                    end=1000,
                    sourceText="Good morning.",
                    translatedText="[CN] Good morning.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            bilingual=False,
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            file_name="custom-export",
        )

        output_path = Path(result.path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.fileName, "custom-export.srt")
        content = output_path.read_text(encoding="utf-8-sig")
        self.assertIn("[CN] Good morning.", content)
        self.assertNotIn("Good morning.\n[CN] Good morning.", content)

    def test_export_srt_resolves_name_conflicts_without_overwriting(self) -> None:
        existing_path = FIXTURE_DIR / "subtitle-file.bilingual.srt"
        existing_path.write_text("existing", encoding="utf-8-sig")

        result = export_srt(
            [
                SubtitleSegment(
                    id="seg-003a",
                    start=0,
                    end=1000,
                    sourceText="Good morning.",
                    translatedText="[CN] Good morning.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            bilingual=True,
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
        )

        self.assertEqual(result.fileName, "subtitle-file.bilingual(1).srt")
        self.assertTrue(result.conflictResolved)
        self.assertTrue((FIXTURE_DIR / "subtitle-file.bilingual(1).srt").exists())

    def test_export_srt_sanitizes_invalid_file_names(self) -> None:
        result = export_srt(
            [
                SubtitleSegment(
                    id="seg-003b",
                    start=0,
                    end=1000,
                    sourceText="Safe export.",
                    translatedText="[CN] Safe export.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            bilingual=False,
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            file_name='unsafe:name<>?"',
        )

        self.assertEqual(result.fileName, "unsafe_name_.srt")
        self.assertTrue(result.sanitizedFileName)
        self.assertTrue((FIXTURE_DIR / "unsafe_name_.srt").exists())

    def test_export_srt_raises_when_timeline_is_invalid(self) -> None:
        with self.assertRaises(SrtGenerationError):
            export_srt(
                [
                    SubtitleSegment(
                        id="seg-004",
                        start=2000,
                        end=1000,
                        sourceText="Broken timeline.",
                        translatedText="[CN] Broken timeline.",
                        sourceLanguage="en",
                        targetLanguage="zh-CN",
                    )
                ],
                bilingual=True,
                source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            )

    def test_export_srt_preserves_timestamps_beyond_two_minutes(self) -> None:
        result = export_srt(
            [
                SubtitleSegment(
                    id="seg-004a",
                    start=121000,
                    end=125500,
                    sourceText="Long tail segment.",
                    translatedText="[CN] Long tail segment.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            bilingual=True,
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            file_name="long-range",
        )

        content = Path(result.path).read_text(encoding="utf-8-sig")
        self.assertIn("00:02:01,000 --> 00:02:05,500", content)
        self.assertIn("[CN] Long tail segment.", content)

    def test_export_recognition_text_writes_txt_with_source_only(self) -> None:
        result = export_subtitles(
            [
                SubtitleSegment(
                    id="seg-201",
                    start=1200,
                    end=4500,
                    sourceText="Hello everyone, welcome to this video.",
                    translatedText="This translated text must not be exported.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                ),
                SubtitleSegment(
                    id="seg-202",
                    start=4600,
                    end=8300,
                    sourceText="",
                    translatedText="This empty source segment must stay untranslated.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                ),
            ],
            export_format="recognition_text",
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
        )

        output_path = Path(result.path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.fileName, "subtitle-file.recognition.txt")
        self.assertEqual(result.format, "recognition_text")
        self.assertIsNone(result.wordMode)

        content = output_path.read_text(encoding="utf-8-sig")
        self.assertIn("[00:00:01.200 - 00:00:04.500]", content)
        self.assertIn("[00:00:04.600 - 00:00:08.300]", content)
        self.assertIn("Hello everyone, welcome to this video.", content)
        self.assertNotIn("This translated text must not be exported.", content)
        self.assertNotIn("This empty source segment must stay untranslated.", content)

    def test_export_recognition_text_normalizes_custom_extension_to_txt(self) -> None:
        result = export_subtitles(
            [
                SubtitleSegment(
                    id="seg-203",
                    start=0,
                    end=1000,
                    sourceText="Keep the recognized source.",
                    translatedText="Do not write the translation.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            export_format="recognition_text",
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            file_name="custom-recognition.srt",
        )

        output_path = Path(result.path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.fileName, "custom-recognition.txt")
        self.assertEqual(output_path.suffix, ".txt")
        self.assertIn(
            "Keep the recognized source.",
            output_path.read_text(encoding="utf-8-sig"),
        )

    def test_export_recognition_text_raises_when_segments_are_empty(self) -> None:
        with self.assertRaises(EmptySubtitleExportError):
            export_subtitles(
                [],
                export_format="recognition_text",
                source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            )

    def test_export_recognition_text_raises_when_all_source_text_is_empty(self) -> None:
        with self.assertRaisesRegex(ExportServiceError, "No recognition text available"):
            export_subtitles(
                [
                    SubtitleSegment(
                        id="seg-204",
                        start=0,
                        end=1000,
                        sourceText=" ",
                        translatedText="Translation should not matter.",
                        sourceLanguage="en",
                        targetLanguage="zh-CN",
                    ),
                    SubtitleSegment(
                        id="seg-205",
                        start=1000,
                        end=2000,
                        sourceText="\n",
                        translatedText="Another ignored translation.",
                        sourceLanguage="en",
                        targetLanguage="zh-CN",
                    ),
                ],
                export_format="recognition_text",
                source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            )

    def test_export_word_writes_docx_with_bilingual_table_auto_name(self) -> None:
        result = export_word(
            [
                SubtitleSegment(
                    id="seg-101",
                    start=0,
                    end=1200,
                    sourceText="Hello there.",
                    translatedText="你好。",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
        )

        output_path = Path(result.path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.fileName, "subtitle-file_bilingual.docx")
        self.assertEqual(result.format, "word")
        self.assertEqual(result.wordMode, "bilingualTable")

        with ZipFile(output_path) as archive:
            self.assertIn("word/document.xml", archive.namelist())
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("Start Time", document_xml)
        self.assertIn("End Time", document_xml)
        self.assertIn("Source Text", document_xml)
        self.assertIn("Translated Text", document_xml)
        self.assertIn("Hello there.", document_xml)
        self.assertIn("你好。", document_xml)

    def test_export_word_supports_custom_name_and_blank_translation_cells(self) -> None:
        result = export_subtitles(
            [
                SubtitleSegment(
                    id="seg-102",
                    start=0,
                    end=1400,
                    sourceText="Missing translation is okay here.",
                    translatedText="",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            export_format="word",
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            file_name="custom-review",
        )

        output_path = Path(result.path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.fileName, "custom-review.docx")

        with ZipFile(output_path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("Missing translation is okay here.", document_xml)

    def test_export_word_preserves_unicode_and_safe_timestamps(self) -> None:
        result = export_word(
            [
                SubtitleSegment(
                    id="seg-103",
                    start=-1,
                    end=2500,
                    sourceText="こんにちは",
                    translatedText="안녕하세요",
                    sourceLanguage="ja",
                    targetLanguage="ko",
                )
            ],
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            file_name="unicode-export",
        )

        with ZipFile(Path(result.path)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("こんにちは", document_xml)
        self.assertIn("안녕하세요", document_xml)
        self.assertIn("--", document_xml)
        self.assertIn("00:00:02.500", document_xml)

    def test_export_word_preserves_timestamps_beyond_two_minutes(self) -> None:
        result = export_word(
            [
                SubtitleSegment(
                    id="seg-103a",
                    start=121000,
                    end=125500,
                    sourceText="Transcript tail segment.",
                    translatedText="[CN] Transcript tail segment.",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            word_mode="transcript",
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
            file_name="long-range",
        )

        with ZipFile(Path(result.path)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("00:02:01.000 -&gt; 00:02:05.500", document_xml)
        self.assertIn("Transcript tail segment.", document_xml)

    def test_export_word_supports_transcript_mode_with_auto_name(self) -> None:
        result = export_word(
            [
                SubtitleSegment(
                    id="seg-104",
                    start=1500,
                    end=4100,
                    sourceText="Let's test the transcript export.",
                    translatedText="我们来测试文稿导出。",
                    sourceLanguage="en",
                    targetLanguage="zh-CN",
                )
            ],
            word_mode="transcript",
            source_file_path=FIXTURE_DIR / "subtitle-file.srt",
        )

        output_path = Path(result.path)
        self.assertTrue(output_path.exists())
        self.assertEqual(result.fileName, "subtitle-file_transcript.docx")
        self.assertEqual(result.wordMode, "transcript")

        with ZipFile(output_path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("LinguaSub Transcript Export", document_xml)
        self.assertIn("00:00:01.500 -&gt; 00:00:04.100", document_xml)
        self.assertIn("Source: ", document_xml)
        self.assertIn("Translation: ", document_xml)
        self.assertIn("Let's test the transcript export.", document_xml)
        self.assertIn("我们来测试文稿导出。", document_xml)


if __name__ == "__main__":
    unittest.main()
