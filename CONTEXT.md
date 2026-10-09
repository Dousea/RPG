# Over the River

A text RPG in a zombie apocalypse: the player types what their character does, the engine decides what happens, and a narrator tells it.

## Language

### Turns

**Turn**:
Everything that follows one input from the player, from parsing it to the narrated story.
_Avoid_: round, step, move

**Plan**:
The ordered actions the engine reads from one turn's input.
_Avoid_: action list, command

**Leg**:
The part of a turn's plan that runs in one zone; a zone change ends a leg, and the turn may go on with one more leg planned at the destination.
_Avoid_: round, plan run, scene plan
