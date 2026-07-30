import inspect

from hetushu_scraper.config import (
    CSS_STYLE,
    MAX_RETRIES,
    RETRY_DELAY_BASE,
    DEFAULT_CONCURRENCY,
    DEFAULT_REQUEST_DELAY,
)
from hetushu_scraper.fetcher import fetch_chapter
from hetushu_scraper.downloader import download_hetushu_book
from hetushu_scraper.cli import run_cli


class TestConfig:
    def test_css_contains_paragraph_style(self):
        assert "text-indent" in CSS_STYLE

    def test_css_contains_image_style(self):
        assert "img" in CSS_STYLE
        assert "max-width: 100%" in CSS_STYLE
        assert "height: auto" in CSS_STYLE

    def test_css_contains_code_style(self):
        assert "pre" in CSS_STYLE
        assert "code" in CSS_STYLE

    def test_retries_default(self):
        assert MAX_RETRIES == 3

    def test_retry_delay_base(self):
        assert RETRY_DELAY_BASE == 2

    def test_default_concurrency_value(self):
        assert DEFAULT_CONCURRENCY == 8

    def test_default_concurrency_type(self):
        assert isinstance(DEFAULT_CONCURRENCY, int)
        assert DEFAULT_CONCURRENCY > 0

    def test_default_request_delay_value(self):
        assert DEFAULT_REQUEST_DELAY == 0.0

    def test_default_request_delay_type(self):
        assert isinstance(DEFAULT_REQUEST_DELAY, (int, float))
        assert DEFAULT_REQUEST_DELAY >= 0

    def test_fetch_chapter_accepts_sem(self):
        sig = inspect.signature(fetch_chapter)
        assert "sem" in sig.parameters

    def test_fetch_chapter_accepts_delay(self):
        sig = inspect.signature(fetch_chapter)
        param = sig.parameters["delay"]
        assert param.default == 0

    def test_download_book_accepts_concurrency(self):
        sig = inspect.signature(download_hetushu_book)
        assert "concurrency" in sig.parameters

    def test_download_book_accepts_delay(self):
        sig = inspect.signature(download_hetushu_book)
        assert "delay" in sig.parameters

    def test_download_book_accepts_no_cache(self):
        sig = inspect.signature(download_hetushu_book)
        assert "no_cache" in sig.parameters

    def test_no_cache_defaults_to_false(self):
        sig = inspect.signature(download_hetushu_book)
        param = sig.parameters["no_cache"]
        assert param.default is False
