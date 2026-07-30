import zipfile
from pathlib import Path

from ebooklib import epub
from lxml import etree

from hetushu_scraper.config import CSS_STYLE


def _nav_css():
    return epub.EpubItem(
        uid="style_nav", file_name="style/nav.css", media_type="text/css", content=CSS_STYLE
    )


class TestEpubToc:
    def test_section_href_uses_fragment_identifier(self):
        vol = epub.Section("第一卷")
        vol.href = "chapter_1.xhtml#v1"
        assert vol.href == "chapter_1.xhtml#v1"

    def _find_ncx_path(self, zf: zipfile.ZipFile) -> str | None:
        for name in zf.namelist():
            if name.endswith("toc.ncx"):
                return name
        return None

    def _build_book(self, toc, *, set_section_href=True):
        book = epub.EpubBook()
        book.set_title("Test Book")
        book.set_language("zh-CN")
        nav_css = _nav_css()
        book.add_item(nav_css)
        spine = ["nav"]
        epub_toc = []
        for vol_index, (vol_section, vol_chapters) in enumerate(toc, start=1):
            for c in vol_chapters:
                c.add_item(nav_css)
                book.add_item(c)
                spine.append(c)
            if set_section_href and vol_chapters:
                vol_section.href = f"{vol_chapters[0].file_name}#v{vol_index}"
            epub_toc.append((vol_section, vol_chapters))
        book.toc = epub_toc
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        return book

    def test_ncx_no_duplicate_src(self, tmp_path):
        ch1 = epub.EpubHtml(title="第一章", file_name="chapter_1.xhtml", lang="zh-CN")
        ch1.content = "<h2>第一章</h2><p>内容</p>"
        ch2 = epub.EpubHtml(title="第二章", file_name="chapter_2.xhtml", lang="zh-CN")
        ch2.content = "<h2>第二章</h2><p>内容</p>"
        vol = epub.Section("第一卷")
        book = self._build_book([(vol, [ch1, ch2])])
        epub_path = Path(tmp_path / "test.epub")
        epub.write_epub(str(epub_path), book)
        self._check_ncx_no_duplicate_src(str(epub_path))

    def test_ncx_multiple_volumes_no_duplicates(self, tmp_path):
        ch1 = epub.EpubHtml(title="第一章", file_name="chapter_1.xhtml", lang="zh-CN")
        ch1.content = "<h2>第一章</h2><p>内容</p>"
        ch2 = epub.EpubHtml(title="第二章", file_name="chapter_2.xhtml", lang="zh-CN")
        ch2.content = "<h2>第二章</h2><p>内容</p>"
        ch3 = epub.EpubHtml(title="第三章", file_name="chapter_3.xhtml", lang="zh-CN")
        ch3.content = "<h2>第三章</h2><p>内容</p>"
        vol1 = epub.Section("第一卷")
        vol2 = epub.Section("第二卷")
        book = self._build_book([(vol1, [ch1, ch2]), (vol2, [ch3])])
        epub_path = Path(tmp_path / "test2.epub")
        epub.write_epub(str(epub_path), book)
        self._check_ncx_no_duplicate_src(str(epub_path))

    def _check_ncx_no_duplicate_src(self, epub_path: str):
        with zipfile.ZipFile(epub_path) as zf:
            ncx_path = self._find_ncx_path(zf)
            assert ncx_path is not None, "toc.ncx not found in EPUB"
            ncx_data = zf.read(ncx_path)
        root = etree.fromstring(ncx_data)
        ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
        srcs = [el.get("src") for el in root.findall(".//ncx:content", ns)]
        assert len(srcs) == len(set(srcs)), (
            f"Duplicate src values found in NCX: {[s for s in srcs if srcs.count(s) > 1]}"
        )

    def test_ncx_section_href_has_fragment(self, tmp_path):
        ch1 = epub.EpubHtml(title="第一章", file_name="chapter_1.xhtml", lang="zh-CN")
        ch1.content = "<h2>第一章</h2><p>内容</p>"
        vol = epub.Section("第一卷")
        book = self._build_book([(vol, [ch1])])
        epub_path = Path(tmp_path / "test5.epub")
        epub.write_epub(str(epub_path), book)

        with zipfile.ZipFile(str(epub_path)) as zf:
            ncx_path = self._find_ncx_path(zf)
            assert ncx_path is not None
            ncx_data = zf.read(ncx_path)

        root = etree.fromstring(ncx_data)
        ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
        ncx_srcs = {el.get("src") for el in root.findall(".//ncx:content", ns)}
        assert "chapter_1.xhtml#v1" in ncx_srcs

    def test_first_chapter_ncx_has_single_entry(self, tmp_path):
        ch1 = epub.EpubHtml(title="第一章", file_name="chapter_1.xhtml", lang="zh-CN")
        ch1.content = "<h2>第一章</h2><p>内容</p>"
        ch2 = epub.EpubHtml(title="第二章", file_name="chapter_2.xhtml", lang="zh-CN")
        ch2.content = "<h2>第二章</h2><p>内容</p>"
        vol = epub.Section("第一卷")
        book = self._build_book([(vol, [ch1, ch2])])
        epub_path = Path(tmp_path / "test4.epub")
        epub.write_epub(str(epub_path), book)

        with zipfile.ZipFile(str(epub_path)) as zf:
            ncx_path = self._find_ncx_path(zf)
            assert ncx_path is not None
            ncx_data = zf.read(ncx_path)

        root = etree.fromstring(ncx_data)
        ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
        srcs = [el.get("src") for el in root.findall(".//ncx:content", ns)]
        ch1_refs = [s for s in srcs if s == "chapter_1.xhtml"]
        assert len(ch1_refs) == 1, (
            f"Expected exactly 1 NCX entry for chapter_1.xhtml, got {len(ch1_refs)}: {ch1_refs}"
        )

    def test_duplicate_when_href_missing(self, tmp_path):
        """Without fragment identifier, NCX should still have duplicates
        (ebooklib auto-fills Section src with first child's file_name)."""
        ch1 = epub.EpubHtml(title="第一章", file_name="chapter_1.xhtml", lang="zh-CN")
        ch1.content = "<h2>第一章</h2><p>内容</p>"
        ch2 = epub.EpubHtml(title="第二章", file_name="chapter_2.xhtml", lang="zh-CN")
        ch2.content = "<h2>第二章</h2><p>内容</p>"
        vol = epub.Section("第一卷")
        book = self._build_book([(vol, [ch1, ch2])], set_section_href=False)
        epub_path = Path(tmp_path / "test6.epub")
        epub.write_epub(str(epub_path), book)

        with zipfile.ZipFile(str(epub_path)) as zf:
            ncx_path = self._find_ncx_path(zf)
            assert ncx_path is not None
            ncx_data = zf.read(ncx_path)

        root = etree.fromstring(ncx_data)
        ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
        srcs = [el.get("src") for el in root.findall(".//ncx:content", ns)]
        ch1_refs = [s for s in srcs if s == "chapter_1.xhtml"]
        assert len(ch1_refs) == 2, (
            f"Expected 2 NCX entries for chapter_1.xhtml (auto-fill bug), got {len(ch1_refs)}"
        )

    def test_ncx_all_src_point_to_existing_files(self, tmp_path):
        ch1 = epub.EpubHtml(title="第一章", file_name="chapter_1.xhtml", lang="zh-CN")
        ch1.content = "<h2>第一章</h2><p>内容</p>"
        ch2 = epub.EpubHtml(title="第二章", file_name="chapter_2.xhtml", lang="zh-CN")
        ch2.content = "<h2>第二章</h2><p>内容</p>"
        vol = epub.Section("第一卷")
        book = self._build_book([(vol, [ch1, ch2])])
        epub_path = Path(tmp_path / "test3.epub")
        epub.write_epub(str(epub_path), book)

        with zipfile.ZipFile(str(epub_path)) as zf:
            ncx_path = self._find_ncx_path(zf)
            assert ncx_path is not None
            ncx_data = zf.read(ncx_path)
            file_list = set(zf.namelist())
            prefix = str(Path(ncx_path).parent) + "/"

        root = etree.fromstring(ncx_data)
        ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
        for el in root.findall(".//ncx:content", ns):
            src = el.get("src")
            if src and "#" not in src:
                assert prefix + src in file_list, (
                    f"NCX references {prefix}{src} which does not exist in the EPUB"
                )
