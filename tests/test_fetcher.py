import pytest

from hetushu_scraper.fetcher import (
    clean_typography,
    decode_order_token,
    reorder_paragraphs,
    strip_paragraph_spam,
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


class TestStripParagraphSpam:
    def test_removes_var_junk(self):
        assert strip_paragraph_spam("我听说<var>https://m.hetushu.com.com</var>族比") == (
            "我听说族比"
        )

    def test_removes_dfn_junk(self):
        assert strip_paragraph_spam("前者……<dfn>hetｕshu.ｃｏｍ•coｍ</dfn>") == "前者……"

    def test_removes_tt_junk(self):
        assert strip_paragraph_spam("那仅<tt>m.hetushu.com.com</tt>仅只是") == "那仅仅只是"

    def test_removes_samp_junk(self):
        assert strip_paragraph_spam("呼~呼<samp>和*图*书</samp>~") == "呼~呼~"

    def test_removes_code_junk(self):
        assert strip_paragraph_spam("前面<code>www.hetushu.com.com</code>后面") == (
            "前面后面"
        )

    def test_removes_obscured_url_junk(self):
        assert strip_paragraph_spam("外<samp>ｈｅｔushu•ｃoｍ.com</samp>族") == "外族"

    def test_plain_text_passes_through(self):
        assert strip_paragraph_spam("普通文本") == "普通文本"

    def test_empty_fragment(self):
        assert strip_paragraph_spam("") == ""
