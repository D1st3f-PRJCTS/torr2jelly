import unittest
import tempfile
import os
import sys
import json

# Ensure project and package roots are in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_torr2jelly_dir = os.path.dirname(_current_dir)
_epic_root = os.path.dirname(_torr2jelly_dir)
for p in (_epic_root, _torr2jelly_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.strm_engine import (
        sanitize_filename,
        clean_media_title,
        extract_video_files,
        parse_episode_info,
        sync_single_torrent,
        sync_all_torrents,
        remove_torrent_files,
        find_torrent_root_folder,
        get_media_structure,
        create_media_folder,
        rename_media_item,
        move_media_files,
        delete_media_item,
        auto_organize_seasons,
        rename_torrent_root_folder
    )
except ImportError:
    from torr2jelly.backend.strm_engine import (
        sanitize_filename,
        clean_media_title,
        extract_video_files,
        parse_episode_info,
        sync_single_torrent,
        sync_all_torrents,
        remove_torrent_files,
        find_torrent_root_folder,
        get_media_structure,
        create_media_folder,
        rename_media_item,
        move_media_files,
        delete_media_item,
        auto_organize_seasons,
        rename_torrent_root_folder
    )

class TestSTRMEngine(unittest.TestCase):

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Movie: The Beginning / Part 1"), "Movie The Beginning Part 1")
        self.assertEqual(sanitize_filename("File?*<>|name"), "Filename")
        self.assertEqual(sanitize_filename("  Extra   Spaces  "), "Extra Spaces")
        self.assertEqual(sanitize_filename('A "quote" & <tag>'), "A quote & tag")

    def test_clean_media_title(self):
        cases = [
            ("Dune.Part.Two.2024.2160p.UHD.HDR10.DV.x265", "Dune Part Two"),
            ("[Toloka] Severance (Season 1) WEBRip 1080p UkrEng", "Severance"),
            ("The.Lord.of.the.Rings.The.Fellowship.of.the.Ring.(2001).BDRip.x264", "The Lord of the Rings The Fellowship of the Ring"),
            ("Breaking Bad Сезон 1-2 1080p", "Breaking Bad"),
            ("Chernobyl (2019) 1080p BluRay", "Chernobyl"),
            ("Inception.2010.1080p.BDRip", "Inception"),
            ("2001 A Space Odyssey", "2001 A Space Odyssey"),
            ("1984", "1984"),
            ("Dark S01 720p WEB-DL", "Dark"),
            ("[Hurtom] Stranger Things (Season 4) [2022] WEB-DL 2160p", "Stranger Things"),
            ("Legend (2015) BDRemux 1080p 2xUkr/Eng | Sub...", "Legend"),
        ]
        for raw, expected in cases:
            cleaned = clean_media_title(raw)
            self.assertEqual(cleaned, expected, f"Failed for {raw}: got {cleaned}, expected {expected}")

    def test_sync_single_torrent_movie(self):
        with tempfile.TemporaryDirectory() as tmp_media:
            torrent_data = {
                "hash": "movie123hash",
                "title": "Inception.2010.1080p.BDRip",
                "file_stats": [
                    {"id": 0, "path": "Inception.2010.mkv", "size": 1000}
                ]
            }
            stream_url = "http://torrserver:8090"
            paths = sync_single_torrent(torrent_data, tmp_media, stream_url)
            self.assertEqual(len(paths), 1)
            self.assertTrue(os.path.exists(paths[0]))
            self.assertTrue(paths[0].endswith("movies/Inception/Inception.strm"))

    def test_sync_single_torrent_tv(self):
        with tempfile.TemporaryDirectory() as tmp_media:
            torrent_data = {
                "hash": "series456hash",
                "title": "Severance (Season 1)",
                "file_stats": [
                    {"id": 0, "path": "Severance/Season 1/Severance.S01E01.mkv", "size": 1000},
                    {"id": 1, "path": "Severance/Season 1/Severance.S01E02.mkv", "size": 1000}
                ]
            }
            stream_url = "http://torrserver:8090"
            paths = sync_single_torrent(torrent_data, tmp_media, stream_url)
            self.assertEqual(len(paths), 2)

            for p in paths:
                self.assertTrue(os.path.exists(p))
                self.assertTrue("shows/Severance/Season 01" in p)

    def test_remove_torrent_files(self):
        with tempfile.TemporaryDirectory() as tmp_media:
            torrent_data = {
                "hash": "delhash123",
                "title": "Old Movie (2000)",
                "file_stats": [
                    {"id": 0, "path": "Old.Movie.2000.mkv", "size": 500}
                ]
            }
            stream_url = "http://torrserver:8090"
            paths = sync_single_torrent(torrent_data, tmp_media, stream_url)
            self.assertEqual(len(paths), 1)
            self.assertTrue(os.path.exists(paths[0]))

            removed = remove_torrent_files(torrent_data, tmp_media)
            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(paths[0]))
            movie_dir = os.path.dirname(paths[0])
            self.assertFalse(os.path.exists(movie_dir))

    def test_sync_cleans_up_orphaned_strm_files(self):
        with tempfile.TemporaryDirectory() as tmp_media:
            torrent_data = {
                "hash": "movie123hash",
                "title": "Old Movie Title",
                "file_stats": [
                    {"id": 0, "path": "Legend.mkv", "size": 1000}
                ]
            }
            stream_url = "http://torrserver:8090"
            paths1 = sync_single_torrent(torrent_data, tmp_media, stream_url)
            self.assertEqual(len(paths1), 1)
            old_strm = paths1[0]
            self.assertTrue(os.path.exists(old_strm))
            old_dir = os.path.dirname(old_strm)

            # Re-sync with a cleaned or changed title
            torrent_data["title"] = "New Movie Title"
            paths2 = sync_single_torrent(torrent_data, tmp_media, stream_url)
            self.assertEqual(len(paths2), 1)
            new_strm = paths2[0]
            self.assertTrue(os.path.exists(new_strm))
            self.assertNotEqual(old_strm, new_strm)

            # Old orphaned strm and directory must be cleaned up automatically!
            self.assertFalse(os.path.exists(old_strm))
            self.assertFalse(os.path.exists(old_dir))

    def test_media_file_structure_operations(self):
        with tempfile.TemporaryDirectory() as tmp_media:
            show_root = os.path.join(tmp_media, "shows", "TestShow")
            os.makedirs(show_root, exist_ok=True)

            # Create folder
            created = create_media_folder(show_root, "Season 01")
            self.assertEqual(created, "Season 01")
            self.assertTrue(os.path.isdir(os.path.join(show_root, "Season 01")))

            # Path traversal rejection
            with self.raises(ValueError):
                create_media_folder(show_root, "../../escaped")

            # Create test files
            f1 = os.path.join(show_root, "Season 01", "ep1.strm")
            with open(f1, "w") as fl:
                fl.write("http://stream/1\n")

            # Get media structure
            struct = get_media_structure(show_root, "shows/TestShow")
            self.assertTrue(struct["exists"])
            self.assertIn("Season 01", struct["folders"])
            self.assertEqual(len(struct["files"]), 1)
            self.assertEqual(struct["files"][0]["name"], "ep1.strm")

            # Rename file
            renamed = rename_media_item(show_root, "Season 01/ep1.strm", "TestShow.S01E01.strm")
            self.assertEqual(renamed, "Season 01/TestShow.S01E01.strm")
            self.assertTrue(os.path.exists(os.path.join(show_root, "Season 01", "TestShow.S01E01.strm")))

            # Move file
            create_media_folder(show_root, "Season 02")
            moved = move_media_files(show_root, ["Season 01/TestShow.S01E01.strm"], "Season 02")
            self.assertEqual(moved, 1)
            self.assertTrue(os.path.exists(os.path.join(show_root, "Season 02", "TestShow.S01E01.strm")))
            self.assertFalse(os.path.exists(os.path.join(show_root, "Season 01", "TestShow.S01E01.strm")))

            # Delete file
            self.assertTrue(delete_media_item(show_root, "Season 02/TestShow.S01E01.strm"))
            self.assertFalse(os.path.exists(os.path.join(show_root, "Season 02", "TestShow.S01E01.strm")))

    def test_auto_organize_loose_episodes(self):
        with tempfile.TemporaryDirectory() as tmp_media:
            show_root = os.path.join(tmp_media, "shows", "MessyShow")
            os.makedirs(show_root, exist_ok=True)

            # Create loose files right in the root (nasypom)
            loose_files = [
                "MessyShow.S01E01.strm",
                "MessyShow.S01E02.strm",
                "MessyShow.2x01.strm",
                "MessyShow.Special.strm"
            ]
            for lf in loose_files:
                with open(os.path.join(show_root, lf), "w") as fl:
                    fl.write("http://stream/link\n")

            res = auto_organize_seasons(show_root)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["moved_count"], 4)

            # Verify organized structure
            self.assertTrue(os.path.exists(os.path.join(show_root, "Season 01", "MessyShow.S01E01.strm")))
            self.assertTrue(os.path.exists(os.path.join(show_root, "Season 01", "MessyShow.S01E02.strm")))
            self.assertTrue(os.path.exists(os.path.join(show_root, "Season 02", "MessyShow.2x01.strm")))
            self.assertTrue(os.path.exists(os.path.join(show_root, "Season 00", "MessyShow.Special.strm")))

            # Verify no loose files left in root
            for lf in loose_files:
                self.assertFalse(os.path.exists(os.path.join(show_root, lf)))

    def raises(self, exc):
        return self.assertRaises(exc)

    def test_rename_torrent_root_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            shows_dir = os.path.join(tmpdir, "shows")
            old_root = os.path.join(shows_dir, "Old Show Name")
            os.makedirs(os.path.join(old_root, "Season 01"), exist_ok=True)
            with open(os.path.join(old_root, "Season 01", "ep1.strm"), "w") as f:
                f.write("stream")

            new_root = rename_torrent_root_folder(old_root, "New Better Show Name")
            self.assertIsNotNone(new_root)
            self.assertTrue(os.path.exists(new_root))
            self.assertFalse(os.path.exists(old_root))
            self.assertTrue(os.path.exists(os.path.join(new_root, "Season 01", "ep1.strm")))

if __name__ == "__main__":
    unittest.main()
