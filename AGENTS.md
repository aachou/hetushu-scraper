# hetushu-scraper — agent instructions

## Setup

- **Python >=3.14** required (`pyproject.toml` enforces this).
- Package manager: **uv** (`uv sync`, `uv lock`, `uv run`). No pip-based workflow.
- **Tests**: `uv run pytest` (39 tests covering config, cache, fetcher, epub). Uses `tmp_path` + `monkeypatch` for cache isolation.

## Run

```bash
uv run main.py                               # prompts for book ID
uv run main.py 12345                         # download book 12345
uv run main.py 12345 --headless              # hide browser window
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
  - `fetcher.py` — `fetch_chapter()` + `clean_typography()`
  - `downloader.py` — `download_hetushu_book()`
  - `cli.py` — `run_cli()`
- **Entry point**: `main.py` (root file)
  - Root `main.py` does `from hetushu_scraper.cli import run_cli`.
- **CloakBrowser** (not raw Playwright) wraps Chromium; `headless=False` default, `humanize=True`. First run downloads ~200MB Chromium silently.
- **Async** concurrency via `asyncio.Semaphore()` (default 8, configurable via `--concurrency`) + `asyncio.as_completed()`. Rate limiting via `--delay` (seconds per request, default 0).
- **Cache** at `.chapter_cache/{book_id}/{idx}.json` (atomic writes via `.tmp`+`os.replace`). Delete dir to force full redownload.
- **Windows fix**: `hetushu_scraper/__init__.py` forces UTF-8 on stdout/stderr; skips when `PYTEST_VERSION` is set.
- **Python 3.14+ quirk**: `try/finally` wrapping a `for` loop with a nested `try/except/finally` (that has `break` + `return`) triggers a SyntaxError. The homepage retry loop was restructured to put the `for` loop outside the outer `try` to avoid this.

## Caveats

- **No linter, type checker, or formatter** configured. Do not assume any exist.
- **`intercept_route()`** blocks images/fonts but not CSS/JS.
- Failed chapters are retried once automatically; if still failing, EPUB includes only successfully downloaded content with a failure summary at the end.
- Git remote: `git@github.com:aachou/hetushu-scraper.git` (SSH). Single `main` branch.
- Cache is preserved after EPUB generation by default (use `--no-cache` to discard).

## Github release

```bash
gh release create v<version> --title "v<version> — <summary>" --notes "<body>"
```

- Title 格式: `v<version> — <中文概括>`
- Body 分三部分: `## 新功能` `## BUG 修复` `## 新测试`，如果对应部分的内容为空则不输出这个章节
- 不要对 Markdown 内任何符号加反斜杠转义（包括反引号包围的代码）— shell 中直接写纯文本，不嵌套引号
