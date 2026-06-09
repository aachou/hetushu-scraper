import asyncio
import io
import json
import os
import random
import shutil
import sys
from tqdm import tqdm
from cloakbrowser import launch_async
from ebooklib import epub
from urllib.parse import urljoin

# ---- Windows UTF-8 编码加固 ------------------------------------------------
# 强制 stdout/stderr 使用 UTF-8，避免 GBK 终端输出 emoji 时崩溃
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# --- 配置项 ---
MAX_CONCURRENT_PAGES = 8
sem = asyncio.Semaphore(MAX_CONCURRENT_PAGES)
MAX_RETRIES = 3                     # 全局重试次数
RETRY_DELAY_BASE = 2                # 重试基础等待秒数（指数递增: 2, 4, 6...）
CACHE_DIR = ".chapter_cache"        # 断点续传缓存目录（删除即可强制全量重下）

# --- CSS 样式 ---
CSS_STYLE = """
    p { text-indent: 2em; margin-bottom: 0.5em; line-height: 1.6; }
"""

# 动态 User-Agent 池，每次运行随机选取，降低指纹识别风险
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]


def clean_typography(text):
    text = text.replace('"', '“').replace("'", '‘')
    if text.startswith('”'):
        text = '“' + text[1:]
    return text


async def intercept_route(route):
    if route.request.resource_type in ["image", "media", "font"]:
        await route.abort()
    else:
        await route.continue_()


# ---------------------------------------------------------------------------
# 缓存系统 — 断点续传 & 崩溃恢复
# ---------------------------------------------------------------------------

def _cache_dir_for(book_id: str) -> str:
    """返回某本书的缓存目录，不存在则创建。"""
    d = os.path.join(CACHE_DIR, book_id)
    os.makedirs(d, exist_ok=True)
    return d


def _cached_path(book_id: str, idx: int) -> str:
    """返回第 idx 章的缓存文件路径。"""
    return os.path.join(_cache_dir_for(book_id), f"{idx}.json")


def get_cached_indices(book_id: str) -> set:
    """扫描缓存目录，返回所有已成功缓存的章节索引。"""
    d = os.path.join(CACHE_DIR, book_id)
    if not os.path.isdir(d):
        return set()
    indices = set()
    for fname in os.listdir(d):
        if fname.endswith(".json"):
            try:
                indices.add(int(fname[:-5]))
            except ValueError:
                pass
    return indices


def build_epub_html_from_cache(book_id: str, idx: int, nav_css):
    """从缓存构建 EpubHtml 对象，缓存损坏时自动删除并返回 None。"""
    path = _cached_path(book_id, idx)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        c = epub.EpubHtml(title=data["title"], file_name=f"chapter_{idx}.xhtml", lang="zh-CN")
        c.content = data["content"]
        c.add_item(nav_css)
        return c
    except (json.JSONDecodeError, KeyError, TypeError):
        # 缓存文件损坏 → 删除后返回 None，触发重新下载
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def save_chapter_cache(book_id: str, idx: int, title: str, content: str):
    """原子写入章节缓存（先写 .tmp 再 rename，防止断电/崩溃导致半截文件）。"""
    path = _cached_path(book_id, idx)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"title": title, "content": content}, f, ensure_ascii=False)
    os.replace(tmp_path, path)  # POSIX / Windows 均可保证原子性


def clear_cache(book_id: str):
    """EPUB 成功生成后，清理该书所有缓存。"""
    d = os.path.join(CACHE_DIR, book_id)
    if os.path.isdir(d):
        shutil.rmtree(d)


# ---------------------------------------------------------------------------
# 章节下载（含自动重试 + 缓存落盘）
# ---------------------------------------------------------------------------

