# Local LLM RPG

A text-based RPG game powered by a local Large Language Model (LLM) with advanced memory management and semantic search capabilities. This project creates an immersive storytelling experience using AI-driven narrative generation with persistent game state and intelligent memory retrieval.

## 🎮 Project Overview

This RPG system combines traditional text-based adventure gaming with cutting-edge AI technology to create dynamic, contextual storytelling. The game features a post-apocalyptic setting where players navigate through various locations, interact with NPCs, manage inventory, and experience AI-generated narrative responses that adapt to their choices.

### Key Features

- **AI-Powered Storytelling**: Uses local LLM (via LM Studio) for dynamic narrative generation
- **Hybrid Memory System**: Combines short-term recent events with long-term semantic memory
- **Persistent Game State**: All game data is stored in JSON files and maintained across sessions
- **Semantic Search**: FAISS-powered similarity search for retrieving relevant past events
- **Web Interface**: Modern, terminal-styled web UI built with Flask and Tailwind CSS
- **Real-time Gameplay**: Instant responses and state updates through REST API

## 🏗️ Technical Architecture

### Core Components

#### 1. **Flask Web Server** (`app.py`)

- **Framework**: Flask with JSON API endpoints
- **Routes**:
  - `/` - Serves the game interface
  - `/play` - Processes player input and returns game responses
  - `/reset` - Resets game state to initial conditions

#### 2. **LLM Integration**

- **Local Model**: Connects to LM Studio running locally on port 1234
- **API**: OpenAI-compatible chat completions endpoint
- **Response Format**: Structured JSON with story text, events, and state changes
- **Dual Purpose**: Main gameplay responses + event summarization

#### 3. **Hybrid Memory System**

##### Phase 3 Memory Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Short-term    │    │   Deep Memory    │    │   Summaries     │
│  (events.json)  │    │ (full_event_log) │    │(summaries.json) │
│                 │    │                  │    │                 │
│ Last 5 events   │    │ All events ever  │    │ Condensed past  │
│ Immediate       │    │ FAISS indexed    │    │ Long-term arc   │
│ context         │    │ Semantic search  │    │ Narrative flow  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

##### Memory Components

- **Recent Events**: Last 5 actions stored in `events.json` for immediate context
- **Deep Memory**: Complete event history in `full_event_log.json` with FAISS indexing
- **Semantic Search**: Vector similarity search using sentence transformers
- **Auto-Summarization**: LLM-generated summaries when event count exceeds threshold

#### 4. **FAISS Vector Search Engine**

```python
# Key Implementation Details:
- Model: 'all-MiniLM-L6-v2' sentence transformer
- Index Type: IndexFlatIP (Inner Product for cosine similarity)
- Embedding Dimension: 384
- Normalization: L2 normalization for cosine similarity
- Real-time Updates: Index rebuilt after each new event
```

#### 5. **Game State Management**

##### JSON Data Structure

```
gamedata/
├── character.json     # Player stats, inventory, status
├── world.json         # Current location, time of day
├── events.json        # Recent 5 events (short-term memory)
├── full_event_log.json # Complete event history (deep memory)
├── locations.json     # All locations with descriptions, items, connections
├── npcs.json          # NPC data with status and locations
└── summaries.json     # LLM-generated story summaries
```

##### State Update Flow

1. Load current state from JSON files
2. Perform semantic search on player input
3. Filter contextual data (current location, nearby areas, present NPCs)
4. Assemble hybrid prompt with deep memories + recent context
5. Process LLM response and parse state changes
6. Update JSON files and rebuild FAISS index

#### 6. **Frontend Interface**

- **Technology**: HTML5 + Tailwind CSS + Vanilla JavaScript
- **Design**: Retro terminal aesthetic with green-on-black color scheme
- **Font**: VT323 monospace for authentic computer terminal feel
- **Layout**: Responsive design with story panel and action input
- **Features**: Auto-scrolling, blinking cursor, reset functionality

### Data Flow Architecture

```
Player Input → Flask Route → Game Turn Processing
     ↓
Semantic Search (FAISS) ← Full Event Log
     ↓
Context Assembly ← Current State (JSON files)
     ↓
LLM Prompt Generation → LM Studio
     ↓
Response Parsing ← AI-Generated JSON
     ↓
State Updates → JSON Files + FAISS Rebuild
     ↓
Frontend Response ← Game Results
```

## 🛠️ Technical Implementation Details

### Memory Management Strategy

#### Semantic Search Implementation

- **Purpose**: Retrieve contextually relevant past events based on current player input
- **Technology**: FAISS (Facebook AI Similarity Search) with sentence transformers
- **Model**: `all-MiniLM-L6-v2` for generating 384-dimensional embeddings
- **Search**: Returns top 2 most semantically similar past events

#### Heuristic Filtering

