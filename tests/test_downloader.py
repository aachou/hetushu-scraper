import asyncio
import os

import pytest
from ebooklib import epub

from hetushu_scraper import downloader
from hetushu_scraper.cache import get_cached_indices
from hetushu_scraper.config import CSS_STYLE
from hetushu_scraper.downloader import (
    assemble_epub,
    build_toc,
    plan_fetch,
    download_hetushu_book,
    download_books,
)


TOC_DATA = [
    {
        "volume": "第一卷",
        "chapters": [
            {"title": "第一章", "href": "1.html"},
            {"title": "第二章", "href": "2.html"},
        ],
    },
    {
        "volume": "第二卷",
        "chapters": [{"title": "第三章", "href": "3.html"}],
    },
]


class TestBuildToc:
    def test_builds_structure_and_href_map(self):
        base = "https://www.hetushu.com/book/42/index.html"
        toc_info, href_map = build_toc(TOC_DATA, base)
        assert toc_info == [
            {"volume": "第一卷", "chapters": [("第一章", 1), ("第二章", 2)]},
            {"volume": "第二卷", "chapters": [("第三章", 3)]},
        ]
        assert href_map[1] == "https://www.hetushu.com/book/42/1.html"
        assert href_map[3] == "https://www.hetushu.com/book/42/3.html"

    def test_empty_toc(self):
        toc_info, href_map = build_toc([], "https://x/")
        assert toc_info == []
        assert href_map == {}


class TestPlanFetch:
    def test_fetches_missing_only(self):
        assert plan_fetch(3, {1, 3}, True) == {2}

    def test_use_cache_false_redownloads_everything(self):
        assert plan_fetch(3, {1, 2, 3}, False) == {1, 2, 3}

    def test_no_cache_needed(self):
        assert plan_fetch(3, set(), True) == {1, 2, 3}


class TestAssembleEpub:
    def _nav_css(self):
        return epub.EpubItem(
            uid="style_nav",
            file_name="style/nav.css",
            media_type="text/css",
            content=CSS_STYLE,
        )

    def _chapter(self, idx, title):
        c = epub.EpubHtml(title=title, file_name=f"chapter_{idx}.xhtml", lang="zh-CN")
        c.content = f"<h2>{title}</h2><p>内容</p>"
        c.add_item(self._nav_css())
        return c

    def _spine_files(self, book):
        return [
            item.file_name for item in book.spine if not isinstance(item, str)
        ]

    def test_assembles_toc_and_spine(self):
        toc_info, _ = build_toc(TOC_DATA, "https://x/")
        chapters = {
            1: self._chapter(1, "第一章"),
            2: self._chapter(2, "第二章"),
            3: self._chapter(3, "第三章"),
        }
        book = assemble_epub("测试书", toc_info, chapters, self._nav_css())
        assert book.title == "测试书"
        assert len(book.toc) == 2
        assert self._spine_files(book) == [
            "chapter_1.xhtml",
            "chapter_2.xhtml",
            "chapter_3.xhtml",
        ]

    def test_skips_missing_chapters(self):
        toc_info, _ = build_toc(TOC_DATA, "https://x/")
        chapters = {2: self._chapter(2, "第二章")}
        book = assemble_epub("测试书", toc_info, chapters, self._nav_css())
        assert self._spine_files(book) == ["chapter_2.xhtml"]
        assert len(book.toc) == 1

    def test_nav_suppresses_list_numbers_keeps_hierarchy(self, tmp_path):
        import zipfile

        from pathlib import Path

        assert "list-style-type: none" in CSS_STYLE
        assert "nav#id > ol" in CSS_STYLE

        toc_info, _ = build_toc(TOC_DATA, "https://x/")
        chapters = {
            1: self._chapter(1, "第一章"),
            2: self._chapter(2, "第二章"),
            3: self._chapter(3, "第三章"),
        }
        book = assemble_epub("测试书", toc_info, chapters, self._nav_css())
        epub_path = Path(tmp_path / "test_nav.epub")
        epub.write_epub(str(epub_path), book)

        with zipfile.ZipFile(str(epub_path)) as zf:
            names = zf.namelist()
            nav_name = next(n for n in names if n.endswith("nav.xhtml"))
            nav_data = zf.read(nav_name).decode("utf-8")
            css_name = next(n for n in names if n.endswith("style/nav.css"))
            css_data = zf.read(css_name).decode("utf-8")

        assert 'rel="stylesheet"' in nav_data
        assert "style/nav.css" in nav_data
        assert nav_data.count("<ol") >= 3
        assert nav_data.count("</ol>") == nav_data.count("<ol")
        assert "list-style-type: none" in css_data
        assert "nav#id > ol" in css_data


