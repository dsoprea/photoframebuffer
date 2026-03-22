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


class TestReadKey(unittest.TestCase):
    def _call(self, stdin_bytes: str, select_ready: bool = True) -> str | None:
        # Simulate select reporting stdin ready, then stdin.read returning the given bytes.
        select_result = ([unittest.mock.sentinel.stdin], [], []) if select_ready else ([], [], [])
        with unittest.mock.patch("select.select", return_value=select_result):
            with unittest.mock.patch("sys.stdin") as mock_stdin:
                # First read returns the first char; subsequent reads return the rest.
                chars = list(stdin_bytes)
                mock_stdin.read.side_effect = ["".join(chars[:1]), "".join(chars[1:])]
                return pfb.entrypoints.slideshow._read_key(5.0)

    def test_left_arrow(self):
        self.assertEqual(self._call("\x1b[D"), "left")

    def test_right_arrow(self):
        self.assertEqual(self._call("\x1b[C"), "right")

    def test_timeout_returns_none(self):
        # When select reports stdin not ready, None must be returned.
        select_result = ([], [], [])
        with unittest.mock.patch("select.select", return_value=select_result):
            result = pfb.entrypoints.slideshow._read_key(5.0)
        self.assertIsNone(result)

    def test_unrecognised_key_returns_none(self):
        self.assertIsNone(self._call("x"))


class TestWaitForKey(unittest.TestCase):
    def test_non_tty_sleeps_and_returns_none(self):
        # When stdin is not a tty, _wait_for_key must sleep and return None.
        with unittest.mock.patch("os.isatty", return_value=False):
            with unittest.mock.patch("time.sleep") as mock_sleep:
                result = pfb.entrypoints.slideshow._wait_for_key(3.0)
        mock_sleep.assert_called_once_with(3.0)
        self.assertIsNone(result)

    def test_tty_uses_raw_mode_and_returns_key(self):
        # When stdin is a tty, raw mode must be set and the key returned.
        with unittest.mock.patch("os.isatty", return_value=True):
            with unittest.mock.patch("termios.tcgetattr", return_value=[]):
                with unittest.mock.patch("termios.tcsetattr"):
                    with unittest.mock.patch("tty.setraw"):
                        with unittest.mock.patch(
                            "pfb.entrypoints.slideshow._read_key", return_value="right"
                        ):
                            result = pfb.entrypoints.slideshow._wait_for_key(5.0)
        self.assertEqual(result, "right")

    def test_tty_restores_terminal_on_exception(self):
        # Terminal settings must be restored even if _read_key raises.
        saved = [object()]
        with unittest.mock.patch("os.isatty", return_value=True):
            with unittest.mock.patch("termios.tcgetattr", return_value=saved):
                with unittest.mock.patch("termios.tcsetattr") as mock_restore:
                    with unittest.mock.patch("tty.setraw"):
                        with unittest.mock.patch(
                            "pfb.entrypoints.slideshow._read_key", side_effect=RuntimeError
                        ):
                            with self.assertRaises(RuntimeError):
                                pfb.entrypoints.slideshow._wait_for_key(5.0)
        mock_restore.assert_called_once()


