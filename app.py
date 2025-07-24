# app.py
# This script runs the Flask web server for our RPG.

import os
import json
import requests # Make sure to install this: pip install requests
from flask import Flask, request, jsonify, render_template # Make sure to install this: pip install Flask

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Game Constants ---
GAME_DATA_DIR = "gamedata"
CHARACTER_FILE = os.path.join(GAME_DATA_DIR, "character.json")
WORLD_FILE = os.path.join(GAME_DATA_DIR, "world.json")
EVENTS_FILE = os.path.join(GAME_DATA_DIR, "events.json")
MAX_EVENTS = 5 # The number of recent events to keep in context

# === Helper Functions (from your original script) ===

def setup_game_files():
    """Creates the gamedata directory and initial JSON files if they don't exist."""
    os.makedirs(GAME_DATA_DIR, exist_ok=True)
    if not os.path.exists(CHARACTER_FILE):
        with open(CHARACTER_FILE, 'w') as f:
            json.dump({"name": "Orton", "status": ["healthy"], "inventory": ["pocket knife", "water bottle"]}, f, indent=4)
    if not os.path.exists(WORLD_FILE):
        with open(WORLD_FILE, 'w') as f:
            json.dump({"current_location": "an abandoned apartment", "time_of_day": "Morning"}, f, indent=4)
    if not os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'w') as f:
            json.dump(["The adventure begins."], f, indent=4)

def load_state():
    """Loads all game state from JSON files into a dictionary."""
    with open(CHARACTER_FILE, 'r') as f:
        character_data = json.load(f)
    with open(WORLD_FILE, 'r') as f:
        world_data = json.load(f)
    with open(EVENTS_FILE, 'r') as f:
        events_data = json.load(f)
    return {"character": character_data, "world": world_data, "events": events_data}

def save_state(state_data):
    """Saves the provided state back to the individual JSON files."""
    with open(CHARACTER_FILE, 'w') as f:
        json.dump(state_data["character"], f, indent=4)
    with open(WORLD_FILE, 'w') as f:
        json.dump(state_data["world"], f, indent=4)
    with open(EVENTS_FILE, 'w') as f:
        json.dump(state_data["events"], f, indent=4)

# === LLM Integration (The REAL version) ===