class FakePage:
    def __init__(self, browser, toc_data, paragraphs, token=""):
        self._browser = browser
        self._toc = toc_data
        self._paras = paragraphs
        self._token = token

    async def route(self, *args, **kwargs):
        pass

    async def goto(self, url, **kwargs):
        self._browser.goto_count += 1
        self._browser.goto_by_url[url] = self._browser.goto_by_url.get(url, 0) + 1
        self._browser.last_goto_url = url
        for frag, remaining in self._browser.fail_urls.items():
            if frag in url and remaining > 0:
                self._browser.fail_urls[frag] -= 1
                raise TimeoutError("simulated navigation failure")

    async def wait_for_selector(self, *args, **kwargs):
        pass

    async def wait_for_function(self, *args, **kwargs):
        pass

    async def evaluate(self, js, *args):
        if "getElementById('content')" in js:
            return self._paras
        if "querySelector('h2')" in js:
            import re

            m = re.search(r"/book/([^/]+)/", self._browser.last_goto_url or "")
            return f"书名{m.group(1) if m else '未知'}"
        if "querySelectorAll('dt, dd')" in js:
            return self._toc
        if "fetch('r" in js:
            return self._token
        return None

    async def close(self):
        pass


class FakeContext:
    def __init__(self, browser, toc_data, paragraphs, token=""):
        self._browser = browser
        self._toc = toc_data
        self._paras = paragraphs
        self._token = token

    async def new_page(self):
        return FakePage(self._browser, self._toc, self._paras, self._token)

    def on(self, *args, **kwargs):
        pass

    async def close(self):
        pass


class FakeBrowser:
    def __init__(self, toc_data, paragraphs, token="", fail_urls=None):
        self._toc = toc_data
        self._paras = paragraphs
        self._token = token
        self.fail_urls = fail_urls or {}
        self.goto_count = 0
        self.goto_by_url: dict[str, int] = {}
        self.last_goto_url: str | None = None

    async def new_context(self, **kwargs):
        return FakeContext(self, self._toc, self._paras, self._token)

    async def close(self):
        pass


def _make_launch(browser):
    async def _launch(**kwargs):
        return browser

    return _launch


def _epub_in(out_dir):
    return [
        f for f in os.listdir(out_dir)
        if f.endswith(".epub")
    ]


class FailingPage:
    def __init__(self, body_html):
        self._body = body_html

    async def route(self, *args, **kwargs):
        pass

    async def goto(self, *args, **kwargs):
        raise TimeoutError("nav timeout")

    async def evaluate(self, js):
        return self._body

    async def close(self):
        pass


class FailingContext:
    def __init__(self, browser):
        self._browser = browser

    def on(self, *args, **kwargs):
        pass

    async def new_page(self):
        page = FailingPage(self._browser.body_html)
        self._browser.pages.append(page)
        return page

    async def close(self):
        pass


class FailingBrowser:
    def __init__(self, body_html="<html><body>无法加载</body></html>"):
        self.body_html = body_html
        self.pages = []

    async def new_context(self, **kwargs):
        return FailingContext(self)

    async def close(self):
        pass


