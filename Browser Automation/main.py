# main.py
"""
Browser Agent — Entry Point
Usage:
    python main.py
    python main.py --task "Search for Qwen2.5 on DuckDuckGo"
    python main.py --task "Find weather of Delhi" --url "https://duckduckgo.com"
"""
import asyncio
import argparse
from agent.browser_agent import BrowserAgent
def parse_args():
    parser = argparse.ArgumentParser(description="AI Browser Agent")
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        help="Task for the agent to complete",
    )
    parser.add_argument(
        "--url",
        type=str,
        default="https://www.duckduckgo.com",   # DuckDuckGo — no bot detection
        help="Starting URL (default: https://www.duckduckgo.com)",
    )
    return parser.parse_args()
EXAMPLE_TASKS = [
    "Search for 'weather of Delhi' and tell me the result",
    "Search for 'Qwen2.5 model' and tell me the first result title",
    "Go to github.com and find the trending repositories",
    "Go to Wikipedia and search for 'Transformer neural network'",
    "Go to news.ycombinator.com and find the top story",
]
async def main():
    args = parse_args()
    if args.task is None:
        print("\nExample tasks:")
        for i, t in enumerate(EXAMPLE_TASKS, 1):
            print(f"  {i}. {t}")
        print()
        task = input("Enter your task (or pick a number): ").strip()
        if task.isdigit() and 1 <= int(task) <= len(EXAMPLE_TASKS):
            task = EXAMPLE_TASKS[int(task) - 1]
    else:
        task = args.task
    agent = BrowserAgent()
    await agent.run(task=task, start_url=args.url)
if __name__ == "__main__":
    asyncio.run(main())