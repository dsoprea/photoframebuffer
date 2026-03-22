"""Tests for pfb.entrypoints.slideshow."""

import pathlib
import tempfile
import unittest
import unittest.mock

import pfb.entrypoints.slideshow


class TestCollectFilesFromDirectory(unittest.TestCase):
    def test_lists_all_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            files = pfb.entrypoints.slideshow._collect_files(tmpdir, None, None)
            self.assertEqual(len(files), 2)

    def test_files_sorted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            files = pfb.entrypoints.slideshow._collect_files(tmpdir, None, None)
            self.assertEqual(files, sorted(files))

    def test_excludes_subdirectories(self):
        # Subdirectories must not appear in the file list.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "img.jpg").touch()
            (pathlib.Path(tmpdir) / "subdir").mkdir()
            files = pfb.entrypoints.slideshow._collect_files(tmpdir, None, None)
            self.assertEqual(len(files), 1)

    def test_empty_directory_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            files = pfb.entrypoints.slideshow._collect_files(tmpdir, None, None)
            self.assertEqual(files, [])


class TestCollectFilesFromFileList(unittest.TestCase):
    def test_reads_paths_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_file = pathlib.Path(tmpdir) / "list.txt"
            list_file.write_text("a.jpg\nb.jpg\n")
            files = pfb.entrypoints.slideshow._collect_files(str(list_file), None, None)
            self.assertEqual(files, ["a.jpg", "b.jpg"])

    def test_skips_blank_lines(self):
        # Blank lines in the file list must be ignored.
        with tempfile.TemporaryDirectory() as tmpdir:
            list_file = pathlib.Path(tmpdir) / "list.txt"
            list_file.write_text("a.jpg\n\nb.jpg\n")
            files = pfb.entrypoints.slideshow._collect_files(str(list_file), None, None)
            self.assertEqual(len(files), 2)

    def test_prepends_root_to_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_file = pathlib.Path(tmpdir) / "list.txt"
            list_file.write_text("a.jpg\n")
            files = pfb.entrypoints.slideshow._collect_files(str(list_file), None, "/photos")
            self.assertEqual(files, ["/photos/a.jpg"])

    def test_root_not_applied_when_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            list_file = pathlib.Path(tmpdir) / "list.txt"
            list_file.write_text("a.jpg\n")
            files = pfb.entrypoints.slideshow._collect_files(str(list_file), None, None)
            self.assertEqual(files, ["a.jpg"])


class TestCollectFilesFilter(unittest.TestCase):
    def test_filter_retains_matching_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.png").touch()
            files = pfb.entrypoints.slideshow._collect_files(tmpdir, "*.jpg", None)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].endswith("a.jpg"))

    def test_filter_no_match_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            files = pfb.entrypoints.slideshow._collect_files(tmpdir, "*.png", None)
            self.assertEqual(files, [])

    def test_filter_applied_to_filename_not_full_path(self):
        # The filter pattern must match only the filename, not the directory portion.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "photo.jpg").touch()
            files = pfb.entrypoints.slideshow._collect_files(tmpdir, "photo.*", None)
            self.assertEqual(len(files), 1)


class TestSlideshowMain(unittest.TestCase):
    def test_exits_when_no_files_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb0", tmpdir]):
                with self.assertRaises(SystemExit) as ctx:
                    pfb.entrypoints.slideshow.main()
                self.assertEqual(ctx.exception.code, 1)

    def test_displays_each_file(self):
        # Every file in the source must be passed to display_image exactly once.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = unittest.mock.MagicMock()
            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0"]):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                    pfb.entrypoints.slideshow.main()
            self.assertEqual(mock_fb.display_image.call_count, 2)

    def test_opens_framebuffer_with_given_device(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = unittest.mock.MagicMock()
            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb1", tmpdir, "--time", "0"]):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb) as mock_cls:
                    pfb.entrypoints.slideshow.main()
            mock_cls.assert_called_once_with("/dev/fb1")

    def test_skips_unreadable_file_and_continues(self):
        # A file that raises on display must be skipped; remaining files still shown.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = unittest.mock.MagicMock()
            mock_fb.display_image.side_effect = [OSError("unreadable"), None]
            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0"]):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                    pfb.entrypoints.slideshow.main()
            self.assertEqual(mock_fb.display_image.call_count, 2)


if __name__ == "__main__":
    unittest.main()
