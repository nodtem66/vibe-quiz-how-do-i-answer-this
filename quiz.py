import json
import os
import secrets
import time
from enum import Enum

from fastapi import WebSocket
from openrouter import OpenRouter
from openrouter.errors import OpenRouterError
from pydantic import BaseModel


class Question(BaseModel):
    id: int
    question: str
    choices: list[str]
    correct_index: int


class QuizSessionState(str, Enum):
    LOBBY = "LOBBY"
    QUESTION = "QUESTION"
    REVEAL = "REVEAL"
    LEADERBOARD = "LEADERBOARD"
    FINISHED = "FINISHED"


class QuizSession:
    def __init__(self):
        self.state: QuizSessionState = QuizSessionState.LOBBY
        self.topic: str = ""
        self.questions: list[Question] = []
        self.num_questions = 0
        self.current_question_idx: int = -1
        self.question_started_at: float | None = None
        self.players: dict[str, dict] = {}  # player_id -> {name, score}
        self.answers: dict[
            int, dict[str, int]
        ] = {}  # question_id -> {player_id: choice_id}
        self.elapsed_time: dict[
            int, dict[str, float]
        ] = {}  # question_id -> {player_id: elapsed_time}
        self.host_socket: WebSocket | None = None
        self.player_sockets: dict[str, WebSocket] = {}
        self.host_access_token: str = secrets.token_urlsafe(32)

    def current_question(self) -> Question | None:
        if 0 <= self.current_question_idx < self.num_questions:
            return self.questions[self.current_question_idx]
        return None

    def start_question(self):
        self.question_started_at = time.monotonic()

    def add_player(self, player_id: str, name: str, ws: WebSocket):
        if any(
            player["name"] == name and existing_id != player_id
            for existing_id, player in self.players.items()
        ):
            return False

        if player_id in self.players:
            self.players[player_id]["name"] = name
        else:
            self.players[player_id] = {"name": name, "score": 0}
        self.player_sockets[player_id] = ws
        return True

    def disconnect_player(self, player_id: str, ws: WebSocket):
        if self.player_sockets.get(player_id) is ws:
            self.player_sockets.pop(player_id, None)

    def record_answer(self, player_id: str, choice_id: int):
        if self.state != QuizSessionState.QUESTION or self.current_question_idx < 0:
            return
        # Save answer
        current_answer = self.answers.setdefault(self.current_question_idx, {})
        current_answer[player_id] = choice_id
        # Save elapsed time
        elapsed_time = self.elapsed_time.setdefault(self.current_question_idx, {})
        elapsed_time[player_id] = (
            time.monotonic() - self.question_started_at
            if self.question_started_at is not None
            else 30.0
        )

    def grade_answer(self):
        if self.state != QuizSessionState.REVEAL:
            return
        q = self.questions[self.current_question_idx]
        answer = self.answers.setdefault(self.current_question_idx, {})
        elapsed_time = self.elapsed_time.setdefault(self.current_question_idx, {})
        for player_id, answer_idx in answer.items():
            if q.correct_index == answer_idx:
                extra_score = min(20.0, max(0.0, 30.0 - elapsed_time[player_id]))
                self.players[player_id]["score"] += round(100 + extra_score)


async def _generate_quiz(topic: str, num_questions: int = 5) -> list[Question]:
    return [
        Question(
            id=_id,
            question=f"Demo question {_id} on {topic}",
            choices=[
                "Option A" + (" (Correct)" if _id % 4 == 0 else ""),
                "Option B" + (" (Correct)" if _id % 4 == 1 else ""),
                "Option C" + (" (Correct)" if _id % 4 == 2 else ""),
                "Option D" + (" (Correct)" if _id % 4 == 3 else ""),
            ],
            correct_index=(_id % 4),
        )
        for _id in range(1, num_questions + 1)
    ]


DEFAULT_PROMPT = """You are a quiz generator for undergrad students to learn a specific topic.
Generate a quiz about '{topic}' with {num_questions} multiple choice (4 choices) questions.
Return ONLY a raw JSON array of objects. Do not include markdown formatting, code blocks, or explanatory text.
Schema per item:
{{
  "id": integer (1 to N),
  "question": "string",
  "choices": ["Option A", "Option B", "Option C", "Option D"],
  "correct_index": integer (0 to 3)
}}
"""


async def generate_quiz(
    topic: str, num_questions: int = 5, prompt: str = DEFAULT_PROMPT
) -> list[Question]:
    try:
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("OPENROUTER_MODEL")
        with OpenRouter(api_key=api_key) as open_router:
            res = open_router.chat.send(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt.format(
                            topic=topic, num_questions=num_questions
                        ),
                    }
                ],
                provider={"sort": "price"},
                stream=False,
            )
            data: list = json.loads(str(res.choices[0].message.content))
            if len(data) != num_questions:
                raise RuntimeError(f"Response from {model} is not correct")
            return [Question(**q) for q in data]
    except json.JSONDecodeError:
        print("Error: Invalid json from OpenRouter api")
    except (ValueError, OpenRouterError, RuntimeError) as e:
        print("Error: ", e.__class__.__name__, str(e))

    return await _generate_quiz(topic, num_questions)
