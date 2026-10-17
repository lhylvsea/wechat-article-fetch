#!/usr/bin/env python3
"""
微信公众号文章抓取工具 (wechat-article-fetch)

用法:
    python3 fetch.py "<文章URL>" [--markdown] [--out DIR]

输出默认 JSON: {"title","author","account","date","url","markdown","images"}
加 --markdown 输出纯 Markdown（含 frontmatter）。
加 --out DIR 时把结果写入文件（JSON 存 article.json / Markdown 存 article.md）。

原理:
- 微信服务端对非微信客户端 UA 返回反爬页, 必须用 MicroMessenger 的 UA
- 正文在 HTML 的 #js_content 里; 图片真实 URL 在 img 的 data-src 属性
- 标题/公众号/发布时间在页面内嵌 JS 变量和 HTML 里

原则: 只抓取用户给出的单篇文章链接, 不批量爬取; 被限流时如实报错。
"""

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

# 微信服务端对非微信客户端 UA 返回反爬页, 必须冒充 MicroMessenger。
# 微信对出口 IP 有间歇性限流, 被反爬页挡住时换 UA 重试几次一般能过。
WX_UAS = [
    # iOS 微信
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.40",
    # Android 微信
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Build/TQ3A.230605.012) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/114.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.38",
    # Mac 微信
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/17.0 "
    "Safari/537.36 MicroMessenger/3.7.0",
]

# 反爬/异常页特征 (注意: "已被删除"/"违规" 等词在正常页面的 JS 模板里也会出现, 不能用)
_BLOCK_HINTS = ("环境异常", "操作频繁", "请在微信客户端打开")


def fetch_page(url: str, retries: int = 4, timeout: int = 60) -> str:
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL 必须以 http(s):// 开头")
    if "mp.weixin.qq.com" not in url:
        raise ValueError("只支持 mp.weixin.qq.com 域名下的公众号文章链接")
    last_err = "未知"
    for attempt in range(retries):
        ua = WX_UAS[attempt % len(WX_UAS)]
        try:
            # 微信页面常达 3MB+, 出口慢时 20s 不够, 放宽到 60s
            r = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
        except requests.RequestException as e:
            last_err = f"网络请求失败: {e}"
            time.sleep(2)
            continue
        if r.status_code != 200:
            last_err = f"HTTP {r.status_code}"
            time.sleep(2)
            continue
        # 微信页面声明 charset=utf-8; requests 的 apparent_encoding 经常猜错 (如 MacRoman)
        m = re.search(rb'charset=["\']?([\w-]+)', r.content[:4000], re.I)
        encoding = (m.group(1).decode("ascii", "ignore") if m else "utf-8")
        text = r.content.decode(encoding, "replace")
        if "js_content" in text and not any(h in text for h in _BLOCK_HINTS):
            return text
        # 反爬页或空页: 换个 UA 再试
        last_err = "微信返回了反爬/异常页 (疑似限流), 重试中…"
        time.sleep(3)
    raise RuntimeError(
        f"抓取失败: 连续 {retries} 次请求都被微信挡回 ({last_err})。稍后再试。"
    )


def _js_var(text: str, name: str) -> str:
    """从页面内嵌 JS 提取 var name = "..."/'...' 的值"""
    m = re.search(
        r'var\s+' + re.escape(name) + r"""\s*=\s*(['"])((?:(?!\1).)*)\1""",
        text,
        re.S,
    )
    if not m:
        return ""
    v = m.group(2)
    # 手工还原 JS 转义, 不用 unicode_escape (会把 UTF-8 文本搞成乱码)
    v = v.replace("\\/", "/").replace("\\n", "\n").replace("\\t", "\t")
    v = v.replace("\\\\", "\x00").replace('\\"', '"').replace("\\'", "'")
    v = v.replace("\x00", "\\")
    return html.unescape(v).strip()


def _decode_hex_escapes(text: str) -> str:
    """把 \\x22 这类字面转义还原成字符 (公众号名常藏在这种 JS 字符串里)"""
    return re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda m: chr(int(m.group(1), 16)),
        text,
    )


def extract_meta(text: str) -> dict:
    soup = BeautifulSoup(text, "html.parser")
    decoded = _decode_hex_escapes(text)

    def og(prop):
        tag = soup.find("meta", attrs={"property": prop})
        return (tag.get("content", "") if tag else "").strip()

    # 标题: #activity-name > .js_title_inner 优先, 其次 JS 变量, 其次 og:title
    title = ""
    h1 = soup.select_one("#activity-name")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        m = re.search(r"""msg_title\s*=\s*(['"])((?:(?!\1).)*)\1""", text, re.S)
        if m:
            title = html.unescape(m.group(2)).strip()
    if not title:
        title = og("og:title")

    # 作者
    author = _js_var(text, "author")

    # 公众号名称: mpprofile 的 data-nickname (在 \x 转义的 JS 字符串里)
    account = ""
    m = re.search(r'data-nickname="([^"]+)"', decoded)
    if m:
        account = m.group(1).strip()
    if not account:
        for sel in (".rich_media_meta_nickname", ".profile_nickname"):
            tag = soup.select_one(sel)
            if tag and tag.get_text(strip=True):
                account = tag.get_text(strip=True)
                break

    # 发布时间: var ct (10 位时间戳) 优先, 其次页面内 URL 编码 JSON 里的 publish_time
    date = ""
    ct = _js_var(text, "ct")
    ts = ct if ct.isdigit() else ""
    if not ts:
        m = re.search(r'publish_time%22%3A(\d{10})', text)
        if m:
            ts = m.group(1)
    if not ts:
        m = re.search(r'"publish_time"\s*:\s*(\d{10})', urllib.parse.unquote(text))
        if m:
            ts = m.group(1)
    if ts:
        date = datetime.fromtimestamp(
            int(ts), tz=timezone(timedelta(hours=8))
        ).strftime("%Y-%m-%d %H:%M")
    if not date:
        tag = soup.select_one("#publish_time")
        if tag:
            date = tag.get_text(strip=True)

    return {"title": title, "author": author, "account": account, "date": date}


