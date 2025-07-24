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
LOCATIONS_FILE = os.path.join(GAME_DATA_DIR, "locations.json")
NPCS_FILE = os.path.join(GAME_DATA_DIR, "npcs.json")
SUMMARIES_FILE = os.path.join(GAME_DATA_DIR, "summaries.json")
MAX_EVENTS = 5 # The number of recent events to keep in context
EVENTS_THRESHOLD = 10 # Trigger summarization when events exceed this number

# === Helper Functions (from your original script) ===

def setup_game_files():
    """Creates the gamedata directory and initial JSON files if they don't exist."""
    os.makedirs(GAME_DATA_DIR, exist_ok=True)
    if not os.path.exists(CHARACTER_FILE):
        with open(CHARACTER_FILE, 'w') as f:
            json.dump({"name": "Orton", "status": ["healthy"], "inventory": ["pocket knife", "water bottle"]}, f, indent=4)
    if not os.path.exists(WORLD_FILE):
        with open(WORLD_FILE, 'w') as f:
            json.dump({"current_location": "Apartment B2", "time_of_day": "Morning"}, f, indent=4)
    if not os.path.exists(EVENTS_FILE):
        with open(EVENTS_FILE, 'w') as f:
            json.dump(["The adventure begins."], f, indent=4)
    if not os.path.exists(LOCATIONS_FILE):
        with open(LOCATIONS_FILE, 'w') as f:
            json.dump({
                "Apartment B2": {
                    "description": "A cramped apartment with boarded windows and scattered debris. The air smells of mold and decay.",
                    "connections": ["Hallway"],
                    "items": ["rusty can", "torn newspaper"]
                },
                "Hallway": {
                    "description": "A dimly lit hallway with flickering overhead lights. Doors line both sides, most are locked or barricaded.",
                    "connections": ["Apartment B2", "Stairwell"],
                    "items": ["broken glass"]
                },
                "Stairwell": {
                    "description": "A concrete stairwell echoing with distant sounds. Graffiti covers the walls and the air is thick with dust.",
                    "connections": ["Hallway", "Ground Floor"],
                    "items": []
                },
                "Ground Floor": {
                    "description": "The building's entrance area. Sunlight streams through cracked windows, illuminating the abandoned lobby.",
                    "connections": ["Stairwell"],
                    "items": ["old magazine", "bent spoon"]
                }
            }, f, indent=4)
    if not os.path.exists(NPCS_FILE):
        with open(NPCS_FILE, 'w') as f:
            json.dump({
                "Dale": {
                    "description": "A weathered survivor wearing a patched leather jacket. His eyes dart nervously around the room",
                    "location": "Hallway",
                    "status": ["cautious", "armed"]
                },
                "Sarah": {
                    "description": "An elderly woman clutching a worn backpack. She moves slowly but with purpose",
                    "location": "Ground Floor",
                    "status": ["tired", "determined"]
                }
            }, f, indent=4)
    if not os.path.exists(SUMMARIES_FILE):
        with open(SUMMARIES_FILE, 'w') as f:
            json.dump([], f, indent=4)

def load_state():
    """Loads all game state from JSON files into a dictionary."""
    with open(CHARACTER_FILE, 'r') as f:
        character_data = json.load(f)
    with open(WORLD_FILE, 'r') as f:
        world_data = json.load(f)
    with open(EVENTS_FILE, 'r') as f:
        events_data = json.load(f)
    with open(LOCATIONS_FILE, 'r') as f:
        locations_data = json.load(f)
    with open(NPCS_FILE, 'r') as f:
        npcs_data = json.load(f)
    with open(SUMMARIES_FILE, 'r') as f:
        summaries_data = json.load(f)
    return {
        "character": character_data, 
        "world": world_data, 
        "events": events_data, 
        "locations": locations_data, 
        "npcs": npcs_data,
        "summaries": summaries_data
    }

