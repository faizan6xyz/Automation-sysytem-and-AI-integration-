import os
import time
import json
import shutil
import sqlite3
import base64
import tempfile
import ctypes
import ctypes.wintypes
from openai import OpenAI
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

NIM_MODEL = "meta/llama-3.1-8b-instruct"

# ── Chrome profile config ──────────────────────────────────────────────────────
CHROME_USER_DATA = r"C:\Users\faiza\AppData\Local\Google\Chrome\User Data"
PROFILE_NAME     = "Profile 23"

COOKIE_DOMAINS = [
    ".google.com",
    ".youtube.com",
    ".googleapis.com",
    "docs.google.com",
    "accounts.google.com",
]

# ── Prompt ─────────────────────────────────────────────────────────────────────
BROWSER_AGENT_PROMPT = """
You are a web automation agent. You are given the current HTML structure of a webpage and a goal to achieve.
Your job is to analyze the HTML and decide the next single action to take to progress toward the goal.

You will receive:
- GOAL: what needs to be achieved
- CURRENT URL: the current page
- HTML: the simplified interactive elements of the page

You must respond EXACTLY in this format and nothing else:
ACTION: action_name
TARGET: css_selector
VALUE: value (or None)

Available actions:
1. click       — click a button, link, or element
2. type        — type text into an input field
3. select      — select an option from a dropdown
4. scroll      — scroll down the page
5. navigate    — go to a URL directly (use TARGET as the URL, VALUE as None)
6. wait        — wait for page to load
7. done        — goal has been achieved

Rules:
- Only one action per response
- Use precise CSS selectors (id > class > tag)
- The browser is already logged in — NEVER try to log in, type an email, or type a password
- If you see a login page, respond: ACTION: wait / TARGET: None / VALUE: None
- If goal is already achieved, respond ACTION: done
- Never repeat the same action twice in a row
- If a selector does not work, try a different one
- Never navigate away from the intended website domain
"""

# ── Cookie decryption ──────────────────────────────────────────────────────────

def _get_encryption_key() -> bytes:
    """Read the AES key from Chrome's Local State, decrypt it with Windows DPAPI."""
    local_state_path = os.path.join(CHROME_USER_DATA, "Local State")
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)

    encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
    encrypted_key     = base64.b64decode(encrypted_key_b64)
    encrypted_key     = encrypted_key[5:]  # strip the literal "DPAPI" prefix

    import win32crypt
    key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    return key


def _decrypt_value(encrypted_value: bytes, key: bytes) -> str:
    """Decrypt a single AES-256-GCM cookie value (Chrome 80+) or legacy DPAPI."""
    if not encrypted_value:
        return ""
    try:
        if encrypted_value[:3] in (b"v10", b"v11"):
            from Crypto.Cipher import AES
            nonce      = encrypted_value[3:15]
            ciphertext = encrypted_value[15:-16]
            tag        = encrypted_value[-16:]
            cipher     = AES.new(key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
        # Legacy DPAPI (Chrome < 80)
        import win32crypt
        return win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1].decode("utf-8")
    except Exception as e:
        return ""


def _robocopy_file(src: str, dst: str) -> bool:
    """
    Copy src -> dst while Chrome has it open.
    Chrome uses shared read access on the Cookies file, so a plain
    copy works — we just need to avoid Python's default open() which
    fails on locked files. We try three approaches in order:
      1. robocopy (no /B — avoids needing SeBackupPrivilege)
      2. PowerShell Copy-Item
      3. ctypes CreateFile with full share flags
    """
    import subprocess, shutil as _sh
    src_dir  = os.path.dirname(src)
    src_name = os.path.basename(src)
    dst_dir  = os.path.dirname(dst)
    os.makedirs(dst_dir, exist_ok=True)

    # ── 1. robocopy without /B (no admin rights needed) ──────────────────────
    try:
        r = subprocess.run(
            ["robocopy", src_dir, dst_dir, src_name,
             "/R:0", "/W:0", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
            capture_output=True, timeout=15
        )
        result_path = os.path.join(dst_dir, src_name)
        if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
            if os.path.abspath(result_path) != os.path.abspath(dst):
                _sh.move(result_path, dst)
            return True
    except Exception:
        pass

    # ── 2. PowerShell Copy-Item ───────────────────────────────────────────────
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Copy-Item -LiteralPath '{src}' -Destination '{dst}' -Force"],
            capture_output=True, timeout=15
        )
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            return True
    except Exception:
        pass

    # ── 3. ctypes CreateFile with FILE_SHARE_READ|WRITE|DELETE ───────────────
    try:
        import ctypes, ctypes.wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        GENERIC_READ   = 0x80000000
        SHARE_ALL      = 0x00000001 | 0x00000002 | 0x00000004
        OPEN_EXISTING  = 3
        FILE_FLAG_SEQUENTIAL = 0x08000000
        INVALID_HANDLE = ctypes.wintypes.HANDLE(-1).value

        h = k32.CreateFileW(src, GENERIC_READ, SHARE_ALL, None,
                            OPEN_EXISTING, FILE_FLAG_SEQUENTIAL, None)
        if h != INVALID_HANDLE:
            try:
                buf  = ctypes.create_string_buffer(1 << 20)
                read = ctypes.wintypes.DWORD(0)
                with open(dst, "wb") as out:
                    while True:
                        ok = k32.ReadFile(h, buf, len(buf), ctypes.byref(read), None)
                        if not ok or read.value == 0:
                            break
                        out.write(buf.raw[:read.value])
            finally:
                k32.CloseHandle(h)
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                return True
    except Exception:
        pass

    return False
