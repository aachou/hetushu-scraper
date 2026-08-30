import pytest

from hetushu_scraper.config import SPAM_TAGS
from hetushu_scraper.fetcher import (
    _build_extract_js,
    clean_typography,
    decode_order_token,
    reorder_paragraphs,
)


class TestCleanTypography:
    def test_converts_double_quotes(self):
        result = clean_typography('He said: "hello"')
        assert result == "He said: \u201chello\u201c"

    def test_converts_single_quotes(self):
        result = clean_typography("It said: 'hello'")
        assert result == "It said: \u2018hello\u2018"

    def test_fixes_leading_closing_quote(self):
        assert clean_typography("\u201d开头") == "\u201c开头"

    def test_normal_text_passes_through(self):
        assert clean_typography("普通文本") == "普通文本"

    def test_empty_string(self):
        assert clean_typography("") == ""

    def test_mixed_quotes(self):
        result = clean_typography("He asked: \"How are you?\" I said: 'I am fine'")
        assert (
            result == "He asked: \u201cHow are you?\u201c I said: \u2018I am fine\u2018"
        )

    def test_fixes_leading_right_single_quote(self):
        result = clean_typography("\u2018开头")
        assert result == "\u2018开头"

    def test_fixes_leading_right_double_quote(self):
        result = clean_typography("\u201d开头")
        assert result == "\u201c开头"

    def test_preserves_em_dash(self):
        result = clean_typography("word\u2014word")
        assert "\u2014" in result


TOKEN = "MzhXJTFFJTU2TCU1M0QlNDNOJTYxSiU2MlglMzZZJTIxQiU3MUglOUklNDBBJTU5SCUzM0slMzdOJTUxVSU2M1AlMzhRJTIzWSU0MlUlNDVQJTE3SyUyNVElNDlQJTBCJTEyVyU5TSU2NU4lNTlBJTMwSCU0OUolMjlUJThLJTY4TiUyM0YlNjlNJTcxVSUzRSU0OVYlMkklMzBBJTE3WSUxOEklMjlYJTI3UyUzM0klMTNTJTc2ViU3MlUlNThEJTM3UiU0QyU2MVklNzBCJTE2WiU3NkclNDVBJTI0QyUzNlIlNTRJJTUwTyU1OEglMjBPJTQ4SyUxN1clMzlMJTIyTCUyM1UlMzVPJTY5RiU3OEclMTBQJTY0VCU1Ng=="

from tests.scrambled_fixture import SCRAMBLED  # noqa: E402
from tests.scrambled_ch2_fixture import SCRAMBLED_CH2  # noqa: E402

TOKEN_CH2 = "NDNUJTIyVCU0NlIlNDhLJTEyQSUzN00lNFQlMjBHJTE1WCU4WCUzMkMlMThLJTUyWSUzN1ElMjFZJTI1RyU1N1olNTZEJTIyTSUxMlQlNDJUJTI0WSU0MUMlMUklNDBWJTJTJTM1SiU1Nk8lNDVJJTM2WCUxMUMlMTlVJTYwRiUzM1olNTdUJTEyQyUyOEQlMzdSJTNMJTQ5QyU0OFYlMzNCJTE3SyU0M00lMzJEJTUzSiU5SiU1MVMlMTBNJTBZJTU3QiUyM0QlNTVFJTMxSiUzMlQlMTVIJTQwTSUyMA=="


class TestDecodeOrderToken:
    def test_decodes_to_74_entries(self):
        indices = decode_order_token(TOKEN)
        assert len(indices) == 74

    def test_decodes_to_integers(self):
        indices = decode_order_token(TOKEN)
        assert all(isinstance(i, int) for i in indices)


