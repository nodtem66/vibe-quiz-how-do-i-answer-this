import argparse
import os
import uuid
from contextlib import asynccontextmanager

import qrcode
import qrcode.image.svg
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException
from fastapi.responses import FileResponse
from pydantic_core import PydanticSerializationError

from quiz import QuizSession, QuizSessionState, generate_quiz

quiz_session = QuizSession()

def parseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="General science")
    parser.add_argument("--questions", type=int, default=5)
    parser.add_argument("--port", type=int, default=8000, help="local server port")
    return parser.parse_args()

def generate_qrcode(url: str) -> str:
    svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathFillImage)
    svg_text = svg.to_string()
    if isinstance(svg_text, bytes):
        svg_text = svg_text.decode("utf-8")
    return svg_text

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage shared memory of quiz session.

    It consists of the start up logics, yield, and the shutdown logics.
    https://fastapi.tiangolo.com/advanced/events/
    """
    # Start up
    args = parseArgs()
    quiz_session.topic = args.topic
    quiz_session.questions = await generate_quiz(
        args.topic,
        args.questions,
    )
    quiz_session.num_questions = len(quiz_session.questions)
    tunnel_url = os.getenv("PLAYER_URL")
    quiz_session.player_url = tunnel_url
    if tunnel_url is not None:
        quiz_session.player_qrcode_svg = generate_qrcode(tunnel_url)
    
    print("=" * 30)
    print("Quiz session is ready!")
    print(
        f"Host URL:\thttp://localhost:{args.port}/?token={quiz_session.host_access_token}"
    )
    print(f"Player URL:\thttp://localhost:{args.port}/")
    print(f"           \t{tunnel_url}")
    print("=" * 30)
    # End start up
    yield
    # Shut down
    # End shut down


app = FastAPI(lifespan=lifespan)


async def broadcast_state():
    if quiz_session is None:
        return
    q = quiz_session.current_question()
    question_payload = None
    if q is not None:
        question_payload = {
            "id": q.id,
            "question": q.question
            if quiz_session.state is not QuizSessionState.LEADERBOARD
            else None,
            "choices": q.choices,
            "correct_index": q.correct_index
            if quiz_session.state
            in [QuizSessionState.REVEAL, QuizSessionState.LEADERBOARD]
            else None,
        }

    leaderboard = sorted(
        [
            {"name": v["name"], "score": v["score"]}
            for v in quiz_session.players.values()
        ],
        key=lambda x: x["score"],
        reverse=True,
    )

    payload = {
        "state": quiz_session.state,
        "topic": quiz_session.topic,
        "question": question_payload,
        "question_num": quiz_session.current_question_idx + 1,
        "total_questions": quiz_session.num_questions,
        "players_count": len(quiz_session.players),
        "leaderboard": leaderboard,
    }

    if quiz_session.host_socket:
        if quiz_session.state == QuizSessionState.LOBBY:
            payload["player_url"] = quiz_session.player_url,
            payload["player_qrcode_svg"] = quiz_session.player_qrcode_svg,
        try:
            await quiz_session.host_socket.send_json(
                {
                    "role": "host",
                    "full_quiz": [q.model_dump() for q in quiz_session.questions],
                    **payload,
                }
            )
        except PydanticSerializationError:
            print("Error: pydantic exception during sending payload to host")
        except RuntimeError:
            print("Error: cannot send payload to host")

    dead_sockets = []
    for player_id, ws in quiz_session.player_sockets.items():
        try:
            has_answered = player_id in quiz_session.answers.get(
                quiz_session.current_question_idx, {}
            )
            await ws.send_json(
                {
                    "role": "player",
                    "player_id": player_id,
                    "has_answered": has_answered,
                    **payload,
                }
            )
        except RuntimeError, OSError, WebSocketException, WebSocketDisconnect:
            print(f"Error: Cannot send payload to player {player_id}")
            dead_sockets.append((player_id, ws))

    for player_id, ws in dead_sockets:
        quiz_session.disconnect_player(player_id, ws)


@app.get("/")
async def frontend(token: str = ""):
    if token == quiz_session.host_access_token:
        return FileResponse("static/host.html")
    return FileResponse("static/index.html")


@app.websocket("/ws")
async def websocket_handler(ws: WebSocket, token: str = ""):
    if token == quiz_session.host_access_token:
        await host_websocket(ws)
        return
    await player_websocket(ws)


async def player_websocket(ws: WebSocket):
    await ws.accept()
    client_id = str(uuid.uuid4())
    player_id = client_id

    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "JOIN_PLAYER":
                name = data.get("name", "Anonymous")
                requested_player_id = data.get("player_id")
                player_id = (
                    requested_player_id
                    if isinstance(requested_player_id, str)
                    and requested_player_id in quiz_session.players
                    else client_id
                )
                if not quiz_session.add_player(player_id, name, ws):
                    await ws.send_json(
                        {
                            "error": "A player with that name has already joined.",
                        }
                    )
                    continue
                await broadcast_state()
            elif action == "SUBMIT_ANSWER":
                choic_idx = data.get("choice_index")
                if quiz_session.player_sockets.get(player_id) is ws:
                    quiz_session.record_answer(player_id, choic_idx)
                await broadcast_state()
    except WebSocketException, WebSocketDisconnect:
        if quiz_session.player_sockets.get(player_id) is ws:
            quiz_session.disconnect_player(player_id, ws)
            await broadcast_state()


async def host_websocket(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "INIT_HOST":
                quiz_session.host_socket = ws
                await broadcast_state()
            elif action == "NEXT_STATE":
                if quiz_session.state == QuizSessionState.LOBBY:
                    quiz_session.state = QuizSessionState.QUESTION
                    quiz_session.current_question_idx = 0
                    quiz_session.start_question()
                elif quiz_session.state == QuizSessionState.QUESTION:
                    quiz_session.state = QuizSessionState.REVEAL
                    quiz_session.grade_answer()
                elif quiz_session.state == QuizSessionState.REVEAL:
                    quiz_session.state = QuizSessionState.LEADERBOARD
                elif quiz_session.state == QuizSessionState.LEADERBOARD:
                    if (
                        quiz_session.current_question_idx + 1
                        < quiz_session.num_questions
                    ):
                        quiz_session.current_question_idx += 1
                        quiz_session.state = QuizSessionState.QUESTION
                        quiz_session.start_question()
                    else:
                        quiz_session.state = QuizSessionState.FINISHED
                await broadcast_state()
    except (WebSocketException, WebSocketDisconnect) as e:
        print("Host socket Error:", str(e))