def export_cookies() -> dict:
    """
    Read cookies directly from Chrome's SQLite DB using Windows DPAPI.
    Works even if Chrome is running (copies DB to a temp file first).
    Returns a Playwright-compatible storage_state dict.
    """
    print("[Auth] Reading cookies directly from Chrome (DPAPI + SQLite)...")

    try:
        key = _get_encryption_key()
    except Exception as e:
        print(f"[Auth] ERROR: Could not read encryption key: {e}")
        print("       → Make sure you are running CMD as your NORMAL user (NOT as Administrator)")
        print("       → pip install pywin32 pycryptodome   if not already installed")
        exit(1)

    cookies_db = os.path.join(CHROME_USER_DATA, PROFILE_NAME, "Network", "Cookies")
    if not os.path.exists(cookies_db):
        print(f"[Auth] ERROR: Cookie DB not found at: {cookies_db}")
        print("       → Check CHROME_USER_DATA and PROFILE_NAME at the top of this file")
        exit(1)

    # Copy Cookies DB (and journal/wal companions) to a temp dir with robocopy
    tmp_dir = tempfile.mkdtemp()
    tmp_db  = os.path.join(tmp_dir, "Cookies")   # keep original name for robocopy
    if not _robocopy_file(cookies_db, tmp_db):
        print("[Auth] ERROR: robocopy failed to copy the Cookies file.")
        exit(1)
    for suffix in ("-journal", "-wal", "-shm"):
        companion = cookies_db + suffix
        if os.path.exists(companion) and os.path.getsize(companion) > 0:
            _robocopy_file(companion, tmp_db + suffix)

    cookies = []
    seen    = set()
    rows    = []

    try:
        conn   = sqlite3.connect(tmp_db)
        cursor = conn.cursor()

        # Detect actual table name — Chrome 127+ renamed it in some builds
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        print(f"[Auth] Tables in cookie DB: {tables}")

        if "cookies" in tables:
            table_name = "cookies"
        elif "chrome_cookies" in tables:
            table_name = "chrome_cookies"
        else:
            print(f"[Auth] ERROR: No cookie table found. Tables present: {tables}")
            conn.close()
            exit(1)

        # Also detect column names — schema changed across versions
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [r[1] for r in cursor.fetchall()]
        print(f"[Auth] Columns: {cols}")

        # samesite column is absent in some older builds
        has_samesite = "samesite" in cols
        select_cols  = "name, encrypted_value, host_key, path, expires_utc, is_secure, is_httponly"
        if has_samesite:
            select_cols += ", samesite"

        placeholders = " OR ".join(["host_key = ? OR host_key LIKE ?"] * len(COOKIE_DOMAINS))
        params = []
        for domain in COOKIE_DOMAINS:
            params.append(domain)
            params.append(f"%{domain.lstrip('.')}")

        cursor.execute(f"SELECT {select_cols} FROM {table_name} WHERE {placeholders}", params)
        raw_rows = cursor.fetchall()
        conn.close()

        # Normalise rows to always have 8 fields (pad samesite=1/Lax if missing)
        rows = [r if has_samesite else r + (1,) for r in raw_rows]

    except Exception as e:
        print(f"[Auth] ERROR reading cookie DB: {e}")
        exit(1)
    finally:
        try:
            import shutil as _shutil
            _shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    samesite_map = {-1: "Unspecified", 0: "Unspecified", 1: "Lax", 2: "Strict", 3: "None"}

    for name, enc_val, host_key, path, expires_utc, is_secure, is_httponly, samesite in rows:
        value = _decrypt_value(enc_val, key)
        if not value:
            continue

        dedup_key = (name, host_key, path)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        cookie = {
            "name":     name,
            "value":    value,
            "domain":   host_key,
            "path":     path or "/",
            "secure":   bool(is_secure),
            "httpOnly": bool(is_httponly),
            "sameSite": samesite_map.get(samesite, "Lax"),
        }
        # Chrome stores time as microseconds since Jan 1 1601 → convert to Unix epoch
        if expires_utc and expires_utc > 0:
            cookie["expires"] = int((expires_utc / 1_000_000) - 11_644_473_600)

        cookies.append(cookie)

    print(f"[Auth] Exported {len(cookies)} cookies from {PROFILE_NAME}.")

    if len(cookies) == 0:
        print("[Auth] ERROR: No cookies found.")
        print("       → Make sure you are logged into Google in Chrome Profile 23")
        print("       → Run CMD as your NORMAL user, NOT as Administrator")
        exit(1)

    return {"cookies": cookies, "origins": []}


