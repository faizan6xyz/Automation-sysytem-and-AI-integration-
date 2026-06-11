import json
import re
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer
from RAG_Load import retrieve
def web_search(query: str) -> str:
    """Call your browser agent / DuckDuckGo / SerpAPI here."""
    from duckduckgo_search import DDGS
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=3))
    if not results:
        return "No results found."
    return "\n".join([f"- {r['title']}: {r['body']}" for r in results])
def rag_search(query: str) -> str:
    """Your existing RAG retrieve."""
    retrieved = retrieve(query)
    chunks = [chunk for chunk, score in retrieved]
    return "\n\n".join(str(c) for c in chunks)

def calculate(expression: str) -> str:
    try:
        return str(eval(expression))
    except Exception as e:
        return f"Error: {e}"
TOOLS = {
    "web_search": web_search,
    "rag_search": rag_search,
    "calculate":  calculate,
}
TOOL_SYSTEM_PROMPT = """You are a helpful assistant with access to these tools:

1. web_search(query: str)
   Use when: user wants to search the web, research a topic, find recent news,
             look something up online, or asks about current events.
   Example triggers: "search for X", "research X", "look up X", "find info about X",
                     "what are the latest X", "I want to know about X"

2. rag_search(query: str)  
   Use when: user asks about documents, uploaded files, or company-specific knowledge.
   Example triggers: "what does our policy say", "find in the documents", "check the files"

3. calculate(expression: str)
   Use when: user wants a mathematical calculation.
   Example triggers: "calculate", "what is 2+2", "solve"

IMPORTANT RULES:
- If a tool is needed, respond ONLY with a JSON block like this:
  {"tool": "web_search", "arguments": {"query": "your search query"}}
- Do NOT add any text before or after the JSON when calling a tool.
- If no tool is needed, respond normally in plain text.
- Only call ONE tool per response.
"""
def parse_tool_call(text: str):
    """Extract tool call JSON from LLM output. Returns dict or None."""
    # find JSON block in the response
    match = re.search(r'\{.*\}', text.strip(), re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        if "tool" in data and "arguments" in data:
            return data
    except json.JSONDecodeError:
        pass
    return None
def execute_tool(tool_call: dict) -> str:
    tool_name = tool_call["tool"]
    args      = tool_call["arguments"]

    if tool_name not in TOOLS:
        return f"Unknown tool: {tool_name}"

    print(f"[Tool called: {tool_name}({args})]")
    result = TOOLS[tool_name](**args)
    print(f"[Tool result preview: {result[:100]}...]")
    return result
model_name = "Qwen/Qwen2.5-3B-Instruct"
tokenizer  = AutoTokenizer.from_pretrained(model_name)
model      = AutoModelForCausalLM.from_pretrained(
    model_name,
    dtype=torch.float16,
    device_map="auto"
)
messages = [{"role": "system", "content": TOOL_SYSTEM_PROMPT}]
print("Assistant ready. Type 'exit' to quit.\n")
SCORE_THRESHOLD = 0.8
while True:
    user_input = input("You: ").strip()
    if user_input.lower() == "exit":
        break
    messages.append({"role": "user", "content": user_input})
    prompt  = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs  = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=150,       # tool calls are short
            do_sample=False,          # greedy — more reliable JSON
            temperature=None,
            top_p=None,
            repetition_penalty=1.1,
            eos_token_id=tokenizer.eos_token_id,
        )
    llm_response = tokenizer.decode(
        outputs[0][inputs.input_ids.shape[1]:],
        skip_special_tokens=True
    ).strip()
    print(f"[LLM raw]: {llm_response}")
    tool_call = parse_tool_call(llm_response)
    if tool_call:
        tool_result = execute_tool(tool_call)
        messages[-1] = {"role": "user", "content": user_input}
        messages.append({
            "role": "assistant",
            "content": llm_response
        })
        messages.append({
            "role": "user",
            "content": f"Tool result:\n{tool_result}\n\nNow answer the user's question using this result."
        })
        prompt2 = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs2 = tokenizer(prompt2, return_tensors="pt").to(model.device)
        streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
        print("Assistant: ", end="", flush=True)
        final_outputs = model.generate(
            **inputs2,
            max_new_tokens=400,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.1,
            eos_token_id=tokenizer.eos_token_id,
            streamer=streamer,
        )
        final_response = tokenizer.decode(
            final_outputs[0][inputs2.input_ids.shape[1]:],
            skip_special_tokens=True
        ).strip()
        messages.pop()   # remove "Tool result: ..."
        messages.pop()   # remove LLM's JSON response
        messages[-1] = {"role": "user", "content": user_input}
        messages.append({"role": "assistant", "content": final_response})
    else:
        retrieved  = retrieve(user_input)
        top_score  = max(score for _, score in retrieved)
        if top_score >= SCORE_THRESHOLD and not tool_call:
            chunks  = [chunk for chunk, _ in retrieved]
            context = "\n\n".join(str(c) for c in chunks)
            print(f"[RAG active — score: {top_score:.4f}]")
            rag_msg = messages[:-1] + [{
                "role": "user",
                "content": (
                    f"Context:\n{context}\n\n"
                    f"Question: {user_input}"
                )
            }]
            prompt_rag = tokenizer.apply_chat_template(
                rag_msg, tokenize=False, add_generation_prompt=True
            )
            inputs_rag = tokenizer(prompt_rag, return_tensors="pt").to(model.device)
            streamer   = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

            print("Assistant: ", end="", flush=True)
            rag_outputs = model.generate(
                **inputs_rag,
                max_new_tokens=400,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.1,
                eos_token_id=tokenizer.eos_token_id,
                streamer=streamer,
            )
            final_response = tokenizer.decode(
                rag_outputs[0][inputs_rag.input_ids.shape[1]:],
                skip_special_tokens=True
            ).strip()
        else:
            print(f"[RAG skipped — score: {top_score:.4f}]")
            print("Assistant: ", end="", flush=True)
            streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
            final_outputs = model.generate(
                **inputs,
                max_new_tokens=400,
                do_sample=True,
                temperature=0.7,
                top_p=0.9,
                repetition_penalty=1.1,
                eos_token_id=tokenizer.eos_token_id,
                streamer=streamer,
            )
            final_response = tokenizer.decode(
                final_outputs[0][inputs.input_ids.shape[1]:],
                skip_special_tokens=True
            ).strip()

        messages[-1] = {"role": "user",      "content": user_input}
        messages.append({"role": "assistant", "content": final_response})
    if len(messages) > 21:
        messages = [messages[0]] + messages[-20:]
    print()