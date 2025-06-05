from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import random
import time, os
from uuid import uuid4
import requests
import uvicorn
import pika
import json
from contextlib import contextmanager
import threading

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# GAME_TASKS_QUEUE = 'game_tasks' # Superseded by GAME_LOGIC_QUEUE
GAME_LOGIC_QUEUE = 'game_logic_tasks'
BOARD_SIZE = 20 # Default board size
GAME_TICK_INTERVAL = 1 # Seconds between game ticks (e.g., 0.2 for 5 updates/sec)
COORDINATOR_IP = '100.120.4.105'


# --- New Game State Management and Models ---
game_instances: Dict[str, 'GameStateModel'] = {}

class Position(BaseModel):
    x: int
    y: int

class GameStateModel(BaseModel):
    snake: List[Position]
    food: Position
    score: int
    gameOver: bool
    direction: str # Current direction of the snake (e.g., "UP", "DOWN")
    boardSize: int = BOARD_SIZE
    gameId: Optional[str] = None # Will be set when instance is created
    last_move_processed_time: float = 0.0 # Timestamp of the last processed move

class JoinResponse(BaseModel):
    gameId: str
    initialState: GameStateModel

class MovePlayerPayload(BaseModel):
    gameId: str
    direction: Position # Expecting dx, dy from frontend

class UpdateGameStateInternalPayload(BaseModel):
    gameId: str
    newState: GameStateModel

class GameLogicTaskPayload(BaseModel):
    task_type: str = "update_game_state"
    gameId: str
    current_state: GameStateModel # This will contain the 'direction' string
    # requested_direction: Position # Removed, direction is now in current_state.direction
    task_id: str

# Helper function to translate dx, dy to direction string
def position_to_direction_str(pos: Position, current_direction_str: str) -> str:
    if pos.x == 1 and pos.y == 0: return "RIGHT"
    if pos.x == -1 and pos.y == 0: return "LEFT"
    if pos.x == 0 and pos.y == 1: return "DOWN"  # Assuming positive y is down for frontend, adjust if necessary
    if pos.x == 0 and pos.y == -1: return "UP"    # Assuming negative y is up for frontend, adjust if necessary
    # If (0,0) or invalid, keep current direction
    return current_direction_str



def create_initial_game_state(game_id: str) -> GameStateModel:
    mid_x, mid_y = BOARD_SIZE // 2, BOARD_SIZE // 2
    initial_snake = [
        Position(x=mid_x, y=mid_y),
        Position(x=mid_x - 1, y=mid_y),
        Position(x=mid_x - 2, y=mid_y),
    ]
    # Ensure food is not on the snake initially
    while True:
        food_pos = Position(x=random.randint(0, BOARD_SIZE - 1), y=random.randint(0, BOARD_SIZE - 1))
        if food_pos not in initial_snake:
            break
    return GameStateModel(
        gameId=game_id,
        snake=initial_snake,
        food=food_pos,
        score=0,
        gameOver=False,
        direction="RIGHT", # Initial direction
        boardSize=BOARD_SIZE,
        last_move_processed_time=0.0
    )

from typing import Optional

@contextmanager
def rabbitmq_channel():
    connection = None
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=COORDINATOR_IP,  # <- IP Tailscale del servidor RabbitMQ
                port=5672,   
                credentials=pika.PlainCredentials('myuser', 'mypassword')
            )
        )
        channel = connection.channel()
        yield channel
    finally:
        if connection and connection.is_open:
            connection.close()


# --- New Snake Game API Endpoints ---

game_instances = {}

@app.post("/join", response_model=JoinResponse)
async def join_game():
    game_id = uuid4().hex
    initial_state = create_initial_game_state(game_id)
    initial_state.last_move_processed_time = time.time() # Initialize on game creation
    game_instances[game_id] = initial_state
    print(f"Game created with ID: {game_id}")
    return JoinResponse(gameId=game_id, initialState=initial_state)

