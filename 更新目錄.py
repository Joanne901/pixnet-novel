# -*- coding: utf-8 -*-
"""抓取痞客邦部落格所有分類的文章，產生網頁目錄 index.html。

分類清單直接讀部落格側邊欄，作者開新分類時會自動出現。
GitHub Actions 每天會自動執行一次。
"""
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BLOG = "https://lance530125.pixnet.net/blog"

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "index.html"
TEMPLATE = HERE / "template.html"
TAIPEI = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def parse_page(page_html, host):
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
            "title": text(title.group(1)),
            "date": published,
            "url": f"https://{host}/blog/posts/{post_id}",
        })
    return posts


def last_page(page_html, cat_url):
    pages = [int(p) for p in re.findall(re.escape(cat_url) + r"\?page=(\d+)", page_html)]
    return max(pages, default=1)


def scrape_category(cat_url):
    host = re.match(r"https?://([^/]+)", cat_url).group(1)
    first = fetch(cat_url)
    total = last_page(first, cat_url)
    posts = parse_page(first, host)
    for page in range(2, total + 1):
        time.sleep(0.5)
        posts += parse_page(fetch(f"{cat_url}?page={page}"), host)

    seen, unique = set(), []
    for p in posts:
        if p["id"] not in seen:
            seen.add(p["id"])
            unique.append(p)
    unique.sort(key=lambda p: (p["date"], p["id"]))
    return unique, first


def list_categories():
    """讀部落格側邊欄的分類，回傳 [(資料夾名稱, 分類)]。"""
    data = json.loads(fetch(BLOG + "/get-widget-data?name=pixCategory"))["data"]
    result = []
    for item in data:
        if item["type"] == "folder":
            folder = item["name"].strip("【】[] ")
            result += [(folder, c) for c in item["children"] if c["type"] == "category"]
        elif item["type"] == "category":
            result.append(("其他", item))
    return result


def main():
    novels, notice = [], ""
    for folder, cat in list_categories():
        cat_url = cat["url"].split("?")[0].rstrip("/")
        posts, first_html = scrape_category(cat_url)
        print(f"  [{folder}] {cat['name']}：{len(posts)} 篇")
        if not notice:
            m = re.search(r'id="spotlight"[^>]*>(.*?)</div>', first_html, re.S)
            notice = text(m.group(1)) if m else ""
        if posts:
            novels.append({
                "group": folder,
                "name": cat["name"].strip(),
                "url": cat_url,
                "posts": posts,
            })

    def build(updated):
        data = {"updated": updated, "notice": notice, "novels": novels}
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
