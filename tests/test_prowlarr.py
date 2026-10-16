import unittest

try:
    from backend.prowlarr_client import determine_release_status
except ImportError:
    from torr2jelly.backend.prowlarr_client import determine_release_status


class TestProwlarrReleaseStatus(unittest.TestCase):
    def test_determine_release_status_gold(self):
        self.assertEqual(determine_release_status(["freeleech"], None), "gold")
        self.assertEqual(determine_release_status([], 0), "gold")
        self.assertEqual(determine_release_status(["Freeleech", "internal"], 1.0), "gold")

    def test_determine_release_status_silver(self):
        self.assertEqual(determine_release_status(["halfleech"], None), "silver")
        self.assertEqual(determine_release_status([], 0.5), "silver")

    def test_determine_release_status_normal(self):
        self.assertEqual(determine_release_status([], None), "normal")
        self.assertEqual(determine_release_status(["scene"], 1.0), "normal")

    def test_settings_only_gold_torrents_default(self):
        try:
            from backend.config import Settings
        except ImportError:
            from torr2jelly.backend.config import Settings
        s = Settings()
        self.assertFalse(s.only_gold_torrents)

    def test_filter_only_gold_torrents(self):
        items = [
            {"title": "Movie A", "release_status": "gold"},
            {"title": "Movie B", "release_status": "silver"},
            {"title": "Movie C", "release_status": "normal"},
        ]
        filtered = [r for r in items if r.get("release_status") == "gold"]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "Movie A")


if __name__ == "__main__":
    unittest.main()
