# hetushu-scraper — agent instructions

## Setup

- **Python >=3.14** required (`pyproject.toml` enforces this).
- Package manager: **uv** (`uv sync`, `uv lock`, `uv run`). No pip-based workflow.
- **Tests**: `uv run pytest` (67 tests covering config, cache, fetcher, downloader, epub). Uses `tmp_path` + `monkeypatch` for cache isolation.

## Run

```bash
uv run main.py                               # prompts for book ID
uv run main.py 12345                         # download book 12345
uv run main.py 12345 --headed                # show the browser window (default is headless)
uv run main.py 12345 --output ./books        # custom output dir
uv run main.py 12345 --max-retries 5         # override retries
uv run main.py 12345 --timeout 60000         # longer page timeout
uv run main.py 12345 --concurrency 4         # limit concurrent pages
uv run main.py 12345 --delay 1.5             # wait 1.5s between requests
uv run main.py 12345 --verbose               # detailed request/response logs
```

## Architecture

- **Package** at `hetushu_scraper/` with 5 modules:
  - `config.py` — constants (retry limits, concurrency, UA pool, CSS)
  - `cache.py` — disk cache system (atomic writes, corrupt detection)
  - `fetcher.py` — `fetch_chapter()` + `clean_typography()` + `reorder_paragraphs()`
  - `downloader.py` — `download_hetushu_book()` + `build_toc()` / `plan_fetch()` / `assemble_epub()` helpers
  - `cli.py` — `run_cli()`
- **Entry point**: `main.py` (root file)
  - Root `main.py` does `from hetushu_scraper.cli import run_cli`.
- **CloakBrowser** (not raw Playwright) wraps Chromium; `headless=True` default, `humanize=True`. First run downloads ~200MB Chromium silently.
- **Page pool**: concurrency (default 8, via `--concurrency`) is implemented as a pool of `min(concurrency, chapters_to_fetch)` browser pages, each driven by an `asyncio.Queue` worker; each page lives in its own context with a random User-Agent. `fetch_chapter()` receives a ready-made `page` (no per-chapter `new_page`/`close`). Rate limiting via `--delay` (seconds per request, default 0). Retries: each chapter retries `--max-retries` times inside `fetch_chapter`, then failed chapters get one outer retry pass at `max_retries=1` reusing the pool.
- **Cache** at `.chapter_cache/{book_id}/{idx}.json` (atomic writes via `.tmp`+`os.replace`). Delete dir to force full redownload. `--no-cache` ignores existing cache (full redownload), skips writing new cache, and clears the dir after EPUB generation.
- **Windows fix**: `hetushu_scraper/__init__.py` forces UTF-8 on stdout/stderr via `reconfigure()`; skips when `PYTEST_VERSION` is set.
- **Python 3.14+ quirk**: `try/finally` wrapping a `for` loop with a nested `try/except/finally` (that has `break` + `return`) triggers a SyntaxError. The homepage retry loop was restructured to put the `for` loop outside the outer `try` to avoid this.

## Caveats

- **No linter, type checker, or formatter** configured. Do not assume any exist.
- **`intercept_route()`** blocks images/media/fonts and `section.js` (the site's anti-scrape reorder script).
- **Anti-scrape reorder**: hetushu serves `#content` paragraphs in scrambled order. `fetch_chapter()` extracts the raw scrambled paragraph text via in-page JS (blocking `section.js` so the DOM stays scrambled, cloning each `#content` div and removing spam elements), fetches `r{sid}.json` (sid from `chap_url`) inside the page to get the `token` response header, then `reorder_paragraphs()` (mirrors `section.content.load()`) restores order. The `token` endpoint returns HTTP 204 with the `token` header and **requires** `X-Requested-With: XMLHttpRequest` (native `fetch()` omits it — must be set explicitly) plus a same-origin `Referer`; the bare URL is Cloudflare edge-cached as 404, so the fetch must append a cache-buster (`?_=<timestamp>`). Token decode: `base64` decode, then split on `[A-Z]+%`. If reorder fails, keeps scrambled order (with a warning in verbose mode).
- **Spam injection**: each chapter injects ~5 junk elements (fake URLs like `m.hetushu.com.com`, `和*图*书` watermarks) wrapped in a **random legacy tag per chapter** (`var`/`dfn`/`code`/`kbd`/`samp`/`tt`/`cite`/`big`/`acronym`/`s`/`q`/`u`/`bdo`/`strike`). Extraction JS removes elements whose tag is in `SPAM_TAGS` (config.py) on a cloned DOM node before reading `textContent` — no regex HTML parsing.
- **No `[2:]` skip**: chapter title is in a separate `<h2>`; paragraphs come straight from the `#content` divs (mask div excluded).
- Failed chapters are retried once automatically; if still failing, EPUB includes only successfully downloaded content with a failure summary at the end.
- Git remote: `git@github.com:aachou/hetushu-scraper.git` (SSH). Single `main` branch.
- Cache is preserved after EPUB generation by default; `--no-cache` ignores existing cache (full redownload), skips writing new cache, and clears the cache dir afterwards.

## Github release

```bash
gh release create v<version> --title "v<version> — <summary>" --notes "<body>"
```

- Title 格式: `v<version> — <中文概括>`
- Body 分三部分: `## 新功能` `## BUG 修复` `## 新测试`，如果对应部分的内容为空则不输出这个章节
- 不要对 Markdown 内任何符号加反斜杠转义（包括反引号包围的代码）— shell 中直接写纯文本，不嵌套引号
