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
    def _call(self, stdin_bytes: bytes) -> str | None:
        # Mirror stdin by slicing the same buffer os.read would consume.
        buf = bytearray(stdin_bytes)

        def fake_read(_fd, nbytes):
            n = min(nbytes, len(buf))
            chunk = bytes(buf[:n])
            del buf[:n]
            return chunk

        def fake_select(rlist, wlist, xlist, timeout=None):
            # Ready whenever there are bytes left for the next os.read.
            if buf:
                return (rlist, [], [])
            return ([], [], [])

        with unittest.mock.patch("select.select", side_effect=fake_select):
            with unittest.mock.patch("os.read", side_effect=fake_read):
                return pfb.entrypoints.slideshow._read_key(5.0)

    def test_left_arrow(self):
        self.assertEqual(self._call(b"\x1b[D"), "left")

    def test_right_arrow(self):
        self.assertEqual(self._call(b"\x1b[C"), "right")

    def test_escape_quits(self):
        self.assertEqual(self._call(b"\x1b"), "quit")

    def test_timeout_returns_none(self):
        # When select reports stdin not ready, None must be returned.
        with unittest.mock.patch("select.select", return_value=([], [], [])):
            result = pfb.entrypoints.slideshow._read_key(5.0)
        self.assertIsNone(result)

    def test_unrecognised_key_returns_none(self):
        self.assertIsNone(self._call(b"x"))


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
    def _run(
        self,
        tmpdir: str,
        extra_args: list[str] = (),
        keys: list = (),
        max_displays: int | None = None,
        display_side_effects: list | None = None,
    ) -> unittest.mock.MagicMock:
        """Run main(), stopping after max_displays calls to display_image.

        _wait_for_key is mocked to return pre-canned keys then None (timeout).
        A private _Stop exception terminates the infinite loop once max_displays
        images have been shown, avoiding the need for any real sleeping.
        """
        if max_displays is None:
            max_displays = sum(1 for p in pathlib.Path(tmpdir).iterdir() if p.is_file())

        mock_fb = unittest.mock.MagicMock()
        if display_side_effects is not None:
            mock_fb.display_image.side_effect = display_side_effects

        key_list = list(keys)

        class _Stop(Exception):
            pass

        def _key_side_effect(timeout):
            # Stop once max_displays images have been shown.
            n = mock_fb.display_image.call_count
            if n >= max_displays:
                raise _Stop()
            # Return the pre-canned key for this display index, or None on timeout.
            return key_list[n - 1] if n - 1 < len(key_list) else None

        argv = ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0"] + list(extra_args)
        with unittest.mock.patch("sys.argv", argv):
            with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                with unittest.mock.patch(
                    "pfb.entrypoints.slideshow._wait_for_key", side_effect=_key_side_effect
                ):
                    try:
                        pfb.entrypoints.slideshow.main()
                    except _Stop:
                        pass
        return mock_fb

    def test_exits_when_no_files_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb0", tmpdir]):
                with self.assertRaises(SystemExit) as ctx:
                    pfb.entrypoints.slideshow.main()
                self.assertEqual(ctx.exception.code, 1)

    def test_displays_each_file(self):
        # Every file must be displayed once per pass.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = self._run(tmpdir)
            self.assertEqual(mock_fb.display_image.call_count, 2)

    def test_opens_framebuffer_with_given_device(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = unittest.mock.MagicMock()

            class _Stop(Exception):
                pass

            def _key_side_effect(timeout):
                if mock_fb.display_image.call_count >= 1:
                    raise _Stop()
                return None

            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb1", tmpdir, "--time", "0"]):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb) as mock_cls:
                    with unittest.mock.patch(
                        "pfb.entrypoints.slideshow._wait_for_key", side_effect=_key_side_effect
                    ):
                        try:
                            pfb.entrypoints.slideshow.main()
                        except _Stop:
                            pass
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
            # timeout → b, left → back to a, then stop
            mock_fb = self._run(tmpdir, keys=[None, "left"], max_displays=3)
            displayed = [c.args[0] for c in mock_fb.display_image.call_args_list]
            self.assertTrue(displayed[0].endswith("a.jpg"))
            self.assertTrue(displayed[1].endswith("b.jpg"))
            self.assertTrue(displayed[2].endswith("a.jpg"))

    def test_left_key_at_first_image_stays(self):
        # Pressing left at the first image must redisplay it rather than going out of bounds.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = self._run(tmpdir, keys=["left", "left"], max_displays=3)
            displayed = [c.args[0] for c in mock_fb.display_image.call_args_list]
            # First three displays are all a.jpg (left keeps index at 0).
            self.assertTrue(all(p.endswith("a.jpg") for p in displayed[:3]))

    def test_loops_after_list_exhausted(self):
        # After the last image the slideshow must loop back to the first.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = self._run(tmpdir, max_displays=3)
            displayed = [c.args[0] for c in mock_fb.display_image.call_args_list]
            # Third display must be the first file again.
            self.assertEqual(displayed[0], displayed[2])

    def test_reshuffles_on_loop_with_random(self):
        # With --random, the list must be reshuffled at the start of each loop.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            with unittest.mock.patch("random.shuffle") as mock_shuffle:
                self._run(tmpdir, extra_args=["--random"], max_displays=3)
            # Once for the initial shuffle, once when the list wraps around.
            self.assertEqual(mock_shuffle.call_count, 2)

    def test_no_reshuffle_on_loop_without_random(self):
        # Without --random, shuffle must never be called, even across loops.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            with unittest.mock.patch("random.shuffle") as mock_shuffle:
                self._run(tmpdir, max_displays=3)
            mock_shuffle.assert_not_called()

    def test_random_flag_shuffles_order(self):
        # With --random, files must be shuffled before the first pass.
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["a.jpg", "b.jpg", "c.jpg"]:
                (pathlib.Path(tmpdir) / name).touch()
            with unittest.mock.patch("random.shuffle") as mock_shuffle:
                self._run(tmpdir, extra_args=["--random"])
            self.assertGreaterEqual(mock_shuffle.call_count, 1)

    def test_no_random_flag_preserves_order(self):
        # Without --random, shuffle must not be called on the first pass.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            with unittest.mock.patch("random.shuffle") as mock_shuffle:
                self._run(tmpdir)
            mock_shuffle.assert_not_called()

    def test_timestamp_flag_passed_to_display_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = self._run(tmpdir, extra_args=["--timestamp"])
            mock_fb.display_image.assert_called_once_with(
                unittest.mock.ANY,
                show_timestamp=True,
                show_model=False,
                slideshow_gutter=True,
            )

    def test_model_flag_passed_to_display_image(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            mock_fb = self._run(tmpdir, extra_args=["--model"])
            mock_fb.display_image.assert_called_once_with(
                unittest.mock.ANY,
                show_timestamp=False,
                show_model=True,
                slideshow_gutter=True,
            )

    def test_skips_unreadable_file_and_continues(self):
        # A file that raises on display must be skipped; remaining files still shown.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = self._run(
                tmpdir,
                display_side_effects=[OSError("unreadable"), None],
            )
            self.assertEqual(mock_fb.display_image.call_count, 2)

    def test_quit_key_exits(self):
        # Escape must end the slideshow without looping to another image.
        with tempfile.TemporaryDirectory() as tmpdir:
            (pathlib.Path(tmpdir) / "a.jpg").touch()
            (pathlib.Path(tmpdir) / "b.jpg").touch()
            mock_fb = unittest.mock.MagicMock()
            with unittest.mock.patch("sys.argv", ["pfb_slideshow", "/dev/fb0", tmpdir, "--time", "0"]):
                with unittest.mock.patch("pfb.framebuffer.Framebuffer", return_value=mock_fb):
                    with unittest.mock.patch(
                        "pfb.entrypoints.slideshow._wait_for_key", return_value="quit"
                    ):
                        with self.assertRaises(SystemExit) as ctx:
                            pfb.entrypoints.slideshow.main()
            self.assertEqual(ctx.exception.code, 0)
            mock_fb.display_image.assert_called_once()


if __name__ == "__main__":
    unittest.main()