class TestDownloadPipeline:
    def test_full_download_writes_epub_and_cache(self, tmp_path, monkeypatch, patch_cache_dir):
        browser = FakeBrowser(TOC_DATA, ["第一段。", "第二段。"])
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        out = str(tmp_path / "out")
        asyncio.run(
            download_hetushu_book("42", output=out, concurrency=2, verbose=False)
        )
        assert _epub_in(out)
        assert get_cached_indices("42") == {1, 2, 3}
        assert browser.goto_count == 4

    def test_cache_reuse_skips_network(self, tmp_path, monkeypatch, patch_cache_dir):
        browser = FakeBrowser(TOC_DATA, ["第一段。", "第二段。"])
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        out = str(tmp_path / "out")
        asyncio.run(download_hetushu_book("42", output=out, concurrency=2))
        browser.goto_count = 0
        asyncio.run(download_hetushu_book("42", output=out, concurrency=2))
        assert browser.goto_count == 1

    def test_no_cache_redownloads_and_clears(self, tmp_path, monkeypatch, patch_cache_dir):
        browser = FakeBrowser(TOC_DATA, ["第一段。", "第二段。"])
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        out = str(tmp_path / "out")
        asyncio.run(download_hetushu_book("42", output=out, concurrency=2))
        assert get_cached_indices("42") == {1, 2, 3}
        browser.goto_count = 0
        asyncio.run(
            download_hetushu_book("42", output=out, concurrency=2, no_cache=True)
        )
        assert browser.goto_count == 4
        assert get_cached_indices("42") == set()

    def test_empty_toc_aborts(self, tmp_path, monkeypatch, patch_cache_dir):
        browser = FakeBrowser([], [])
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        out = str(tmp_path / "out")
        asyncio.run(download_hetushu_book("42", output=out, concurrency=2))
        assert not os.path.exists(out)

    def test_outer_retry_recovers_failed_chapter(self, tmp_path, monkeypatch, patch_cache_dir):
        browser = FakeBrowser(TOC_DATA, ["第一段。", "第二段。"], fail_urls={"2.html": 1})
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        out = str(tmp_path / "out")
        asyncio.run(
            download_hetushu_book("42", output=out, concurrency=2, max_retries=1)
        )
        assert get_cached_indices("42") == {1, 2, 3}
        assert browser.goto_by_url.get(
            "https://www.hetushu.com/book/42/2.html", 0
        ) == 2
        assert _epub_in(out)

    def test_all_failures_reported_no_cache(self, tmp_path, monkeypatch, patch_cache_dir):
        browser = FakeBrowser(
            TOC_DATA, ["第一段。"], fail_urls={"1.html": 99, "2.html": 99, "3.html": 99}
        )
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        out = str(tmp_path / "out")
        asyncio.run(
            download_hetushu_book("42", output=out, concurrency=2, max_retries=1)
        )
        assert get_cached_indices("42") == set()
        assert _epub_in(out)

    def test_index_failure_writes_debug_snapshot(self, tmp_path, monkeypatch):
        from hetushu_scraper.downloader import _load_index

        body = "<html><body><div id='dir'>加载失败现场</div></body></html>"
        browser = FailingBrowser(body)
        monkeypatch.chdir(tmp_path)
        toc_data, title = asyncio.run(
            _load_index(
                browser,
                "42",
                "https://x/book/42/index.html",
                max_retries=1,
                timeout=1000,
                verbose=False,
            )
        )
        assert toc_data is None
        assert title is None
        snapshot = tmp_path / "debug_42" / "index_page.html"
        assert snapshot.exists()
        assert "加载失败现场" in snapshot.read_text(encoding="utf-8")

    def test_download_books_serial(self, tmp_path, monkeypatch, patch_cache_dir):
        browser = FakeBrowser(TOC_DATA, ["第一段。", "第二段。"])
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        out = str(tmp_path / "out")
        asyncio.run(
            download_books(["42", "43"], output=out, concurrency=2, max_retries=1)
        )
        epubs = sorted(_epub_in(out))
        assert epubs == ["书名42.epub", "书名43.epub"]
        assert get_cached_indices("42") == {1, 2, 3}
        assert get_cached_indices("43") == {1, 2, 3}
        assert browser.goto_count == 8

    def test_download_books_rejects_epub_output(self, monkeypatch, patch_cache_dir):
        import pytest

        browser = FakeBrowser(TOC_DATA, ["第一段。"])
        monkeypatch.setattr(downloader, "launch_async", _make_launch(browser))
        with pytest.raises(ValueError):
            asyncio.run(
                download_books(["42", "43"], output="out.epub", concurrency=2)
            )
        assert browser.goto_count == 0
