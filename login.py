#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import hashlib
import hmac
import json
import os
import random
import sys
import time
import urllib.parse
import uuid
from typing import Any, Dict, Optional, Tuple

import requests

API_URL = "https://i.instagram.com/api/{version}/"
V = "v1"
USER_AGENT = "Instagram 320.0.0.35.109 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 564998725)"
IG_SIG_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SIG_KEY_VERSION = "4"
IG_CAPABILITIES = "3brTvw"
APPLICATION_ID = "567067343352427"
FB_HTTP_ENGINE = "Liger"

COOKIE_JSON_PATH = "cookie.json"
ENV_FILE_PATH = ".env"
CONFIG_JSON_PATH = "config.json"

# ---------- Environment & Config Helpers ----------

def load_env_config() -> Dict[str, str]:
    """
    Load configuration from .env file, config.json, and OS environment variables.
    Returns dictionary with keys such as IG_SESSIONID, IG_COOKIE, IG_USERNAME, IG_PASSWORD, DEFAULT_RPS.
    """
    config: Dict[str, str] = {}

    # 1. Read .env file if it exists
    if os.path.exists(ENV_FILE_PATH):
        try:
            with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if v:
                        config[k] = v
        except Exception:
            pass

    # 2. Read config.json if it exists
    if os.path.exists(CONFIG_JSON_PATH):
        try:
            with open(CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
                j = json.load(f)
                if isinstance(j, dict):
                    if j.get("sessionid"):
                        config.setdefault("IG_SESSIONID", str(j["sessionid"]).strip())
                    if j.get("cookie"):
                        config.setdefault("IG_COOKIE", str(j["cookie"]).strip())
                    if j.get("username"):
                        config.setdefault("IG_USERNAME", str(j["username"]).strip())
                    if j.get("password"):
                        config.setdefault("IG_PASSWORD", str(j["password"]).strip())
                    if j.get("default_rps"):
                        config.setdefault("DEFAULT_RPS", str(j["default_rps"]).strip())
        except Exception:
            pass

    # 3. System environment variables override config files
    for env_key in ("IG_SESSIONID", "IG_COOKIE", "IG_USERNAME", "IG_PASSWORD", "DEFAULT_RPS"):
        val = os.environ.get(env_key)
        if val and val.strip():
            config[env_key] = val.strip()

    return config

def save_to_env_file(key_values: Dict[str, str], filepath: str = ENV_FILE_PATH) -> bool:
    """
    Save or update key-value pairs into .env file while preserving comments and structure.
    """
    try:
        existing_lines = []
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                existing_lines = f.readlines()

        keys_to_update = dict(key_values)
        updated_lines = []

        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k in keys_to_update:
                    updated_lines.append(f"{k}={keys_to_update.pop(k)}\n")
                    continue
            updated_lines.append(line)

        # Append any remaining keys that were not already in the file
        for k, v in keys_to_update.items():
            updated_lines.append(f"{k}={v}\n")

        with open(filepath, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)
        return True
    except Exception as e:
        print(f"Peringatan: Gagal menyimpan ke {filepath}: {e}", file=sys.stderr)
        return False

# ---------- Utilities ----------

def generate_uuid(return_hex: bool = False, seed: Optional[str] = None) -> str:
    if seed:
        m = hashlib.md5()
        m.update(seed.encode("utf-8"))
        new_uuid = uuid.UUID(m.hexdigest())
    else:
        new_uuid = uuid.uuid1()
    return new_uuid.hex if return_hex else str(new_uuid)

def generate_device_id(seed: Optional[str] = None) -> str:
    return "android-%s" % generate_uuid(True, (seed or "")[:16])

def generate_adid(seed: Optional[str] = None, username: Optional[str] = None, dsuser: Optional[str] = None) -> str:
    modified_seed = seed or dsuser or username or generate_uuid()
    sha2 = hashlib.sha256()
    sha2.update(modified_seed.encode("utf-8"))
    modified_seed = sha2.hexdigest()
    return generate_uuid(False, modified_seed)

def default_headers(useragent: str, igcap: str, appid: str) -> Dict[str, str]:
    return {
        "User-Agent": useragent,
        "Connection": "close",
        "Accept": "*/*",
        "Accept-Language": "en-US",
        "Accept-Encoding": "gzip, deflate",
        "X-IG-Capabilities": igcap,
        "X-IG-Connection-Type": "WIFI",
        "X-IG-Connection-Speed": f"{random.randint(1000,5000)}kbps",
        "X-IG-App-ID": appid,
        "X-IG-Bandwidth-Speed-KBPS": "-1.000",
        "X-IG-Bandwidth-TotalBytes-B": "0",
        "X-IG-Bandwidth-TotalTime-MS": "0",
        "X-FB-HTTP-Engine": FB_HTTP_ENGINE,
    }

def sign_params(signature_key: str, key_version: str, params: dict) -> Dict[str, str]:
    json_params = json.dumps(params, separators=(",", ":"))
    mac = hmac.new(signature_key.encode("ascii"), json_params.encode("ascii"), digestmod=hashlib.sha256).hexdigest()
    return {
        "ig_sig_key_version": key_version,
        "signed_body": f"{mac}.{json_params}",
    }

def get_cookie_value(jar: requests.cookies.RequestsCookieJar, key: str, domain: str = "instagram.com") -> Optional[str]:
    now = int(time.time())
    eternity = now + 100 * 365 * 24 * 60 * 60
    # Prefer latest-expiring cookie for the domain
    for c in sorted(jar, key=lambda c: c.expires or eternity, reverse=True):
        if c.expires and c.expires < now:
            continue
        cookiedomain = c.domain[1:] if c.domain.startswith(".") else c.domain
        if not (cookiedomain.endswith(domain) or domain.endswith(cookiedomain)):
            continue
        if c.name.lower() == key.lower():
            return c.value
    return None

# ---------- Cookie JSON Helpers ----------

def write_cookie_json(sessionid: str, csrftoken: str, mid: str, ds_user_id: str,
                      per_cookie_expiry: Optional[Dict[str, Optional[int]]] = None,
                      expiry_days: int = 30) -> None:
    now = int(time.time())
    per_cookie_expiry = per_cookie_expiry or {}

    expiries = []
    for k in ("sessionid", "csrftoken", "mid", "ds_user_id"):
        v = per_cookie_expiry.get(k)
        if isinstance(v, int) and v > now:
            expiries.append(v)
    overall_expiry = min(expiries) if expiries else now + expiry_days * 24 * 60 * 60

    data = {
        "iat": now,
        "overall_expiry": overall_expiry,
        "cookies": {
            "sessionid": sessionid or "",
            "csrftoken": csrftoken or "",
            "mid": mid or "",
            "ds_user_id": ds_user_id or ""
        },
        "per_cookie_expiry": {
            "sessionid": per_cookie_expiry.get("sessionid"),
            "csrftoken": per_cookie_expiry.get("csrftoken"),
            "mid": per_cookie_expiry.get("mid"),
            "ds_user_id": per_cookie_expiry.get("ds_user_id")
        }
    }
    with open(COOKIE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def read_cookie_json() -> Optional[Dict[str, Any]]:
    try:
        with open(COOKIE_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def cookie_json_valid(d: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(d, dict):
        return False
    now = int(time.time())
    overall = d.get("overall_expiry")
    c = (d.get("cookies") or {})
    # sessionid is the absolute requirement for authenticated requests
    required_ok = bool(c.get("sessionid"))
    return bool(required_ok and isinstance(overall, (int, float)) and overall > now)

# ---------- Browser Cookie Helpers ----------

def parse_cookie_header(raw_cookie: str) -> Dict[str, str]:
    """Parse a raw Cookie header string into key-value pairs."""
    cookies: Dict[str, str] = {}
    for item in raw_cookie.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def fetch_web_tokens() -> Tuple[str, str]:
    """Fetch initial anonymous csrftoken and mid cookies directly from instagram.com web."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        s.get("https://www.instagram.com/", timeout=10)
        csrftoken = s.cookies.get("csrftoken") or ""
        mid = s.cookies.get("mid") or ""
        return csrftoken, mid
    except Exception:
        return "", ""

def extract_ds_user_id_from_session(sessionid: str) -> str:
    """Extract numeric ds_user_id from sessionid if present (format: <user_id>%3A...)."""
    try:
        unquoted = urllib.parse.unquote(sessionid)
        first_part = unquoted.split(":")[0].strip()
        if first_part.isdigit():
            return first_part
    except Exception:
        pass
    return ""

def create_session_from_cookie_input(raw_input: str) -> Tuple[str, str, str, str]:
    """
    Process cookie input provided by user.
    Accepts:
      1) Full Cookie header (e.g., 'sessionid=...; csrftoken=...; ds_user_id=...; mid=...')
      2) Raw sessionid value directly (e.g., '123456789%3A...')
    Returns (sessionid, csrftoken, mid, ds_user_id).
    """
    raw_input = raw_input.strip()
    if not raw_input:
        raise LoginError("Input cookie tidak boleh kosong.")

    if "sessionid=" in raw_input or ";" in raw_input:
        cookies = parse_cookie_header(raw_input)
        sessionid = cookies.get("sessionid", "").strip()
        csrftoken = cookies.get("csrftoken", "").strip()
        mid = cookies.get("mid", "").strip()
        ds_user_id = cookies.get("ds_user_id", "").strip()
    else:
        sessionid = raw_input
        csrftoken = ""
        mid = ""
        ds_user_id = ""

    if not sessionid:
        raise LoginError("Tidak dapat menemukan 'sessionid' pada input yang diberikan.")

    if not ds_user_id:
        ds_user_id = extract_ds_user_id_from_session(sessionid) or "0"

    # Auto-fetch web tokens if missing
    if not csrftoken or not mid:
        fetched_csrf, fetched_mid = fetch_web_tokens()
        csrftoken = csrftoken or fetched_csrf or "missing_csrf"
        mid = mid or fetched_mid or generate_uuid(True)[:24]

    return sessionid, csrftoken, mid, ds_user_id

def prompt_cookie_interactive() -> Tuple[str, str, str, str]:
    """
    Interactive prompt offering browser cookie input (recommended) or mobile login,
    with option to save credentials into .env.
    """
    print("\n" + "=" * 60)
    print("🔐 Autentikasi Akun Instagram Diperlukan")
    print("=" * 60)
    print("1. Masukkan Cookie dari Browser / sessionid (Direkomendasikan)")
    print("   - Aman, cepat, dan tidak memicu verifikasi checkpoint / 2FA.")
    print("2. Login Otomatis dengan Username & Password (Eksperimental)")
    print("   - Rentan diblokir/dibatasi oleh proteksi keamanan Instagram.")
    print("=" * 60)

    choice = input("Pilih metode login [1/2] (default: 1): ").strip()
    if choice == "2":
        username = input("Masukkan username Instagram: ").strip()
        password = input("Masukkan password Instagram: ").strip()
        print("Mencoba login ke server Instagram...")
        try:
            sessionid, csrftoken, mid, dsuserid = login_instagram(username, password)
            write_cookie_json(sessionid, csrftoken, mid, dsuserid)
            print("✅ Login berhasil! Cookie disimpan ke cookie.json")

            save_choice = input("Simpan username & password ke file .env agar otomatis digunakan seterusnya? [Y/n]: ").strip().lower()
            if save_choice in ("", "y", "yes"):
                save_to_env_file({"IG_USERNAME": username, "IG_PASSWORD": password})
                print("✅ Kredensial disimpan ke file .env!")

            return sessionid, csrftoken, mid, dsuserid
        except LoginError as e:
            print(f"\n❌ Login otomatis gagal: {e}")
            print("💡 Instagram memblokir login otomatis via skrip ini.")
            print("Silakan beralih ke Opsi 1 (Masukkan Cookie Browser secara manual).\n")
            return prompt_cookie_interactive()

    print("\n📌 Cara mendapatkan Cookie Instagram dari Browser:")
    print("1. Buka https://www.instagram.com di browser dan pastikan Anda sudah login.")
    print("2. Buka DevTools (Tekan F12 atau klik kanan -> Inspect).")
    print("3. Di tab 'Application' (Chrome/Edge) atau 'Storage' (Firefox):")
    print("   Klik 'Cookies' -> 'https://www.instagram.com' -> salin Value dari 'sessionid'.")
    print("   (Atau di tab 'Network' -> klik salah satu request -> salin seluruh isi header 'Cookie').\n")

    raw_cookie = input("Tempelkan nilai 'sessionid' atau header 'Cookie' di sini: ").strip()
    sessionid, csrftoken, mid, dsuserid = create_session_from_cookie_input(raw_cookie)
    write_cookie_json(sessionid, csrftoken, mid, dsuserid)
    print("✅ Cookie berhasil diverifikasi dan disimpan ke cookie.json!")

    save_choice = input("Simpan sessionid ini ke file .env agar otomatis digunakan seterusnya? [Y/n]: ").strip().lower()
    if save_choice in ("", "y", "yes"):
        save_to_env_file({"IG_SESSIONID": sessionid})
        print("✅ Sesi disimpan ke file .env!")

    print("")
    return sessionid, csrftoken, mid, dsuserid

# ---------- Login Core ----------

class LoginError(Exception):
    pass

def login_instagram(username: str, password: str, timeout_prelogin: int = 10, timeout_login: int = 20) -> Tuple[str, str, str, str]:
    """
    Perform the mobile-app-like login and return tuple:
    (sessionid, csrftoken, mid, ds_user_id)
    Raises LoginError on failure with meaningful message.
    """
    s = requests.Session()
    s.headers.update(default_headers(USER_AGENT, IG_CAPABILITIES, APPLICATION_ID))

    # Pre-login to fetch CSRF
    prelogin_url = API_URL.format(version=V) + "si/fetch_headers/"
    prelogin_query = {"challenge_type": "signup", "guid": generate_uuid(True)}
    try:
        r = s.post(prelogin_url, params=prelogin_query, headers={"Content-type": "application/x-www-form-urlencoded; charset=UTF-8"}, timeout=timeout_prelogin)
    except requests.RequestException as e:
        raise LoginError(f"Network error during prelogin: {e}")

    csrftoken = get_cookie_value(s.cookies, "csrftoken")
    if not csrftoken:
        raise LoginError("Unable to get CSRF from prelogin.")

    device_id = generate_device_id()
    login_params = {
        "device_id": device_id,
        "guid": generate_uuid(False),
        "adid": generate_adid(username=username),
        "phone_id": generate_uuid(False, seed=device_id),
        "csrftoken": csrftoken,
        "username": username,
        "password": password,
        "login_attempt_count": 0,
    }
    signed = sign_params(IG_SIG_KEY, SIG_KEY_VERSION, login_params)
    login_url = API_URL.format(version=V) + "accounts/login/"

    try:
        r = s.post(login_url, data=signed, headers={"Content-type": "application/x-www-form-urlencoded; charset=UTF-8"}, timeout=timeout_login)
    except requests.RequestException as e:
        raise LoginError(f"Network error during login: {e}")

    # Attempt JSON parse, but tolerate non-JSON
    try:
        j = r.json()
    except Exception:
        j = {"status": "unknown", "text": r.text}

    # Detect common error states
    if r.status_code != 200:
        if isinstance(j, dict) and j.get("error_type") == "needs_upgrade":
            raise LoginError("Instagram API menolak versi aplikasi ini ('needs_upgrade'). Instagram mewajibkan enkripsi password mobile terbaru. Disarankan menggunakan metode Cookie browser.")
        raise LoginError(f"HTTP {r.status_code} during login: {j}")

    if not isinstance(j, dict):
        raise LoginError(f"Unexpected login response: {j}")

    if j.get("two_factor_required"):
        raise LoginError("Two-factor authentication required on this account; interactive flow not implemented. Disarankan menggunakan Cookie browser.")

    if j.get("challenge_required"):
        raise LoginError("Challenge / checkpoint required by Instagram. Selesaikan verifikasi di aplikasi atau gunakan Cookie browser.")

    if not j.get("logged_in_user", {}).get("pk"):
        raise LoginError(f"Unable to login: {j}")

    # Extract cookies
    sessionid = get_cookie_value(s.cookies, "sessionid", domain="instagram.com")
    csrftoken = get_cookie_value(s.cookies, "csrftoken", domain="instagram.com") or csrftoken
    mid = get_cookie_value(s.cookies, "mid", domain="instagram.com")
    dsuserid = get_cookie_value(s.cookies, "ds_user_id", domain="instagram.com") or str(j.get("logged_in_user", {}).get("pk", ""))

    if not sessionid:
        raise LoginError("Login succeeded but sessionid cookie is missing.")

    return (sessionid, csrftoken or "", mid or "", dsuserid or "")

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Instagram authentication and cookie exporter")
    ap.add_argument("-u", "--username", help="Instagram username")
    ap.add_argument("-p", "--password", help="Instagram password")
    ap.add_argument("-c", "--cookie", help="Raw cookie header or sessionid string")
    ap.add_argument("--save", action="store_true", help="Save the provided credentials/cookie to .env")
    ap.add_argument("--json", action="store_true", help="Output cookies in JSON format")
    args = ap.parse_args()

    try:
        if args.cookie:
            sessionid, csrftoken, mid, dsuserid = create_session_from_cookie_input(args.cookie)
            write_cookie_json(sessionid, csrftoken, mid, dsuserid)
            if args.save:
                save_to_env_file({"IG_SESSIONID": sessionid})
                print("✅ Sesi disimpan ke .env")
        elif args.username and args.password:
            sessionid, csrftoken, mid, dsuserid = login_instagram(args.username, args.password)
            write_cookie_json(sessionid, csrftoken, mid, dsuserid)
            if args.save:
                save_to_env_file({"IG_USERNAME": args.username, "IG_PASSWORD": args.password})
                print("✅ Kredensial disimpan ke .env")
        else:
            sessionid, csrftoken, mid, dsuserid = prompt_cookie_interactive()

        if args.json:
            print(json.dumps(
                {"sessionid": sessionid, "csrftoken": csrftoken, "mid": mid, "ds_user_id": dsuserid},
                ensure_ascii=False, indent=2
            ))
        else:
            print(f"sessionid:  {sessionid}")
            print(f"csrftoken:  {csrftoken}")
            print(f"mid:        {mid}")
            print(f"ds_user_id: {dsuserid}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