class TestReorderParagraphs:
    def test_reorders_to_narrative_order(self):
        ordered = reorder_paragraphs(SCRAMBLED, TOKEN)
        assert len(ordered) == 74
        assert set(ordered) == set(SCRAMBLED)
        assert ordered[0] == "\u201c唔。\u201d"
        assert "当林动费尽所有的力气" in ordered[1]

    def test_reorders_fake_data_losslessly(self):
        paragraphs = [f"scrambled-{i}" for i in range(74)]
        ordered = reorder_paragraphs(paragraphs, TOKEN)
        assert len(ordered) == 74
        assert set(ordered) == set(paragraphs)

    def test_reorders_chapter2_and_strips_spam(self):
        ordered = reorder_paragraphs(SCRAMBLED_CH2, TOKEN_CH2)
        assert len(ordered) == 58
        assert set(ordered) == set(SCRAMBLED_CH2)
        assert ordered[0] == "清晨，大雾笼罩着这座僻静的山峰，白蒙蒙的，让人的视线，都是变得模糊了起来。"
        all_text = "".join(ordered)
        assert "hetushu.com.com" not in all_text
        assert "和*图*书" not in all_text
        assert "和图" not in all_text.replace("和图书", "")

    def test_mismatched_count_raises(self):
        with pytest.raises(ValueError):
            reorder_paragraphs(["a", "b", "c"], TOKEN)


class TestExtractJs:
    def test_embeds_all_spam_tags(self):
        js = _build_extract_js()
        for tag in SPAM_TAGS:
            assert tag in js
        assert "querySelectorAll" in js
        assert "textContent" in js
        assert "mask" in js

    def test_returns_empty_when_no_content(self):
        js = _build_extract_js()
        assert "if (!content) return [];" in js


class _FakePage:
    def __init__(self, paragraphs, token="", fail_gotos=0):
        self._paras = paragraphs
        self._token = token
        self._fail = fail_gotos
        self.goto_calls = 0

    async def goto(self, *args, **kwargs):
        self.goto_calls += 1
        if self.goto_calls <= self._fail:
            raise TimeoutError("simulated navigation failure")

    async def wait_for_selector(self, *args, **kwargs):
        pass

    async def wait_for_function(self, *args, **kwargs):
        pass

    async def evaluate(self, js, *args):
        if "getElementById('content')" in js:
            return self._paras
        if "fetch('r" in js:
            return self._token
        return None


def _nav_css():
    from ebooklib import epub

    from hetushu_scraper.config import CSS_STYLE

    return epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=CSS_STYLE,
    )


class TestFetchChapter:
    def _run(self, page, *args, **kwargs):
        import asyncio

        from hetushu_scraper.fetcher import fetch_chapter

        return asyncio.run(
            fetch_chapter(
                page,
                "42",
                1,
                "第一章",
                "https://www.hetushu.com/book/42/1.html",
                _nav_css(),
                *args,
                **kwargs,
            )
        )

    def test_retries_then_succeeds(self, monkeypatch, patch_cache_dir):
        import asyncio

        from hetushu_scraper import fetcher

        async def _no_sleep(_):
            pass

        monkeypatch.setattr(fetcher.asyncio, "sleep", _no_sleep)
        page = _FakePage(["第一段", "第二段"], fail_gotos=1)
        idx, title, c, err = self._run(page, max_retries=2)
        assert err is None
        assert c is not None
        assert page.goto_calls == 2
        assert "<p>第一段</p>" in c.content

    def test_gives_up_after_max_retries(self, monkeypatch, patch_cache_dir):
        import asyncio

        from hetushu_scraper import fetcher

        async def _no_sleep(_):
            pass

        monkeypatch.setattr(fetcher.asyncio, "sleep", _no_sleep)
        page = _FakePage(["第一段"], fail_gotos=3)
        idx, title, c, err = self._run(page, max_retries=2)
        assert c is None
        assert err is not None
        assert page.goto_calls == 2

    def test_keeps_scrambled_order_on_reorder_failure(self, patch_cache_dir):
        page = _FakePage(["第二段", "第一段"], token="SGVsbG8=")
        idx, title, c, err = self._run(page, max_retries=1)
        assert err is None
        assert c is not None
        assert "<p>第二段</p>" in c.content
        assert "<p>第一段</p>" in c.content

    def test_saves_cache_by_default(self, patch_cache_dir):
        from hetushu_scraper.cache import get_cached_indices

        page = _FakePage(["第一段"])
        self._run(page, max_retries=1)
        assert get_cached_indices("42") == {1}

    def test_no_cache_skips_save(self, patch_cache_dir):
        from hetushu_scraper.cache import get_cached_indices

        page = _FakePage(["第一段"])
        self._run(page, max_retries=1, use_cache=False)
        assert get_cached_indices("42") == set()