# ── HTML cleaning ──────────────────────────────────────────────────────────────

def clean_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "meta", "noscript", "svg", "img"]):
        tag.decompose()
    interactive = soup.find_all([
        "input", "button", "a", "select",
        "form", "textarea", "label", "nav",
        "h1", "h2", "h3", "li"
    ])
    cleaned = []
    for tag in interactive:
        attrs_to_keep = ["id", "class", "name", "type", "href",
                         "placeholder", "value", "action"]
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs_to_keep}
        cleaned.append(str(tag))
    return "\n".join(cleaned)[:4000]


# ── LLM interaction ────────────────────────────────────────────────────────────

def get_next_action(goal: str, current_url: str, html: str, history: list) -> str:
    messages = [
        {"role": "system", "content": BROWSER_AGENT_PROMPT},
        *history,
        {"role": "user", "content": f"GOAL: {goal}\nCURRENT URL: {current_url}\nHTML:\n{html}"}
    ]
    response = client.chat.completions.create(
        model=NIM_MODEL,
        messages=messages,
        max_tokens=200,
        temperature=0
    )
    return response.choices[0].message.content.strip()


def parse_action(response: str) -> tuple:
    try:
        lines  = [l.strip() for l in response.strip().split("\n") if l.strip()]
        action = lines[0].split("ACTION:")[-1].strip().lower()
        target = lines[1].split("TARGET:")[-1].strip()
        value  = lines[2].split("VALUE:")[-1].strip()
        value  = None if value.lower() == "none" else value
        return action, target, value
    except Exception as e:
        print(f"Parse error: {e} | Response: {response}")
        return "wait", None, None


# ── Browser control ────────────────────────────────────────────────────────────

def execute_action(page, action: str, target: str, value: str) -> bool:
    try:
        if action == "click":
            page.click(target, timeout=5000)
        elif action == "type":
            page.focus(target)
            page.type(target, value, delay=80)
        elif action == "select":
            page.select_option(target, value, timeout=5000)
        elif action == "scroll":
            page.evaluate("window.scrollBy(0, 500)")
        elif action == "navigate":
            page.goto(target, wait_until="domcontentloaded", timeout=15000)
        elif action == "wait":
            time.sleep(2)
        elif action == "done":
            return True
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"Action failed: {e}")
        return False


def launch_browser(playwright, auth_state: dict):
    print("[Browser] Launching browser with exported cookies...")
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--disable-infobars",
        ]
    )
    context = browser.new_context(
        storage_state=auth_state,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="Asia/Kolkata",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    return browser, context


# ── Main agent loop ────────────────────────────────────────────────────────────

def run_browser_agent(goal: str, start_url: str, max_steps: int = 20):
    print(f"\nGoal: {goal}")
    print(f"Starting at: {start_url or 'https://www.google.com'}")
    print("=" * 50)

    auth_state   = export_cookies()
    history      = []
    last_actions = []

    with sync_playwright() as p:
        browser, context = launch_browser(p, auth_state)
        page = context.new_page()

        url = start_url.strip() if start_url.strip() else "https://www.google.com"
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)

        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")
            current_url = page.url

            if "accounts.google.com" in current_url and "signin" in current_url:
                print("[WARNING] Redirected to Google login — cookies may be expired.")
                break

            try:
                raw_html = page.content()
            except Exception as e:
                print(f"Page closed or crashed: {e}")
                break

            clean = clean_html(raw_html)
            print(f"URL: {current_url}")

            response              = get_next_action(goal, current_url, clean, history)
            action, target, value = parse_action(response)
            print(f"Action: {action} | Target: {target} | Value: {value}")

            last_actions.append(f"{action}:{target}")
            if len(last_actions) > 3:
                last_actions.pop(0)
            if len(last_actions) == 3 and len(set(last_actions)) == 1:
                print("Loop detected — same action 3 times in a row. Stopping.")
                break

            history.append({"role": "assistant", "content": response})

            if action == "done":
                print("\n" + "=" * 50)
                print("Goal achieved!")
                print("=" * 50)
                break

            success = execute_action(page, action, target, value)
            if not success:
                history.append({
                    "role": "user",
                    "content": f"The action failed: {action} on '{target}'. Try a different selector or approach."
                })

        else:
            print("\nMax steps reached — goal not achieved.")

        input("\nPress Enter to close browser...")
        browser.close()


if __name__ == "__main__":
    goal      = input("Enter your goal: ")
    start_url = input("Enter starting URL (leave blank for Google): ")
    run_browser_agent(goal, start_url)