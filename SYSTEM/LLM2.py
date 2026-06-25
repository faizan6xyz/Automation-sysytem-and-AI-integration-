import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TextStreamer
from RAG_Load import retrieve
model_name = "Qwen/Qwen2.5-3B-Instruct"
print("Loading Qwen Model...")
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name, 
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16, 
    device_map="auto"
)
streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
print("Model loaded.\n")
HISTORY_FILE = "SYSTEM/chat_history.json" 
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        messages = json.loads(content) if content else []
else:
    messages = [{"role": "system", "content": "You are a helpful AI assistant. Answer clearly and use the provided context when available."}]
print("Assistant ready.")
print("Type 'exit' to quit.\n")
SCORE_THRESHOLD = 0.06 
while True:
    user_input = input("You: ")
    if user_input.lower() == "exit":
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=2, ensure_ascii=False)
        print("Conversation saved.")
        break
    retrieved = retrieve(user_input)
    if retrieved:
        retrieved_chunks = [item['text'] for item in retrieved]
        top_score = max(item['score'] for item in retrieved)
        if retrieved_chunks:
            context = "\n\n".join(retrieved_chunks)
            print(f"[RAG Active | Found {len(retrieved_chunks)} chunks | Top Score: {top_score:.4f}]")
            rag_prompt = (
                f"Context:\n{context}\n\n"
                f"Question: {user_input}\n\n"
                f"Answer:"
            )
        else:
            print("[RAG Skipped - No relevant chunks found]")
            rag_prompt = user_input
    else:
        print("[RAG Skipped - No results]")
        rag_prompt = user_input
    messages.append({"role": "user", "content": rag_prompt})
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=300,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.05,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
            streamer=streamer
        )
    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
    print()
    messages[-1] = {"role": "user", "content": user_input}
    messages.append({"role": "assistant", "content": response})
    if len(messages) > 21:
        messages = [messages[0]] + messages[-20:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)