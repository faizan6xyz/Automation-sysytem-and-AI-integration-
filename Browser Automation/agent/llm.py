# agent/llm.py
"""
Local HuggingFace LLM wrapper.
Loads Qwen2.5-3B-Instruct directly from disk — no internet, no token.
"""
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from rich.console import Console
from config.settings import HF_MODEL
console = Console()
class HFAgent:
    def __init__(self):
        self.model_path = HF_MODEL
        self.pipe = None
        self._load()
    def _load(self):
        console.print(f"[bold cyan]Loading model from:[/]\n  {self.model_path}")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype  = torch.float16 if device == "cuda" else torch.float32
        console.print(f"[bold cyan]Device:[/] {device}  |  dtype: {dtype}")
        # local_files_only=True  → never ping the internet
        # trust_remote_code=True → needed for Qwen
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            local_files_only=True,
            trust_remote_code=True,
        )
        model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=dtype,
            device_map="auto",
            local_files_only=True,
            trust_remote_code=True,
        )
        self.pipe = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            max_new_tokens=256,
            do_sample=False,
            temperature=None,
            top_p=None,
        )
        console.print("[bold green]Model ready.[/]")
    def chat(self, system_prompt: str, user_prompt: str) -> str:
        """Send a chat prompt, return only the assistant reply."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ]
        try:
            formatted = self.pipe.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            result    = self.pipe(formatted)
            generated = result[0]["generated_text"]

            # Strip the input prompt — keep only new tokens
            if formatted in generated:
                generated = generated[len(formatted):].strip()
        except Exception:
            prompt = (
                f"<|system|>\n{system_prompt}\n"
                f"<|user|>\n{user_prompt}\n"
                f"<|assistant|>\n"
            )
            result    = self.pipe(prompt)
            generated = result[0]["generated_text"]
            if "<|assistant|>" in generated:
                generated = generated.split("<|assistant|>")[-1].strip()
        return generated
