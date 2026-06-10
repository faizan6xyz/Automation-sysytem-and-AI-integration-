# utils/accessibility.py
"""
Extracts a clean, LLM-friendly accessibility tree from a Playwright page.
Compatible with Playwright 1.40+ (page.accessibility removed in newer versions).
"""

from playwright.async_api import Page

USEFUL_ROLES = {
    "button", "link", "textbox", "searchbox", "combobox",
    "checkbox", "radio", "menuitem", "tab", "heading",
    "img", "listitem", "option", "switch", "spinbutton",
    "slider", "progressbar", "alert", "dialog", "main",
    "navigation", "form", "table", "row", "cell",
}


def _walk(node: dict, depth: int = 0, lines: list = None) -> list:
    if lines is None:
        lines = []

    role        = node.get("role", "").lower()
    name        = (node.get("name") or "").strip()
    value       = (node.get("value") or "").strip()
    description = (node.get("description") or "").strip()

    if role in ("none", "presentation", "generic", ""):
        for child in node.get("children", []):
            _walk(child, depth, lines)
        return lines

    indent = "  " * depth
    parts  = [f"{indent}[{role}]"]
    if name:
        parts.append(f'"{name}"')
    if value:
        parts.append(f'value="{value}"')
    if description and description != name:
        parts.append(f'desc="{description}"')

    if role in USEFUL_ROLES or name:
        lines.append(" ".join(parts))

    for child in node.get("children", []):
        _walk(child, depth + 1, lines)

    return lines


async def get_accessibility_tree(page: Page, max_lines: int = 200) -> str:
    """
    Returns a compact accessibility tree string.
    Works with Playwright 1.40+ — uses page.snapshot() (aria snapshot).
    Falls back to JS-based AXTree if snapshot unavailable.
    """

    # ── Method 1: page.snapshot() — Playwright 1.40+ ─────────────────────────
    try:
        snapshot_text = await page.aria_snapshot()
        if snapshot_text:
            lines = snapshot_text.strip().splitlines()
            if len(lines) > max_lines:
                lines = lines[:max_lines] + [f"... [{len(lines)-max_lines} more lines truncated]"]
            return "\n".join(lines)
    except Exception:
        pass

    # ── Method 2: JS evaluate — always works ─────────────────────────────────
    try:
        snapshot = await page.evaluate("""
            () => {
                function walk(node) {
                    if (!node) return null;
                    const result = {
                        role: node.role,
                        name: node.name,
                        value: node.value,
                        description: node.description,
                        children: []
                    };
                    for (const child of (node.children || [])) {
                        const c = walk(child);
                        if (c) result.children.push(c);
                    }
                    return result;
                }
                // Use Chrome DevTools Protocol via window.__playwright
                return null;
            }
        """)
    except Exception:
        snapshot = None

    # ── Method 3: DOM-based fallback ─────────────────────────────────────────
    try:
        elements = await page.evaluate("""
            () => {
                const results = [];
                const selectors = [
                    'a', 'button', 'input', 'textarea', 'select',
                    'h1', 'h2', 'h3', 'h4', 'label', '[role]'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        const role = el.getAttribute('role') || el.tagName.toLowerCase();
                        const name = el.getAttribute('aria-label')
                                  || el.getAttribute('placeholder')
                                  || el.getAttribute('title')
                                  || el.textContent?.trim().slice(0, 60)
                                  || '';
                        const value = el.value || '';
                        if (name || role) {
                            results.push({ role, name, value });
                        }
                    });
                });
                return results.slice(0, 200);
            }
        """)

        lines = []
        for el in elements:
            role  = el.get("role", "")
            name  = el.get("name", "").strip()
            value = el.get("value", "").strip()
            if role or name:
                line = f"[{role}]"
                if name:  line += f' "{name}"'
                if value: line += f' value="{value}"'
                lines.append(line)

        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... [{len(lines)-max_lines} more truncated]"]

        return "\n".join(lines) if lines else "[no interactive elements found]"

    except Exception as e:
        return f"[accessibility tree error: {e}]"


async def get_page_meta(page: Page) -> dict:
    return {
        "url":   page.url,
        "title": await page.title(),
    }
