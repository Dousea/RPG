"""A which-one question the validator asks when a name fits several things, and the candidates that answer it (llm-contract)."""

from dataclasses import dataclass
from typing import Literal

from modules.action.pins import Pinned

CandidateKind = Literal["item", "zone", "container"]


@dataclass(frozen=True)
class Candidate:
    """One thing a name could mean: a zone or container by id, an item by its qualified name ("broken Baseball Bat")."""

    kind: CandidateKind
    id: str
    name: str
    description: str
    pinned_as: str = ""

    def written(self) -> str:
        """What goes into the action's target field to name exactly this: a pin for a zone or container, the qualified name for an item."""
        if self.kind == "item":
            return self.id
        return Pinned(self.pinned_as or self.name, self.kind, self.id)


class Question(str):
    """The words of a which-one refusal; `asked` is the name that fit several things and `candidates` what it could mean."""

    asked: str
    candidates: tuple[Candidate, ...]

    def __new__(cls, text: str, asked: str, candidates: tuple[Candidate, ...]) -> "Question":
        question = super().__new__(cls, text)
        question.asked = asked
        question.candidates = candidates
        return question
