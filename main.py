# -*- coding: utf-8 -*-

import asyncio
import csv
import httpx
import json
import os
import re
import sys
import time
from datetime import datetime
from math import ceil
from typing import Any, Dict, List, Optional, Tuple
from tqdm import tqdm

from login import (
    login_instagram,
    read_cookie_json,
    write_cookie_json,
    cookie_json_valid,
    prompt_cookie_interactive,
    create_session_from_cookie_input,
    load_env_config,
    save_to_env_file,
    LoginError,
)

PARENT_QUERY_HASH = "97b41c52301f77ce508f55e66d17620e"
CHILD_QUERY_HASH = "51fdd02b67508306ad4484ff574a0b62"
COMMENTS_PER_PAGE = 50

class ScrapeError(Exception):
    pass

class AuthenticationError(ScrapeError):
    pass

class RateLimitError(ScrapeError):
    pass

def extract_shortcode(url: str) -> Optional[str]:
    """
    Extract the Instagram shortcode from various URL formats or raw shortcode input.
    Supports:
      - https://www.instagram.com/reel/SHORTCODE/
      - https://www.instagram.com/reels/SHORTCODE/
      - https://www.instagram.com/p/SHORTCODE/
      - https://www.instagram.com/tv/SHORTCODE/
      - https://www.instagram.com/share/reel/SHORTCODE/
      - Raw shortcode string directly
    """
    url = url.strip()
    if not url:
        return None
    # If it is formatted like a URL (contains / or .), extract shortcode via path
    if "/" in url or "." in url:
        m = re.search(r"(?:reel|reels|p|tv)/([^/?#&]+)", url)
        return m.group(1) if m else None
    # Direct shortcode input (typically 9 to 15 alphanumeric characters, underscores, hyphens)
    if re.fullmatch(r"[A-Za-z0-9_-]{9,15}", url):
        return url
    return None

def cookies_string(sessionid: str, csrftoken: str, mid: str, dsuserid: str) -> str:
    return f"sessionid={sessionid}; ds_user_id={dsuserid}; csrftoken={csrftoken}; mid={mid}"

def build_headers(shortcode: str, cookies_str: str) -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "X-IG-App-ID": "936619743392459",
        "X-ASBD-ID": "129477",
        "Referer": f"https://www.instagram.com/reel/{shortcode}/",
        "Cookie": cookies_str,
    }

