"""Flask front end for the RPG.

This module is deliberately thin: it does HTTP and nothing else. A turn is
`GameEngine.play()`, which owns the LLM call, the state changes, the memory
index and persistence. Game rules live in `managers/` and `modules/`.
"""

import json
import logging
import queue
import threading
from collections.abc import Iterator
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

import config
from adapters.creation_payload import build_from_payload, creation_screen
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


def _turn_input() -> tuple[str, list[str], Any]:
    """The player's input and the ids they picked from the `@` list, or "" and the error response a turn request gets instead."""
    payload = request.get_json(silent=True) or {}
    player_input = (payload.get("input") or "").strip()
    if not player_input:
        return "", [], (jsonify({"error": "No input provided"}), 400)
    if not get_engine().has_game:
        return (
            "",
            [],
            (jsonify({"error": "Create a character first.", "needs_creation": True}), 409),
        )
    mentions = payload.get("mentions")
    ids = [m for m in mentions if isinstance(m, str)] if isinstance(mentions, list) else []
    return player_input, ids, None


@app.route("/play", methods=["POST"])
def play():
    """Receives player input, runs a game turn, and returns the result."""
    player_input, mentions, error = _turn_input()
    if error:
        return error
    return jsonify(get_engine().play(player_input, mentions=mentions))


@app.route("/play/stream", methods=["POST"])
def play_stream():
    """Runs a turn and sends its events as JSON lines as they happen, then {"type": "done", "turn": ...}.

    The turn runs on its own thread, so a player who closes the page mid-turn
    still gets the turn decided, recorded and saved.
    """
    player_input, mentions, error = _turn_input()
    if error:
        return error
    engine = get_engine()
    events: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def run() -> None:
        try:
            turn = engine.play(player_input, on_event=events.put, mentions=mentions)
            events.put({"type": "done", "turn": turn})
        except Exception as exc:
            logger.exception("Streamed turn failed")
            events.put({"type": "error", "message": str(exc)})
        events.put(None)

    def lines() -> Iterator[str]:
        while (event := events.get()) is not None:
            yield json.dumps(event) + "\n"

    threading.Thread(target=run, daemon=True).start()
    return Response(
        lines(),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/reset", methods=["POST"])
def reset_game():
    """Deletes the save; the page then shows the creation screen."""
    result = get_engine().reset()
    return jsonify({"message": "Game has been reset.", "state": result})


@app.route("/creation", methods=["GET"])
def creation_options():
    """Everything the creation screen needs."""
    return jsonify(creation_screen())


@app.route("/creation", methods=["POST"])
def create_character():
    """Validate a build; an invalid one starts nothing, a valid one starts day 1."""
    payload = request.get_json(silent=True)
    build = build_from_payload(payload) if isinstance(payload, dict) else None
    if build is None:
        return jsonify({"errors": ["The build is missing or malformed."]}), 400
    errors, snapshot = get_engine().create_character(build)
    if errors:
        return jsonify({"errors": errors}), 400
    return jsonify(snapshot)


@app.route("/save/export", methods=["GET"])
def export_save():
    """Download the current game as a save file."""
    engine = get_engine()
    if not engine.has_game:
        return jsonify({"error": "There is no game to save."}), 409
    payload = engine.export_save()
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
