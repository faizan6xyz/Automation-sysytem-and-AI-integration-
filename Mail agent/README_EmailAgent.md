# Email Agent

An AI-powered email assistant built on **NVIDIA NIM (Llama 3.1-8B)**. Manage your Gmail inbox using plain English — read, search, and send emails with or without attachments.

---

## Features

- **Read emails** — fetch and summarize your latest inbox messages
- **Search emails** — find emails by subject keyword
- **Send emails** — compose and send with optional file attachments
- **Natural language interface** — just describe what you want done
- **Step-by-step reasoning** — the agent thinks before acting, up to 10 steps

---

## Prerequisites

- Python 3.8+
- A Gmail account with **App Password** enabled (not your regular password)
- An [NVIDIA NIM API key](https://integrate.api.nvidia.com)

---

## Installation

```bash
pip install openai
```

> The standard library modules `smtplib`, `imaplib`, and `email` are built into Python — no extra install needed.

---

## Gmail Setup (Required)

Gmail blocks direct password login. You must generate an **App Password**:

1. Go to your Google Account → **Security**
2. Enable **2-Step Verification** (required)
3. Go to **Security → App Passwords**
4. Select app: *Mail*, device: *Other* → click **Generate**
5. Copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)

Then update these constants in `email_agent.py`:

```python
EMAIL_ADDRESS  = "you@gmail.com"
EMAIL_PASSWORD = "xxxx xxxx xxxx xxxx"   # App password, not your real password
```

---

## Configuration

```python
NVIDIA_API_KEY = "your-nvidia-nim-api-key"
EMAIL_ADDRESS  = "you@gmail.com"
EMAIL_PASSWORD = "your-app-password"
NIM_MODEL      = "meta/llama-3.1-8b-instruct"
```

---

## Usage

Edit the last line of `email_agent.py` and run:

```bash
python email_agent.py
```

### Example Goals

```python
# Read and summarize latest emails
run_email_agent("Read my last 3 emails and give me a summary")

# Send a plain email
run_email_agent("Send an email to friend@gmail.com saying I'll be late to the meeting")

# Send with a single attachment
run_email_agent(
    "Send an email to boss@gmail.com with subject 'Monthly Report' "
    "and attach the file C:/Users/you/report.pdf"
)

# Send with multiple attachments
run_email_agent(
    "Send an email to team@gmail.com saying here are this week's files, "
    "and attach C:/Users/you/data.csv and C:/Users/you/notes.docx"
)

# Search for emails
run_email_agent("Search my inbox for emails about 'invoice'")
```

---

## Available Tools

| Tool | Parameters | Description |
|---|---|---|
| `send_email` | `to`, `subject`, `body`, `attachments` *(optional)* | Sends an email via Gmail SMTP |
| `read_emails` | `folder` *(default: INBOX)*, `limit` *(default: 5)* | Fetches and returns recent emails |
| `search_emails` | `keyword` | Searches inbox by subject keyword |

---

## How It Works

### The Agent Loop

```
User provides a plain-English goal
             │
             ▼
  Build message history
  [system prompt + user goal]
             │
             ▼
     LLM decides next action
             │
      ┌──────┴──────┐
      │             │
   TOOL call    FINAL ANSWER
      │             │
  Parse tool     Print result
  name + args       │
      │            Done ✓
  Execute tool
      │
  Append to history:
  assistant → tool call
  user      → tool result
      │
  Repeat (max 10 steps)
```

---

### Step-by-Step Internals

#### 1. System Prompt
The agent is given a fixed system prompt that defines:
- Which tools exist and what parameters they take
- The exact text format it must respond in (`TOOL:` / `INPUT:` or `FINAL ANSWER:`)
- Examples for sending with and without attachments

#### 2. LLM Response Parsing (`parse_response`)
Every reply from the LLM is checked for one of three patterns:

| Pattern | Meaning | What happens |
|---|---|---|
| Contains `FINAL ANSWER:` | Task is complete | Print answer and stop |
| Contains `TOOL:` and `INPUT:` | Agent wants to call a tool | Parse and execute the tool |
| Neither | Malformed response | Stop the loop |

The tool name is extracted from after `TOOL:` and the JSON args from after `INPUT:`.

#### 3. Tool Execution
Each tool maps to a Python function:

**`send_email`**
- Builds a `MIMEMultipart` message
- Attaches files using `MIMEBase` + base64 encoding (skips missing files with a warning)
- Connects to `smtp.gmail.com:465` over SSL and sends

**`read_emails`**
- Connects to `imap.gmail.com` over SSL
- Selects the folder (default: `INBOX`)
- Fetches the last N message IDs, then fetches each full message
- Extracts `From`, `Subject`, and the first 300 chars of the plain-text body
- Returns all emails joined by `---` separators

**`search_emails`**
- Same IMAP connection as above
- Uses IMAP's native `SUBJECT "keyword"` search command
- Returns the last 5 matching emails (From + Subject only)

#### 4. Conversation History
The agent maintains a running message list across steps:

```
[system prompt]
[user: original goal]
[assistant: TOOL: read_emails / INPUT: {...}]
[user: Tool result: From: ... Subject: ...]
[assistant: FINAL ANSWER: Here is your summary...]
```

Each tool result is fed back as a `user` message so the LLM can reason about it before deciding the next action. This is what makes it an *agent* rather than a single-shot call.

#### 5. Stopping Conditions
The loop ends when any of these occur:
- The LLM responds with `FINAL ANSWER:` → success
- A response can't be parsed → unknown format, stop
- 10 steps are reached → max steps exceeded, stop

---

### Send Email — Attachment Flow

```
For each file path in attachments:
    │
    ├── File exists? ──No──→ Print warning, skip
    │
    └── Yes → Read bytes
             → Wrap in MIMEBase("application", "octet-stream")
             → Base64 encode
             → Add Content-Disposition header with filename
             → Attach to message
```

All attachments are sent in a single SMTP connection alongside the message body.

---

## Project Structure

```
email_agent.py    # Main application — all logic in one file
```

---

## Security Notes

- **Never commit your API key or app password to version control.** Move them to environment variables or a `.env` file:

```python
import os
EMAIL_ADDRESS  = os.environ["EMAIL_ADDRESS"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
NVIDIA_API_KEY = os.environ["NVIDIA_API_KEY"]
```

- The app password grants full Gmail access — treat it like a real password
- Email bodies are truncated to **300 characters** when reading, to keep LLM context manageable
- The agent fetches at most the **last 5 emails** by default to avoid token overflow

---

## Limitations

- Gmail only (SMTP: `smtp.gmail.com:465`, IMAP: `imap.gmail.com`)
- Searches by **subject line only** — full-body search not supported
- Attachments must be **local file paths** on the machine running the script
- Max **10 reasoning steps** per request before the agent stops
- Read body preview is capped at **300 characters** per email
