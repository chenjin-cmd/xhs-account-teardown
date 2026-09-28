#!/usr/bin/env python3
"""抓取小红书账号主页（匿名 SSR）：用户信息 + 第一页笔记列表 + 封面图下载。

用法:
    python3 fetch_profile.py "<账号链接或user_id>" [-o 输出目录] [--token <xsec_token>]

说明:
    - 手机 UA 请求 /user/profile/<id> ，解析 window.__INITIAL_STATE__ 的 profile 段。
    - 匿名上限: 第一页笔记(<=8篇) 的 id/标题/类型/赞/藏/评 + 封面图 CDN 直链。
    - 笔记详情(正文/全图)匿名不可得, 需笔记级 xsec_token, 见 fetch_note.py。
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


def parse_state(html: str):
    m = re.search(r"__INITIAL_STATE__=(.*?)</script>", html, re.DOTALL)
    if not m:
        return None
    raw = m.group(1).strip().rstrip(";")
    raw = re.sub(r"\bundefined\b", "null", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="账号链接或 user_id")
    ap.add_argument("-o", "--out", default=".", help="输出目录")
    ap.add_argument("--token", default=None, help="xsec_token(链接里带则自动提取)")
    args = ap.parse_args()

    target = args.target.strip()
    user_id, token, source = None, args.token, "pc_user"
    if target.startswith("http"):
        u = urlparse(target)
        m = re.search(r"/user/profile/([0-9a-fA-F]{24})", u.path)
        if not m:
            sys.exit(f"[error] 链接中未找到 /user/profile/<24位id>: {target}")
        user_id = m.group(1)
        q = parse_qs(u.query)
        token = token or (q.get("xsec_token", [None])[0])
        source = q.get("xsec_source", ["pc_user"])[0]
    else:
        user_id = target

    out = Path(args.out)
    (out / "covers").mkdir(parents=True, exist_ok=True)

    qs = f"?xsec_token={token}&xsec_source={source}" if token else ""
    url = f"https://www.xiaohongshu.com/user/profile/{user_id}{qs}"
    html = fetch_html(url)
    state = parse_state(html)
    if state is None or "profile" not in state:
        sys.exit("[error] 主页 SSR 解析失败(可能触发风控或链接失效)。勿无限重试。")

    prof = state["profile"]
    ui = prof.get("userInfo", {})
    profile = {
        "user_id": user_id,
        "nickname": ui.get("nickname"),
        "red_id": ui.get("redId"),
        "desc": ui.get("desc"),
        "follows": ui.get("follows"),
        "fans": ui.get("fans"),
        "like_and_collect": ui.get("likeAndCollect"),
        "collections": [c.get("name") for c in prof.get("noteCollectionList", [])],
    }
    notes = []
    for i, n in enumerate(prof.get("noteData", []), 1):
        cover = (n.get("cover") or {}).get("url", "")
        if cover.startswith("//"):
            cover = "https:" + cover
        notes.append({
            "idx": i,
            "id": n.get("id"),
            "title": n.get("title"),
            "type": n.get("type"),
            "likes": n.get("likes"),
            "collects": n.get("collects"),
            "comments": n.get("comments"),
            "sticky": bool(n.get("sticky")),
            "cover_url": cover,
            "cover_file": f"covers/cover{i}.jpg",
        })

    (out / "profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "notes_list.json").write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")

    for n in notes:  # 串行限速下载封面
        if n["cover_url"]:
            subprocess.run(["curl", "-sL", "--max-time", "25", "-o", str(out / n["cover_file"]), n["cover_url"]],
                           capture_output=True)

    print(f"[ok] {profile['nickname']} | 粉丝 {profile['fans']} | 赞藏 {profile['like_and_collect']}")
    print(f"[ok] 笔记 {len(notes)} 篇(主页第一页上限), 封面已存 {out/'covers'}")
    for n in notes:
        print(f"  {n['idx']}. [{n['type']}] {n['title']}  赞{n['likes']} 藏{n['collects']} 评{n['comments']}")
    print("[note] 详情/全文需笔记级 xsec_token, 用 fetch_note.py + 带 token 的笔记链接")


if __name__ == "__main__":
    main()