def query_llm(prompt_text):
    """
    Sends the assembled prompt to a local LLM running via LM Studio and returns the response.
    """
    # --- IMPORTANT ---
    # Make sure LM Studio is running and a model is loaded.
    # This URL is the default for LM Studio's local server.
    # You might need to change the port if you've configured it differently.
    url = "http://localhost:1234/v1/chat/completions"

    headers = {"Content-Type": "application/json"}
    
    # This payload structure is required by the OpenAI-compatible endpoint.
    payload = {
        "model": "local-model", # This value doesn't matter for LM Studio
        "messages": [
            # We can add a system prompt to guide the LLM's behavior
            {
                "role": "system",
                "content": (
                    "You are a text-based RPG game master. "
                    "Describe the world, actions, and consequences in a gritty, narrative style. "
                    "Your response MUST be a single, valid JSON object (not wrapped in markdown code blocks) with three keys: "
                    "'response_text' (the story narrative for the player), "
                    "'new_event' (a brief summary of what happened for the event log), "
                    "and 'state_changes' (a JSON object with filenames as keys and the changed data as values). "
                    "For state_changes, use 'character.json' for character updates and 'world.json' for world updates. "
                    "Example: {\"response_text\": \"You see...\", \"new_event\": \"Orton did something\", \"state_changes\": {\"character.json\": {\"status\": [\"tired\"]}}}"
                )
            },
            {
                "role": "user",
                "content": prompt_text
            }
        ],
        "temperature": 0.7,
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        # Extract the content from the LLM's response
        llm_response_json = response.json()['choices'][0]['message']['content']
        
        # It's good practice to print what the LLM returned, for debugging
        print("--- LLM Raw Response ---")
        print(llm_response_json)
        print("------------------------")

        return llm_response_json

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to LLM Studio: {e}")
        # Return an error message in the same JSON format
        return json.dumps({
            "response_text": f"Error: Could not connect to the LLM. Is LM Studio running? ({e})",
            "new_event": "A connection error occurred.",
            "state_changes": {}
        })
    except (KeyError, IndexError) as e:
        print(f"Error parsing LLM response: {e}")
        return json.dumps({
            "response_text": f"Error: The LLM returned an unexpected response format. Check the LM Studio console. ({e})",
            "new_event": "An LLM format error occurred.",
            "state_changes": {}
        })


def run_game_turn(player_input):
    """
    This function orchestrates a single turn of the game.
    """
    # Step A: Load Game State
    state = load_state()
    
    # Step B: Assemble the LLM Prompt
    # Flatten the data for easy formatting
    char = state['character']
    world = state['world']
    events = state['events']

    # Format recent events (up to 5, in reverse chronological order)
    events_section = ""
    for i, event in enumerate(events[:5]):  # Take only the first 5 (most recent)
        events_section += f"    {event}\n\n"
    
    # Remove trailing newlines if events exist
    if events_section:
        events_section = events_section.rstrip("\n")

    llm_prompt = f"""[CHARACTER]
Name: {char['name']}, Status: {', '.join(char['status'])}, Inventory: {', '.join(char['inventory'])}

[WORLD]
Location: {world['current_location']}, Time: {world['time_of_day']}

[RECENT EVENTS]

{events_section}

[SCENE]
{player_input}"""
    print("--- Assembled Prompt for LLM ---")
    print(llm_prompt)
    print("--------------------------------")

    # Step C: Query the LLM
    llm_response_str = query_llm(llm_prompt)

    # Step D: Parse and Apply LLM Response
    try:
        # Clean up the response if it's wrapped in markdown code blocks
        clean_response = llm_response_str.strip()
        if clean_response.startswith('```json'):
            clean_response = clean_response[7:]  # Remove ```json
        if clean_response.startswith('```'):
            clean_response = clean_response[3:]   # Remove ```
        if clean_response.endswith('```'):
            clean_response = clean_response[:-3]  # Remove trailing ```
        clean_response = clean_response.strip()
        
        llm_data = json.loads(clean_response)
    except json.JSONDecodeError as e:
        # If the LLM returns invalid JSON, we can't proceed with state changes.
        return {
            "story_text": f"LLM Response Error: The AI returned invalid JSON. The game state has not been changed.\n\nJSON Error: {str(e)}\n\nRaw response:\n{llm_response_str}",
            "current_location": state['world']['current_location'],
            "inventory": state['character']['inventory']
        }

    # Update state dictionaries based on the 'state_changes' block
    state_changes = llm_data.get("state_changes", {})
    for file_key, changes in state_changes.items():
        # Handle both "character.json" and variations like "orton.json"
        if file_key in ["character.json", "orton.json"]:
            state["character"].update(changes)
        elif file_key in ["world.json"]:
            state["world"].update(changes)
        else:
            print(f"Warning: Unknown file key in state_changes: {file_key}")

    # Add the new event and trim the log
    new_event = llm_data.get("new_event")
    if new_event:
        state["events"].insert(0, new_event)
        state["events"] = state["events"][:MAX_EVENTS]

    # Step E: Save Game State
    save_state(state)

    # Prepare the data to send back to the frontend
    turn_result = {
        "story_text": llm_data.get("response_text", "The world is silent."),
        "current_location": state['world']['current_location'],
        "inventory": state['character']['inventory']
    }
    return turn_result


# === Flask Web Routes ===

@app.route('/')
def index():
    """Serves the main HTML page for the game."""
    return render_template('index.html')

@app.route('/play', methods=['POST'])
def play():
    """
    This is the API endpoint that the frontend calls.
    It receives player input, runs a game turn, and returns the result.
    """
    player_input = request.json.get('input')
    if not player_input:
        return jsonify({"error": "No input provided"}), 400
    
    # Run the game logic
    result = run_game_turn(player_input)
    
    return jsonify(result)

@app.route('/reset', methods=['POST'])
def reset_game():
    """API endpoint to reset the game state to default."""
    # Delete old files
    if os.path.exists(CHARACTER_FILE): os.remove(CHARACTER_FILE)
    if os.path.exists(WORLD_FILE): os.remove(WORLD_FILE)
    if os.path.exists(EVENTS_FILE): os.remove(EVENTS_FILE)
    
    # Create fresh ones
    setup_game_files()
    
    return jsonify({"message": "Game has been reset."})


# === Main Execution Block ===
if __name__ == "__main__":
    print("Starting RPG server...")
    setup_game_files()
    # 'host="0.0.0.0"' makes the server accessible on your local network
    app.run(host="0.0.0.0", port=5000, debug=True)

