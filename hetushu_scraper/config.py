DEFAULT_CONCURRENCY = 8
DEFAULT_REQUEST_DELAY = 0.0
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2
CACHE_DIR = ".chapter_cache"

CSS_STYLE = """
    p { text-indent: 2em; margin-bottom: 0.5em; line-height: 1.6; }
    img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
    pre { background: #f5f5f5; padding: 1em; border-radius: 4px; overflow-x: auto; font-size: 0.9em; }
    code { background: #f0f0f0; padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.9em; }
    pre code { background: none; padding: 0; border-radius: 0; }
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]
