import asyncio
import base64
import re

from ebooklib import epub
from tqdm import tqdm

from .config import MAX_RETRIES, RETRY_DELAY_BASE, SPAM_TAGS
from .cache import save_chapter_cache


_RQUOT = "\u201c"
_LQUOT = "\u2018"
_RDQUOT = "\u201d"
_LDQUOT = "\u2019"


def clean_typography(text: str) -> str:
    text = text.replace('"', _RQUOT).replace("'", _LQUOT)
    if text.startswith(_RDQUOT):
        text = _RQUOT + text[1:]
    if text.startswith(_LDQUOT):
        text = _LQUOT + text[1:]
    text = re.sub(r"(\w)\u2014(\w)", "\\1\u2014\\2", text)
    return text


def decode_order_token(token: str) -> list[int]:
    """Decode the hetushu anti-scrape order token into a list of indices.

    Mirrors the site's `base64.decode(...).split(/[A-Z]+%/)` in `section.js`.
    """
    decoded = base64.b64decode(token).decode("utf-8")
    return [int(x) for x in re.split(r"[A-Z]+%", decoded) if x]


def reorder_paragraphs(paragraphs: list[str], token: str) -> list[str]:
    """Reorder scrambled paragraphs using the server-provided token.

    Mirrors `section.content.load()` in `section.js`: each scrambled div is
    placed at the position given by the token, then emitted in index order.
    """
    indices = decode_order_token(token)
    if len(indices) != len(paragraphs):
        raise ValueError(
            f"order token has {len(indices)} entries but got {len(paragraphs)} paragraphs"
        )
    b = 0
    child_node: dict[int, int] = {}
    for i, v in enumerate(indices):
        if v < 5:
            child_node[v] = i
            b += 1
        else:
            child_node[v - b] = i
    return [paragraphs[child_node[k]] for k in sorted(child_node)]


def _build_extract_js() -> str:
    spam_selector = ",".join(SPAM_TAGS)
    return f"""
() => {{
    const content = document.getElementById('content');
    if (!content) return [];
    const paras = [];
    for (const node of content.childNodes) {{
        if (node.nodeType !== 1) continue;
        if (node.tagName === 'H2') continue;
        if (node.classList && node.classList.contains('mask')) continue;
        if (node.tagName !== 'DIV') continue;
        const clone = node.cloneNode(true);
        if ('{spam_selector}') {{
            for (const el of clone.querySelectorAll('{spam_selector}')) el.remove();
        }}
        paras.push(clone.textContent.trim());
    }}
    return paras;
}}
"""


_EXTRACT_JS = _build_extract_js()


async def intercept_route(route):
    if route.request.resource_type in ["image", "media", "font"]:
        await route.abort()
    elif "section.js" in route.request.url:
        await route.abort()
    else:
        await route.continue_()


async def fetch_chapter(
    page,
    book_id,
    global_idx,
    chap_title,
    chap_url,
    nav_css,
    *,
    delay=0,
    max_retries=None,
    timeout=None,
    verbose=False,
    use_cache=True,
):
    max_retries = MAX_RETRIES if max_retries is None else max_retries
    timeout = 30000 if timeout is None else timeout
    selector_timeout = int(timeout * 2 / 3)

    sid_match = re.search(r"/(\d+)\.html", chap_url)
    sid = sid_match.group(1) if sid_match else ""

    for attempt in range(max_retries):
        if delay:
            await asyncio.sleep(delay)
        try:
            if verbose:
                tqdm.write(f"  📄 请求第 {global_idx} 章: {chap_title}")
            await page.goto(chap_url, timeout=timeout)
            await page.wait_for_selector("#content", timeout=selector_timeout)
            try:
                await page.wait_for_function(
                    "() => { const c = document.getElementById('content'); return c && c.children.length > 0; }",
                    timeout=selector_timeout,
                )
            except Exception:
                pass

            paragraphs = await page.evaluate(_EXTRACT_JS)

            ordered = paragraphs
            if sid and paragraphs:
                try:
                    token = await page.evaluate(
                        """async (sid) => {
                            const resp = await fetch('r' + sid + '.json?_=' + Date.now(), {
                                headers: { 'X-Requested-With': 'XMLHttpRequest' }
                            });
                            if (resp.status === 200) {
                                return await resp.text();
                            }
                            return resp.headers.get('token') || '';
                        }""",
                        sid,
                    )
                    if token:
                        ordered = reorder_paragraphs(paragraphs, token)
                except Exception as e:
                    if verbose:
                        tqdm.write(
                            f"  ⚠️ 第 {global_idx} 章重排失败，保留原始顺序: {e}"
                        )

            final_paragraphs = [clean_typography(p) for p in ordered]
            html_content = "".join([f"<p>{p}</p>" for p in final_paragraphs])

            file_name = f"chapter_{global_idx}.xhtml"
            c = epub.EpubHtml(title=chap_title, file_name=file_name, lang="zh-CN")
            c.content = f"<h2>{chap_title}</h2>{html_content}"
            c.add_item(nav_css)

            if use_cache:
                save_chapter_cache(book_id, global_idx, chap_title, c.content)

            return global_idx, chap_title, c, None
        except Exception as e:
            if attempt < max_retries - 1:
                retry_delay = RETRY_DELAY_BASE * (attempt + 1)
                tqdm.write(
                    f"⚠️ 第 {global_idx} 章「{chap_title}」下载失败，"
                    f"{retry_delay} 秒后重试 ({attempt + 1}/{max_retries})... {e}"
                )
                await asyncio.sleep(retry_delay)
            else:
                return global_idx, chap_title, None, str(e)
