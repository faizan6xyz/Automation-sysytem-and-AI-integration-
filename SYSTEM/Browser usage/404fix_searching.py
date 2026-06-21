import json
import os
import glob
import re
import time
import requests
import threading
from openai import OpenAI
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

NIM_MODEL    = "meta/llama-3.1-8b-instruct"
MCP_BASE     = "http://localhost:3000/mcp"

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
            time.sleep(0.2)              # Wait briefly to ensure file is fully written
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

# ---------------------------------------------------------------------------
# LLM PROMPTS & HELPERS
# ---------------------------------------------------------------------------

QUERY_EXTRACT_PROMPT = """Extract just the search query from the user's goal.
Strip away phrases like "search for", "on youtube", "on google", site names, etc.
Reply with ONLY the search query text, nothing else.

Example:
Goal: "search python tutorials on youtube"
Reply: python tutorials

Goal: "find me research papers about transformers"
Reply: research papers about transformers
"""

def extract_query(goal: str) -> str:
    response = client.chat.completions.create(
        model=NIM_MODEL,
        messages=[
            {"role": "system", "content": QUERY_EXTRACT_PROMPT},
            {"role": "user", "content": goal},
        ],
        max_tokens=30,
        temperature=0,
    )
    return response.choices[0].message.content.strip().strip('"')

PICKER_PROMPT = """You are given an accessibility tree snapshot of a webpage.
Find the actual SEARCH INPUT field where a user types text. 
Look for elements with roles like 'combobox', 'textbox', 'searchbox', or 'input'.
DO NOT pick container elements like 'search', 'form', 'region', or 'generic'.

Reply with ONLY the ref value, nothing else. Example reply: e42
If you cannot find it, reply: NONE
"""