@app.post("/move")
async def move_snake(payload: MovePlayerPayload):
    game_id = payload.gameId
    current_time = time.time()
    current_game_state = game_instances.get(game_id)

    if not current_game_state:
        return JSONResponse(content={"status": "error", "message": "Game not found"}, status_code=404)

    if current_time - current_game_state.last_move_processed_time < 1.0: # 1 second throttle
        return JSONResponse(content={"status": "too_many_requests", "message": "Move ignored, too soon after last move."}, status_code=429)

    # Redundant assignments of game_id and current_game_state removed.
    # current_game_state (defined and checked earlier in the function) is used in subsequent logic.

    if not current_game_state or current_game_state.gameOver:
        return {"status": "error", "message": "Game not found or over"}, 404

    # Determine new direction string based on payload.direction (dx, dy)
    # The frontend sends dx, dy; we convert to string direction for the game state.
    new_direction_str = position_to_direction_str(payload.direction, current_game_state.direction)

    # Prevent snake from immediately reversing
    can_change_direction = True
    if (new_direction_str == "LEFT" and current_game_state.direction == "RIGHT") or \
       (new_direction_str == "RIGHT" and current_game_state.direction == "LEFT") or \
       (new_direction_str == "UP" and current_game_state.direction == "DOWN") or \
       (new_direction_str == "DOWN" and current_game_state.direction == "UP"):
        can_change_direction = False
    
    if can_change_direction:
        current_game_state.direction = new_direction_str
    # If cannot change (e.g. reversing), current_game_state.direction remains as is.

    # The game loop will now pick up this updated current_game_state.direction
    # So, this endpoint primarily just updates the intended direction.
    # For immediate feedback or if not using a game loop, you might still queue a task here.
    # However, with a game loop, this endpoint's main job is to set the direction.
    # For now, we will still queue a task to make the move feel responsive, 
    # even if the game loop would also pick it up.

    current_game_state.last_move_processed_time = current_time # Update timestamp after all validations pass

    task_id = uuid4().hex
    # Create a snapshot of the state to send for this specific move task
    # The worker will use current_game_state.direction from this snapshot.
    task_payload_data = GameLogicTaskPayload(
        gameId=game_id,
        current_state=current_game_state.copy(deep=True), # Send a copy with the latest direction
        task_id=task_id
    )

    try:
        with rabbitmq_channel() as channel:
            channel.queue_declare(queue=GAME_LOGIC_QUEUE, durable=True)
            channel.basic_publish(
                exchange='',
                routing_key=GAME_LOGIC_QUEUE,
                body=task_payload_data.json(),
                properties=pika.BasicProperties(
                    delivery_mode=2, # Persistent
                    content_type='application/json',
                    correlation_id=task_id
                )
            )
        print(f"Sent game logic task {task_id} (from /move) to queue {GAME_LOGIC_QUEUE} for game {game_id} with direction {current_game_state.direction}")
        return {"status": "move_direction_updated_and_queued", "task_id": task_id, "new_direction": current_game_state.direction}
    except Exception as e:
        print(f"Error sending game logic task from /move for game {game_id}: {e}")
        return {"status": "error", "message": str(e)}, 500

@app.get("/state/{game_id}", response_model=GameStateModel)
async def get_game_state(game_id: str):
    current_game_state = game_instances.get(game_id)
    if not current_game_state:
        return JSONResponse(content={"status": "error", "message": "Game not found"}, status_code=404)
    return current_game_state

def game_loop():
    """Periodically queues game state update tasks for all active games."""
    while True:
        time.sleep(GAME_TICK_INTERVAL)
        # Iterate over a copy of game instances in case of modification during iteration
        active_games = list(game_instances.values()) 
        for game_state in active_games:
            if not game_state.gameOver:
                task_id = uuid4().hex
                # The worker will use game_state.direction
                task_payload_data = GameLogicTaskPayload(
                    gameId=game_state.gameId,
                    current_state=game_state.copy(deep=True), # Send a copy
                    task_id=task_id
                )
                try:
                    with rabbitmq_channel() as channel:
                        channel.queue_declare(queue=GAME_LOGIC_QUEUE, durable=True)
                        channel.basic_publish(
                            exchange='',
                            routing_key=GAME_LOGIC_QUEUE,
                            body=task_payload_data.json(),
                            properties=pika.BasicProperties(
                                delivery_mode=2, # Persistent
                                content_type='application/json',
                                correlation_id=task_id
                            )
                        )
                    # Optional: print(f"Game loop queued task {task_id} for game {game_state.gameId} with direction {game_state.direction}")
                except Exception as e:
                    print(f"[GAME LOOP ERROR] Could not queue task for game {game_state.gameId}: {e}")

@app.post("/internal/game_state_updated")
async def internal_update_game_state(payload: UpdateGameStateInternalPayload):
    game_id = payload.gameId
    new_state = payload.newState
    if game_id in game_instances:
        game_instances[game_id] = new_state
        print(f"Internal update for game {game_id} processed. Score: {new_state.score}, Game Over: {new_state.gameOver}")
        return {"status": "state_updated_for_game", "gameId": game_id}
    else:
        print(f"[WARN] Received internal update for unknown game_id: {game_id}")
        return {"status": "error", "message": "Game ID not found during internal update"}, 404

workers_info: Dict[str, dict] = {}

@app.post("/report")
async def report_worker_status(info: dict):
    name = info.get("name")
    if name:
        workers_info[name] = info
    return {"status": "ok"}

@app.get("/workers")
async def get_workers():
    return list(workers_info.values())

if __name__ == "__main__":
    # Start the game loop in a background thread
    game_loop_thread = threading.Thread(target=game_loop, daemon=True)
    game_loop_thread.start()
    print("Game loop started in background thread.")

    uvicorn.run(app, host="0.0.0.0", port=8000)