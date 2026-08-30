import asyncio
import os
import random
import time

from collections.abc import Sequence

from ebooklib import epub
from cloakbrowser import launch_async
from tqdm import tqdm
from urllib.parse import urljoin

from .config import (
    MAX_RETRIES,
    RETRY_DELAY_BASE,
    DEFAULT_CONCURRENCY,
    DEFAULT_REQUEST_DELAY,
    USER_AGENTS,
    CSS_STYLE,
)
from .cache import get_cached_indices, build_epub_html_from_cache, clear_cache
from .fetcher import fetch_chapter, intercept_route


_INDEX_TOC_JS = """() => {
    const dirDiv = document.getElementById('dir');
    let result = [];
    let currentVolume = "正文";
    let currentChapters = [];
    dirDiv.querySelectorAll('dt, dd').forEach(item => {
        if (item.tagName === 'DT') {
            if (currentChapters.length > 0)
                result.push({ volume: currentVolume, chapters: currentChapters });
            currentVolume = item.innerText.trim();
            currentChapters = [];
        } else {
            const a = item.querySelector('a');
            if (a) currentChapters.push({
                title: a.innerText.trim(),
                href: a.getAttribute('href')
            });
        }
    });
    if (currentChapters.length > 0)
        result.push({ volume: currentVolume, chapters: currentChapters });
    return result;
}"""


def build_toc(toc_data: list[dict], base_url: str) -> tuple[list[dict], dict[int, str]]:
    """Convert raw TOC data into (volume list, idx -> resolved chapter URL)."""
    toc_info = []
    href_map: dict[int, str] = {}
    global_idx = 1
    for vol_data in toc_data:
        chapters_info = []
        for ch in vol_data["chapters"]:
            href_map[global_idx] = urljoin(base_url, ch["href"])
            chapters_info.append((ch["title"], global_idx))
            global_idx += 1
        toc_info.append({"volume": vol_data["volume"], "chapters": chapters_info})
    return toc_info, href_map


def plan_fetch(total_chapters: int, cached_indices: set[int], use_cache: bool) -> set[int]:
    """Return the chapter indices that still need to be fetched."""
    all_indices = set(range(1, total_chapters + 1))
    if not use_cache:
        return all_indices
    return all_indices - cached_indices


def assemble_epub(
    book_title: str,
    toc_info: list[dict],
    downloaded_chapters: dict[int, epub.EpubHtml],
    nav_css: epub.EpubItem,
) -> epub.EpubBook:
    book = epub.EpubBook()
    book.set_title(book_title)
    book.set_language("zh-CN")
    book.add_item(nav_css)
    epub_toc = []
    spine = ["nav"]
    for vol_index, item in enumerate(toc_info, start=1):
        vol_section = epub.Section(item["volume"])
        vol_items = []
        for _title, idx in item["chapters"]:
            c = downloaded_chapters.get(idx)
            if c:
                book.add_item(c)
                spine.append(c)
                vol_items.append(c)
        if vol_items:
            vol_section.href = f"{vol_items[0].file_name}#v{vol_index}"
            epub_toc.append((vol_section, vol_items))
    book.toc = epub_toc
    book.spine = spine
    book.add_item(epub.EpubNcx())
    nav = epub.EpubNav()
    nav.add_link(href=nav_css.file_name, rel="stylesheet", type="text/css")
    book.add_item(nav)
    return book


def _attach_verbose_logging(ctx, verbose: bool) -> None:
    if verbose:
        ctx.on("request", lambda req: print(f"  ▶ REQ {req.method} {req.url}"))
        ctx.on("response", lambda res: print(f"  ◀ RES {res.status} {res.url}"))


async def _load_index(browser, book_id: str, base_url: str, *, max_retries, timeout, verbose):
    last_error = None
    for attempt in range(max_retries):
        ctx = None
        page = None
        try:
            ctx = await browser.new_context(user_agent=random.choice(USER_AGENTS))
            _attach_verbose_logging(ctx, verbose)
            page = await ctx.new_page()
            await page.route("**/*", intercept_route)
            await page.goto(base_url, timeout=timeout)
            book_title = await page.evaluate(
                "() => document.querySelector('h2').innerText.trim()"
            )
            toc_data = await page.evaluate(_INDEX_TOC_JS)
            if verbose:
                vol_count = len(toc_data)
                ch_count = sum(len(v["chapters"]) for v in toc_data)
                print(f"  📖 书名: {book_title}")
                print(f"  📑 目录: {vol_count} 卷, {ch_count} 章")
            return toc_data, book_title
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                retry_delay = RETRY_DELAY_BASE * (attempt + 1)
                print(
                    f"⚠️ 首页加载失败（第 {attempt + 1} 次），{retry_delay} 秒后重试... ({e})"
                )
                await asyncio.sleep(retry_delay)
            else:
                print(f"❌ 首页解析失败（已重试 {max_retries} 次）: {last_error}")
                debug_dir = f"debug_{book_id}"
                os.makedirs(debug_dir, exist_ok=True)
                try:
                    body_html = await page.evaluate(
                        "() => document.getElementById('dir')?.outerHTML || document.body.outerHTML"
                    )
                    with open(
                        f"{debug_dir}/index_page.html", "w", encoding="utf-8"
                    ) as f:
                        f.write(body_html)
                    print(f"📸 页面快照已保存到 {debug_dir}/index_page.html")
                except Exception:
                    pass
        finally:
            if page:
                await page.close()
            if ctx:
                await ctx.close()
    return None, None


