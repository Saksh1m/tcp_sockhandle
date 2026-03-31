from __future__ import annotations

from pathlib import Path
import unittest


class WebAssetTests(unittest.TestCase):
    def test_index_html_exists_and_has_core_controls(self) -> None:
        page = Path("app/static/index.html")
        self.assertTrue(page.exists())
        content = page.read_text(encoding="utf-8")
        self.assertIn("Location Sharing Web App", content)
        self.assertIn("Start Live GPS", content)
        self.assertIn("Subscribe", content)


if __name__ == "__main__":
    unittest.main()
