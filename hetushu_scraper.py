import asyncio
import sys
from tqdm import tqdm
from cloakbrowser import launch_async  # 核心：替换原有的 async_playwright 导入
from ebooklib import epub
from urllib.parse import urljoin

# --- 配置项 ---
# 既然用了 CloakBrowser 源码级防爬，可以安全地将并发重回 8
MAX_CONCURRENT_PAGES = 8
sem = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

# --- CSS 样式 ---
CSS_STYLE = """
    p { text-indent: 2em; margin-bottom: 0.5em; line-height: 1.6; }
"""

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

async def fetch_chapter(context, global_idx, chap_title, chap_url, nav_css):
    async with sem:
        page = await context.new_page()
        try:
            await page.route("**/*", intercept_route)
            await page.goto(chap_url, timeout=30000)
            await page.wait_for_selector('#content', timeout=20000)
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
            
            # --- 完全不做任何标题修改，保持原汁原味 ---
            file_name = f"chapter_{global_idx}.xhtml"
            c = epub.EpubHtml(title=chap_title, file_name=file_name, lang='zh-CN')
            c.content = f"<h2>{chap_title}</h2>{html_content}"
            c.add_item(nav_css)
            
            return global_idx, chap_title, c, None
        except Exception as e:
            return global_idx, chap_title, None, str(e)
        finally:
            await page.close()

async def download_hetushu_book(book_id: str):
    base_url = f"https://www.hetushu.com/book/{book_id}/index.html"
    
    print(f"\n🚀 正在通过 CloakBrowser 隐身引擎启动浏览器，抓取书籍 ID: {book_id}")
    
    # 核心修改：使用 CloakBrowser 异步启动
    # humanize=True 会让鼠标、滚动行为在底层更像真人操作，自动绕过大多数防火墙
    browser = await launch_async(
        headless=False,  # 对于严格反爬的网站，有头(False)模式隐身效果最好
        humanize=True
    )
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    )
    
    page = await context.new_page()
    try:
        await page.goto(base_url, timeout=30000)
        book_title = await page.evaluate("() => document.querySelector('h2').innerText.trim()")
        
        toc_data = await page.evaluate("""() => {
            const dirDiv = document.getElementById('dir');
            let result = [];
            let currentVolume = "正文";
            let currentChapters = [];
            dirDiv.querySelectorAll('dt, dd').forEach(item => {
                if (item.tagName === 'DT') {
                    if (currentChapters.length > 0) result.push({ volume: currentVolume, chapters: currentChapters });
                    currentVolume = item.innerText.trim();
                    currentChapters = [];
                } else {
                    const a = item.querySelector('a');
                    if (a) currentChapters.push({ title: a.innerText.trim(), href: a.getAttribute('href') });
                }
            });
            if (currentChapters.length > 0) result.push({ volume: currentVolume, chapters: currentChapters });
            return result;
        }""")
    except Exception as e:
        print(f"❌ 主页解析失败: {e}")
        await browser.close()
        return
    finally:
        await page.close()

    book = epub.EpubBook()
    book.set_title(book_title)
    book.set_language('zh-CN')
    
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=CSS_STYLE)
    book.add_item(nav_css)

    tasks = []
    global_idx = 1
    toc_info = [] 
    
    for vol_data in toc_data:
        chapters_info = []
        for ch in vol_data['chapters']:
            chap_url = urljoin(base_url, ch['href'])
            tasks.append(fetch_chapter(context, global_idx, ch['title'], chap_url, nav_css))
            chapters_info.append((ch['title'], global_idx))
            global_idx += 1
        toc_info.append({'volume': vol_data['volume'], 'chapters': chapters_info})

    total_chapters = global_idx - 1
    print(f"📦 共发现 {total_chapters} 章，开始高并发抓取...")
    
    downloaded_chapters = {}
    with tqdm(total=total_chapters, desc="下载进度", unit="章") as pbar:
        for coro in asyncio.as_completed(tasks):
            idx, title, epub_obj, error = await coro
            if epub_obj:
                downloaded_chapters[idx] = epub_obj
            else:
                tqdm.write(f"❌ 失败: {title} - {error}")
            pbar.update(1)

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
        
        # 核心：卷名链接到该分卷第一章，让卷名在目录中可点击跳转
        if vol_items:
            vol_section.href = vol_items[0].file_name
            epub_toc.append((vol_section, vol_items))
    
    book.toc = epub_toc
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    safe_title = "".join([c for c in book_title if c.isalnum() or c in (' ', '_', '-')]).strip()
    epub.write_epub(f"{safe_title}.epub", book)
    print(f"\n🎉 电子书已生成: {safe_title}.epub")
    await browser.close()

if __name__ == '__main__':
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
    target_id = sys.argv[1] if len(sys.argv) > 1 else input("请输入书籍 ID: ").strip()
    if target_id:
        asyncio.run(download_hetushu_book(target_id))
