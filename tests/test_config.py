from hetushu_scraper.config import CSS_STYLE, MAX_RETRIES, RETRY_DELAY_BASE, MAX_CONCURRENT_PAGES


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

    def test_max_concurrent_pages(self):
        assert MAX_CONCURRENT_PAGES == 8
