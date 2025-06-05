import random
import psutil, time, requests, socket
from fastapi import FastAPI
from contextlib import asynccontextmanager
import uvicorn
import threading
from uuid import uuid4
import pika
import json
import os

# Configuration
COORDINATOR_IP = "100.120.4.105"
NODE_NAME = "snake-worker"
RABBIT_HOST = COORDINATOR_IP
RABBIT_PORT = 5672
RABBIT_USER = "myuser"
RABBIT_PASS = "mypassword"
GAME_LOGIC_QUEUE = "game_logic_tasks"
BOARD_SIZE = 20

last_net_bytes = [0]
last_time = [time.time()]
first_call = [True]

# Function to get resource usage,
def get_resource_usage():
    usage = psutil.cpu_times_percent(interval=None)
    net = psutil.net_io_counters(pernic=True)
    total_bytes = 0
    for iface, counters in net.items():
        total_bytes += counters.bytes_sent + counters.bytes_recv
    current_time = time.time()
    elapsed = current_time - last_time[0]
    if first_call[0]:
        net_mbs = 0.0
        first_call[0] = False
    elif elapsed > 0:
        net_mbs = (total_bytes - last_net_bytes[0]) / 1024 / 1024 / elapsed
    else:
        net_mbs = 0.0
    last_net_bytes[0] = total_bytes
    last_time[0] = current_time
    return {
        "name": NODE_NAME,
        "cpu": round(usage.user + usage.system, 2),
        "ram": psutil.virtual_memory().percent,
        "net": round(net_mbs, 2),
        "ip": socket.gethostbyname(socket.gethostname())
    }

# Background thread to report resource usage to the coordinator
def background_report():
    while True:
        try:
            usage = get_resource_usage()
            requests.post(f"http://{COORDINATOR_IP}:8000/report", json=usage, timeout=5)
        except Exception as e:
            print(f"[DEBUG] background_report error: {e}")
        time.sleep(1)

# Function to register the worker with the coordinator
def try_register():
    try:
        data = get_resource_usage()
        requests.post(f"http://{COORDINATOR_IP}:8000/register", json=data, timeout=5)
        print("[✔️] Successfully registered to coordinator")
    except Exception as e:
        print(f"[⚠️] Registration failed: {e}")

# Function to execute tasks from RabbitMQ
def execute_task(ch, method, properties, body):
    try:
        requests.post(f"http://{COORDINATOR_IP}:8000/working", json={
            "name": NODE_NAME,
            "status": "executing task",
            "task_id": str(uuid4())
        }, timeout=5)

        task = json.loads(body)
        if task.get("task_type") != "update_game_state":
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        state = task["current_state"]
        game_id = task["gameId"]
        direction = state["direction"]
        snake = state["snake"]
        food = state["food"]
        score = state["score"]

        new_head = {"x": snake[0]["x"], "y": snake[0]["y"]}
        if direction == "UP": new_head["y"] -= 1
        elif direction == "DOWN": new_head["y"] += 1
        elif direction == "LEFT": new_head["x"] -= 1
        elif direction == "RIGHT": new_head["x"] += 1

        # Check for wall collision
        hit_wall = (
            new_head["x"] < 0 or new_head["x"] >= BOARD_SIZE or
            new_head["y"] < 0 or new_head["y"] >= BOARD_SIZE
        )

        if hit_wall:
            lost = True
            updated_state = {
                "gameId": game_id,
                "snake": snake,  # Keep the snake as is
                "food": food,
                "score": score,
                "gameOver": True,
                "direction": direction,
                "boardSize": BOARD_SIZE
            }
        else:
            new_snake = [new_head] + snake
            ate_food = new_head == food
            if not ate_food:
                new_snake.pop()
            else:
                score += 1
                while True:
                    new_food = {
                        "x": random.randint(0, BOARD_SIZE - 1),
                        "y": random.randint(0, BOARD_SIZE - 1)
                    }
                    if new_food not in new_snake:
                        food = new_food
                        break
            lost = new_snake[0] in new_snake[1:]
            updated_state = {
                "gameId": game_id,
                "snake": new_snake,
                "food": food,
                "score": score,
                "gameOver": lost,
                "direction": direction,
                "boardSize": BOARD_SIZE
            }

        requests.post(
            f"http://{COORDINATOR_IP}:8000/internal/game_state_updated",
            json={"gameId": game_id, "newState": updated_state},
            timeout=5
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)

        requests.post(f"http://{COORDINATOR_IP}:8000/working", json={
            "name": NODE_NAME,
            "status": "free",
            "task_id": None
        }, timeout=5)

    except Exception as e:
        print(f"[❌] Error executing task: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

# RabbitMQ callback function
def callback(ch, method, properties, body):
    execute_task(ch, method, properties, body)

# Function to get optimal parameters based on worker load
def get_optimal_params():
    try:
        workers_info = requests.get(f"http://{COORDINATOR_IP}:8000/workers", timeout=5).json()
        queue_info = requests.get(f"http://{COORDINATOR_IP}:8000/queue_size", timeout=5).json()
        num_workers = len(workers_info)
        pending_tasks = queue_info.get("pending_tasks", 0)
        cpu_count = os.cpu_count() or 2
        if pending_tasks > 100:
            threads = min(cpu_count * 2, 32)
            prefetch = 4
        elif pending_tasks > 0:
            threads = cpu_count
            prefetch = 2
        else:
            threads = max(1, cpu_count // 2)
            prefetch = 1
        return threads, prefetch
    except Exception as e:
        print(f"[⚠️] Could not optimize params: {e}")
        return os.cpu_count() or 2, 1

# Function to start RabbitMQ consumer
def start_rabbitmq_consumer(prefetch_count=1):
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        virtual_host='/',
        credentials=creds,
        heartbeat=60,
        blocked_connection_timeout=30
    )
    try:
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.queue_declare(queue=GAME_LOGIC_QUEUE, durable=True)
        channel.basic_qos(prefetch_count=prefetch_count)
        channel.basic_consume(queue=GAME_LOGIC_QUEUE, on_message_callback=callback, auto_ack=False)
        channel.start_consuming()
    except Exception as e:
        print(f"[❌] RabbitMQ error: {e}")

# Main function to create FastAPI app and start background tasks
def create_app():
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        threading.Thread(target=background_report, daemon=True).start()
        num_threads, prefetch = get_optimal_params()
        print(f"[Worker] Starting {num_threads} RabbitMQ consumers (prefetch={prefetch})")
        for _ in range(num_threads):
            threading.Thread(target=start_rabbitmq_consumer, args=(prefetch,), daemon=True).start()
        threading.Thread(target=try_register, daemon=True).start()
        yield

    app = FastAPI(lifespan=lifespan)
    return app

app = create_app()

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8004)