class TestSlideshowMain(unittest.TestCase):
    def _run(self, tmpdir: str, extra_args: list[str] = (), keys: list = ()) -> unittest.mock.MagicMock:
        """Run main() with a mocked framebuffer and pre-canned key sequence."""
        mock_fb = unittest.mock.MagicMock()
        key_iter = iter(list(keys) + [None] * 100)
        argv = ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0"] + list(extra_args)
        with unittest.mock.patch("sys.argv", argv):
            with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                with unittest.mock.patch(
                    "pfb.entrypoints.slideshow._wait_for_key", side_effect=key_iter
                ):
                    pfb.entrypoints.slideshow.main()
        return mock_fb

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
            mock_fb = self._run(tmpdir)
            self.assertEqual(mock_fb.display_image.call_count, 2)

    def test_opens_framebuffer_with_given_device(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = unittest.mock.MagicMock()
            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb1", tmpdir, "--time", "0"]):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb) as mock_cls:
                    with unittest.mock.patch("pfb.entrypoints.slideshow._wait_for_key", return_value=None):
                        pfb.entrypoints.slideshow.main()
            mock_cls.assert_called_once_with("/dev/fb1")

    def test_right_key_advances_to_next_image(self):
        # A 'right' key press must advance to the next image immediately.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = self._run(tmpdir, keys=["right"])
            displayed = [c.args[0] for c in mock_fb.display_image.call_args_list]
            self.assertTrue(displayed[0].endswith("a.jpg"))
            self.assertTrue(displayed[1].endswith("b.jpg"))

    def test_left_key_goes_to_previous_image(self):
        # After advancing to image 1, a 'left' key must redisplay image 0.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            # timeout → advance to b, then left → back to a, then timeout → advance past end
            mock_fb = self._run(tmpdir, keys=[None, "left"])
            displayed = [c.args[0] for c in mock_fb.display_image.call_args_list]
            self.assertTrue(displayed[0].endswith("a.jpg"))
            self.assertTrue(displayed[1].endswith("b.jpg"))
            self.assertTrue(displayed[2].endswith("a.jpg"))

    def test_left_key_at_first_image_stays(self):
        # Pressing left at the first image must redisplay it rather than going out of bounds.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = self._run(tmpdir, keys=["left", "left"])
            displayed = [c.args[0] for c in mock_fb.display_image.call_args_list]
            # First three displays are all a.jpg (left keeps index at 0).
            self.assertTrue(all(p.endswith("a.jpg") for p in displayed[:3]))

    def test_random_flag_shuffles_order(self):
        # With --random, files must be passed to shuffle before display.
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["a.jpg", "b.jpg", "c.jpg"]:
                (pathlib.Path(tmpdir) / name).touch()
            mock_fb = unittest.mock.MagicMock()
            argv = ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0", "--random"]
            with unittest.mock.patch("sys.argv", argv):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                    with unittest.mock.patch("pfb.entrypoints.slideshow._wait_for_key", return_value=None):
                        with unittest.mock.patch("random.shuffle") as mock_shuffle:
                            pfb.entrypoints.slideshow.main()
            mock_shuffle.assert_called_once()

    def test_no_random_flag_preserves_order(self):
        # Without --random, shuffle must not be called.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = unittest.mock.MagicMock()
            argv = ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0"]
            with unittest.mock.patch("sys.argv", argv):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                    with unittest.mock.patch("pfb.entrypoints.slideshow._wait_for_key", return_value=None):
                        with unittest.mock.patch("random.shuffle") as mock_shuffle:
                            pfb.entrypoints.slideshow.main()
            mock_shuffle.assert_not_called()

    def test_timestamp_flag_passed_to_display_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = self._run(tmpdir, extra_args=["--timestamp"])
            mock_fb.display_image.assert_called_once_with(
                unittest.mock.ANY, show_timestamp=True, show_model=False
            )

    def test_model_flag_passed_to_display_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = self._run(tmpdir, extra_args=["--model"])
            mock_fb.display_image.assert_called_once_with(
                unittest.mock.ANY, show_timestamp=False, show_model=True
            )

    def test_skips_unreadable_file_and_continues(self):
        # A file that raises on display must be skipped; remaining files still shown.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = unittest.mock.MagicMock()
            mock_fb.display_image.side_effect = [OSError("unreadable"), None]
            argv = ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0"]
            with unittest.mock.patch("sys.argv", argv):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                    with unittest.mock.patch("pfb.entrypoints.slideshow._wait_for_key", return_value=None):
                        pfb.entrypoints.slideshow.main()
            self.assertEqual(mock_fb.display_image.call_count, 2)


if __name__ == "__main__":
    unittest.main()
