# wechat-article-fetch

把单篇微信公众号文章链接原样抓成 Markdown / JSON（标题、公众号名、作者、发布时间、正文、图片），不用付费 API、不用登录。

Fetch a single WeChat Official Account article URL into Markdown / JSON (title, account name, author, publish date, body, images). No paid API, no login.

## 安装 / Install

```bash
pip install --break-system-packages requests beautifulsoup4
```

## 用法 / Usage

```bash
python3 scripts/fetch.py "<文章URL>" [--markdown] [--out DIR]
```

- 默认输出 JSON 到 stdout：`title / author / account / date / url / images / markdown`
- `--markdown`：输出纯 Markdown，顶部带 YAML frontmatter（title/account/author/date/source），图片以 `![](url)` 内嵌保留在正文原位置
- `--out DIR`：结果写入目录文件（`article.json` 或 `article.md`），否则只打印到 stdout

## 作为 Agent skill 使用 / As an agent skill

读 `SKILL.md`：触发词、实现要点（MicroMessenger UA 反爬、图片真实 URL 取 `data-src`、按页面声明 charset 解码）都在里面。

## 红线 / Rules

- 只抓取用户给出的**单篇**文章链接，不做批量爬取
- 遵守反爬：失败时如实报错（限流/文章被删/链接无效），不编造内容
- 抓到的正文只按用户要求使用，不做二次分发
