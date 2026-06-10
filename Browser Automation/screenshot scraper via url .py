import asyncio
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
import pyautogui
import time

URL = input("Enter the URL: ").strip()
OUTPUT_DIR = Path("dataset")


def url_to_filename(url: str, index: int) -> str:
    clean = re.sub(r"https?://", "", url)
    clean = re.sub(r"[^\w\-]", "_", clean)
    clean = clean.strip("_")
    return f"{index:03d}_{clean}.png"


async def screenshot_url(url: str):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = url_to_filename(url, 1)
    save_path = OUTPUT_DIR / filename

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--start-maximized"]
        )
        context = await browser.new_context(viewport=None, no_viewport=True)
        page = await context.new_page()

        try:
            await page.goto(url, timeout=15000, wait_until="networkidle")
            await page.wait_for_timeout(2000)  # wait for full render

            # 👇 pyautogui captures the ENTIRE screen including taskbar
            screenshot = pyautogui.screenshot()
            screenshot.save(str(save_path))

            w, h = screenshot.size
            print(f"Saved: {save_path} ({w}x{h})")

        except Exception as e:
            print(f"Error: {e}")

        finally:
            await page.close()
            await browser.close()

    manifest_path = OUTPUT_DIR / "manifest.txt"
    manifest_exists = manifest_path.exists()

    with open(manifest_path, "a", encoding="utf-8") as f:
        if not manifest_exists:
            f.write("=" * 50 + "\n")
            f.write("        SCREENSHOT MANIFEST\n")
            f.write("=" * 50 + "\n\n")
        f.write(f"Run — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  URL      : {url}\n")
        f.write(f"  File     : {filename}\n")
        f.write(f"  Size     : {w}x{h}\n")
        f.write("-" * 50 + "\n\n")


if __name__ == "__main__":
    asyncio.run(screenshot_url(URL))