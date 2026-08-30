from typing import Final

DEFAULT_CONCURRENCY: Final[int] = 8
DEFAULT_REQUEST_DELAY: Final[float] = 0.0
MAX_RETRIES: Final[int] = 3
RETRY_DELAY_BASE: Final[int] = 2
CACHE_DIR: Final[str] = ".chapter_cache"

SPAM_TAGS: Final[tuple[str, ...]] = (
    "code",
    "kbd",
    "samp",
    "tt",
    "var",
    "dfn",
    "cite",
    "big",
    "acronym",
    "s",
    "q",
    "u",
    "bdo",
    "del",
    "ins",
    "sub",
    "sup",
    "center",
    "font",
    "strike",
    "nobr",
    "marquee",
    "mark",
    "small",
)

CSS_STYLE = """
    p { text-indent: 2em; margin-bottom: 0.5em; line-height: 1.6; }
    img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
    pre { background: #f5f5f5; padding: 1em; border-radius: 4px; overflow-x: auto; font-size: 0.9em; }
    code { background: #f0f0f0; padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.9em; }
    pre code { background: none; padding: 0; border-radius: 0; }
    nav#id ol { list-style-type: none; padding-left: 1.2em; margin: 0.2em 0; }
    nav#id > ol { padding-left: 0; }
    nav#id > ol > li { margin-top: 0.4em; }
"""

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]
