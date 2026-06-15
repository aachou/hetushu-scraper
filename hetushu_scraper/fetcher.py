import asyncio

from ebooklib import epub
from tqdm import tqdm

from .config import MAX_RETRIES, RETRY_DELAY_BASE
from .cache import save_chapter_cache


def clean_typography(text):
    text = text.replace('"', '\u201c').replace("'", '\u2018')
    if text.startswith('\u201d'):
        text = '\u201c' + text[1:]
    return text


async def intercept_route(route):
    if route.request.resource_type in ["image", "media", "font"]:
        await route.abort()
    else:
        await route.continue_()


async def fetch_chapter(context, book_id, global_idx, chap_title, chap_url, nav_css,
                        *, sem, delay=0, max_retries=None, timeout=None, verbose=False):
    max_retries = max_retries or MAX_RETRIES
    timeout = timeout or 30000
    selector_timeout = int(timeout * 2 / 3)

    for attempt in range(max_retries):
        async with sem:
            if delay:
                await asyncio.sleep(delay)
            page = None
            try:
                if verbose:
                    tqdm.write(f"  📄 请求第 {global_idx} 章: {chap_title}")
                page = await context.new_page()
                await page.route("**/*", intercept_route)
                await page.goto(chap_url, timeout=timeout)
                await page.wait_for_selector("#content", timeout=selector_timeout)
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

                save_chapter_cache(book_id, global_idx, chap_title, c.content)

                return global_idx, chap_title, c, None
            except Exception as e:
                if attempt < max_retries - 1:
                    retry_delay = RETRY_DELAY_BASE * (attempt + 1)
                    tqdm.write(
                        f"⚠️ 第 {global_idx} 章「{chap_title}」下载失败，"
                        f"{retry_delay} 秒后重试 ({attempt+1}/{max_retries})... {e}"
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    return global_idx, chap_title, None, str(e)
            finally:
                if page:
                    await page.close()

    return global_idx, chap_title, None, "Unknown error"
