import unittest

from mikasa.helpers._utilities import (
    format_duration,
    format_eta,
    format_size,
    format_uptime,
    progress_bar,
)


class FormattingTests(unittest.TestCase):
    def test_duration(self):
        self.assertEqual(format_duration(0), "0:00")
        self.assertEqual(format_duration(65), "1:05")
        self.assertEqual(format_duration(3725), "1:02:05")
        self.assertEqual(format_duration(-5), "0:00")

    def test_size(self):
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(1536), "1.5 KB")
        self.assertEqual(format_size(5 * 1024 * 1024), "5.0 MB")

    def test_eta(self):
        self.assertEqual(format_eta(0), "0s")
        self.assertEqual(format_eta(45), "45s")
        self.assertEqual(format_eta(90), "1m 30s")
        self.assertEqual(format_eta(3700), "1h 1m")

    def test_progress_bar(self):
        self.assertEqual(progress_bar(0, 100, width=10), "----------")
        self.assertEqual(progress_bar(100, 100, width=10), "##########")
        self.assertEqual(progress_bar(50, 100, width=10), "#####-----")
        self.assertEqual(progress_bar(5, 0, width=10), "----------")

    def test_uptime(self):
        self.assertEqual(format_uptime(0), "0:00")
        self.assertEqual(format_uptime(45), "0:45")
        self.assertEqual(format_uptime(3700), "1:01:40")
        self.assertEqual(format_uptime(90061), "1 days, 1:01:01")
        self.assertEqual(format_uptime(-5), "0:00")