async def fetch_chapter(context, book_id, global_idx, chap_title, chap_url, nav_css):
    """下载单章内容，失败时自动重试（指数退避），成功后写入磁盘缓存。"""
    for attempt in range(MAX_RETRIES):
        async with sem:
            page = await context.new_page()
            try:
                await page.route("**/*", intercept_route)
                await page.goto(chap_url, timeout=30000)
                await page.wait_for_selector("#content", timeout=20000)
                await page.wait_for_timeout(1000)

                text_content = await page.evaluate("""() => {
                    const content = document.getElementById('content');
                    if (!content) return '';
                    return content.innerText;
                }""")

                raw_paragraphs = [p.strip() for p in text_content.split('\n') if p.strip()]
                clean_paragraphs = [clean_typography(p) for p in raw_paragraphs]
                final_paragraphs = clean_paragraphs[2:] if len(clean_paragraphs) > 2 else clean_paragraphs

                html_content = "".join([f"<p>{p}</p>" for p in final_paragraphs])

                file_name = f"chapter_{global_idx}.xhtml"
                c = epub.EpubHtml(title=chap_title, file_name=file_name, lang='zh-CN')
                c.content = f"<h2>{chap_title}</h2>{html_content}"
                c.add_item(nav_css)

                # 写入磁盘缓存（断点续传 / 崩溃恢复）
                save_chapter_cache(book_id, global_idx, chap_title, c.content)

                return global_idx, chap_title, c, None
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY_BASE * (attempt + 1)
                    tqdm.write(
                        f"⚠️ 第 {global_idx} 章「{chap_title}」下载失败，"
                        f"{delay} 秒后重试 ({attempt+1}/{MAX_RETRIES})... {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    return global_idx, chap_title, None, str(e)
            finally:
                await page.close()

    return global_idx, chap_title, None, "Unknown error"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def download_hetushu_book(book_id: str):
    base_url = f"https://www.hetushu.com/book/{book_id}/index.html"
    ua = random.choice(USER_AGENTS)

    print(f"\n\U0001f680 正在通过 CloakBrowser 隐身引擎启动浏览器，抓取书籍 ID: {book_id}")
    print(f"\U0001f4cb 本次 User-Agent: {ua[:80]}...")

    browser = await launch_async(headless=False, humanize=True)
    context = await browser.new_context(user_agent=ua)

    # ---- 首页加载（带重试）-----------------------------------------------
    last_error = None
    for attempt in range(MAX_RETRIES):
        page = await context.new_page()
        try:
            await page.goto(base_url, timeout=30000)

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

            break  # 成功，跳出重试循环
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (attempt + 1)
                print(f"⚠️ 首页加载失败（第 {attempt+1} 次），{delay} 秒后重试... ({e})")
                await asyncio.sleep(delay)
            else:
                print(f"❌ 首页解析失败（已重试 {MAX_RETRIES} 次）: {last_error}")
                await browser.close()
                return
        finally:
            await page.close()

    # ---- 解析目录结构 ---------------------------------------------------
    toc_info = []          # [{ volume, chapters: [(title, idx), ...] }, ...]
    title_map = {}         # idx → title（快速查找）
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
    # 只保留有效范围内的缓存（防止不同书籍使用同一 ID 导致脏数据）
    cached_indices = {idx for idx in cached_indices if 1 <= idx <= total_chapters}
    if cached_indices:
        print(f"\U0001f4cc 检测到已有缓存: {len(cached_indices)}/{total_chapters} 章（将跳过网络请求）")

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

    # ① 从磁盘缓存恢复
    for idx in sorted(cached_indices):
        c = build_epub_html_from_cache(book_id, idx, nav_css)
        if c:
            downloaded_chapters[idx] = c

    # ② 创建未缓存章节的网络下载任务
    tasks = []
    global_idx = 1
    for vol_data in toc_data:
        for ch in vol_data['chapters']:
            if global_idx not in cached_indices:
                chap_url = urljoin(base_url, ch['href'])
                tasks.append(
                    fetch_chapter(context, book_id, global_idx, ch['title'], chap_url, nav_css)
                )
            global_idx += 1

    to_fetch = len(tasks)
    if to_fetch == 0:
        print(f"\U0001f4e6 全部章节 ({total_chapters} 章) 均已缓存，跳过网络抓取，直接生成 EPUB")
    else:
        cached_count = len(cached_indices)
        print(f"\U0001f4e6 共 {total_chapters} 章，需下载 {to_fetch} 章" +
              (f"（已缓存 {cached_count} 章）" if cached_count else "") +
              "，开始高并发抓取...")

    # ---- 网络下载（并发）------------------------------------------------
    if to_fetch > 0:
        with tqdm(total=to_fetch, desc="下载进度", unit="章") as pbar:
            for coro in asyncio.as_completed(tasks):
                idx, title, epub_obj, error = await coro
                if epub_obj:
                    downloaded_chapters[idx] = epub_obj
                else:
                    tqdm.write(f"❌ 失败: {title} - {error}")
                pbar.update(1)

    # ---- 组装 EPUB -----------------------------------------------------
    epub_toc = []
    spine = ['nav']

    for item in toc_info:
        vol_section = epub.Section(item['volume'])
        vol_items = []

        for title, idx in item['chapters']:
            c = downloaded_chapters.get(idx)
            if c:
                book.add_item(c)
                spine.append(c)
                vol_items.append(c)

        # 卷名链接到该卷第一章，让卷名在目录中可点击跳转
        if vol_items:
            vol_section.href = vol_items[0].file_name
            epub_toc.append((vol_section, vol_items))

    book.toc = epub_toc
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    safe_title = "".join([c for c in book_title if c.isalnum() or c in (' ', '_', '-')]).strip()
    epub.write_epub(f"{safe_title}.epub", book)

    # 生成成功 → 清理该书缓存
    clear_cache(book_id)
    print(f"\n\U0001f389 电子书已生成: {safe_title}.epub")
    await browser.close()


if __name__ == '__main__':
    # Python 3.8+ 的 Windows 默认已是 ProactorEventLoop，
    # 这里显式设置以兼容 Python 3.7 及更早版本
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    target_id = sys.argv[1] if len(sys.argv) > 1 else input("请输入书籍 ID: ").strip()
    if target_id:
        asyncio.run(download_hetushu_book(target_id))