- **Location-based**: Only includes NPCs and items in current/adjacent locations
- **Relevance**: Filters game world data to provide focused context to LLM
- **Performance**: Reduces prompt size while maintaining narrative coherence

#### Auto-Summarization

- **Trigger**: Activates when events exceed 10 items
- **Process**: LLM condenses older events into narrative paragraphs
- **Result**: Maintains long-term story continuity without context overflow

### LLM Prompt Engineering

#### Structured Prompt Format

```
[CHARACTER] - Current player state
[DEEP MEMORY] - Semantically retrieved past events
[WORLD] - Current location and time
[ITEMS IN CURRENT LOCATION] - Available objects
[NEARBY LOCATIONS] - Connected areas
[NPCS PRESENT] - Characters in current location
[SUMMARY OF PAST EVENTS] - Long-term narrative
[RECENT EVENTS] - Last 5 actions
[SCENE] - Current player input
```

#### Response Format Requirements

- **Structure**: Valid JSON with three required keys
- **Content**: `response_text`, `new_event`, `state_changes`
- **State Updates**: Specific file targeting for precise game state modifications

## 📋 Requirements

### System Dependencies

```
Python 3.8+
LM Studio (local LLM server)
Compatible local language model
```

### Python Packages

```
Flask==2.3.3
requests==2.31.0
faiss-cpu==1.7.4
sentence-transformers==2.2.2
numpy==1.24.3
```

## 🚀 Installation & Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup LM Studio

1. Download and install [LM Studio](https://lmstudio.ai/)
2. Load a compatible chat model (recommend 7B+ parameters)
3. Start local server on port 1234
4. Ensure OpenAI-compatible API is enabled

### 3. Run the Game

```bash
python app.py
```

### 4. Access Game Interface

Open your browser and navigate to: `http://localhost:5000`

## 🎯 Game Features

### World Exploration

- **Post-apocalyptic setting** with interconnected locations
- **Dynamic descriptions** generated by AI based on context
- **Item management** with persistent inventory system
- **Location-based interactions** with environmental objects

### NPC Interactions

- **Contextual NPCs** with unique personalities and statuses
- **Location-aware encounters** - NPCs appear only in their designated areas
- **Dynamic dialogue** generated based on current game state and history

### Memory System Benefits

- **Continuity**: References to past events maintain story coherence
- **Depth**: Long-term character development and world evolution
- **Relevance**: Semantic search surfaces meaningful connections
- **Performance**: Efficient memory usage with summarization

## 🧠 AI & Memory System

### Semantic Memory Retrieval

The system uses advanced NLP to understand player intent and retrieve relevant past experiences:

- **Input Analysis**: Player commands are encoded into vector embeddings
- **Similarity Search**: FAISS finds the most contextually relevant past events
- **Context Integration**: Retrieved memories are woven into the current narrative

### State Persistence

Every game action is preserved across sessions:

- **Complete History**: Full event log maintains perfect recall
- **Efficient Access**: FAISS indexing enables fast similarity searches
- **Narrative Continuity**: Summarization preserves long-term story arcs

### Dynamic World Building

The AI creates an evolving world that responds to player choices:

- **Consistent Locations**: Physical spaces maintain logical properties
- **Persistent NPCs**: Characters remember interactions and evolve
- **Consequence System**: Past actions influence future possibilities

## 🔧 Configuration

### Memory System Tuning

- `MAX_EVENTS = 5`: Number of recent events in short-term memory
- `EVENTS_THRESHOLD = 10`: Trigger point for auto-summarization
- `k=2`: Number of deep memories retrieved per search

### LLM Settings

- Temperature: 0.7 (balanced creativity/consistency)
- Model: Local model via LM Studio
- API Endpoint: `http://localhost:1234/v1/chat/completions`

## 📁 Project Structure

```
RPG/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This documentation
├── templates/
│   └── index.html        # Web interface
└── gamedata/
    ├── character.json    # Player data
    ├── world.json        # World state
    ├── events.json       # Recent events
    ├── full_event_log.json # Complete history
    ├── locations.json    # Game world map
    ├── npcs.json         # Non-player characters
    └── summaries.json    # Story summaries
```

## 🎮 How to Play

1. **Start the game** by running the Flask application
2. **Read the scenario** presented in the story panel
3. **Type your action** in the input field (e.g., "look around", "take the knife", "talk to Dale")
4. **View the AI response** as the story unfolds based on your choices
5. **Continue exploring** - your actions shape the narrative and world state

## 🔮 Future Enhancements

- **Multiple character classes** with unique abilities
- **Combat system** with tactical decision-making
- **Branching storylines** with multiple endings
- **Save/load game slots** for multiple playthroughs
- **Enhanced NPC AI** with individual memory systems
- **Multiplayer support** for collaborative storytelling
