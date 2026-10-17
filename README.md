# wechat-article-fetch

把**单篇**微信公众号文章链接 (`mp.weixin.qq.com/s/...`) 原样抓成 Markdown / JSON:
标题、公众号名称、作者、发布时间、正文、图片列表。**不用付费 API, 不用登录。**

Fetch a **single** WeChat Official Account article into Markdown / JSON: title,
account name, author, publish date, body text and image list. No paid API, no login.

## 安装 / Install

```bash
git clone https://github.com/lhylvsea/wechat-article-fetch.git
cd wechat-article-fetch
pip install requests beautifulsoup4
```

## 用法 / Usage

```bash
cd scripts
# JSON 输出到 stdout
python3 fetch.py "https://mp.weixin.qq.com/s/xxxx"

# 纯 Markdown 输出 (带 YAML frontmatter)
python3 fetch.py "https://mp.weixin.qq.com/s/xxxx" --markdown

# 结果写入目录
python3 fetch.py "https://mp.weixin.qq.com/s/xxxx" --markdown --out ./out
```

输出字段 / Output fields: `title / author / account / date / url / images / markdown`

## 原理 / How it works

- 必须用 MicroMessenger 的 UA, 否则微信服务端返回反爬页 (脚本内置 3 个 UA, 被挡时自动轮换重试)。
- 正文在 `#js_content` div 里; 图片真实 URL 在 img 的 `data-src` 属性。
- 按页面声明 charset 解码 (`requests` 的 `apparent_encoding` 常猜错导致乱码)。

详见 [SKILL.md](SKILL.md)。

## 红线 / Rules

- 只抓取用户给出的**单篇**文章链接, 不做批量爬取。
- 失败时如实报错 (限流 / 文章被删 / 链接无效), 不编造内容。
