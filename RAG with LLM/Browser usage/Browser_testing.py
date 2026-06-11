import os
import time
import json
from openai import OpenAI
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)
NIM_MODEL       = "meta/llama-3.1-8b-instruct"
AUTH_STATE_FILE = "auth_state.json"
COOKIES_FILE    = r"C:\Users\faiza\OneDrive\Desktop\youtube_cookies.json"
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
- If login is needed first, do that before anything else
- If goal is already achieved, respond ACTION: done
- Never repeat the same action twice in a row
- If a selector does not work, try a different one
"""
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
        attrs_to_keep = ["id", "class", "name", "type", "href", "placeholder", "value", "action"]
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in attrs_to_keep}
        cleaned.append(str(tag))
    return "\n".join(cleaned)[:4000]
def get_next_action(goal: str, current_url: str, html: str, history: list) -> str:
    messages = [
        {"role": "system", "content": BROWSER_AGENT_PROMPT},
        *history,
        {"role": "user", "content": f"""
GOAL: {goal}
CURRENT URL: {current_url}
HTML:
{html}
"""}
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
def normalize_same_site(value: str) -> str:
    mapping = {
        "strict":         "Strict",
        "lax":            "Lax",
        "none":           "None",
        "no_restriction": "None",
        "unspecified":    "Lax",
        "":               "Lax",
    }
    return mapping.get(str(value).lower(), "Lax")
def build_auth_state_from_cookies():
    """Convert Cookie-Editor export format → Playwright storage_state format."""
    with open(COOKIES_FILE, "r") as f:
        raw_cookies = json.load(f)
    cookies = []
    for c in raw_cookies:
        cookie = {
            "name":     c["name"],
            "value":    c["value"],
            "domain":   c["domain"],
            "path":     c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure":   c.get("secure", False),
            "sameSite": normalize_same_site(c.get("sameSite", "Lax")),
        }
        if "expirationDate" in c:
            cookie["expires"] = int(c["expirationDate"])
        cookies.append(cookie)
    auth_state = {"cookies": cookies, "origins": []}
    with open(AUTH_STATE_FILE, "w") as f:
        json.dump(auth_state, f)
    print(f"[Auth] auth_state.json built from {len(cookies)} cookies.")
def launch_browser(playwright):
    if not os.path.exists(AUTH_STATE_FILE):
        if os.path.exists(COOKIES_FILE):
            print("[Auth] Building session from exported cookies...")
            build_auth_state_from_cookies()
        else:
            print(f"[Auth] ERROR: Neither auth_state.json nor cookies file found.")
            print(f"[Auth] Expected cookies at: {COOKIES_FILE}")
            print("[Auth] Steps to fix:")
            print("  1. Open Chrome → go to youtube.com (make sure you're logged in)")
            print("  2. Click Cookie-Editor extension → Export → copies to clipboard")
            print("  3. Paste into a file saved at the path above")
            print("  4. Run this script again")
            exit(1)
    print(f"[Auth] Loading session from '{AUTH_STATE_FILE}'")
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
        ]
    )
    context = browser.new_context(
        storage_state=AUTH_STATE_FILE,
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
def apply_stealth(page):
    try:
        stealth = Stealth()
        stealth.apply_stealth_sync(page)
    except Exception:
        pass
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
def run_browser_agent(goal: str, start_url: str, max_steps: int = 20):
    print(f"\nGoal: {goal}")
    print(f"Starting at: {start_url}")
    print("=" * 50)
    history = []
    with sync_playwright() as p:
        browser, context = launch_browser(p)
        page = context.new_page()
        apply_stealth(page)
        url = start_url.strip() if start_url.strip() else "https://www.youtube.com"
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")
            current_url = page.url
            raw_html    = page.content()
            clean       = clean_html(raw_html)
            print(f"URL: {current_url}")
            response              = get_next_action(goal, current_url, clean, history)
            action, target, value = parse_action(response)
            print(f"Action: {action} | Target: {target} | Value: {value}")
            history.append({"role": "assistant", "content": response})
            if action == "done":
                print("\n" + "=" * 50)
                print("Goal achieved!")
                print("=" * 50)
                break
            success = execute_action(page, action, target, value)
            if not success:
                print("Action failed — asking LLM to retry with different approach")
                history.append({
                    "role": "user",
                    "content": f"The action failed: {action} on {target}. Try a different selector or approach."
                })
        else:
            print("\nMax steps reached — goal not achieved.")
        input("\nPress Enter to close browser...")
        browser.close()
if __name__ == "__main__":
    goal      = input("Enter your goal: ")
    start_url = input("Enter starting URL (leave blank for YouTube): ")
    run_browser_agent(goal, start_url)