def save_state(state_data):
    """Saves the provided state back to the individual JSON files."""
    with open(CHARACTER_FILE, 'w') as f:
        json.dump(state_data["character"], f, indent=4)
    with open(WORLD_FILE, 'w') as f:
        json.dump(state_data["world"], f, indent=4)
    with open(EVENTS_FILE, 'w') as f:
        json.dump(state_data["events"], f, indent=4)
    with open(LOCATIONS_FILE, 'w') as f:
        json.dump(state_data["locations"], f, indent=4)
    with open(NPCS_FILE, 'w') as f:
        json.dump(state_data["npcs"], f, indent=4)
    with open(SUMMARIES_FILE, 'w') as f:
        json.dump(state_data["summaries"], f, indent=4)

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
                    "IMPORTANT: Only perform actions that the player explicitly requests. Do not assume or perform actions automatically. "
                    "If the player says 'look around' or 'scan the area', only DESCRIBE what they see - do not pick up items or interact with objects unless specifically told to do so. "
                    "Your response MUST be a single, valid JSON object (not wrapped in markdown code blocks) with three keys: "
                    "'response_text' (the story narrative for the player), "
                    "'new_event' (a brief summary of what happened for the event log), "
                    "and 'state_changes' (a JSON object with filenames as keys and the changed data as values). "
                    "For state_changes: "
                    "- 'character.json' for character updates (use 'inventory' key in lowercase) "
                    "- 'world.json' for world updates (current_location, time_of_day only) "
                    "- 'locations.json' for location updates: ALWAYS use specific location name as key, then 'items' array "
                    "- 'npcs.json' for NPC updates (specific NPC name as key) "
                    "CRITICAL: When moving items, update 'locations.json' with the specific location name, NOT 'world.json'. "
                    "Example for taking an item: {'locations.json': {'Apartment B2': {'items': ['remaining_item1', 'remaining_item2']}}}"
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


def query_llm_for_summary(text_to_summarize):
    """
    Sends events to the LLM for summarization and returns only the text content.
    """
    url = "http://localhost:1234/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "model": "local-model",
        "messages": [
            {
                "role": "system",
                "content": "You are a story summarizer. Condense the following events into a single, concise narrative paragraph."
            },
            {
                "role": "user",
                "content": text_to_summarize
            }
        ],
        "temperature": 0.5,
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        # Extract only the text content from the LLM's response
        llm_response = response.json()['choices'][0]['message']['content']
        
        print("--- LLM Summary Response ---")
        print(llm_response)
        print("---------------------------")
        
        return llm_response.strip()

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to LLM Studio for summary: {e}")
        return f"Summary unavailable due to connection error: {e}"
    except (KeyError, IndexError) as e:
        print(f"Error parsing LLM summary response: {e}")
        return f"Summary unavailable due to parsing error: {e}"


def run_summarization_check(state):
    """
    Checks if summarization is needed and performs it if the event count exceeds the threshold.
    """
    events = state["events"]
    
    # Check if we need to summarize
    if len(events) <= EVENTS_THRESHOLD:
        return  # No summarization needed
    
    print(f"Events count ({len(events)}) exceeds threshold ({EVENTS_THRESHOLD}). Running summarization...")
    
    # Calculate how many events to summarize (leave 2 most recent)
    events_to_keep = 2
    events_to_summarize = events[events_to_keep:]  # Get older events (everything except the 2 most recent)
    
    # Join events into a single string for summarization
    events_text = "\n".join(events_to_summarize)
    
    # Get summary from LLM
    summary_paragraph = query_llm_for_summary(events_text)
    
    # Add summary to the summaries list
    state["summaries"].append(summary_paragraph)
    
    # Trim the events list to keep only the most recent events
    state["events"] = events[:events_to_keep]
    
    print(f"Summarization complete. Events reduced from {len(events)} to {len(state['events'])}.")
    print(f"New summary added: {summary_paragraph}")


