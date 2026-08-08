import asyncio
import base64
import re
from html import unescape

from ebooklib import epub
from tqdm import tqdm

from .config import MAX_RETRIES, RETRY_DELAY_BASE
from .cache import save_chapter_cache


_RQUOT = "\u201c"
_LQUOT = "\u2018"
_RDQUOT = "\u201d"
_LDQUOT = "\u2019"

_SPAM_ELEM_RE = re.compile(
    r"<(?:code|kbd|samp|tt|var|dfn|cite|big|acronym|s|q|u|bdo|del|ins|sub|sup|center|font|strike|nobr|marquee|mark|small)\b[^>]*>.*?</(?:code|kbd|samp|tt|var|dfn|cite|big|acronym|s|q|u|bdo|del|ins|sub|sup|center|font|strike|nobr|marquee|mark|small)>",
    re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")


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


def strip_paragraph_spam(html_fragment: str) -> str:
    """Remove injected junk (fake URLs/watermarks) and leftover tags.

    The site wraps spam in a random legacy element per chapter
    (``<var>``/``<dfn>``/``<code>``/``<kbd>``/``<samp>``/``<tt>``/...), so
    the whole element including its content is dropped before tag stripping.
    """
    text = _SPAM_ELEM_RE.sub("", html_fragment)
    text = _TAG_RE.sub("", text)
    return unescape(text).strip()


async def intercept_route(route):
    if route.request.resource_type in ["image", "media", "font"]:
        await route.abort()
    elif "section.js" in route.request.url:
        await route.abort()
    else:
        await route.continue_()


async def fetch_chapter(
    context,
    book_id,
    global_idx,
    chap_title,
    chap_url,
    nav_css,
    *,
    sem,
    delay=0,
    max_retries=None,
    timeout=None,
    verbose=False,
):
    max_retries = max_retries or MAX_RETRIES
    timeout = timeout or 30000
    selector_timeout = int(timeout * 2 / 3)

    sid_match = re.search(r"/(\d+)\.html", chap_url)
    sid = sid_match.group(1) if sid_match else ""

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

                # section.js is blocked, so #content keeps the scrambled order.
                raw_html_paragraphs = await page.evaluate(
                    """() => {
                        const content = document.getElementById('content');
                        if (!content) return [];
                        const paras = [];
                        for (const node of content.childNodes) {
                            if (node.nodeType !== 1) continue;
                            if (node.tagName === 'H2') continue;
                            if (node.classList && node.classList.contains('mask')) continue;
                            if (node.tagName === 'DIV') paras.push(node.innerHTML);
                        }
                        return paras;
                    }"""
                )

                scrambled = [strip_paragraph_spam(p) for p in raw_html_paragraphs]

                ordered = scrambled
                if sid and scrambled:
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
                            ordered = reorder_paragraphs(scrambled, token)
                    except Exception as e:
                        if verbose:
                            tqdm.write(
                                f"  ⚠️ 第 {global_idx} 章重排失败，保留原始顺序: {e}"
                            )

                clean_paragraphs = [clean_typography(p) for p in ordered]
                final_paragraphs = clean_paragraphs

                html_content = "".join([f"<p>{p}</p>" for p in final_paragraphs])

                file_name = f"chapter_{global_idx}.xhtml"
                c = epub.EpubHtml(title=chap_title, file_name=file_name, lang="zh-CN")
                c.content = f"<h2>{chap_title}</h2>{html_content}"
                c.add_item(nav_css)

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
            finally:
                if page:
                    await page.close()

    return global_idx, chap_title, None, "Unknown error"