def _img_url(tag: Tag) -> str:
    # 微信文章图片真实 URL 在 data-src, 兼容 data-srcset 取第一张
    url = tag.get("data-src") or tag.get("src") or ""
    if not url and tag.get("data-srcset"):
        url = tag["data-srcset"].split(",")[0].split()[0]
    if url.startswith("data:"):  # 透明占位图等
        return ""
    return url.strip()


def node_to_md(node, images: list, name: str = "") -> str:
    parts = []
    for child in node.children:
        if isinstance(child, NavigableString):
            t = str(child).strip()
            if t:
                parts.append(t)
            continue
        if not isinstance(child, Tag):
            continue
        cname = child.name
        if cname == "img":
            url = _img_url(child)
            if url:
                images.append(url)
                alt = child.get("alt", "") or f"图片{len(images)}"
                parts.append(f"\n\n![{alt}]({url})\n\n")
        elif cname == "br":
            parts.append("\n")
        elif cname in ("h1", "h2", "h3"):
            t = child.get_text(strip=True)
            if t:
                level = {"h1": "#", "h2": "##", "h3": "###"}[cname]
                parts.append(f"\n\n{level} {t}\n\n")
        elif cname == "blockquote":
            t = child.get_text("\n", strip=True)
            if t:
                quoted = "\n".join("> " + line for line in t.split("\n"))
                parts.append(f"\n\n{quoted}\n\n")
        elif cname == "li":
            t = child.get_text(strip=True)
            if t:
                parts.append(f"\n- {t}")
        elif cname in ("ol", "ul"):
            parts.append("\n" + node_to_md(child, images, cname))
        elif cname == "table":
            parts.append("\n\n" + node_to_md(child, images, cname) + "\n\n")
        elif cname in ("tr",):
            row = " | ".join(
                c.get_text(strip=True) for c in child.find_all(["td", "th"])
            )
            if row:
                parts.append(f"\n| {row} |")
        else:
            parts.append(node_to_md(child, images, cname))
    sep = "\n" if name in ("p", "section", "div") else ""
    inner = "".join(parts)
    return f"{sep}{inner}{sep}" if sep else inner


def extract_content(text: str) -> tuple[str, list]:
    soup = BeautifulSoup(text, "html.parser")
    content = soup.find(id="js_content")
    if content is None:
        raise RuntimeError("未找到正文容器 #js_content")
    images = []
    md = node_to_md(content, images)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()  # 3+ 换行压成两个
    return md, images


def main():
    ap = argparse.ArgumentParser(description="微信公众号文章抓取")
    ap.add_argument("url", help="公众号文章链接 (mp.weixin.qq.com)")
    ap.add_argument("--markdown", action="store_true",
                    help="输出纯 Markdown 而非 JSON")
    ap.add_argument("--out", help="结果写入目录 (默认只打印到 stdout)")
    args = ap.parse_args()

    try:
        text = fetch_page(args.url)
        meta = extract_meta(text)
        md, images = extract_content(text)
    except (ValueError, RuntimeError) as e:
        print(f"抓取失败: {e}", file=sys.stderr)
        sys.exit(1)

    if not meta["title"] and not md:
        print("抓取失败: 页面无标题无正文, 可能是文章已被删除或链接无效",
              file=sys.stderr)
        sys.exit(1)

    data = {
        "title": meta["title"],
        "author": meta["author"],
        "account": meta["account"],
        "date": meta["date"],
        "url": args.url,
        "images": [{"index": i + 1, "url": u} for i, u in enumerate(images)],
        "markdown": md,
    }

    if args.markdown:
        fm = (
            "---\n"
            f"title: \"{meta['title']}\"\n"
            f"account: \"{meta['account']}\"\n"
            f"author: \"{meta['author']}\"\n"
            f"date: \"{meta['date']}\"\n"
            f"source: {args.url}\n"
            "---\n\n"
        )
        output = fm + md + "\n"
        fname = "article.md"
    else:
        output = json.dumps(data, ensure_ascii=False, indent=2)
        fname = "article.json"

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        path = os.path.join(args.out, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"已保存: {path} (图片 {len(images)} 张, 正文 {len(md)} 字)",
              file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
