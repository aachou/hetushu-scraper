from hetushu_scraper.fetcher import clean_typography


class TestCleanTypography:
    def test_converts_double_quotes(self):
        result = clean_typography('He said: "hello"')
        assert result == 'He said: \u201chello\u201c'

    def test_converts_single_quotes(self):
        result = clean_typography("It said: 'hello'")
        assert result == 'It said: \u2018hello\u2018'

    def test_fixes_leading_closing_quote(self):
        assert clean_typography('\u201d开头') == "\u201c开头"

    def test_normal_text_passes_through(self):
        assert clean_typography("普通文本") == "普通文本"

    def test_empty_string(self):
        assert clean_typography("") == ""

    def test_mixed_quotes(self):
        result = clean_typography('He asked: "How are you?" I said: \'I am fine\'')
        assert result == 'He asked: \u201cHow are you?\u201c I said: \u2018I am fine\u2018'

    def test_fixes_leading_right_single_quote(self):
        result = clean_typography('\u2018开头')
        assert result == '\u2018开头'

    def test_fixes_leading_right_double_quote(self):
        result = clean_typography('\u201d开头')
        assert result == '\u201c开头'

    def test_preserves_em_dash(self):
        result = clean_typography('word\u2014word')
        assert '\u2014' in result
