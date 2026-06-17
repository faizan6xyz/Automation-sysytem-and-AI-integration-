import json
import os
import glob
import re
import requests
import time
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)
NIM_MODEL    = "meta/llama-3.1-8b-instruct"
MCP_BASE     = "http://localhost:3000/mcp"


# ── Robust Snapshot Finding Utilities ─────────────────────────────────────────

def extract_snapshot_path(text: str) -> str | None:
    """Extract the snapshot file path from markdown link like [Snapshot](.playwright-mcp\page-xxx.yml)"""
    match = re.search(r'\[Snapshot\]\(([^)]+)\)', text)
    if match:
        return match.group(1)
    return None

def find_and_read_snapshot_file(filename: str) -> str:
    """Search for a specific snapshot file in .playwright-mcp folders."""
    current_dir = os.getcwd()
    while True:
        candidate = os.path.join(current_dir, ".playwright-mcp", filename)
        if os.path.exists(candidate):
            # Wait briefly to ensure file is fully written
            time.sleep(0.2) 
            with open(candidate, "r", encoding="utf-8") as f:
                return f.read()
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
    return ""

def find_and_read_latest_snapshot() -> str:
    """Search for the latest snapshot file in .playwright-mcp folders."""
    current_dir = os.getcwd()
    latest_file = None
    latest_mtime = 0
    
    while True:
        pattern = os.path.join(current_dir, ".playwright-mcp", "page-*.yml")
        files = glob.glob(pattern)
        for f in files:
            mtime = os.path.getmtime(f)
            if mtime > latest_mtime:
                latest_mtime = mtime
                latest_file = f
        
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
        
    if latest_file:
        print(f"    [found snapshot file: {latest_file}]")
        time.sleep(0.2) # Ensure file write completion
        with open(latest_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""


class MCPClient:
    def __init__(self, base_url: str = MCP_BASE):
        self.base_url    = base_url
        self._req_id     = 0
        self._session_id = None
        self._tools      = []

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json",
             "Accept": "application/json, text/event-stream"}
        if self._session_id:
            h["mcp-session-id"] = self._session_id
        return h

    def _parse_sse(self, text: str) -> dict:
        results = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
                if "error" in data:
                    raise RuntimeError(f"MCP error: {data['error']}")
                r = data.get("result", {})
                if r:
                    results.append(r)
            except json.JSONDecodeError:
                continue
        if not results:
            return {}
        merged = {}
        for r in results:
            merged.update(r)
        return merged

    def _do_post(self, payload: dict) -> requests.Response:
        return requests.post(
            self.base_url, json=payload,
            headers=self._headers(), timeout=30
        )

    def _handshake(self):
        payload = {
            "jsonrpc": "2.0", "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nim-browser-agent", "version": "1.0"},
            }
        }
        resp = self._do_post(payload)
        resp.raise_for_status()
        if "mcp-session-id" in resp.headers:
            self._session_id = resp.headers["mcp-session-id"]
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._do_post(notif)
        print(f"[MCP] Session: {self._session_id}")

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
        if params:
            payload["params"] = params
        resp = self._do_post(payload)
        if resp.status_code == 404:
            print("[MCP] 404 — reconnecting...")
            self._session_id = None
            self._handshake()
            resp = self._do_post(payload)
        resp.raise_for_status()
        if "mcp-session-id" in resp.headers:
            self._session_id = resp.headers["mcp-session-id"]
        return self._parse_sse(resp.text)

    def _coerce_args(self, arguments: dict, tool_name: str) -> dict:
        if tool_name == "browser_snapshot":
            arguments.pop("filename", None)
        schema = next(
            (t["function"]["parameters"] for t in self._tools
             if t["function"]["name"] == tool_name), {}
        )
        props = schema.get("properties", {})
        coerced = {}
        for k, v in arguments.items():
            etype = props.get(k, {}).get("type")
            if etype == "boolean" and isinstance(v, str):
                coerced[k] = v.lower() == "true"
            elif etype == "number" and isinstance(v, str):
                coerced[k] = float(v)
            elif etype == "integer" and isinstance(v, str):
                coerced[k] = int(v)
            else:
                coerced[k] = v
        return coerced

    def start(self):
        self._handshake()
        print("[MCP] Handshake complete.")

    def stop(self):
        print("[MCP] Done.")

    def list_tools(self) -> list[dict]:
        if self._tools:
            return self._tools
        result = self._rpc("tools/list")
        allowed = {
            "browser_navigate", "browser_snapshot", "browser_type",
            "browser_click", "browser_press_key", "browser_wait_for",
            "browser_scroll", "browser_navigate_back",
        }
        raw = [t for t in result.get("tools", []) if t["name"] in allowed]
        self._tools = [
            {"type": "function", "function": {
                "name":        t["name"],
                "description": t.get("description", ""),
                "parameters":  t.get("inputSchema", {"type": "object", "properties": {}}),
            }}
            for t in raw
        ]
        print(f"[MCP] {len(self._tools)} tools exposed to LLM: "
              f"{[t['function']['name'] for t in self._tools]}")
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> str:
        arguments = self._coerce_args(arguments, name)
        print(f"    coerced: {json.dumps(arguments)[:200]}")
        
        try:
            result  = self._rpc("tools/call", {"name": name, "arguments": arguments})
        except Exception as e:
            print(f"    [RPC Error]: {e}")
            return f"### Error\n{str(e)}"

        content = result.get("content", [])
        
        parts = []
        for c in content:
            if c.get("type") == "text":
                parts.append(c["text"])
            elif c.get("type") == "resource" and "resource" in c:
                res_text = c["resource"].get("text", "")
                if res_text:
                    parts.append(res_text)
        text = "\n".join(parts) if parts else ""
        
        if name == "browser_snapshot":
            if text and len(text) > 20 and not text.startswith("### Snapshot"):
                return text
            
            if text:
                path = extract_snapshot_path(text)
                if path:
                    filename = os.path.basename(path)
                    file_content = find_and_read_snapshot_file(filename)
                    if file_content:
                        return file_content
            
            return find_and_read_latest_snapshot() or "Snapshot empty."
            
        return text if text else "OK"