async def graphql_request(client: httpx.AsyncClient, query_hash: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    var_str = json.dumps(variables, separators=(",", ":"))
    url = "https://www.instagram.com/graphql/query/"
    params = {"query_hash": query_hash, "variables": var_str}
    r = await client.get(url, params=params, follow_redirects=False, timeout=25)

    if r.status_code in (301, 302, 303, 307, 308):
        raise AuthenticationError("Redirected ke halaman login (sesi kedaluwarsa atau invalid).")
    if r.status_code == 401:
        raise AuthenticationError("Unauthorized (401) - Cookie sessionid kedaluwarsa atau tidak valid.")
    if r.status_code == 429:
        raise RateLimitError("HTTP 429: Too Many Requests (Instagram rate limit tercapai).")
    if r.status_code != 200:
        text = r.text[:200] if r.text else f"HTTP {r.status_code}"
        raise ScrapeError(f"HTTP {r.status_code}: {text}")

    try:
        data = r.json()
    except Exception:
        raise ScrapeError("Gagal mengurai respon JSON dari GraphQL Instagram.")

    if isinstance(data, dict):
        if data.get("require_login") or data.get("message") == "checkpoint_required":
            raise AuthenticationError(f"Instagram meminta login / checkpoint: {data.get('message')}")
        if data.get("status") == "fail":
            msg = data.get("message", "Unknown error")
            if "wait a few minutes" in msg.lower() or "rate" in msg.lower():
                raise RateLimitError(f"Rate limited oleh Instagram: {msg}")
            raise ScrapeError(f"Instagram GraphQL gagal: {msg}")

    return data

async def process_comment_node(
    client: httpx.AsyncClient,
    node: Dict[str, Any],
    include_replies: bool,
    limiter: "RateLimiter",
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Parse a single parent comment node, including its nested reply comments if requested.
    Returns (flat_lines, struct_item).
    """
    comment_id = str(node.get("id", ""))
    text = node.get("text", "") or ""
    clean_text = " ".join(text.splitlines())
    user = node.get("owner", {}).get("username", "")
    created_at = node.get("created_at")

    flat_lines: List[str] = [f"{user}: {clean_text}"]
    replies_struct: List[Dict[str, Any]] = []

    if include_replies:
        threaded = node.get("edge_threaded_comments", {})
        if isinstance(threaded, dict):
            expected_replies = threaded.get("count", 0)
            initial_edges = threaded.get("edges", [])
            page_info = threaded.get("page_info", {})

            for e in initial_edges:
                r_node = e.get("node", {})
                r_text = r_node.get("text", "") or ""
                r_clean = " ".join(r_text.splitlines())
                r_user = r_node.get("owner", {}).get("username", "")
                r_time = r_node.get("created_at")
                r_id = str(r_node.get("id", ""))
                flat_lines.append(f"  ↳ {r_user}: {r_clean}")
                replies_struct.append({
                    "id": r_id,
                    "username": r_user,
                    "text": r_text,
                    "created_at": r_time,
                })

            has_next = page_info.get("has_next_page", False)
            cursor = page_info.get("end_cursor")

            # Fetch remaining replies if not all were included in the parent payload
            if has_next and cursor and comment_id and len(replies_struct) < expected_replies:
                tries = 0
                while has_next and cursor:
                    await limiter.wait()
                    vars_child = {"comment_id": comment_id, "first": COMMENTS_PER_PAGE, "after": cursor}
                    try:
                        res = await graphql_request(client, CHILD_QUERY_HASH, vars_child)
                        sub_thread = res.get("data", {}).get("comment", {}).get("edge_threaded_comments", {})
                        sub_edges = sub_thread.get("edges", [])
                        for e in sub_edges:
                            r_node = e.get("node", {})
                            r_text = r_node.get("text", "") or ""
                            r_clean = " ".join(r_text.splitlines())
                            r_user = r_node.get("owner", {}).get("username", "")
                            r_time = r_node.get("created_at")
                            r_id = str(r_node.get("id", ""))
                            flat_lines.append(f"  ↳ {r_user}: {r_clean}")
                            replies_struct.append({
                                "id": r_id,
                                "username": r_user,
                                "text": r_text,
                                "created_at": r_time,
                            })

                        sub_pinfo = sub_thread.get("page_info", {})
                        has_next = sub_pinfo.get("has_next_page", False)
                        cursor = sub_pinfo.get("end_cursor")
                    except Exception:
                        break

    struct_item = {
        "id": comment_id,
        "username": user,
        "text": text,
        "created_at": created_at,
        "reply_count": len(replies_struct),
        "replies": replies_struct,
    }

    return flat_lines, struct_item

async def parse_parent_comments(
    client: httpx.AsyncClient,
    data: Dict[str, Any],
    include_replies: bool,
    limiter: "RateLimiter",
) -> Tuple[List[str], Dict[str, Any], List[Dict[str, Any]]]:
    try:
        media = data["data"]["shortcode_media"]
        if not media:
            raise ScrapeError("Media tidak ditemukan. Kemungkinan postingan telah dihapus, shortcode salah, atau akun di-private.")
        edge_info = media["edge_media_to_parent_comment"]
        edges = edge_info["edges"]
        page_info = edge_info["page_info"]
    except KeyError:
        raise ScrapeError("Struktur GraphQL tidak sesuai; data komentar tidak ditemukan.")

    flat: List[str] = []
    struct: List[Dict[str, Any]] = []

    for edge in edges:
        node = edge.get("node", {})
        node_flat, node_struct = await process_comment_node(client, node, include_replies, limiter)
        flat.extend(node_flat)
        struct.append(node_struct)

    return flat, page_info, struct

def get_counts_from_first_page(data: dict) -> int:
    try:
        media = data["data"]["shortcode_media"]
        count = media["edge_media_to_parent_comment"].get("count")
        if isinstance(count, int) and count >= 0:
            return count
    except Exception:
        pass
    return 0

def format_timestamp(ts: Any) -> str:
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return ""

def write_outputs(
    shortcode: str,
    comments_flat: List[str],
    comments_struct: List[Dict[str, Any]],
    output_base_dir: str = "download_comments",
) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_folder_name = f"{shortcode}_{timestamp}"
    session_dir = os.path.join(output_base_dir, session_folder_name)
    os.makedirs(session_dir, exist_ok=True)

    txt_path = os.path.join(session_dir, f"{shortcode}_comments.txt")
    json_path = os.path.join(session_dir, f"{shortcode}_comments.json")
    csv_path = os.path.join(session_dir, f"{shortcode}_comments.csv")

    # 1. Tulis TXT
    tmp_txt = txt_path + ".tmp"
    with open(tmp_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(comments_flat))
    os.replace(tmp_txt, txt_path)

    # 2. Tulis JSON
    total_parents = len(comments_struct)
    total_replies = sum(len(c.get("replies", [])) for c in comments_struct)
    total_all = total_parents + total_replies

    tmp_json = json_path + ".tmp"
    payload = {
        "generated_at": int(time.time()),
        "shortcode": shortcode,
        "parent_comment_count": total_parents,
        "reply_comment_count": total_replies,
        "total_comments": total_all,
        "comments": comments_struct,
    }
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_json, json_path)

    # 3. Tulis CSV
    tmp_csv = csv_path + ".tmp"
    csv_fieldnames = [
        "comment_id",
        "comment_type",
        "parent_id",
        "username",
        "text",
        "reply_to_username",
        "created_at",
        "created_time",
        "reply_count",
    ]
    with open(tmp_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fieldnames)
        writer.writeheader()
        for parent in comments_struct:
            p_id = str(parent.get("id", ""))
            p_user = parent.get("username", "")
            p_text = parent.get("text", "")
            p_created = parent.get("created_at")
            replies = parent.get("replies", [])

            # Baris komentar utama (parent)
            writer.writerow({
                "comment_id": p_id,
                "comment_type": "parent",
                "parent_id": "",
                "username": p_user,
                "text": p_text,
                "reply_to_username": "",
                "created_at": p_created or "",
                "created_time": format_timestamp(p_created),
                "reply_count": len(replies),
            })

            # Baris setiap balasan (replies)
            for reply in replies:
                r_id = str(reply.get("id", ""))
                r_user = reply.get("username", "")
                r_text = reply.get("text", "")
                r_created = reply.get("created_at")
                writer.writerow({
                    "comment_id": r_id,
                    "comment_type": "reply",
                    "parent_id": p_id,
                    "username": r_user,
                    "text": r_text,
                    "reply_to_username": p_user,
                    "created_at": r_created or "",
                    "created_time": format_timestamp(r_created),
                    "reply_count": 0,
                })
    os.replace(tmp_csv, csv_path)

    print(f"\n📁 Sesi scraping tersimpan di folder: {session_dir}")
    print(f"   ├─ CSV  : {csv_path}")
    print(f"   ├─ JSON : {json_path}")
    print(f"   └─ TXT  : {txt_path}")
    print(f"\n📊 Total: {total_parents} komentar utama & {total_replies} balasan (total {total_all} komentar)")

    return session_dir

async def refresh_cookies_interactive(shortcode: str) -> Tuple[str, str, str, str, Dict[str, str]]:
    print("\n⚠️ Cookie kedaluwarsa atau tidak valid. Silakan perbarui cookie.")
    sessionid, csrftoken, mid, dsuserid = prompt_cookie_interactive()
    headers = build_headers(shortcode, cookies_string(sessionid, csrftoken, mid, dsuserid))
    return sessionid, csrftoken, mid, dsuserid, headers

def headers_from_store(shortcode: str, fallback: Tuple[str, str, str, str]) -> Dict[str, str]:
    dj = read_cookie_json()
    if cookie_json_valid(dj):
        c = dj["cookies"]
        ck = cookies_string(c["sessionid"], c["csrftoken"], c["mid"], c["ds_user_id"])
    else:
        ck = cookies_string(*fallback)
    return build_headers(shortcode, ck)

class RateLimiter:
    def __init__(self, rps: float):
        self.rps = max(0.1, float(rps))
        self.interval = 1.0 / self.rps
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.perf_counter()
            delta = now - self._last
            if delta < self.interval:
                await asyncio.sleep(self.interval - delta)
            self._last = time.perf_counter()

async def fetch_all_pages(
    shortcode: str,
    session_tuple: Tuple[str, str, str, str],
    rps: float,
    include_replies: bool = True,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    async with httpx.AsyncClient(http2=True, timeout=httpx.Timeout(25.0, connect=10.0), limits=limits) as client:
        current_session = session_tuple
        headers = headers_from_store(shortcode, current_session)
        client.headers.update(headers)

        limiter = RateLimiter(rps)
        variables = {"shortcode": shortcode, "first": COMMENTS_PER_PAGE}

        await limiter.wait()
        try:
            data = await graphql_request(client, PARENT_QUERY_HASH, variables)
        except AuthenticationError:
            si, ct, m, du, headers = await refresh_cookies_interactive(shortcode)
            current_session = (si, ct, m, du)
            client.headers.update(headers)
            await limiter.wait()
            data = await graphql_request(client, PARENT_QUERY_HASH, variables)

        flat, page_info, struct = await parse_parent_comments(client, data, include_replies, limiter)
        total_count = get_counts_from_first_page(data) or len(struct)
        total_pages = max(1, ceil(total_count / COMMENTS_PER_PAGE))

        all_flat: List[str] = list(flat)
        all_struct: List[Dict[str, Any]] = list(struct)

        has_next = page_info.get("has_next_page", False)
        cursor = page_info.get("end_cursor")

        bar = tqdm(total=total_pages, desc="Fetching comments", unit="page", leave=True)
        bar.set_postfix_str(f"total: {len(all_flat)}")
        bar.update(1)

        async def fetch_one(after_cursor: Optional[str]) -> Tuple[List[str], List[Dict[str, Any]], bool, Optional[str]]:
            nonlocal current_session, headers
            await limiter.wait()
            dj = read_cookie_json()
            hdrs = headers_from_store(shortcode, current_session) if cookie_json_valid(dj) else headers
            client.headers.update(hdrs)
            vars2 = {"shortcode": shortcode, "first": COMMENTS_PER_PAGE}
            if after_cursor:
                vars2["after"] = after_cursor

            tries = 0
            while True:
                tries += 1
                try:
                    d2 = await graphql_request(client, PARENT_QUERY_HASH, vars2)
                    f2, pinfo2, s2 = await parse_parent_comments(client, d2, include_replies, limiter)
                    return f2, s2, pinfo2.get("has_next_page", False), pinfo2.get("end_cursor")
                except AuthenticationError:
                    si, ct, m, du, hdrs2 = await refresh_cookies_interactive(shortcode)
                    current_session = (si, ct, m, du)
                    headers = hdrs2
                    client.headers.update(headers)
                    continue
                except RateLimitError as rle:
                    if tries >= 3:
                        raise ScrapeError(f"Terlalu sering request (Rate Limited): {rle}. Silakan turunkan RPS atau tunggu beberapa saat.")
                    wait_time = 5.0 * tries
                    print(f"\n⚠️ Rate limit terdeteksi, menunggu {wait_time} detik sebelum mencoba lagi...")
                    await asyncio.sleep(wait_time)
                except ScrapeError:
                    if tries >= 3:
                        raise
                    await asyncio.sleep(1.5 * tries)

        current_after = cursor
        while has_next and current_after:
            f2, s2, has_next, next_after = await fetch_one(current_after)
            all_flat.extend(f2)
            all_struct.extend(s2)
            bar.set_postfix_str(f"total: {len(all_flat)}")
            bar.update(1)
            if len(all_struct) > total_count:
                total_count = len(all_struct)
                new_total_pages = max(total_pages, ceil(total_count / COMMENTS_PER_PAGE))
                if new_total_pages != total_pages:
                    bar.total = new_total_pages
                    bar.refresh()
                    total_pages = new_total_pages
            current_after = next_after

        bar.close()
        return all_flat, all_struct

def prompt_rps() -> float:
    config = load_env_config()
    default_rps_str = config.get("DEFAULT_RPS", "1.0")
    try:
        default_rps = float(default_rps_str)
    except ValueError:
        default_rps = 1.0

    while True:
        val = input(f"Max requests per second (tekan Enter untuk default: {default_rps}): ").strip()
        if not val:
            return default_rps
        try:
            rps = float(val)
            if rps <= 0:
                print("Masukkan angka positif.")
                continue
            if rps > 3.0:
                print("⚠️ Peringatan: RPS > 3.0 sangat berisiko memicu rate limit (HTTP 429) Instagram.")
            return rps
        except ValueError:
            print(f"Masukkan nilai numerik seperti 0.5, 1.0, 2.0 (atau Enter untuk {default_rps}).")

def load_or_login_get_cookies_interactive() -> Tuple[str, str, str, str]:
    # 1. Prioritas utama: jika cookie.json sudah ada dan masih valid
    dj = read_cookie_json()
    if cookie_json_valid(dj):
        c = dj["cookies"]
        print("✅ Menggunakan sesi yang tersimpan dari cookie.json")
        return c["sessionid"], c["csrftoken"], c["mid"], c["ds_user_id"]

    # 2. Prioritas kedua: baca otomatis dari file .env atau config.json
    cfg = load_env_config()

    if cfg.get("IG_COOKIE"):
        print("✅ Memuat IG_COOKIE dari file .env...")
        try:
            sessionid, csrftoken, mid, dsuserid = create_session_from_cookie_input(cfg["IG_COOKIE"])
            write_cookie_json(sessionid, csrftoken, mid, dsuserid)
            return sessionid, csrftoken, mid, dsuserid
        except Exception as e:
            print(f"⚠️ Gagal memuat IG_COOKIE dari .env: {e}")

    if cfg.get("IG_SESSIONID"):
        print("✅ Memuat IG_SESSIONID dari file .env...")
        try:
            sessionid, csrftoken, mid, dsuserid = create_session_from_cookie_input(cfg["IG_SESSIONID"])
            write_cookie_json(sessionid, csrftoken, mid, dsuserid)
            return sessionid, csrftoken, mid, dsuserid
        except Exception as e:
            print(f"⚠️ Gagal memuat IG_SESSIONID dari .env: {e}")

    if cfg.get("IG_USERNAME") and cfg.get("IG_PASSWORD"):
        print(f"✅ Memuat kredensial akun ({cfg['IG_USERNAME']}) dari file .env...")
        try:
            sessionid, csrftoken, mid, dsuserid = login_instagram(cfg["IG_USERNAME"], cfg["IG_PASSWORD"])
            write_cookie_json(sessionid, csrftoken, mid, dsuserid)
            return sessionid, csrftoken, mid, dsuserid
        except LoginError as e:
            print(f"⚠️ Login otomatis dengan kredensial .env gagal: {e}")
            print("💡 Silakan masukkan cookie browser manual di bawah ini.")

    # 3. Jika belum ada kredensial sama sekali, tampilkan prompt interaktif
    return prompt_cookie_interactive()

async def amain():
    # Jika URL dimasukkan langsung sebagai argumen CLI (e.g. python3 main.py <url>)
    if len(sys.argv) > 1 and sys.argv[1].strip() and not sys.argv[1].startswith("-"):
        reel_url = sys.argv[1].strip()
        print(f"URL dari argumen: {reel_url}")
    else:
        reel_url = input("Masukkan URL Instagram Reel/Post (atau shortcode): ").strip()

    shortcode = extract_shortcode(reel_url)
    if not shortcode:
        print("\n❌ Format URL tidak valid!")
        print("Format yang didukung:")
        print(" - https://www.instagram.com/reel/<shortcode>/")
        print(" - https://www.instagram.com/reels/<shortcode>/")
        print(" - https://www.instagram.com/p/<shortcode>/")
        print(" - https://www.instagram.com/tv/<shortcode>/")
        print(" - Atau langsung masukkan shortcode (contoh: C8xyz123)")
        sys.exit(1)

    cfg = load_env_config()
    include_replies = cfg.get("INCLUDE_REPLIES", "true").lower() in ("true", "1", "yes")

    rps = prompt_rps()
    sessionid, csrftoken, mid, dsuserid = load_or_login_get_cookies_interactive()
    comments_flat, comments_struct = await fetch_all_pages(
        shortcode, (sessionid, csrftoken, mid, dsuserid), rps, include_replies=include_replies
    )

    write_outputs(shortcode, comments_flat, comments_struct)

def main():
    try:
        asyncio.run(amain())
    except LoginError as le:
        print(f"\n❌ Login error: {le}")
        sys.exit(1)
    except ScrapeError as se:
        print(f"\n❌ Scrape error: {se}")
        sys.exit(1)
    except httpx.RequestError as he:
        print(f"\n❌ Network error: {he}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ Dibatalkan oleh pengguna.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