def pick_search_ref(snapshot: str) -> str | None:
    # Truncate very large snapshots to save tokens, but keep enough context
    safe_snapshot = snapshot[:15000] if len(snapshot) > 15000 else snapshot
    response = client.chat.completions.create(
        model    = NIM_MODEL,
        messages = [
            {"role": "system",  "content": PICKER_PROMPT},
            {"role": "user",    "content": safe_snapshot},
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
- Video titles matching the query (if YouTube).
Reply with one word: YES or NO
"""

def confirm_success(snapshot: str, query: str) -> bool:
    # Send a larger chunk to ensure we catch the results area
    safe_snapshot = snapshot[:30000] if len(snapshot) > 30000 else snapshot
    response = client.chat.completions.create(
        model    = NIM_MODEL,
        messages = [
            {"role": "system",  "content": CONFIRM_PROMPT},
            {"role": "user",    "content": f"Query was: {query}\n\nSnapshot:\n{safe_snapshot}"},
        ],
        max_tokens  = 5,
        temperature = 0,
    )
    ans = response.choices[0].message.content.strip().upper()
    print(f"    [LLM success check]: {ans}")
    return ans.startswith("Y")

class MCPClient:
    def __init__(self, base_url: str = MCP_BASE):
        self.base_url    = base_url
        self._req_id     = 0
        self._session_id = None
        self._tools      = []
        self._lock       = threading.Lock()
        
        # Keepalive management
        self._keepalive_thread = None
        self._stop_keepalive = threading.Event()

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
        with self._lock:
            payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method}
            if params:
                payload["params"] = params
            
            print(f"[DEBUG] Sending '{method}' with session ID: {self._session_id}")

            for attempt in range(3):
                resp = self._do_post(payload)

                if resp.status_code == 404:
                    print(f"[DEBUG] 404 received for '{method}' (attempt {attempt+1}). Body: {resp.text[:200]}")
                    
                    if attempt < 2:
                        print("[MCP] 404 — reconnecting...")
                        self._session_id = None
                        self._handshake()
                        print(f"[DEBUG] Retrying '{method}' with new session ID: {self._session_id}")
                        continue
                    else:
                        raise RuntimeError(f"Session expired after retries")
                
                resp.raise_for_status()
                
                if "mcp-session-id" in resp.headers:
                    new_id = resp.headers["mcp-session-id"]
                    if new_id != self._session_id:
                        self._session_id = new_id
                        
                return self._parse_sse(resp.text)
            
            raise RuntimeError(f"Failed to complete {method}")

    def _keepalive_loop(self):
        while not self._stop_keepalive.is_set():
            try:
                self._rpc("ping", {})
            except Exception:
                pass
            self._stop_keepalive.wait(timeout=3)  # Ping every 3 seconds

    def start(self):
        self._handshake()
        self._stop_keepalive.clear()
        self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
        self._keepalive_thread.start()
        print("[MCP] Handshake complete.")

    def stop(self):
        self._stop_keepalive.set()
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=5)
        print("[MCP] Done.")

    def pause_keepalive(self):
        """Temporarily stop keepalive pings during heavy operations"""
        self._stop_keepalive.set()
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=2)

    def resume_keepalive(self):
        """Resume keepalive pings"""
        self._stop_keepalive.clear()
        if not self._keepalive_thread or not self._keepalive_thread.is_alive():
            self._keepalive_thread = threading.Thread(target=self._keepalive_loop, daemon=True)
            self._keepalive_thread.start()

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

    def call_tool(self, name: str, arguments: dict) -> str:
        arguments = self._coerce_args(arguments, name)
        print(f"    [Tool Call] {name}: {json.dumps(arguments)[:200]}")
        
        try:
            result = self._rpc("tools/call", {"name": name, "arguments": arguments})
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
            # If the MCP server returns a reference to a file, read it
            if text and len(text) > 20 and not text.startswith("### Snapshot"):
                # Check if it's a markdown link to a file
                path = extract_snapshot_path(text)
                if path:
                    filename = os.path.basename(path)
                    file_content = find_and_read_snapshot_file(filename)
                    if file_content:
                        return file_content   
            
            # Fallback to finding the latest file if content is empty or just a link
            if not text or text.startswith("### Snapshot") or extract_snapshot_path(text):
                local_snap = find_and_read_latest_snapshot()
                if local_snap:
                    return local_snap
                    
        return text if text else "OK"
def run_agent1(goal: str, start_url: str):
    mcp = MCPClient()
    mcp.start()
    mcp.list_tools()
    
    print(f"\nGoal : {goal}")
    print(f"URL  : {start_url}")
    print("=" * 60)

    # --- Step 1: Navigate ---
    print("\n--- Step 1: Navigate ---")
    
    # Pause keepalive during navigation to prevent session conflicts
    mcp.pause_keepalive()
    
    nav_result = mcp.call_tool("browser_navigate", {"url": start_url})
    print(f"  ↩ Nav Result: {nav_result[:100]}...")
    
    mcp.call_tool("browser_wait_for", {"time": 2})
    
    # Resume keepalive now that page is loaded
    mcp.resume_keepalive()

    # --- Step 2: Get Snapshot ---
    print("\n--- Step 2: Snapshot ---")
    mcp.call_tool("browser_wait_for", {"time": 2})
    snapshot = mcp.call_tool("browser_snapshot", {})
    
    # Fallbacks for empty snapshot
    if not snapshot or snapshot == "Snapshot empty.":
        path = extract_snapshot_path(nav_result)
        if path:
            snapshot = find_and_read_snapshot_file(os.path.basename(path))
    if not snapshot or snapshot == "Snapshot empty.":
        snapshot = find_and_read_latest_snapshot()
        
    if not snapshot:
        print("STUCK: Could not get page snapshot.")
        mcp.stop()
        return

    # --- Step 3: Find search ref ---
    print("\n--- Step 3: Find search ref ---")
    ref = pick_search_ref(snapshot)
    
    if not ref:
        print("Could not find search box. Trying '/' key shortcut...")
        mcp.call_tool("browser_press_key", {"key": "/"})
        mcp.call_tool("browser_wait_for", {"time": 1})
        snapshot = mcp.call_tool("browser_snapshot", {})
        ref = pick_search_ref(snapshot)
        
    if not ref:
        print("STUCK: Could not locate search input.")
        mcp.stop()
        return

    query = extract_query(goal)
    print(f"  Query: {query!r}  →  ref: {ref}")

    # --- Step 4: Type and submit ---
    print("\n--- Step 4: Type and submit ---")
    
    def attempt_type(target_ref, query_text):
        return mcp.call_tool("browser_type", {
            "element": "search input",
            "target":  target_ref,
            "text":    query_text,
            "submit":  True,
            "slowly":  False,
        })

    type_result = attempt_type(ref, query)
    print(f"  ↩ Type Result: {type_result[:100]}...")

    # Error Recovery
    if "Error" in type_result or "404" in type_result:
        print(" Action failed. Re-snapshotting to recover...")
        mcp.call_tool("browser_wait_for", {"time": 2})
        snapshot = mcp.call_tool("browser_snapshot", {})
        if not snapshot: 
            snapshot = find_and_read_latest_snapshot()
            
        if snapshot:
            new_ref = pick_search_ref(snapshot)
            if new_ref:
                print(f"  [Retrying with new ref: {new_ref}]")
                type_result = attempt_type(new_ref, query)
                print(f"  ↩ Retry: {type_result[:100]}...")

    # IMPORTANT: Wait longer for search results to load
    print("  Waiting for search results to load...")
    mcp.call_tool("browser_wait_for", {"time": 5}) 
    
    # IMPORTANT: Scroll down to trigger loading of video/results in the DOM
    print("  Scrolling down to ensure results are in snapshot...")
    mcp.call_tool("browser_press_key", {"key": "PageDown"})
    mcp.call_tool("browser_wait_for", {"time": 2})

    # --- Step 5: Confirm results ---
    print("\n--- Step 5: Confirm results ---")
    result_snapshot = mcp.call_tool("browser_snapshot", {})
    
    print(f"  [snapshot size: {len(result_snapshot)} chars]")
    # Print a small preview for debugging
    if len(result_snapshot) > 600:
        print(f"  preview:\n{result_snapshot[:600]}...")
    else:
        print(f"  preview:\n{result_snapshot}")

    if confirm_success(result_snapshot, query):
        print(f"\n{'='*60}")
        print(f"GOAL ACHIEVED: Searched '{query}' successfully.")
        print(f"{'='*60}")
    else:
        print("\nResults unclear — check the browser window.")
        print("Hint: The search likely worked, but the LLM didn't see the results in the snapshot.")
        
    mcp.stop()

if __name__ == "__main__":
    goal      = input("Enter your goal : ").strip()
    start_url = input("Starting URL    : ").strip()
    run_agent1(goal, start_url)