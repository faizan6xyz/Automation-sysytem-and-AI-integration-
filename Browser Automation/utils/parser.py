# utils/parser.py
"""
Parses LLM text output into structured browser actions.

Expected LLM output format:
    ACTION: click | fill | goto | scroll | wait | done
    SELECTOR: <css selector or text>        (optional for goto/wait/done)
    VALUE: <text to type or URL>            (optional)
    REASON: <why this action>               (optional, for logging)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BrowserAction:
    action_type: str          # click | fill | goto | scroll | wait | done | error
    selector: Optional[str] = None
    value: Optional[str] = None
    reason: Optional[str] = None
    raw: str = ""


def parse_action(llm_output: str) -> BrowserAction:
    """
    Parse LLM output into a BrowserAction.
    Robust — handles extra whitespace, mixed case, markdown fences.
    """
    # Strip markdown fences if model wraps in ```
    text = re.sub(r"```[a-z]*", "", llm_output).strip()

    def extract(key: str) -> Optional[str]:
        pattern = rf"(?i)^{key}\s*:\s*(.+)$"
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1).strip() if match else None

    action_type = (extract("ACTION") or "error").lower().strip()
    selector    = extract("SELECTOR")
    value       = extract("VALUE")
    reason      = extract("REASON")

    # Normalise aliases
    if action_type in ("navigate", "open", "visit"):
        action_type = "goto"
    if action_type in ("type", "input", "enter"):
        action_type = "fill"
    if action_type in ("press", "tap", "click"):
        action_type = "click"
    if action_type in ("finish", "complete", "stop"):
        action_type = "done"

    return BrowserAction(
        action_type=action_type,
        selector=selector,
        value=value,
        reason=reason,
        raw=llm_output,
    )
