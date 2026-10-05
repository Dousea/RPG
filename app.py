"""Flask front end for the RPG.

This module is deliberately thin: it does HTTP and nothing else. A turn is
`GameEngine.play()`, which owns the LLM call, the state changes, the memory
index and persistence. Game rules live in `managers/` and `modules/`.
"""

import json
import logging

from flask import Flask, Response, jsonify, render_template, request

import config
from adapters.engine import GameEngine

app = Flask(__name__)
logger = logging.getLogger(__name__)

# The engine is built on first use rather than at import time: constructing it
# loads the save and can pull in the sentence-transformer model, which would
# otherwise run during `flask --app app` startup and in any tooling that merely
# imports this module.
_engine: GameEngine | None = None


def get_engine() -> GameEngine:
    global _engine
    if _engine is None:
        _engine = GameEngine()
    return _engine


@app.route("/")
def index():
    """Serves the main HTML page for the game."""
    return render_template("index.html")


@app.route("/state", methods=["GET"])
def state():
    """Current game state, so a reloaded page shows the real world."""
    return jsonify(get_engine().state())


@app.route("/play", methods=["POST"])
def play():
    """Receives player input, runs a game turn, and returns the result."""
    payload = request.get_json(silent=True) or {}
    player_input = (payload.get("input") or "").strip()
    if not player_input:
        return jsonify({"error": "No input provided"}), 400

    return jsonify(get_engine().play(player_input))


@app.route("/reset", methods=["POST"])
def reset_game():
    """Deletes the save and starts a fresh game."""
    result = get_engine().reset()
    return jsonify({"message": "Game has been reset.", "state": result})


@app.route("/save/export", methods=["GET"])
def export_save():
    """Download the current game as a save file."""
    payload = get_engine().export_save()
    body = json.dumps(payload, indent=2)
    return Response(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=orton-save.json"},
    )


@app.route("/save/import", methods=["POST"])
def import_save():
    """Replace the current game with a save file the player uploads."""
    upload = request.files.get("save")
    if upload is None or not upload.filename:
        return jsonify({"error": "No save file provided."}), 400
    try:
        data = json.loads(upload.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"error": "That file isn't valid save data."}), 400

    result = get_engine().import_save(data)
    if result is None:
        return jsonify({"error": "That save is missing or from an incompatible version."}), 400
    return jsonify(result)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG if config.server.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting RPG server...")
    # Build the engine up front so a slow save load or model warm-up happens
    # before the first request rather than during it.
    get_engine()
    logger.info(f"Server ready at http://{config.server.host}:{config.server.port}")
    app.run(debug=config.server.debug, host=config.server.host, port=config.server.port)