async def _download_all(
    browser,
    work_items,
    book_id: str,
    nav_css,
    *,
    num_pages: int,
    delay: float,
    max_retries: int,
    timeout: int,
    use_cache: bool,
    verbose: bool,
    desc: str = "下载进度",
) -> tuple[dict[int, epub.EpubHtml], list[tuple[int, str, str]]]:
    if not work_items:
        return {}, []
    num_pages = max(1, min(num_pages, len(work_items)))

    contexts = []
    pages = []
    for _ in range(num_pages):
        ctx = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        _attach_verbose_logging(ctx, verbose)
        contexts.append(ctx)
        page = await ctx.new_page()
        await page.route("**/*", intercept_route)
        pages.append(page)

    queue = asyncio.Queue()
    for item in work_items:
        queue.put_nowait(item)
    for _ in pages:
        queue.put_nowait(None)

    results: dict[int, tuple] = {}
    pbar = tqdm(total=len(work_items), desc=desc, unit="章")

    async def worker(page):
        while True:
            item = await queue.get()
            if item is None:
                return
            idx, title, url = item
            t0 = time.perf_counter()
            try:
                res = await fetch_chapter(
                    page,
                    book_id,
                    idx,
                    title,
                    url,
                    nav_css,
                    delay=delay,
                    max_retries=max_retries,
                    timeout=timeout,
                    verbose=verbose,
                    use_cache=use_cache,
                )
            except Exception as e:
                res = (idx, title, None, str(e))
            results[idx] = res
            if verbose and res[2] is not None:
                elapsed = time.perf_counter() - t0
                tqdm.write(f"  ✅ 第 {idx} 章「{title}」({elapsed:.1f}s)")
            pbar.update(1)

    workers = [asyncio.create_task(worker(page)) for page in pages]
    try:
        await asyncio.gather(*workers)
    finally:
        for ctx in contexts:
            await ctx.close()
        pbar.close()

    ordered = [results[item[0]] for item in work_items]
    downloaded = {idx: c for idx, _title, c, _err in ordered if c is not None}
    failed = [(idx, title, err) for idx, title, c, err in ordered if c is None]
    return downloaded, failed


