import os
from openai import OpenAI

# 1. Configuration
# Get your API key from https://build.nvidia.com/
MODEL_NAME = "meta/llama-3.3-70b-instruct" # Or another suitable reasoning model

# Initialize the client pointing to NVIDIA's NIM endpoint
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="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"
)

def get_next_step(goal, current_state, previous_steps):
    """
    Calls the NVIDIA NIM model to determine the next single action.
    """
    
    # Construct the prompt for the LLM
    system_prompt = """
You are a Browser Automation Planner. You output exactly ONE next step, grounded ONLY in the Current State provided — never guess at elements that aren't mentioned there.

Respond with ONLY a JSON object, no markdown, no explanation, no extra text.

Schema:
{
  "action": "navigate" | "click" | "type" | "wait" | "scroll" | "extract_text" | "finish",
  "target": "<element ref/selector from Current State, or URL for navigate, or null>",
  "value": "<text to type, or null>",
  "description": "<one short plain sentence of what this step does>"
}

Rules:
1. One step only. Never combine actions.
2. Use ONLY elements/refs that appear in Current State. If the needed element isn't visible yet, output a "wait" or "navigate" step instead of guessing.
3. If Current State shows the goal is already satisfied, output action "finish".
4. Keep "description" under 12 words.
5. No commentary outside the JSON object.
"""

    # Build the context of what has happened so far
    steps_history = "\n".join([f"{i+1}. {step}" for i, step in enumerate(previous_steps)]) if previous_steps else "No steps taken yet."
    
    user_prompt = f"""
    Goal: {goal}
    Current State: {current_state}
    Previous Steps Taken:
    {steps_history}

    What is the NEXT single step to take?
    """

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2, # Low temperature for deterministic planning
            max_tokens=150
        )
        
        content = response.choices[0].message.content
        return content.strip()

    except Exception as e:
        print(f"Error calling NVIDIA NIM: {e}")
        return None

def execute_automation(goal, max_steps=10):
    """
    Main loop to generate and print steps one by one.
    """
    print(f"🚀 Starting Automation for Goal: '{goal}'\n")
    
    current_state = "Browser is open on homepage."
    previous_steps = []
    
    for i in range(max_steps):
        print(f"--- Step {i+1} ---")
        
        # Get the next step from the LLM
        next_step_json = get_next_step(goal, current_state, previous_steps)
        
        if not next_step_json:
            print("❌ Failed to get a valid step from the LLM.")
            break
            
        print(f"🤖 LLM Decision: {next_step_json}")
        
        # In a real system, you would parse the JSON and execute the action here
        # For this demo, we just add it to history and simulate state change
        previous_steps.append(next_step_json)
        
        # Simulate checking if the task is finished
        if '"finish"' in next_step_json.lower():
            print("✅ Goal achieved! Automation complete.")
            break
            
        # Update simulated state (in reality, this comes from the browser driver)
        current_state = f"Completed step {i+1}. Ready for next action."
        print(f"🔄 State updated: {current_state}\n")

if __name__ == "__main__":
    # Example usage
    user_goal = "Write a mail to the faizan@gmial.com telling about the global warming effects"
    execute_automation(user_goal)