PICKER_PROMPT = """You are given an accessibility tree snapshot of a webpage.
Find the actual SEARCH INPUT field where a user types text. 
Look for elements with roles like 'combobox', 'textbox', 'searchbox', or 'input'.
DO NOT pick container elements like 'search', 'form', 'region', or 'generic'.

Reply with ONLY the ref value, nothing else. Example reply: e42
If you cannot find it, reply: NONE
"""

def pick_search_ref(snapshot: str) -> str | None:
    response = client.chat.completions.create(
        model    = NIM_MODEL,
        messages = [
            {"role": "system",  "content": PICKER_PROMPT},
            {"role": "user",    "content": snapshot[:15000]},
        ],
        max_tokens  = 10,
        temperature = 0,
    )
    ref = response.choices[0].message.content.strip().strip('"').strip("'")
    print(f"    [LLM picked ref]: {ref}")
    return None if ref.upper() == "NONE" else ref


CONFIRM_PROMPT = """You are given an accessibility tree snapshot of a webpage after a search.
Did the search succeed? Look for signs of success such as:
- A list of search results.
- The actual article/content page for the query.
Reply with one word: YES or NO
"""

def confirm_success(snapshot: str, query: str) -> bool:
    response = client.chat.completions.create(
        model    = NIM_MODEL,
        messages = [
            {"role": "system",  "content": CONFIRM_PROMPT},
            {"role": "user",    "content": f"Query was: {query}\n\nSnapshot:\n{snapshot[:8000]}"},
        ],
        max_tokens  = 5,
        temperature = 0,
    )
    ans = response.choices[0].message.content.strip().upper()
    print(f"    [LLM success check]: {ans}")
    return ans.startswith("Y")


