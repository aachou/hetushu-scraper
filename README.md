# hetushu-scraper

抓取[和图书 (Hetushu)](https://www.hetushu.com) 上的小说并一键生成 EPUB 电子书。

## 快速开始

```bash
uv run python -m hetushu_scraper                        # 提示输入书籍 ID
uv run python -m hetushu_scraper 12345                  # 直接下载书籍 12345
uv run python -m hetushu_scraper 12345 --headless       # 无头模式，不显示浏览器
uv run python -m hetushu_scraper 12345 --output ./books # 指定输出目录
uv run python -m hetushu_scraper 12345 --max-retries 5  # 自定义重试次数
uv run python -m hetushu_scraper 12345 --timeout 60000  # 自定义超时（毫秒）
uv run python -m hetushu_scraper 12345 --concurrency 4  # 限制并发数
uv run python -m hetushu_scraper 12345 --delay 1.5      # 请求间隔（秒）
uv run python -m hetushu_scraper 12345 --verbose        # 详细日志
```

> 书籍 ID 可从详情页 URL 获取：`https://www.hetushu.com/book/12345/index.html` → `12345`

首次运行会后台自动下载约 200MB 的 Chromium 内核，请耐心等待几分钟。

## 功能

- **反爬**：CloakBrowser + 随机 User-Agent，模拟真实浏览器行为（默认有头，支持 `--headless`）
- **重试**：失败自动重试（默认 3 次），等待时间指数递增；`--max-retries` 和 `--timeout` 可自由调整
- **缓存**：章节写入 `.chapter_cache/`，支持断点续传；成功生成 EPUB 后自动清理
- **并发与限速**：`--concurrency` 控制最大并行页面数（默认 8），`--delay` 设置每个请求前的等待秒数（默认 0）
- **EPUB**：含卷目录跳转、图片自适应、代码块样式，兼容 Kindle / Apple Books / Calibre
- **报错汇总**：下载结束列出所有失败章节及原因
- **调试快照**：首页解析失败时自动保存 `debug_{book_id}/index_page.html` 供排查
- **详细日志**：`--verbose` 打印每个请求/响应、缓存状态、章节耗时
- **Windows 兼容**：自动强制 UTF-8 编码，避免 emoji 在 GBK 终端崩溃

> 如需强制全量重新下载，删除 `.chapter_cache/` 目录即可。

## FAQ

**启动后弹出浏览器窗口，能关掉吗？**

可以，使用 `--headless` 参数即可隐藏窗口。CloakBrowser 自动化引擎会在后台翻页下载，完成后自动关闭。

**连接失败怎么办？**

内置自动重试。可通过 `--max-retries` 调整重试次数（默认 3），`--timeout` 调整页面超时（默认 30000ms）。若章节多次重试后仍失败，该章节会被跳过，最终 EPUB 只包含成功下载的内容。

**怎么限制并发和爬取速度？**

`--concurrency` 控制同时打开的页面数（默认 8），`--delay` 设置每个请求前的等待秒数（默认 0）。例如 `--concurrency 1 --delay 2` 表示每 2 秒下载一个章节，对目标服务器最友好。

**下载中断了要重头开始吗？**

不需要。脚本会自动检测 `.chapter_cache/` 中的缓存，跳过已下载章节。

## 免责声明

本工具仅供个人学习和研究使用。请遵守目标网站的使用协议，尊重版权，勿将生成的文件用于商业用途或违法传播。
