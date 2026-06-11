import os
import time
import json
from openai import OpenAI
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
  api_key = "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"
)
NIM_MODEL = "meta/llama-3.1-8b-instruct"
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
    return "\n".join(cleaned)[:4000]  # limit tokens
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
            page.fill(target, value, timeout=5000)
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
        time.sleep(1.5)  # let page settle after action
        return True
    except Exception as e:
        print(f"Action failed: {e}")
        return False
def run_browser_agent(goal: str, start_url: str, max_steps: int = 20):
    print(f"\nGoal: {goal}")
    print(f"Starting at: {start_url}")
    print("=" * 50)
    history = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # headless=True to hide browser
        page    = browser.new_page()
        page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        for step in range(max_steps):
            print(f"\n--- Step {step + 1} ---")
            current_url = page.url
            raw_html    = page.content()
            clean       = clean_html(raw_html)
            print(f"URL: {current_url}")
            response           = get_next_action(goal, current_url, clean, history)
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
        input("\nPress Enter to close browser...")  # keep browser open to inspect
        browser.close()
if __name__ == "__main__":
    goal      = input("Enter your goal: ")
    start_url = input("Enter starting URL: ")
    run_browser_agent(goal, start_url)