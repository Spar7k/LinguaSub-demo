"""Tests for burned-in subtitle video export helpers."""

from __future__ import annotations

import subprocess
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.app.models import SubtitleSegment
from backend.app.video_burn_export_service import (
    DEFAULT_VIDEO_BURN_PROFILE,
    VideoMetadata,
    VideoBurnExportServiceError,
    burn_video_subtitles,
    build_ffmpeg_burn_command,
    classify_video_burn_profile,
    generate_ass_content,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class VideoBurnExportServiceTests(unittest.TestCase):
    def make_output_dir(self) -> Path:
        output_dir = FIXTURE_DIR / f"video-burn-{uuid.uuid4().hex}"
        output_dir.mkdir()
        self.addCleanup(lambda: shutil.rmtree(output_dir, ignore_errors=True))
        return output_dir

    def build_segment(
        self,
        segment_id: str = "seg-001",
        *,
        start: int = 0,
        end: int = 1200,
        source_text: str = "Hello.",
        translated_text: str = "你好。",
    ) -> SubtitleSegment:
        return SubtitleSegment(
            id=segment_id,
            start=start,
            end=end,
            sourceText=source_text,
            translatedText=translated_text,
            sourceLanguage="en",
            targetLanguage="zh-CN",
        )

    def get_default_style_fields(self, ass_content: str) -> list[str]:
        for line in ass_content.splitlines():
            if line.startswith("Style: Default,"):
                return line.removeprefix("Style: ").split(",")
        self.fail("Default ASS style was not generated.")

    def test_burn_video_subtitles_builds_expected_ffmpeg_command(self) -> None:
        video_path = FIXTURE_DIR / "sample-video.mp4"
        output_dir = self.make_output_dir()
        output_path = output_dir / "burned output.mp4"
        fake_ffmpeg = output_dir / "ffmpeg-bin"
        captured: dict[str, object] = {}

        def fake_run(command: list[str], *, cwd: Path) -> None:
            captured["command"] = command
            captured["cwd"] = cwd
            self.assertTrue((cwd / "subtitles.ass").exists())
            output_path.write_bytes(b"fake-video")

        with (
            patch(
                "backend.app.video_burn_export_service.resolve_ffmpeg_binary",
                return_value=fake_ffmpeg,
            ),
            patch(
                "backend.app.video_burn_export_service.resolve_ffprobe_binary",
                return_value=None,
            ),
            patch(
                "backend.app.video_burn_export_service._run_ffmpeg_command",
                side_effect=fake_run,
            ) as run_ffmpeg,
        ):
            result = burn_video_subtitles(
                video_path=str(video_path),
                output_path=str(output_path),
                segments=[self.build_segment()],
                mode="bilingual",
            )

        command = captured["command"]
        self.assertIsInstance(command, list)
        self.assertEqual(run_ffmpeg.call_count, 1)
        self.assertIn("-vf", command)
        self.assertIn("subtitles=filename=subtitles.ass", command)
        self.assertIn("-c:v", command)
        self.assertIn("libx264", command)
        self.assertIn("-preset", command)
        self.assertIn("veryfast", command)
        self.assertIn("-pix_fmt", command)
        self.assertIn("yuv420p", command)
        self.assertIn("-c:a", command)
        self.assertIn("aac", command)
        self.assertNotIn("-t", command)
        self.assertEqual(result.outputPath, str(output_path.resolve()))
        self.assertEqual(result.fileName, "burned output.mp4")
        self.assertEqual(result.mode, "bilingual")
        self.assertFalse(Path(captured["cwd"]).exists())

    def test_burn_video_subtitles_rejects_output_overwriting_source_video(self) -> None:
        video_path = FIXTURE_DIR / "sample-video.mp4"

        with self.assertRaises(VideoBurnExportServiceError) as context:
            burn_video_subtitles(
                video_path=str(video_path),
                output_path=str(video_path),
                segments=[self.build_segment()],
                mode="bilingual",
            )

        self.assertIn("must not overwrite the source video", str(context.exception))

    def test_generate_ass_content_preserves_timestamps_beyond_two_minutes(self) -> None:
        content = generate_ass_content(
            [
                self.build_segment(
                    start=121000,
                    end=125500,
                    source_text="Long tail.",
                    translated_text="长尾字幕。",
                )
            ],
            mode="translated",
        )

        self.assertIn("0:02:01.00,0:02:05.50", content)
        self.assertIn("长尾字幕。", content)

    def test_generate_ass_content_uses_portrait_short_smaller_and_higher_style(self) -> None:
        portrait_content = generate_ass_content(
            [self.build_segment()],
            mode="bilingual",
            profile="portrait_short",
        )
        landscape_content = generate_ass_content(
            [self.build_segment()],
            mode="bilingual",
            profile="landscape_long",
        )

        portrait_style = self.get_default_style_fields(portrait_content)
        landscape_style = self.get_default_style_fields(landscape_content)
        self.assertIn("PlayResX: 1080", portrait_content)
        self.assertIn("PlayResY: 1920", portrait_content)
        self.assertLess(int(portrait_style[2]), int(landscape_style[2]))
        self.assertGreater(int(portrait_style[21]), int(landscape_style[21]))

    def test_generate_ass_content_uses_landscape_long_traditional_style(self) -> None:
        content = generate_ass_content(
            [self.build_segment()],
            mode="bilingual",
            profile="landscape_long",
        )
        style = self.get_default_style_fields(content)

        self.assertIn("PlayResX: 1920", content)
        self.assertIn("PlayResY: 1080", content)
        self.assertEqual(style[2], "42")
        self.assertEqual(style[21], "64")
        self.assertNotIn("PlayResX: 1080", content)

    def test_build_ffmpeg_command_does_not_include_duration_limit(self) -> None:
        command = build_ffmpeg_burn_command(
            ffmpeg_binary=Path("ffmpeg.exe"),
            video_path=Path("D:/media/source video.mp4"),
            output_path=Path("D:/media/output video.mp4"),
        )

        self.assertNotIn("-t", command)
        self.assertNotIn("-to", command)

    def test_generate_ass_content_writes_bilingual_text_on_two_lines(self) -> None:
        content = generate_ass_content(
            [self.build_segment(source_text="Hello.", translated_text="你好。")],
            mode="bilingual",
            profile="portrait_short",
        )

        self.assertIn(r"{\fs30}Hello.\N{\fs36}你好。", content)

    def test_generate_ass_content_keeps_translated_mode_without_bilingual_size_tags(self) -> None:
        content = generate_ass_content(
            [self.build_segment(source_text="Hello.", translated_text="你好。")],
            mode="translated",
            profile="portrait_short",
        )

        self.assertIn("你好。", content)
        self.assertNotIn(r"{\fs30}", content)
        self.assertNotIn(r"{\fs36}", content)

    def test_classify_video_burn_profile_uses_rotation_and_duration(self) -> None:
        profile = classify_video_burn_profile(
            VideoMetadata(width=1920, height=1080, duration_seconds=30, rotation=90),
            [self.build_segment(end=30_000)],
        )

        self.assertEqual(profile, "portrait_short")

    def test_burn_video_subtitles_applies_auto_portrait_short_profile(self) -> None:
        video_path = FIXTURE_DIR / "sample-video.mp4"
        output_dir = self.make_output_dir()
        output_path = output_dir / "portrait.mp4"
        fake_ffmpeg = output_dir / "ffmpeg-bin"
        fake_ffprobe = output_dir / "ffprobe-bin"
        captured: dict[str, str] = {}

        def fake_run(command: list[str], *, cwd: Path) -> None:
            captured["ass"] = (cwd / "subtitles.ass").read_text(encoding="utf-8-sig")
            output_path.write_bytes(b"fake-video")

        with (
            patch(
                "backend.app.video_burn_export_service.resolve_ffmpeg_binary",
                return_value=fake_ffmpeg,
            ),
            patch(
                "backend.app.video_burn_export_service.resolve_ffprobe_binary",
                return_value=fake_ffprobe,
            ),
            patch(
                "backend.app.video_burn_export_service._probe_video_metadata",
                return_value=VideoMetadata(width=1080, height=1920, duration_seconds=30),
            ),
            patch(
                "backend.app.video_burn_export_service._run_ffmpeg_command",
                side_effect=fake_run,
            ),
        ):
            burn_video_subtitles(
                video_path=str(video_path),
                output_path=str(output_path),
                segments=[self.build_segment()],
                mode="bilingual",
            )

        style = self.get_default_style_fields(captured["ass"])
        self.assertEqual(style[2], "36")
        self.assertEqual(style[21], "300")

    def test_burn_video_subtitles_falls_back_when_metadata_probe_fails(self) -> None:
        video_path = FIXTURE_DIR / "sample-video.mp4"
        output_dir = self.make_output_dir()
        output_path = output_dir / "fallback.mp4"
        fake_ffmpeg = output_dir / "ffmpeg-bin"
        fake_ffprobe = output_dir / "ffprobe-bin"
        captured: dict[str, str] = {}

        def fake_run(command: list[str], *, cwd: Path) -> None:
            captured["ass"] = (cwd / "subtitles.ass").read_text(encoding="utf-8-sig")
            output_path.write_bytes(b"fake-video")

        with (
            patch(
                "backend.app.video_burn_export_service.resolve_ffmpeg_binary",
                return_value=fake_ffmpeg,
            ),
            patch(
                "backend.app.video_burn_export_service.resolve_ffprobe_binary",
                return_value=fake_ffprobe,
            ),
            patch(
                "backend.app.video_burn_export_service._probe_video_metadata",
                side_effect=ValueError("bad probe"),
            ),
            patch(
                "backend.app.video_burn_export_service._run_ffmpeg_command",
                side_effect=fake_run,
            ),
        ):
            burn_video_subtitles(
                video_path=str(video_path),
                output_path=str(output_path),
                segments=[self.build_segment()],
                mode="bilingual",
            )

        self.assertEqual(DEFAULT_VIDEO_BURN_PROFILE, "landscape_long")
        style = self.get_default_style_fields(captured["ass"])
        self.assertEqual(style[2], "42")
        self.assertEqual(style[21], "64")

    def test_generate_ass_content_escapes_ass_special_text(self) -> None:
        content = generate_ass_content(
            [
                self.build_segment(
                    source_text=r"Use {tag} \ path",
                    translated_text="中文",
                )
            ],
            mode="source",
        )

        self.assertIn(r"Use \{tag\} \\ path", content)

    def test_burn_video_subtitles_cleans_temp_ass_when_ffmpeg_fails(self) -> None:
        video_path = FIXTURE_DIR / "sample-video.mp4"
        output_dir = self.make_output_dir()
        output_path = output_dir / "failed.mp4"
        fake_ffmpeg = output_dir / "ffmpeg-bin"
        captured: dict[str, Path] = {}

        def fake_run(command: list[str], *, cwd: Path) -> None:
            captured["cwd"] = cwd
            self.assertTrue((cwd / "subtitles.ass").exists())
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=command,
                stderr="ffmpeg failed",
            )

        with (
            patch(
                "backend.app.video_burn_export_service.resolve_ffmpeg_binary",
                return_value=fake_ffmpeg,
            ),
            patch(
                "backend.app.video_burn_export_service.resolve_ffprobe_binary",
                return_value=None,
            ),
            patch(
                "backend.app.video_burn_export_service._run_ffmpeg_command",
                side_effect=fake_run,
            ),
        ):
            with self.assertRaises(VideoBurnExportServiceError) as context:
                burn_video_subtitles(
                    video_path=str(video_path),
                    output_path=str(output_path),
                    segments=[self.build_segment()],
                    mode="bilingual",
                )

        self.assertIn("FFmpeg could not export", str(context.exception))
        self.assertIn("cwd", captured)
        self.assertFalse(captured["cwd"].exists())


if __name__ == "__main__":
    unittest.main()