def run_agent(goal: str, start_url: str):
    mcp = MCPClient()
    mcp.start()
    mcp.list_tools()

    print(f"\nGoal : {goal}")
    print(f"URL  : {start_url}")
    print("=" * 60)

    # ── Step 1: Navigate ─────────────────────────────────────────────────────
    print("\n--- Step 1: Navigate ---")
    nav_result = mcp.call_tool("browser_navigate", {"url": start_url})
    print(f"  ↩ {nav_result[:200]}")

    # ── Step 2: Post-Login Stabilization ──────────────────────────────────────
    # CRITICAL: After login, the DOM changes completely. We must wait for stability.
    print("\n--- Step 2: Stabilize & Snapshot ---")
    print("  Waiting for page to stabilize after navigation/login...")
    mcp.call_tool("browser_wait_for", {"time": 5}) 
    
    # Force a fresh snapshot capture
    snapshot = mcp.call_tool("browser_snapshot", {})
    
    # Fallbacks if direct capture fails
    if not snapshot or snapshot == "Snapshot empty.":
        path = extract_snapshot_path(nav_result)
        if path:
            snapshot = find_and_read_snapshot_file(os.path.basename(path))
            
    if not snapshot or snapshot == "Snapshot empty.":
        snapshot = find_and_read_latest_snapshot()

    if not snapshot or snapshot == "Snapshot empty.":
        print("STUCK: Could not get page snapshot after stabilization.")
        mcp.stop()
        return

    print(f"  [snapshot: {len(snapshot)} chars]")
    print(f"  preview:\n{snapshot[:600]}\n...")

    # ── Step 3: LLM picks the search box ref ─────────────────────────────────
    print("\n--- Step 3: Find search ref ---")
    ref = pick_search_ref(snapshot)

    if not ref:
        print("Could not find search box. Trying browser_press_key '/'...")
        mcp.call_tool("browser_press_key", {"key": "/"})
        mcp.call_tool("browser_wait_for", {"time": 2})
        snapshot = mcp.call_tool("browser_snapshot", {})
        ref = pick_search_ref(snapshot)

    if not ref:
        print("STUCK: Could not locate search input.")
        mcp.stop()
        return

    query = goal.lower().replace("search", "").replace("on youtube", "") \
                .replace("on wikipedia", "").replace("on google", "").strip()
    print(f"  Query: {query!r}  →  ref: {ref}")

    # ── Step 4: Type and submit ───────────────────────────────────────────────
    print("\n--- Step 4: Type and submit ---")
    
    def attempt_type(target_ref, query_text):
        type_result = mcp.call_tool("browser_type", {
            "element": "search input",
            "target":  target_ref,
            "text":    query_text,
            "submit":  True,
            "slowly":  False,
        })
        return type_result

    type_result = attempt_type(ref, query)
    print(f"  ↩ {type_result[:200]}")

    # --- ROBUST ERROR RECOVERY ---
    if "Error" in type_result or "404" in type_result:
        print("  ⚠️ Action failed. Re-snapshotting to recover state...")
        mcp.call_tool("browser_wait_for", {"time": 3})
        
        snapshot = mcp.call_tool("browser_snapshot", {})
        if not snapshot or snapshot == "Snapshot empty.":
             snapshot = find_and_read_latest_snapshot()
             
        if snapshot:
            print("  [New snapshot captured. Re-evaluating target...]")
            new_ref = pick_search_ref(snapshot)
            
            if new_ref and new_ref != ref:
                print(f"  [Ref updated: {ref} -> {new_ref}]")
                ref = new_ref
                print("  [Retrying action...]")
                type_result = attempt_type(ref, query)
                print(f"  ↩ Retry: {type_result[:200]}")
            elif new_ref == ref:
                print("  [Ref unchanged. Attempting click-to-focus before retry...]")
                mcp.call_tool("browser_click", {"element": "search area", "target": ref})
                mcp.call_tool("browser_wait_for", {"time": 1})
                type_result = attempt_type(ref, query)
                print(f"  ↩ Retry after click: {type_result[:200]}")
            else:
                print("  ❌ Could not find input field in new snapshot.")
        else:
            print("  ❌ Failed to capture new snapshot for recovery.")

    mcp.call_tool("browser_wait_for", {"time": 3})

    # ── Step 5: Confirm results ───────────────────────────────────────────────
    print("\n--- Step 5: Confirm results ---")
    result_snapshot = mcp.call_tool("browser_snapshot", {})
    print(f"  [snapshot: {len(result_snapshot)} chars]")
    print(f"  preview:\n{result_snapshot[:600]}")

    if confirm_success(result_snapshot, query):
        print(f"\n{'='*60}")
        print(f"GOAL ACHIEVED: Searched '{query}' successfully.")
        print(f"{'='*60}")
    else:
        print("\nResults unclear — check the browser window.")

    mcp.stop()


if __name__ == "__main__":
    goal      = input("Enter your goal : ").strip()
    start_url = input("Starting URL    : ").strip()
    run_agent(goal, start_url)