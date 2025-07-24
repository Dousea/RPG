#!/usr/bin/env python3
"""
Phase 1 Local LLM-powered RPG
A simple, file-based RPG game loop that manages game state using modular JSON files
and assembles context-aware prompts for an LLM at each turn.
"""

import json
import os
from typing import Dict, List, Any


def setup_game_files():
    """Creates the gamedata directory and initial JSON files with default data if they don't exist."""
    # Create gamedata directory if it doesn't exist
    if not os.path.exists("gamedata"):
        os.makedirs("gamedata")
        print("Created gamedata directory.")
    
    # Default data for each file
    default_character = {
        "name": "Orton",
        "status": ["healthy"],
        "inventory": ["pocket knife", "water bottle"]
    }
    
    default_world = {
        "current_location": "Apartment B2",
        "time_of_day": "Morning"
    }
    
    default_events = []
    
    # Create character.json if it doesn't exist
    character_path = "gamedata/character.json"
    if not os.path.exists(character_path):
        with open(character_path, 'w') as f:
            json.dump(default_character, f, indent=2)
        print("Created character.json with default data.")
    
    # Create world.json if it doesn't exist
    world_path = "gamedata/world.json"
    if not os.path.exists(world_path):
        with open(world_path, 'w') as f:
            json.dump(default_world, f, indent=2)
        print("Created world.json with default data.")
    
    # Create events.json if it doesn't exist
    events_path = "gamedata/events.json"
    if not os.path.exists(events_path):
        with open(events_path, 'w') as f:
            json.dump(default_events, f, indent=2)
        print("Created events.json with default data.")


def load_state() -> Dict[str, Any]:
    """Loads all JSON files into a single state dictionary."""
    state = {}
    
    # Load character.json
    with open("gamedata/character.json", 'r') as f:
        state["character"] = json.load(f)
    
    # Load world.json
    with open("gamedata/world.json", 'r') as f:
        state["world"] = json.load(f)
    
    # Load events.json
    with open("gamedata/events.json", 'r') as f:
        state["events"] = json.load(f)
    
    return state


def save_state(state_data: Dict[str, Any]):
    """Saves the provided state back to the individual JSON files."""
    # Save character.json
    with open("gamedata/character.json", 'w') as f:
        json.dump(state_data["character"], f, indent=2)
    
    # Save world.json
    with open("gamedata/world.json", 'w') as f:
        json.dump(state_data["world"], f, indent=2)
    
    # Save events.json
    with open("gamedata/events.json", 'w') as f:
        json.dump(state_data["events"], f, indent=2)


def query_llm(prompt_text: str) -> str:
    """
    Placeholder function for LLM query.
    Prints the full prompt and returns a hardcoded example response.
    """
    print("\n" + "="*60)
    print("LLM PROMPT:")
    print("="*60)
    print(prompt_text)
    print("="*60)
    print("LLM RESPONSE (SIMULATED):")
    print("="*60)
    
    # Hardcoded example response
    simulated_response = {
        "response_text": "You check your pockets and find the rusty pocket knife. The sun is high in the sky.",
        "new_event": "Orton checked his inventory.",
        "state_changes": {
            "character.json": {
                "status": ["healthy", "feeling confident"]
            }
        }
    }
    
    response_json = json.dumps(simulated_response)
    print(response_json)
    print("="*60 + "\n")
    
    return response_json


def run_game_turn(player_input: str):
    """
    Main game loop function that performs a complete turn.
    """
    # Step A: Load Game State
    state = load_state()
    
    # Step B: Assemble the LLM Prompt
    character = state["character"]
    world = state["world"]
    events = state["events"]
    
    # Format status and inventory as comma-separated strings
    status_str = ", ".join(character["status"])
    inventory_str = ", ".join(character["inventory"])
    
    # Format recent events (up to 5, in reverse chronological order)
    events_section = ""
    for i, event in enumerate(events[:5]):  # Take only the first 5 (most recent)
        events_section += f"    {event}\n\n"
    
    # Remove trailing newlines if events exist
    if events_section:
        events_section = events_section.rstrip("\n")
    
    # Assemble the complete prompt
    llm_prompt = f"""[CHARACTER]
Name: {character['name']}, Status: {status_str}, Inventory: {inventory_str}

[WORLD]
Location: {world['current_location']}, Time: {world['time_of_day']}

[RECENT EVENTS]

{events_section}

[SCENE]
{player_input}"""
    
    # Step C: Query the LLM (Placeholder)
    llm_response_json = query_llm(llm_prompt)
    
    # Step D: Parse and Apply LLM Response
    try:
        llm_response = json.loads(llm_response_json)
        
        # 1. Print response text to player
        print("GAME RESPONSE:")
        print(llm_response.get("response_text", ""))
        print()
        
        # 2. Add new event to the top of events list and maintain sliding window of 5
        new_event = llm_response.get("new_event", "")
        if new_event:
            # Insert new event at the beginning
            state["events"].insert(0, new_event)
            # Keep only the 5 most recent events
            state["events"] = state["events"][:5]
        
        # 3. Apply state changes
        state_changes = llm_response.get("state_changes", {})
        for filename, changes in state_changes.items():
            if filename == "character.json":
                # Update character data
                for key, value in changes.items():
                    state["character"][key] = value
            elif filename == "world.json":
                # Update world data
                for key, value in changes.items():
                    state["world"][key] = value
            # Note: events.json changes are handled above with new_event
        
    except json.JSONDecodeError:
        print("Error: Invalid JSON response from LLM")
        return
    
    # Step E: Save Game State
    save_state(state)


def main():
    """Main execution function."""
    print("="*60)
    print("        WELCOME TO THE LOCAL LLM-POWERED RPG")
    print("="*60)
    print("Type 'quit' to exit the game.")
    print("Type anything else to interact with the world.")
    print()
    
    # Setup game files
    setup_game_files()
    print()
    
    # Main game loop
    while True:
        try:
            # Get player input
            player_input = input("> ").strip()
            
            # Check for quit command
            if player_input.lower() == "quit":
                print("Thanks for playing! Goodbye.")
                break
            
            # Skip empty input
            if not player_input:
                print("Please enter a command or type 'quit' to exit.")
                continue
            
            # Run the game turn
            run_game_turn(player_input)
            
        except KeyboardInterrupt:
            print("\n\nGame interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            print("Game continuing...")


if __name__ == "__main__":
    main()
