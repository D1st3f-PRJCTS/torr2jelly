import os
import sys
import tempfile
import unittest

_current_dir = os.path.dirname(os.path.abspath(__file__))
_torr2jelly_dir = os.path.dirname(_current_dir)
for p in (_torr2jelly_dir,):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend import strm_engine
from backend.config import MediaCategory, get_default_categories


class TestCategories(unittest.TestCase):
    def setUp(self):
        self.tmp_media = tempfile.TemporaryDirectory()
        self.media_dir = self.tmp_media.name

    def tearDown(self):
        self.tmp_media.cleanup()

    def test_default_categories(self):
        cats = get_default_categories()
        self.assertEqual(len(cats), 2)
        self.assertEqual(cats[0].id, "movie")
        self.assertEqual(cats[1].id, "show")

    def test_get_category_path(self):
        cat_rel = MediaCategory(id="cartoons", name="Cartoons", type="movie", path="cartoons")
        res_rel = strm_engine.get_category_path(cat_rel, self.media_dir)
        self.assertEqual(res_rel, os.path.join(self.media_dir, "cartoons"))

        cat_abs = MediaCategory(id="external", name="External", type="show", path="/mnt/nas/Shows")
        res_abs = strm_engine.get_category_path(cat_abs, self.media_dir)
        self.assertEqual(res_abs, "/mnt/nas/Shows")

    def test_migrate_category_folder(self):
        old_folder = os.path.join(self.media_dir, "old_movies")
        new_folder = os.path.join(self.media_dir, "new_movies")
        os.makedirs(os.path.join(old_folder, "Inception"), exist_ok=True)
        with open(os.path.join(old_folder, "Inception", "Inception.strm"), "w") as f:
            f.write("http://torrserver:8090/stream?link=123&index=1\n")

        strm_engine.migrate_category_folder(old_folder, new_folder)

        # Old file should now be in new_folder
        self.assertTrue(os.path.exists(os.path.join(new_folder, "Inception", "Inception.strm")))
        self.assertFalse(os.path.exists(os.path.join(old_folder, "Inception", "Inception.strm")))

    def test_sync_to_custom_category(self):
        cats = [
            {"id": "cartoons", "name": "Cartoons", "type": "movie", "path": "animated"},
            {"id": "anime", "name": "Anime", "type": "show", "path": "anime_shows"},
        ]
        torrent_movie = {
            "hash": "hash_cartoons_1",
            "title": "Shrek.2001.1080p",
            "file_stats": [{"id": 0, "path": "Shrek.2001.mkv", "size": 1000}],
        }
        paths = strm_engine.sync_single_torrent(
            torrent_item=torrent_movie,
            media_dir=self.media_dir,
            stream_base_url="http://torrserver:8090",
            override_category="cartoons",
            categories=cats,
        )
        self.assertEqual(len(paths), 1)
        expected_path = os.path.join(self.media_dir, "animated", "Shrek", "Shrek.strm")
        self.assertEqual(os.path.normpath(paths[0]), os.path.normpath(expected_path))
        self.assertTrue(os.path.exists(expected_path))

    def test_sync_show_to_custom_category(self):
        cats = [{"id": "anime", "name": "Anime", "type": "show", "path": "anime_series"}]
        torrent_show = {
            "hash": "hash_anime_1",
            "title": "Attack on Titan (Season 1)",
            "file_stats": [
                {"id": 0, "path": "Attack.on.Titan.S01E01.mkv", "size": 1000},
                {"id": 1, "path": "Attack.on.Titan.S01E02.mkv", "size": 1000},
            ],
        }
        paths = strm_engine.sync_single_torrent(
            torrent_item=torrent_show,
            media_dir=self.media_dir,
            stream_base_url="http://torrserver:8090",
            override_category="anime",
            categories=cats,
        )
        self.assertEqual(len(paths), 2)
        ep1 = os.path.join(
            self.media_dir,
            "anime_series",
            "Attack on Titan",
            "Season 01",
            "Attack.on.Titan.S01E01.strm",
        )
        self.assertTrue(os.path.exists(ep1))

    def test_extract_poster_candidates(self):
        title = "Молодий Папа / The Young Pope [Сезон 1] (2016)"
        candidates = strm_engine.extract_poster_search_candidates(title)
        self.assertIn("The Young Pope", candidates)
        self.assertIn("Молодий Папа", candidates)
        self.assertEqual(candidates[0], "The Young Pope")

    def test_clean_media_title_regression(self):
        # Peaky Blinders should not lose the "s" in Blinders
        clean = strm_engine.clean_media_title("Peaky Blinders 1080p H265 [Ukr,Eng] [Toloka]")
        self.assertEqual(clean, "Peaky Blinders")


if __name__ == "__main__":
    unittest.main()
