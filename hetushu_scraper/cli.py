import argparse
import asyncio
import sys

from .downloader import download_hetushu_book
from .config import MAX_RETRIES


def run_cli():
    parser = argparse.ArgumentParser(description="抓取和图书上的小说并生成 EPUB")
    parser.add_argument('book_id', nargs='?', help='书籍 ID（省略则交互式输入）')
    parser.add_argument('--headless', action='store_true', help='无头模式，不显示浏览器窗口')
    parser.add_argument('--output', '-o', default=None, help='EPUB 输出路径（目录或 .epub 文件路径）')
    parser.add_argument('--max-retries', type=int, default=MAX_RETRIES, help=f'最大重试次数（默认 {MAX_RETRIES}）')
    parser.add_argument('--timeout', type=int, default=30000, help='页面加载超时毫秒数（默认 30000）')
    parser.add_argument('--verbose', '-v', action='store_true', help='启用详细日志')

    args = parser.parse_args()

    if not args.book_id:
        parser.print_help()
        print()
        args.book_id = input("请输入书籍 ID: ").strip()
        if not args.book_id:
            return

    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(download_hetushu_book(
        args.book_id,
        headless=args.headless,
        output=args.output,
        max_retries=args.max_retries,
        timeout=args.timeout,
        verbose=args.verbose,
    ))
