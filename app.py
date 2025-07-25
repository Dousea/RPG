# app.py
# This script runs the Flask web server for our RPG.

import os
import json
import requests # Make sure to install this: pip install requests
from flask import Flask, request, jsonify, render_template # Make sure to install this: pip install Flask
import faiss # Make sure to install this: pip install faiss-cpu
import numpy as np
from sentence_transformers import SentenceTransformer # Make sure to install this: pip install sentence-transformers

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Global Memory System Variables ---
faiss_index = None
sentence_model = None

# --- Game Constants ---
GAME_DATA_DIR = "gamedata"
CHARACTER_FILE = os.path.join(GAME_DATA_DIR, "character.json")
WORLD_FILE = os.path.join(GAME_DATA_DIR, "world.json")
EVENTS_FILE = os.path.join(GAME_DATA_DIR, "events.json")
LOCATIONS_FILE = os.path.join(GAME_DATA_DIR, "locations.json")
NPCS_FILE = os.path.join(GAME_DATA_DIR, "npcs.json")
SUMMARIES_FILE = os.path.join(GAME_DATA_DIR, "summaries.json")
FULL_EVENT_LOG_FILE = os.path.join(GAME_DATA_DIR, "full_event_log.json")
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
    if not os.path.exists(FULL_EVENT_LOG_FILE):
        with open(FULL_EVENT_LOG_FILE, 'w') as f:
            json.dump(["The adventure begins."], f, indent=4)

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
    with open(FULL_EVENT_LOG_FILE, 'r') as f:
        full_event_log_data = json.load(f)
    return {
        "character": character_data, 
        "world": world_data, 
        "events": events_data, 
        "locations": locations_data, 
        "npcs": npcs_data,
        "summaries": summaries_data,
        "full_event_log": full_event_log_data
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
    with open(FULL_EVENT_LOG_FILE, 'w') as f:
        json.dump(state_data["full_event_log"], f, indent=4)

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
                    "Your response must follow this EXACT format with these section markers:\n\n"
                    "STORY:\n"
                    "[Write the narrative story text here]\n\n"
                    "EVENT:\n"
                    "[Write a brief summary for the event log]\n\n"
                    "ACTIONS:\n"
                    "[List any actions that need to happen, one per line. Available actions:]\n"
                    "- TAKE item_name\n"
                    "- DROP item_name\n"
                    "- MOVE_TO location_name\n"
                    "- TIME_ADVANCE morning/afternoon/evening/night\n"
                    "- STATUS_ADD status_name\n"
                    "- STATUS_REMOVE status_name\n"
                    "- NPC_MOVE npc_name TO location_name\n"
                    "- NPC_STATUS npc_name ADD status_name\n"
                    "- NPC_STATUS npc_name REMOVE status_name\n"
                    "[If no actions needed, write: NONE]\n\n"
                    "Example response:\n"
                    "STORY:\n"
                    "You reach down and pick up the rusty can from the floor. It's heavier than expected.\n\n"
                    "EVENT:\n"
                    "Orton picked up a rusty can\n\n"
                    "ACTIONS:\n"
                    "TAKE rusty can"
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
        llm_response_text = response.json()['choices'][0]['message']['content']
        
        # It's good practice to print what the LLM returned, for debugging
        print("--- LLM Raw Response ---")
        print(llm_response_text)
        print("------------------------")

        return llm_response_text

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to LLM Studio: {e}")
        # Return an error message in the simple text format
        return f"STORY:\nError: Could not connect to the LLM. Is LM Studio running? ({e})\n\nEVENT:\nA connection error occurred.\n\nACTIONS:\nNONE"
    except (KeyError, IndexError) as e:
        print(f"Error parsing LLM response: {e}")
        return f"STORY:\nError: The LLM returned an unexpected response format. Check the LM Studio console. ({e})\n\nEVENT:\nAn LLM format error occurred.\n\nACTIONS:\nNONE"


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


def parse_llm_response(llm_response_text):
    """
    Parse the simple text-based LLM response into components.
    Returns a dictionary with 'story', 'event', and 'actions' keys.
    """
    # Initialize default values
    story = "The world is silent."
    event = "Nothing happened."
    actions = []
    
    # Split response into sections
    sections = llm_response_text.split('\n\n')
    current_section = None
    
    for section in sections:
        section = section.strip()
        if section.startswith('STORY:'):
            current_section = 'story'
            story = section[6:].strip()  # Remove 'STORY:' prefix
        elif section.startswith('EVENT:'):
            current_section = 'event'
            event = section[6:].strip()  # Remove 'EVENT:' prefix
        elif section.startswith('ACTIONS:'):
            current_section = 'actions'
            actions_text = section[8:].strip()  # Remove 'ACTIONS:' prefix
            if actions_text.upper() != 'NONE':
                # Split actions by newlines and clean them up
                actions = [action.strip() for action in actions_text.split('\n') if action.strip()]
        elif current_section and section:
            # Continue previous section if we have content
            if current_section == 'story':
                story += '\n' + section
            elif current_section == 'event':
                event += '\n' + section
            elif current_section == 'actions' and section.upper() != 'NONE':
                actions.extend([action.strip() for action in section.split('\n') if action.strip()])
    
    return {
        'story': story,
        'event': event,
        'actions': actions
    }


def execute_action(action_str, state):
    """
    Execute a single action command on the game state.
    Returns True if the action was successful, False otherwise.
    """
    if not action_str or action_str.upper() == 'NONE':
        return True
    
    parts = action_str.strip().split()
    if not parts:
        return False
        
    command = parts[0].upper()
    
    try:
        if command == "TAKE":
            return handle_take_action(parts[1:], state)
        elif command == "DROP":
            return handle_drop_action(parts[1:], state)
        elif command == "MOVE_TO":
            return handle_move_action(parts[1:], state)
        elif command == "TIME_ADVANCE":
            return handle_time_action(parts[1:], state)
        elif command == "STATUS_ADD":
            return handle_status_add_action(parts[1:], state)
        elif command == "STATUS_REMOVE":
            return handle_status_remove_action(parts[1:], state)
        elif command == "NPC_MOVE":
            return handle_npc_move_action(parts[1:], state)
        elif command == "NPC_STATUS":
            return handle_npc_status_action(parts[1:], state)
        else:
            print(f"Warning: Unknown action command: {command}")
            return False
    except Exception as e:
        print(f"Error executing action '{action_str}': {e}")
        return False


def handle_take_action(args, state):
    """Handle TAKE item_name action"""
    if not args:
        return False
        
    item_name = " ".join(args)  # Handle multi-word items
    current_location = state['world']['current_location']
    
    # Remove from location
    if current_location in state['locations']:
        location_items = state['locations'][current_location].get('items', [])
        if item_name in location_items:
            location_items.remove(item_name)
            state['character']['inventory'].append(item_name)
            print(f"Action executed: Took '{item_name}' from {current_location}")
            return True
    
    print(f"Action failed: Could not take '{item_name}' from {current_location}")
    return False


def handle_drop_action(args, state):
    """Handle DROP item_name action"""
    if not args:
        return False
        
    item_name = " ".join(args)
    current_location = state['world']['current_location']
    
    # Remove from inventory
    if item_name in state['character']['inventory']:
        state['character']['inventory'].remove(item_name)
        
        # Add to current location
        if current_location in state['locations']:
            state['locations'][current_location].setdefault('items', []).append(item_name)
            print(f"Action executed: Dropped '{item_name}' in {current_location}")
            return True
    
    print(f"Action failed: Could not drop '{item_name}'")
    return False


def handle_move_action(args, state):
    """Handle MOVE_TO location_name action"""
    if not args:
        return False
        
    target_location = " ".join(args)
    current_location = state['world']['current_location']
    
    # Validate connection exists
    if current_location in state['locations']:
        connections = state['locations'][current_location].get('connections', [])
        if target_location in connections and target_location in state['locations']:
            state['world']['current_location'] = target_location
            print(f"Action executed: Moved from {current_location} to {target_location}")
            return True
    
    print(f"Action failed: Cannot move from {current_location} to {target_location}")
    return False


def handle_time_action(args, state):
    """Handle TIME_ADVANCE time_period action"""
    if not args:
        return False
        
    time_period = args[0].lower()
    valid_times = ['morning', 'afternoon', 'evening', 'night']
    
    if time_period in valid_times:
        state['world']['time_of_day'] = time_period.capitalize()
        print(f"Action executed: Time advanced to {time_period}")
        return True
    
    print(f"Action failed: Invalid time period '{time_period}'")
    return False


def handle_status_add_action(args, state):
    """Handle STATUS_ADD status_name action"""
    if not args:
        return False
        
    status_name = " ".join(args)
    if status_name not in state['character']['status']:
        state['character']['status'].append(status_name)
        print(f"Action executed: Added status '{status_name}' to character")
        return True
    
    print(f"Action failed: Character already has status '{status_name}'")
    return False


def handle_status_remove_action(args, state):
    """Handle STATUS_REMOVE status_name action"""
    if not args:
        return False
        
    status_name = " ".join(args)
    if status_name in state['character']['status']:
        state['character']['status'].remove(status_name)
        print(f"Action executed: Removed status '{status_name}' from character")
        return True
    
    print(f"Action failed: Character does not have status '{status_name}'")
    return False


def handle_npc_move_action(args, state):
    """Handle NPC_MOVE npc_name TO location_name action"""
    if len(args) < 3 or args[-2].upper() != 'TO':
        return False
        
    # Find the TO keyword and split around it
    to_index = -1
    for i, arg in enumerate(args):
        if arg.upper() == 'TO':
            to_index = i
            break
    
    if to_index == -1:
        return False
        
    npc_name = " ".join(args[:to_index])
    location_name = " ".join(args[to_index + 1:])
    
    if npc_name in state['npcs'] and location_name in state['locations']:
        state['npcs'][npc_name]['location'] = location_name
        print(f"Action executed: Moved NPC '{npc_name}' to {location_name}")
        return True
    
    print(f"Action failed: Could not move NPC '{npc_name}' to {location_name}")
    return False


def handle_npc_status_action(args, state):
    """Handle NPC_STATUS npc_name ADD/REMOVE status_name action"""
    if len(args) < 3:
        return False
        
    # Find ADD or REMOVE keyword
    action_index = -1
    action_type = None
    for i, arg in enumerate(args):
        if arg.upper() in ['ADD', 'REMOVE']:
            action_index = i
            action_type = arg.upper()
            break
    
    if action_index == -1:
        return False
        
    npc_name = " ".join(args[:action_index])
    status_name = " ".join(args[action_index + 1:])
    
    if npc_name not in state['npcs']:
        print(f"Action failed: Unknown NPC '{npc_name}'")
        return False
    
    npc_statuses = state['npcs'][npc_name].setdefault('status', [])
    
    if action_type == 'ADD':
        if status_name not in npc_statuses:
            npc_statuses.append(status_name)
            print(f"Action executed: Added status '{status_name}' to NPC '{npc_name}'")
            return True
        else:
            print(f"Action failed: NPC '{npc_name}' already has status '{status_name}'")
            return False
    elif action_type == 'REMOVE':
        if status_name in npc_statuses:
            npc_statuses.remove(status_name)
            print(f"Action executed: Removed status '{status_name}' from NPC '{npc_name}'")
            return True
        else:
            print(f"Action failed: NPC '{npc_name}' does not have status '{status_name}'")
            return False
    
    return False


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
    This function orchestrates a single turn of the game with Phase 3 Hybrid Memory System.
    """
    # Step A: Load Full Game State
    state = load_state()
    
    # Step B: SEMANTIC SEARCH (NEW STEP - Deep Memory Retrieval)
    retrieved_indices = search_faiss_index(player_input, k=2)
    deep_memories = []
    if retrieved_indices:
        deep_memories = [state["full_event_log"][i] for i in retrieved_indices if i < len(state["full_event_log"])]
    
    print(f"Retrieved {len(deep_memories)} deep memories for input: '{player_input}'")
    for i, memory in enumerate(deep_memories):
        print(f"  Deep Memory {i+1}: {memory}")
    
    # Step C: HEURISTIC FILTERING
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
    
    # Step D: Assemble the HYBRID LLM Prompt
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
    
    # Format deep memories (NEW SECTION)
    deep_memory_section = ""
    if deep_memories:
        for memory in deep_memories:
            deep_memory_section += f"    {memory}\n\n"
        deep_memory_section = deep_memory_section.rstrip("\n")
    else:
        deep_memory_section = "    None"
    
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

    # NEW HYBRID PROMPT STRUCTURE
    llm_prompt = f"""[CHARACTER]
Name: {char['name']}, Status: {', '.join(char['status'])}, Inventory: {', '.join(char['inventory'])}

[DEEP MEMORY]
(Recalled from past events based on your input)

{deep_memory_section}

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
(A narrative overview of the long-term past)

{summary_section}

[RECENT EVENTS]
(What just happened)

{events_section}

[SCENE]
{player_input}"""
    
    print("--- Assembled Hybrid Prompt for LLM ---")
    print(llm_prompt)
    print("---------------------------------------")

    # Step E: Query the LLM
    llm_response_str = query_llm(llm_prompt)

    # Step F: Parse and Apply LLM Response (NEW TEXT-BASED PARSING)
    try:
        # Parse the simple text-based response
        parsed_response = parse_llm_response(llm_response_str)
        
        # Extract components
        story_text = parsed_response['story']
        new_event = parsed_response['event']
        actions = parsed_response['actions']
        
        print(f"--- Parsed Response ---")
        print(f"Story: {story_text}")
        print(f"Event: {new_event}")
        print(f"Actions: {actions}")
        print("----------------------")
        
        # Execute all actions
        for action in actions:
            if action.strip():
                success = execute_action(action, state)
                if not success:
                    print(f"Failed to execute action: {action}")
        
    except Exception as e:
        # If parsing fails, we can still return the raw response
        print(f"Error parsing LLM response: {e}")
        return {
            "story_text": f"Response Parsing Error: Could not parse the AI response properly.\n\nError: {str(e)}\n\nRaw response:\n{llm_response_str}",
            "current_location": state['world']['current_location'],
            "inventory": state['character']['inventory']
        }

    # Step G: Add to BOTH memory systems
    if new_event:
        # Add to recent events (short-term memory)
        state["events"].insert(0, new_event)
        state["events"] = state["events"][:MAX_EVENTS]
        
        # Add to full event log (deep memory) - CRITICAL NEW STEP
        state["full_event_log"].append(new_event)
        
        # Rebuild FAISS index immediately for new searchable memory
        build_faiss_index(state["full_event_log"])

    # Step H: Run Summarization Check
    run_summarization_check(state)

    # Step I: Save Game State
    save_state(state)

    # Prepare the data to send back to the frontend
    turn_result = {
        "story_text": story_text,
        "current_location": state['world']['current_location'],
        "inventory": state['character']['inventory']
    }
    return turn_result


# === FAISS Memory System Functions ===

def initialize_sentence_model():
    """Initialize the sentence transformer model globally."""
    global sentence_model
    if sentence_model is None:
        print("Loading sentence transformer model...")
        sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("Sentence transformer model loaded.")

def build_faiss_index(events_list):
    """
    Builds a FAISS index from the provided list of events.
    """
    global faiss_index, sentence_model
    
    # Initialize the model if needed
    initialize_sentence_model()
    
    if not events_list:
        print("No events to index.")
        faiss_index = None
        return
    
    print(f"Building FAISS index from {len(events_list)} events...")
    
    # Generate embeddings for all events
    embeddings = sentence_model.encode(events_list)
    embeddings = np.array(embeddings).astype('float32')
    
    # Create FAISS index
    dimension = embeddings.shape[1]
    faiss_index = faiss.IndexFlatIP(dimension)  # Inner Product (cosine similarity)
    
    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings)
    
    # Add embeddings to index
    faiss_index.add(embeddings)
    
    print(f"FAISS index built with {faiss_index.ntotal} events.")

def search_faiss_index(query_text, k=2):
    """
    Searches the FAISS index for the k most similar events to the query.
    Returns a list of indices into the original events list.
    """
    global faiss_index, sentence_model
    
    if faiss_index is None or sentence_model is None:
        print("FAISS index or sentence model not initialized.")
        return []
    
    if faiss_index.ntotal == 0:
        print("FAISS index is empty.")
        return []
    
    # Encode the query
    query_embedding = sentence_model.encode([query_text])
    query_embedding = np.array(query_embedding).astype('float32')
    
    # Normalize for cosine similarity
    faiss.normalize_L2(query_embedding)
    
    # Search the index
    k = min(k, faiss_index.ntotal)  # Don't search for more than we have
    scores, indices = faiss_index.search(query_embedding, k)
    
    # Return the indices (convert from numpy to list)
    return indices[0].tolist()


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
    if os.path.exists(FULL_EVENT_LOG_FILE): os.remove(FULL_EVENT_LOG_FILE)
    
    # Create fresh ones
    setup_game_files()
    
    # Rebuild FAISS index with fresh data
    state = load_state()
    build_faiss_index(state["full_event_log"])
    
    return jsonify({"message": "Game has been reset."})


# === Main Execution Block ===
if __name__ == "__main__":
    print("Starting RPG server...")
    setup_game_files()
    
    # Initialize FAISS index from existing full event log
    print("Initializing FAISS memory system...")
    state = load_state()
    build_faiss_index(state["full_event_log"])
    print("FAISS memory system ready.")
    
    # 'host="0.0.0.0"' makes the server accessible on your local network
    app.run(host="0.0.0.0", port=5000, debug=True)