async def _run_pipeline(
    browser,
    book_id: str,
    output: str | None,
    base_url: str,
    *,
    max_retries: int,
    timeout: int,
    concurrency: int,
    delay: float,
    use_cache: bool,
    verbose: bool,
) -> None:
    toc_data, book_title = await _load_index(
        browser,
        book_id,
        base_url,
        max_retries=max_retries,
        timeout=timeout,
        verbose=verbose,
    )
    if toc_data is None:
        return

    toc_info, href_map = build_toc(toc_data, base_url)
    total_chapters = sum(len(v["chapters"]) for v in toc_info)
    if total_chapters == 0:
        print("❌ 目录为空，未解析到任何章节")
        return

    cached_indices = get_cached_indices(book_id) if use_cache else set()
    cached_indices = {idx for idx in cached_indices if 1 <= idx <= total_chapters}
    to_fetch = plan_fetch(total_chapters, cached_indices, use_cache)

    if cached_indices:
        print(
            f"📌 检测到已有缓存: {len(cached_indices)}/{total_chapters} 章（将跳过网络请求）"
        )
        if verbose:
            cached_list = sorted(cached_indices)
            print(
                f"  📂 已缓存章节: {cached_list[:10]}{'...' if len(cached_list) > 10 else ''}"
            )

    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=CSS_STYLE,
    )

    downloaded_chapters: dict[int, epub.EpubHtml] = {}
    if use_cache:
        for idx in sorted(cached_indices):
            c = build_epub_html_from_cache(book_id, idx, nav_css)
            if c:
                downloaded_chapters[idx] = c

    fetch_items = []
    for vol in toc_info:
        for title, idx in vol["chapters"]:
            if idx in to_fetch:
                fetch_items.append((idx, title, href_map[idx]))

    failed: list[tuple[int, str, str]] = []
    if not fetch_items:
        print(
            f"📦 全部章节 ({total_chapters} 章) 均已缓存，跳过网络抓取，直接生成 EPUB"
        )
    else:
        num_pages = max(1, min(concurrency, len(fetch_items)))
        print(
            f"📦 共 {total_chapters} 章，需下载 {len(fetch_items)} 章"
            + (f"（已缓存 {len(cached_indices)} 章）" if cached_indices else "")
            + f"，使用 {num_pages} 个页面并发抓取..."
        )
        downloaded, failed = await _download_all(
            browser,
            fetch_items,
            book_id,
            nav_css,
            num_pages=num_pages,
            delay=delay,
            max_retries=max_retries,
            timeout=timeout,
            use_cache=use_cache,
            verbose=verbose,
        )
        downloaded_chapters.update(downloaded)

        if failed:
            print(f"\n⚠️ 首次下载 {len(failed)} 章失败，正在重试...")
            retry_items = [(idx, title, href_map[idx]) for idx, title, _ in failed]
            retry_pages = max(1, min(num_pages, len(retry_items)))
            downloaded, failed = await _download_all(
                browser,
                retry_items,
                book_id,
                nav_css,
                num_pages=retry_pages,
                delay=delay,
                max_retries=1,
                timeout=timeout,
                use_cache=use_cache,
                verbose=verbose,
                desc="重试",
            )
            downloaded_chapters.update(downloaded)

    if failed:
        print(f"\n⚠️ 共 {len(failed)} 章下载失败（已重试）：")
        for idx, title, err in failed:
            print(f"  {idx:>4}. {title} — {err}")

    book = assemble_epub(book_title, toc_info, downloaded_chapters, nav_css)

    safe_title = "".join(
        [c for c in book_title if c.isalnum() or c in (" ", "_", "-")]
    ).strip()

    if output:
        if output.endswith(".epub"):
            epub_path = output
        else:
            os.makedirs(output, exist_ok=True)
            epub_path = os.path.join(output, f"{safe_title}.epub")
    else:
        epub_path = f"{safe_title}.epub"

    epub.write_epub(epub_path, book)

    if not use_cache:
        clear_cache(book_id)
    print(f"\n🎉 电子书已生成: {epub_path}")


async def download_hetushu_book(
    book_id: str,
    *,
    headless: bool = True,
    output: str | None = None,
    max_retries: int | None = None,
    timeout: int | None = None,
    concurrency: int | None = None,
    delay: float | None = None,
    no_cache: bool = False,
    verbose: bool = False,
) -> None:
    await download_books(
        [book_id],
        headless=headless,
        output=output,
        max_retries=max_retries,
        timeout=timeout,
        concurrency=concurrency,
        delay=delay,
        no_cache=no_cache,
        verbose=verbose,
    )


async def download_books(
    book_ids: Sequence[str],
    *,
    headless: bool = True,
    output: str | None = None,
    max_retries: int | None = None,
    timeout: int | None = None,
    concurrency: int | None = None,
    delay: float | None = None,
    no_cache: bool = False,
    verbose: bool = False,
) -> None:
    if len(book_ids) > 1 and output and output.endswith(".epub"):
        raise ValueError("多本书下载时 --output 必须是目录，不能是 .epub 文件路径")

    max_retries = MAX_RETRIES if max_retries is None else max_retries
    timeout = 30000 if timeout is None else timeout
    concurrency = DEFAULT_CONCURRENCY if concurrency is None else concurrency
    delay = DEFAULT_REQUEST_DELAY if delay is None else delay
    use_cache = not no_cache

    print(
        f"\n🚀 正在通过 CloakBrowser {'无头' if headless else ''}模式启动浏览器，"
        f"共 {len(book_ids)} 本书，串行下载..."
    )
    if verbose:
        print(f"  🖥️ 浏览器已启动，headless={headless}")

    browser = await launch_async(headless=headless, humanize=True)
    try:
        for i, book_id in enumerate(book_ids, start=1):
            print(f"\n📚 第 {i}/{len(book_ids)} 本 — 书籍 ID: {book_id}")
            base_url = f"https://www.hetushu.com/book/{book_id}/index.html"
            await _run_pipeline(
                browser,
                book_id,
                output,
                base_url,
                max_retries=max_retries,
                timeout=timeout,
                concurrency=concurrency,
                delay=delay,
                use_cache=use_cache,
                verbose=verbose,
            )
    finally:
        await browser.close()
