import argparse
import asyncio

from .downloader import download_books
from .config import MAX_RETRIES, DEFAULT_CONCURRENCY, DEFAULT_REQUEST_DELAY


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="抓取和图书上的小说并生成 EPUB")
    parser.add_argument(
        "book_id",
        nargs="*",
        help="书籍 ID，可多个（空格分隔）；省略则交互式输入",
    )
    parser.add_argument(
        "--headed", action="store_true", help="显示浏览器窗口（默认无头）"
    )
    parser.add_argument(
        "--output", "-o", default=None, help="EPUB 输出路径（目录或 .epub 文件路径）"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=MAX_RETRIES,
        help=f"最大重试次数（默认 {MAX_RETRIES}）",
    )
    parser.add_argument(
        "--timeout", type=int, default=30000, help="页面加载超时毫秒数（默认 30000）"
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"最大并发页面数（默认 {DEFAULT_CONCURRENCY}）",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help=f"每个请求前等待秒数（默认 {DEFAULT_REQUEST_DELAY}，用于控制爬取速度）",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="忽略已有缓存并重新下载，生成 EPUB 后清除缓存",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="启用详细日志")

    args = parser.parse_args()

    book_ids = args.book_id
    if not book_ids:
        parser.print_help()
        print()
        book_id = input("请输入书籍 ID: ").strip()
        if not book_id:
            return
        book_ids = [book_id]

    try:
        asyncio.run(
            download_books(
                book_ids,
                headless=not args.headed,
                output=args.output,
                max_retries=args.max_retries,
                timeout=args.timeout,
                concurrency=args.concurrency,
                delay=args.delay,
                no_cache=args.no_cache,
                verbose=args.verbose,
            )
        )
    except KeyboardInterrupt:
        print(
            "\n⚠️ 已中断。已下载章节会保留在缓存中，下次运行将断点续传。"
        )
