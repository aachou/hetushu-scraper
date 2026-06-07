# hetushu-scraper

hetushu-scraper 旨在帮助你高效地将<和图书 (Hetushu)>网站上的小说一键抓取并生成 EPUB 格式电子书。

## 环境准备

在运行代码之前，请确保你的电脑已安装 Python（建议 3.8+）。

第一步：安装依赖库。打开终端（CMD、PowerShell 或 Terminal），运行以下命令安装必要的 Python 库：
```
pip install ebooklib playwright tqdm
```

第二步：安装浏览器内核。由于脚本依赖 Playwright 进行网页抓取，需要安装 Chromium 浏览器内核（仅需安装一次）：
```
playwright install chromium
```

## 如何运行

方式A，你可以通过命令行直接启动脚本 `python hetushu_scraper.py` 或者直接双击运行脚本，程序会提示你输入书籍 ID。

方式 B，通过命令行参数传入书籍ID 启动脚本 `python hetushu_scraper.py id`。

(注：书籍 ID 可从和图书网站书籍详情页的 URL 中获取，例如 https://www.hetushu.com/book/12345/index.html，ID 即为 12345)

## 功能特性

* 卷目录跳转：生成的 EPUB 总目录中，卷名（Section）已被设置为可点击。点击卷名会自动跳转到该卷的第一章。
* 高并发抓取：采用异步并发技术，同时开启多个进程，极大地缩短了整本书的下载时间。
* 格式美化：内置基础 CSS 样式，确保在 Kindle、Apple Books、Calibre 等主流阅读器中显示清晰。

## 常见问题解答 (FAQ)

Q: 脚本报错“Playwright not found”？

A: 请重新执行 `pip install playwright` 和 `playwright install chromium`。

---

Q: 抓取时提示连接失败？

A: 本脚本设置了 20 秒的超时重试机制。如果网络环境不稳定，可以适当调大代码中的 `timeout` 参数，或检查你的网络是否能正常访问目标网站。

## 版权与免责声明
该工具仅供个人学习和研究技术使用。

请遵守相关网站的使用协议，尊重书籍版权，请勿将生成的文件用于商业用途或违法传播。
