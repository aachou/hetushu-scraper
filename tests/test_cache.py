import json
import os

import pytest
from ebooklib import epub

from hetushu_scraper.cache import (
    save_chapter_cache,
    get_cached_indices,
    build_epub_html_from_cache,
    clear_cache,
)
from hetushu_scraper.config import CSS_STYLE


def _make_nav_css():
    return epub.EpubItem(
        uid="style_nav", file_name="style/nav.css", media_type="text/css", content=CSS_STYLE
    )


class TestCache:
    def test_save_and_get_indices(self, patch_cache_dir):
        save_chapter_cache("test_book", 1, "第一章", "<p>内容</p>")
        save_chapter_cache("test_book", 2, "第二章", "<p>内容2</p>")
        indices = get_cached_indices("test_book")
        assert indices == {1, 2}

    def test_get_indices_empty_book(self, patch_cache_dir):
        assert get_cached_indices("test_book") == set()

    def test_get_indices_non_existent_dir(self):
        assert get_cached_indices("__no_such_book_xyz__") == set()

    def test_build_epub_html(self, patch_cache_dir):
        save_chapter_cache("test_book", 1, "第一章", "<p>内容</p>")
        nav_css = _make_nav_css()
        c = build_epub_html_from_cache("test_book", 1, nav_css)
        assert c is not None
        assert c.title == "第一章"
        assert c.file_name == "chapter_1.xhtml"
        assert "<p>内容</p>" in c.content

    def test_build_epub_html_missing(self, patch_cache_dir):
        nav_css = _make_nav_css()
        assert build_epub_html_from_cache("test_book", 999, nav_css) is None

    def test_clear_cache(self, patch_cache_dir):
        save_chapter_cache("test_book", 1, "第一章", "<p>内容</p>")
        clear_cache("test_book")
        assert get_cached_indices("test_book") == set()

    def test_clear_cache_nonexistent(self):
        clear_cache("__no_such_book__")

    def test_build_corrupted_cache_removes_file(self, patch_cache_dir):
        from hetushu_scraper import config as cfg
        book_id = "test_book"
        obj_path = os.path.join(cfg.CACHE_DIR, book_id, "1.json")
        os.makedirs(os.path.dirname(obj_path), exist_ok=True)
        with open(obj_path, "w", encoding="utf-8") as f:
            f.write("{corrupt json")
        nav_css = _make_nav_css()
        assert build_epub_html_from_cache(book_id, 1, nav_css) is None
        assert not os.path.exists(obj_path)