def run_game_turn(player_input):
    """
    This function orchestrates a single turn of the game with Heuristic Filtering.
    """
    # Step A: Load Full Game State
    state = load_state()
    
    # Step B: HEURISTIC FILTERING (NEW STEP)
    current_location = state['world']['current_location']
    
    # Create contextual_locations
    contextual_locations = {}
    if current_location in state['locations']:
        # Add current location
        contextual_locations[current_location] = state['locations'][current_location]
        
        # Add connected locations
        connections = state['locations'][current_location].get('connections', [])
        for connected_location in connections:
            if connected_location in state['locations']:
                contextual_locations[connected_location] = state['locations'][connected_location]
    
    # Create contextual_npcs (only NPCs in current location)
    contextual_npcs = {}
    for npc_name, npc_data in state['npcs'].items():
        if npc_data.get('location') == current_location:
            contextual_npcs[npc_name] = npc_data
    
    # Step C: Assemble the NEW LLM Prompt
    char = state['character']
    world = state['world']
    events = state['events']
    
    # Format current location info
    current_location_description = "Unknown location"
    current_location_items = []
    if current_location in state['locations']:
        current_location_description = state['locations'][current_location].get('description', 'No description available')
        current_location_items = state['locations'][current_location].get('items', [])
    
    # Format current location items
    current_items_section = ""
    if current_location_items:
        for item in current_location_items:
            current_items_section += f"    {item}\n"
    else:
        current_items_section = "    None\n"
    
    # Format nearby locations
    nearby_locations_section = ""
    for loc_name, loc_data in contextual_locations.items():
        if loc_name != current_location:  # Don't include current location in nearby
            items_list = loc_data.get('items', [])
            items_str = f", Items: {', '.join(items_list)}" if items_list else ", Items: None"
            nearby_locations_section += f"    {loc_name}: {loc_data.get('description', 'No description')}{items_str}\n\n"
    
    if not nearby_locations_section.strip():
        nearby_locations_section = "    None\n\n"
    
    # Format NPCs present
    npcs_present_section = ""
    for npc_name, npc_data in contextual_npcs.items():
        status_str = ', '.join(npc_data.get('status', []))
        npcs_present_section += f"    {npc_name}: {npc_data.get('description', 'No description')}, Status: {status_str}\n\n"
    
    if not npcs_present_section.strip():
        npcs_present_section = "    None\n\n"
    
    # Format recent events (up to 5, in reverse chronological order)
    events_section = ""
    for event in events[:5]:  # Take only the first 5 (most recent)
        events_section += f"    {event}\n\n"
    
    # Remove trailing newlines if events exist
    if events_section:
        events_section = events_section.rstrip("\n")

    # Format summary of past events
    summary_section = "None"
    if state["summaries"]:
        summary_section = state["summaries"][-1]  # Get the most recent summary

    llm_prompt = f"""[CHARACTER]
Name: {char['name']}, Status: {', '.join(char['status'])}, Inventory: {', '.join(char['inventory'])}

[WORLD]
Current Location: {current_location}
Description: {current_location_description}
Time: {world['time_of_day']}

[ITEMS IN CURRENT LOCATION]

{current_items_section.rstrip()}

[NEARBY LOCATIONS]

{nearby_locations_section.rstrip()}

[NPCS PRESENT]

{npcs_present_section.rstrip()}

[SUMMARY OF PAST EVENTS]

{summary_section}

[RECENT EVENTS]

{events_section}

[SCENE]
{player_input}"""
    
    print("--- Assembled Prompt for LLM ---")
    print(llm_prompt)
    print("--------------------------------")

    # Step D: Query the LLM
    llm_response_str = query_llm(llm_prompt)

    # Step E: Parse and Apply LLM Response
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
        # Handle character updates
        if file_key in ["character.json", "orton.json"]:
            state["character"].update(changes)
        # Handle world updates
        elif file_key in ["world.json"]:
            state["world"].update(changes)
        # Handle location updates
        elif file_key in ["locations.json"]:
            for location_name, location_changes in changes.items():
                if location_name in state["locations"]:
                    state["locations"][location_name].update(location_changes)
                else:
                    print(f"Warning: Unknown location in state_changes: {location_name}")
        # Handle NPC updates
        elif file_key in ["npcs.json"]:
            for npc_name, npc_changes in changes.items():
                if npc_name in state["npcs"]:
                    state["npcs"][npc_name].update(npc_changes)
                else:
                    print(f"Warning: Unknown NPC in state_changes: {npc_name}")
        else:
            print(f"Warning: Unknown file key in state_changes: {file_key}")

    # Add the new event and trim the log
    new_event = llm_data.get("new_event")
    if new_event:
        state["events"].insert(0, new_event)
        state["events"] = state["events"][:MAX_EVENTS]

    # Step F: Run Summarization Check
    run_summarization_check(state)

    # Step G: Save Game State
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
    if os.path.exists(SUMMARIES_FILE): os.remove(SUMMARIES_FILE)
    if os.path.exists(LOCATIONS_FILE): os.remove(LOCATIONS_FILE)
    if os.path.exists(NPCS_FILE): os.remove(NPCS_FILE)
    
    # Create fresh ones
    setup_game_files()
    
    return jsonify({"message": "Game has been reset."})


# === Main Execution Block ===
if __name__ == "__main__":
    print("Starting RPG server...")
    setup_game_files()
    # 'host="0.0.0.0"' makes the server accessible on your local network
    app.run(host="0.0.0.0", port=5000, debug=True)

