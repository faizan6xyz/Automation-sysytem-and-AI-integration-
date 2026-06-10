# Browser Agent — Accessibility Tree + HuggingFace LLM

A local AI browser agent that uses **Playwright's Accessibility Tree** as its
"eyes" and any **HuggingFace model** as its brain.

## Architecture

```
Task
 │
 ▼
┌──────────────────────────────┐
│  Observe: Accessibility Tree │  ← Playwright reads page structure
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Think: HuggingFace LLM      │  ← Qwen2.5 (or any model) decides next action
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Act: Playwright             │  ← click / fill / goto / scroll
└──────────────┬───────────────┘
               │
            (repeat)
```

## Project Structure

```
browser_agent/
├── main.py                   ← entry point
├── requirements.txt
├── .env                      ← your HF token + model name
├── agent/
│   ├── browser_agent.py      ← core observe→think→act loop
│   └── llm.py                ← HuggingFace model wrapper
├── utils/
│   ├── accessibility.py      ← accessibility tree extractor
│   └── parser.py             ← LLM output → structured action
└── config/
    └── settings.py           ← loads .env
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure `.env`
```env
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx     # your HuggingFace token
HF_MODEL=Qwen/Qwen2.5-3B-Instruct   # or any instruct model
MAX_STEPS=15
HEADLESS=False
```

### 3. Run
```bash
# Interactive menu
python main.py

# Direct task
python main.py --task "Search for transformers library on Google"

# With custom starting URL
python main.py --task "Find the README" --url "https://github.com/huggingface/transformers"
```

## How it Works

### Accessibility Tree (why it's better than HTML)

Instead of dumping raw HTML into the LLM (which is huge and noisy), the agent
reads the **accessibility tree** — a structured list of interactive elements:

```
[main]
  [heading] "Google Search"
  [form]
    [searchbox] "Search" 
    [button] "Google Search"
    [button] "I'm Feeling Lucky"
```

This is compact, clean, and directly tells the LLM what it can interact with.

### LLM Output Format

The LLM always responds in this format:
```
ACTION: fill
SELECTOR: Search
VALUE: Qwen2.5 model
REASON: Need to type the search query into the search box
```

### Supported Actions

| Action | What it does |
|--------|-------------|
| `goto` | Navigate to a URL |
| `click` | Click a button or link |
| `fill` | Type text into an input |
| `scroll` | Scroll down the page |
| `wait` | Wait 2 seconds |
| `done` | Task complete, stop |

## Switching Models

Change `HF_MODEL` in `.env` to any instruct model:

```env
HF_MODEL=mistralai/Mistral-7B-Instruct-v0.3
HF_MODEL=google/gemma-2-2b-it
HF_MODEL=microsoft/Phi-3-mini-4k-instruct
HF_MODEL=Qwen/Qwen2.5-3B-Instruct        # recommended for RTX 2050
```

## Tips for RTX 2050 (4GB VRAM)

- Use `Qwen2.5-3B-Instruct` or `Phi-3-mini` — they fit in 4GB
- Set `MAX_STEPS=10` to avoid long runs
- Set `HEADLESS=False` to watch what's happening
- If OOM, add `load_in_4bit=True` in `agent/llm.py`
