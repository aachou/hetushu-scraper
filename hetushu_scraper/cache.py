import json
import os
import shutil

from ebooklib import epub

from .config import CACHE_DIR


def _cache_dir_for(book_id: str) -> str:
    d = os.path.join(CACHE_DIR, book_id)
    os.makedirs(d, exist_ok=True)
    return d


def _cached_path(book_id: str, idx: int) -> str:
    return os.path.join(_cache_dir_for(book_id), f"{idx}.json")


def get_cached_indices(book_id: str) -> set[int]:
    d = os.path.join(CACHE_DIR, book_id)
    if not os.path.isdir(d):
        return set()
    indices: set[int] = set()
    for fname in os.listdir(d):
        if fname.endswith(".json"):
            try:
                indices.add(int(fname[:-5]))
            except ValueError:
                pass
    return indices


def build_epub_html_from_cache(book_id: str, idx: int, nav_css) -> epub.EpubHtml | None:
    path = _cached_path(book_id, idx)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        c = epub.EpubHtml(
            title=data["title"], file_name=f"chapter_{idx}.xhtml", lang="zh-CN"
        )
        c.content = data["content"]
        c.add_item(nav_css)
        return c
    except json.JSONDecodeError, KeyError, TypeError:
        try:
            os.remove(path)
        except OSError:
            pass
        return None


def save_chapter_cache(book_id: str, idx: int, title: str, content: str) -> None:
    path = _cached_path(book_id, idx)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"title": title, "content": content}, f, ensure_ascii=False)
    os.replace(tmp_path, path)


def clear_cache(book_id: str) -> None:
    d = os.path.join(CACHE_DIR, book_id)
    if os.path.isdir(d):
        shutil.rmtree(d)
