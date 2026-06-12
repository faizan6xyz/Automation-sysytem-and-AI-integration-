import os
import sqlite3
import tempfile
import shutil
import ctypes
import ctypes.wintypes

CHROME_USER_DATA = r"C:\Users\faiza\AppData\Local\Google\Chrome\User Data"
PROFILE_NAME     = "Profile 23"

def _copy_locked_file(src, dst):
    import subprocess
    src_dir  = os.path.dirname(src)
    src_name = os.path.basename(src)
    dst_dir  = os.path.dirname(dst)
    os.makedirs(dst_dir, exist_ok=True)
    # Try robocopy first (backup mode bypasses locks)
    try:
        r = subprocess.run(
            ["robocopy", src_dir, dst_dir, src_name, "/B", "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
            capture_output=True, timeout=15
        )
        copied = os.path.join(dst_dir, src_name)
        if r.returncode < 8 and os.path.exists(copied) and os.path.getsize(copied) > 0:
            if copied != dst:
                os.replace(copied, dst)
            return
    except Exception as e:
        print(f"    robocopy failed: {e}")
    # Fallback: PowerShell
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Copy-Item -Path \"{src}\" -Destination \"{dst}\" -Force"],
            capture_output=True, timeout=15
        )
        if os.path.exists(dst) and os.path.getsize(dst) > 0:
            return
    except Exception as e:
        print(f"    PowerShell failed: {e}")
    raise OSError(f"Could not copy locked file: {src}")

print("=" * 60)
print("CHROME COOKIE DIAGNOSTIC")
print("=" * 60)

# 1. List all files in the Network folder
net_dir = os.path.join(CHROME_USER_DATA, PROFILE_NAME, "Network")
print(f"\n[1] Files in {net_dir}:")
if os.path.exists(net_dir):
    for f in sorted(os.listdir(net_dir)):
        full = os.path.join(net_dir, f)
        size = os.path.getsize(full)
        print(f"    {f:<40} {size:>10} bytes")
else:
    print("    ERROR: Network folder does not exist!")

# 2. Check all possible cookie file locations
print("\n[2] Checking cookie file locations:")
candidates = [
    os.path.join(CHROME_USER_DATA, PROFILE_NAME, "Network", "Cookies"),
    os.path.join(CHROME_USER_DATA, PROFILE_NAME, "Cookies"),
    os.path.join(CHROME_USER_DATA, PROFILE_NAME, "Network", "ChromiumCookies"),
]
for c in candidates:
    exists = os.path.exists(c)
    size   = os.path.getsize(c) if exists else 0
    print(f"    {'EXISTS' if exists else 'MISSING':<8}  {size:>10} bytes  {c}")

# 3. Try copying and inspecting the main Cookies file
print("\n[3] Attempting copy + SQLite inspection:")
cookie_path = os.path.join(CHROME_USER_DATA, PROFILE_NAME, "Network", "Cookies")
if os.path.exists(cookie_path):
    tmp_dir = tempfile.mkdtemp()
    tmp_db  = os.path.join(tmp_dir, "Cookies.db")
    try:
        _copy_locked_file(cookie_path, tmp_db)
        copied_size = os.path.getsize(tmp_db)
        print(f"    Copied file size: {copied_size} bytes")

        # Also copy WAL/SHM
        for suffix in ("-wal", "-shm"):
            src = cookie_path + suffix
            if os.path.exists(src):
                dst = tmp_db + suffix
                _copy_locked_file(src, dst)
                print(f"    Copied {suffix}: {os.path.getsize(dst)} bytes")

        # Try opening with different URI modes
        for uri in [
            f"file:{tmp_db}?immutable=1",
            f"file:{tmp_db}?mode=ro",
            tmp_db,
        ]:
            try:
                conn = sqlite3.connect(uri, uri=uri.startswith("file:"))
                cur  = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in cur.fetchall()]
                conn.close()
                print(f"    URI={uri!r:<50}  tables={tables}")
            except Exception as e:
                print(f"    URI={uri!r:<50}  ERROR: {e}")

        # Try with PRAGMA wal_checkpoint
        try:
            conn = sqlite3.connect(tmp_db)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            if "cookies" in tables:
                cur.execute("SELECT COUNT(*) FROM cookies")
                count = cur.fetchone()[0]
                print(f"    After wal_checkpoint: tables={tables}, cookie count={count}")
            conn.close()
        except Exception as e:
            print(f"    wal_checkpoint attempt: ERROR: {e}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
else:
    print("    Cookies file not found at expected path")

# 4. Read first 16 bytes of the file to check magic
print("\n[4] File header (magic bytes):")
if os.path.exists(cookie_path):
    tmp2 = tempfile.mktemp(suffix=".db")
    try:
        _copy_locked_file(cookie_path, tmp2)
        with open(tmp2, "rb") as f:
            header = f.read(16)
        print(f"    Header hex:  {header.hex()}")
        print(f"    Header text: {header}")
        print(f"    SQLite magic: {'YES' if header.startswith(b'SQLite format 3') else 'NO — not a valid SQLite file!'}")
    finally:
        try: os.unlink(tmp2)
        except: pass

print("\n" + "=" * 60)
print("Diagnostic complete.")
input("Press Enter to exit...")