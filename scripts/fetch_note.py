#!/usr/bin/env python3
"""抓取单条小红书笔记详情（需笔记级 xsec_token）：正文/标签/互动/全部图片。

用法:
    python3 fetch_note.py "<带xsec_token的笔记链接>" [-o 输出目录]

说明:
    - 手机 UA 请求 /discovery/item/<noteId>?xsec_token=..&xsec_source=..
    - 解析 __INITIAL_STATE__ 的 noteData.data.noteData。
    - token 与笔记绑定: 缺/错 token 时 SSR 返回空 noteData, 脚本会明确报错。
    - token 来源: 登录态浏览器打开笔记页, 地址栏整链复制(含 xsec_token 参数)。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1")


def fetch_html(url: str) -> str:
    r = subprocess.run(["curl", "-sL", "--max-time", "25", "-H", f"User-Agent: {MOBILE_UA}", url],
                       capture_output=True, text=True)
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="带 xsec_token 的笔记链接")
    ap.add_argument("-o", "--out", default=".", help="输出目录")
    args = ap.parse_args()

    u = urlparse(args.url)
    m = re.search(r"/(?:discovery/item|explore)/([0-9a-fA-F]{24})", u.path)
    if not m:
        sys.exit("[error] 链接中未找到 24 位 noteId（/explore/ 或 /discovery/item/ 路由）")
    note_id = m.group(1)
    q = parse_qs(u.query)
    token = q.get("xsec_token", [None])[0]
    source = q.get("xsec_source", ["pc_user"])[0]
    if not token:
        sys.exit("[error] 链接缺 xsec_token。匿名抓不到笔记详情；请用登录态浏览器地址栏整链复制。")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    url = f"https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_token={token}&xsec_source={source}"
    html = fetch_html(url)
    mm = re.search(r"__INITIAL_STATE__=(.*?)</script>", html, re.DOTALL)
    if not mm:
        sys.exit("[error] 页面无 SSR state（路由无效或风控）。勿无限重试。")
    raw = mm.group(1).strip().rstrip(";")
    raw = re.sub(r"\bundefined\b", "null", raw)
    state = json.loads(raw)
    nd = (state.get("noteData") or {}).get("data", {}).get("noteData") or {}
    if not nd.get("noteId"):
        sys.exit("[error] noteData 为空: xsec_token 与该笔记不匹配或已失效。请重新复制带 token 的链接。")

    inter = nd.get("interactInfo", {})
    meta = {
        "note_id": nd.get("noteId"),
        "title": nd.get("title"),
        "type": nd.get("type"),
        "author": (nd.get("user") or {}).get("nickName"),
        "author_id": (nd.get("user") or {}).get("userId"),
        "desc": nd.get("desc"),
        "tags": [t.get("name") for t in nd.get("tagList", [])],
        "interact": {k: inter.get(k) for k in ("likedCount", "collectedCount", "commentCount", "shareCount")},
        "time": nd.get("time"),
        "last_update": nd.get("lastUpdateTime"),
    }
    imgs = []
    for i, im in enumerate(nd.get("imageList", []), 1):
        url_i = im.get("url") or ""
        if url_i.startswith("//"):
            url_i = "https:" + url_i
        imgs.append({"idx": i, "url": url_i, "file": f"img{i}.jpg",
                     "w": im.get("width"), "h": im.get("height")})

    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "desc.md").write_text(f"# {meta['title']}\n\n{meta['desc']}\n\n标签: " +
                                 " ".join("#" + t for t in meta["tags"]) + "\n", encoding="utf-8")
    for im in imgs:  # 串行限速下载
        if im["url"]:
            subprocess.run(["curl", "-sL", "--max-time", "30", "-o", str(out / im["file"]), im["url"]],
                           capture_output=True)

    print(f"[ok] {meta['title']} | {meta['author']} | 图 {len(imgs)} 张")
    print(f"[ok] 互动: 赞{inter.get('likedCount')} 藏{inter.get('collectedCount')} 评{inter.get('commentCount')} 转{inter.get('shareCount')}")
    print(f"[ok] 正文与图片已存: {out}")


if __name__ == "__main__":
    main()
