# WeChat Article Fetch / 公众号文章抓取

输入一篇微信公众号文章链接, 原样抓成 Markdown / JSON: 标题、公众号名称、
作者、发布时间、正文、图片列表。不用付费 API, 不用登录。

Fetch a single WeChat Official Account article (`mp.weixin.qq.com/s/...`)
into Markdown / JSON: title, account name, author, publish date, body text,
image list. No paid API, no login.

## 触发词 / Trigger phrases

用户说以下任一种意思时用这个 skill:

- "抓这篇公众号文章" / "把这篇公众号文章抓下来"
- "这篇微信文章转成 markdown"
- 发来一个 `mp.weixin.qq.com/s/...` 链接并说要内容/全文

## 用法 / Usage

```bash
cd scripts
pip install requests beautifulsoup4
python3 fetch.py "<文章URL>" [--markdown] [--out DIR]
```

- 默认输出 JSON 到 stdout: `title / author / account / date / url / images / markdown`
- `--markdown`: 输出纯 Markdown, 顶部带 YAML frontmatter (title/account/author/date/source), 图片以内嵌 `![](url)` 形式保留在正文原位置
- `--out DIR`: 结果写入目录文件 (`article.json` 或 `article.md`), 否则只打印到 stdout

依赖: `requests`, `beautifulsoup4`

## 实现要点 / Implementation notes

1. **必须用 MicroMessenger 的 UA**, 否则微信服务端返回反爬页。脚本内置 3 个
   (iOS / Android / Mac 微信), 被反爬页挡住时自动换 UA 重试 (最多 4 次)。
2. 正文在 HTML 的 `#js_content` div 里; 图片真实 URL 在 img 的 `data-src`
   属性 (不是 `src`)。
3. 标题: `#activity-name` → `msg_title` 变量 → `og:title`。
   公众号名: mpprofile 的 `data-nickname` (藏在 `\x22` 转义的 JS 字符串里, 需先还原)
   → `.rich_media_meta_nickname` → `.profile_nickname`。
   发布时间: `var ct` 10 位时间戳 (转北京时间) → 页面内 URL 编码 JSON 的 `publish_time`。
4. 微信页面声明 `charset=utf-8`; `requests` 的 `apparent_encoding` 常猜错
   (如 MacRoman) 会导致乱码, 必须按 meta charset 解码。
5. 微信对出口 IP 有间歇性限流, 偶发反爬重试几次即可; 连续失败则如实报错。

## 红线 / Rules

- 只抓取用户给出的**单篇**文章链接, 不做批量爬取。
- 遵守反爬: 失败时如实报错 (限流/文章被删/链接无效), 不编造内容。
- 抓到的正文只按用户要求使用 (转存/总结/翻译), 不做二次分发。
