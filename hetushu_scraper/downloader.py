import asyncio
import os
import random

from ebooklib import epub
from cloakbrowser import launch_async
from tqdm import tqdm
from urllib.parse import urljoin

from .config import MAX_RETRIES, RETRY_DELAY_BASE, DEFAULT_CONCURRENCY, DEFAULT_REQUEST_DELAY, USER_AGENTS, CSS_STYLE
from .cache import get_cached_indices, build_epub_html_from_cache, clear_cache
from .fetcher import fetch_chapter


async def download_hetushu_book(book_id: str, *, headless=False, output=None, max_retries=None, timeout=None, concurrency=None, delay=None, verbose=False):
    max_retries = max_retries or MAX_RETRIES
    timeout = timeout or 30000
    concurrency = concurrency if concurrency is not None else DEFAULT_CONCURRENCY
    delay = delay if delay is not None else DEFAULT_REQUEST_DELAY
    sem = asyncio.Semaphore(concurrency)

    base_url = f"https://www.hetushu.com/book/{book_id}/index.html"
    ua = random.choice(USER_AGENTS)

    print(f"\n🚀 正在通过 CloakBrowser {'无头' if headless else ''}模式启动浏览器，抓取书籍 ID: {book_id}")
    print(f"📋 本次 User-Agent: {ua[:80]}...")

    browser = await launch_async(headless=headless, humanize=True)
    context = await browser.new_context(user_agent=ua)
    if verbose:
        context.on("request", lambda req: print(f"  ▶ REQ {req.method} {req.url}"))
        context.on("response", lambda res: print(f"  ◀ RES {res.status} {res.url}"))
        print(f"  🖥️ 浏览器已启动，headless={headless}")

    # ---- 首页加载（带重试）-----------------------------------------------
    last_error = None
    for attempt in range(max_retries):
        page = None
        page = await context.new_page()
        try:
            await page.goto(base_url, timeout=timeout)

            book_title = await page.evaluate(
                "() => document.querySelector('h2').innerText.trim()"
            )

            toc_data = await page.evaluate("""() => {
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
            }""")

            if verbose:
                vol_count = len(toc_data)
                ch_count = sum(len(v['chapters']) for v in toc_data)
                print(f"  📖 书名: {book_title}")
                print(f"  📑 目录: {vol_count} 卷, {ch_count} 章")
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = RETRY_DELAY_BASE * (attempt + 1)
                print(f"⚠️ 首页加载失败（第 {attempt+1} 次），{delay} 秒后重试... ({e})")
                await asyncio.sleep(delay)
            else:
                print(f"❌ 首页解析失败（已重试 {max_retries} 次）: {last_error}")
                debug_dir = f"debug_{book_id}"
                os.makedirs(debug_dir, exist_ok=True)
                try:
                    body_html = await page.evaluate("() => document.getElementById('dir')?.outerHTML || document.body.outerHTML")
                    with open(f"{debug_dir}/index_page.html", "w", encoding="utf-8") as f:
                        f.write(body_html)
                    print(f"📸 页面快照已保存到 {debug_dir}/index_page.html")
                except Exception:
                    pass
                await browser.close()
                return
        finally:
            if page:
                await page.close()

    # ---- 解析目录结构 ---------------------------------------------------
    toc_info = []
    title_map = {}
    global_idx = 1
    for vol_data in toc_data:
        chapters_info = []
        for ch in vol_data['chapters']:
            title_map[global_idx] = ch['title']
            chapters_info.append((ch['title'], global_idx))
            global_idx += 1
        toc_info.append({'volume': vol_data['volume'], 'chapters': chapters_info})
    total_chapters = global_idx - 1

    # ---- 检查断点缓存 ---------------------------------------------------
    cached_indices = get_cached_indices(book_id)
    cached_indices = {idx for idx in cached_indices if 1 <= idx <= total_chapters}
    if cached_indices:
        print(f"📌 检测到已有缓存: {len(cached_indices)}/{total_chapters} 章（将跳过网络请求）")
        if verbose:
            cached_list = sorted(cached_indices)
            print(f"  📂 已缓存章节: {cached_list[:10]}{'...' if len(cached_list) > 10 else ''}")

    # ---- 创建 EPUB 骨架 ------------------------------------------------
    book = epub.EpubBook()
    book.set_title(book_title)
    book.set_language('zh-CN')

    nav_css = epub.EpubItem(
        uid="style_nav", file_name="style/nav.css", media_type="text/css", content=CSS_STYLE
    )
    book.add_item(nav_css)

    # ---- 从缓存恢复已下载章节 + 创建下载任务 -------------------------------
    downloaded_chapters = {}

    for idx in sorted(cached_indices):
        c = build_epub_html_from_cache(book_id, idx, nav_css)
        if c:
            downloaded_chapters[idx] = c

    tasks = []
    global_idx = 1
    for vol_data in toc_data:
        for ch in vol_data['chapters']:
            if global_idx not in cached_indices:
                chap_url = urljoin(base_url, ch['href'])
                tasks.append(
                    fetch_chapter(context, book_id, global_idx, ch['title'], chap_url, nav_css,
                                  sem=sem, delay=delay, max_retries=max_retries, timeout=timeout, verbose=verbose)
                )
            global_idx += 1

    to_fetch = len(tasks)
    if to_fetch == 0:
        print(f"📦 全部章节 ({total_chapters} 章) 均已缓存，跳过网络抓取，直接生成 EPUB")
    else:
        cached_count = len(cached_indices)
        print(f"📦 共 {total_chapters} 章，需下载 {to_fetch} 章" +
              (f"（已缓存 {cached_count} 章）" if cached_count else "") +
              "，开始高并发抓取...")

    # ---- 网络下载（并发）------------------------------------------------
    failed_chapters = []
    if to_fetch > 0:
        with tqdm(total=to_fetch, desc="下载进度", unit="章") as pbar:
            for coro in asyncio.as_completed(tasks):
                t0 = asyncio.get_event_loop().time()
                idx, title, epub_obj, error = await coro
                elapsed = asyncio.get_event_loop().time() - t0
                if epub_obj:
                    downloaded_chapters[idx] = epub_obj
                    if verbose:
                        tqdm.write(f"  ✅ 第 {idx} 章「{title}」({elapsed:.1f}s)")
                else:
                    failed_chapters.append((idx, title, error))
                    tqdm.write(f"❌ 失败: {title} - {error}")
                pbar.update(1)

    if failed_chapters:
        print(f"\n⚠️ 共 {len(failed_chapters)} 章下载失败：")
        for idx, title, err in failed_chapters:
            print(f"  {idx:>4}. {title} — {err}")

    # ---- 组装 EPUB -----------------------------------------------------
    epub_toc = []
    spine = ['nav']

    for vol_index, item in enumerate(toc_info, start=1):
        vol_section = epub.Section(item['volume'])
        vol_items = []

        for title, idx in item['chapters']:
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
    book.add_item(epub.EpubNav())

    safe_title = "".join([c for c in book_title if c.isalnum() or c in (' ', '_', '-')]).strip()

    if output:
        if output.endswith('.epub'):
            epub_path = output
        else:
            os.makedirs(output, exist_ok=True)
            epub_path = os.path.join(output, f"{safe_title}.epub")
    else:
        epub_path = f"{safe_title}.epub"

    epub.write_epub(epub_path, book)

    clear_cache(book_id)
    print(f"\n🎉 电子书已生成: {epub_path}")

    await browser.close()
