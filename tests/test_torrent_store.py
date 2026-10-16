import os
import sys
import tempfile
import unittest

_current_dir = os.path.dirname(os.path.abspath(__file__))
_torr2jelly_dir = os.path.dirname(_current_dir)
for p in (_torr2jelly_dir,):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend import strm_engine, torrent_store


class TestTorrentStore(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_users.db")
        os.environ["USERS_DB_PATH"] = self.db_path
        torrent_store.init_torrent_store()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_get_torrent_meta(self):
        h = "cee81b76c63a6fc6ce5380d4cdd471be2ec507e0"
        torrent_store.save_torrent_meta(
            hash_id=h,
            title="True Detective 1080p",
            clean_title="True Detective",
            category="show",
            poster="https://image.tmdb.org/poster.jpg",
            folder_name="True Detective",
        )

        meta = torrent_store.get_torrent_meta(h)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["title"], "True Detective 1080p")
        self.assertEqual(meta["clean_title"], "True Detective")
        self.assertEqual(meta["category"], "show")

        all_meta = torrent_store.get_all_torrent_meta()
        self.assertIn(h, all_meta)

        deleted = torrent_store.delete_torrent_meta(h)
        self.assertTrue(deleted)
        self.assertIsNone(torrent_store.get_torrent_meta(h))

    def test_recover_title_from_disk(self):
        with tempfile.TemporaryDirectory() as media_dir:
            shows_dir = os.path.join(media_dir, "shows", "Severance", "Season 01")
            os.makedirs(shows_dir, exist_ok=True)
            strm_path = os.path.join(shows_dir, "Severance.S01E01.strm")
            test_hash = "abc123def456"
            with open(strm_path, "w") as f:
                f.write(f"http://torrserver:8090/stream?link={test_hash}&index=1&play\n")

            recovered = strm_engine.recover_title_from_disk(test_hash, media_dir)
            self.assertIsNotNone(recovered)
            self.assertEqual(recovered[0], "Severance")
            self.assertEqual(recovered[1], "Severance")


if __name__ == "__main__":
    unittest.main()
