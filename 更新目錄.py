# -*- coding: utf-8 -*-
"""抓取痞客邦分類裡的所有文章，產生網頁目錄 index.html。

GitHub Actions 每天會自動執行一次；要追其他小說，把分類網址加進 CATEGORIES 就好。
"""
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CATEGORIES = [
    "https://lance530125.pixnet.net/blog/categories/8002812455",
]

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "index.html"
TAIPEI = timezone(timedelta(hours=8))
TEMPLATE = HERE / "template.html"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_page(page_html):
    posts = []
    blocks = re.split(r'<div class="article" id="article-', page_html)[1:]
    for block in blocks:
        post_id = re.match(r"(\d+)", block).group(1)
        title = re.search(r'<li class="title".*?<a[^>]*>(.*?)</a>', block, re.S)
        if not title:
            continue

        def span(name):
            m = re.search(r'<span class="%s">([^<]*)</span>' % name, block)
            return m.group(1).strip() if m else ""

        try:
            hh, mm = (span("time") or "00:00").split(":")
            published = datetime(int(span("year")), MONTHS[span("month")],
                                 int(span("date")), int(hh), int(mm))
            published = published.strftime("%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            published = ""
        posts.append({
            "id": post_id,
            "title": html.unescape(re.sub(r"<[^>]+>", "", title.group(1))).strip(),
            "date": published,
            "url": f"https://{{host}}/blog/posts/{post_id}",
        })
    return posts


def last_page(page_html, cat_url):
    pages = [int(p) for p in re.findall(re.escape(cat_url) + r"\?page=(\d+)", page_html)]
    return max(pages, default=1)


def chapter_no(title):
    m = re.search(r"(\d+)\s*[：:]", title) or re.search(r"(\d+)", title)
    return int(m.group(1)) if m else None


def scrape(cat_url):
    host = re.match(r"https?://([^/]+)", cat_url).group(1)
    first = fetch(cat_url)
    name_m = re.search(r'id="spotlight"[^>]*>(.*?)</div>', first, re.S)
    cat_name = None
    for m in re.finditer(re.escape(cat_url) + r'"[^>]*>([^<]+)<', first):
        text = m.group(1).strip()
        if text and not text.isdigit() and text not in ("»", "«", "最後一頁", "第一頁"):
            cat_name = html.unescape(text)
            break

    total = last_page(first, cat_url)
    posts = parse_page(first)
    for page in range(2, total + 1):
        print(f"  讀取第 {page}/{total} 頁…")
        time.sleep(0.5)
        posts += parse_page(fetch(f"{cat_url}?page={page}"))

    seen, unique = set(), []
    for p in posts:
        if p["id"] not in seen:
            seen.add(p["id"])
            p["url"] = p["url"].replace("{host}", host)
            p["no"] = chapter_no(p["title"])
            unique.append(p)
    unique.sort(key=lambda p: (p["date"], p["no"] or 0, p["id"]))

    notice = ""
    if name_m:
        notice = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip()
    return {
        "name": cat_name or "小說",
        "url": cat_url,
        "notice": notice,
        "posts": unique,
    }


def main():
    novels = []
    for cat_url in CATEGORIES:
        cat_url = cat_url.split("?")[0].rstrip("/")
        print(f"抓取 {cat_url}")
        novel = scrape(cat_url)
        print(f"  《{novel['name']}》共 {len(novel['posts'])} 篇")
        novels.append(novel)

    def build(updated):
        data = {"updated": updated, "novels": novels}
        payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        return TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)

    # 章節沒變就不重寫，避免每天都產生一個只改了時間的 commit
    if OUTPUT.exists():
        old = OUTPUT.read_text(encoding="utf-8")
        m = re.search(r'"updated": "([^"]*)"', old)
        if m and build(m.group(1)) == old:
            print("沒有新章節，目錄不用更新")
            return

    OUTPUT.write_text(build(datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M")),
                      encoding="utf-8", newline="\n")
    print(f"完成：{OUTPUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"更新失敗：{exc}")
        sys.exit(1)
