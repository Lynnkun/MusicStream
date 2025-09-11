# server.py
import os
import time
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

app = Flask(__name__, template_folder="temp")
# use eventlet async mode for robust binary websocket handling
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

AUDIO_FILE = "input.mp3"
CHUNK_SIZE = 16 * 1024  # 16KB per piece (bigger chunks are easier to decode)
BPS_ESTIMATE = 128_000 // 8  # bytes per second (approx for 128kbps mp3)

broadcast_started = False
broadcast_finished = False
listeners = set()


def producer():
    """Read audio file and broadcast binary chunks in real-time."""
    global broadcast_finished

    if not os.path.exists(AUDIO_FILE):
        print("Audio file not found:", AUDIO_FILE)
        broadcast_finished = True
        return

    print("Producer: starting stream of", AUDIO_FILE)
    with open(AUDIO_FILE, "rb") as f:
        start_time = time.time()
        bytes_sent = 0

        chunk = f.read(CHUNK_SIZE)
        while chunk:
            # emit binary chunk to all connected clients
            socketio.emit("audio_chunk", chunk, broadcast=True, binary=True)

            bytes_sent += len(chunk)
            expected_time = bytes_sent / BPS_ESTIMATE
            elapsed = time.time() - start_time
            # throttle to approximate real-time playback
            if expected_time > elapsed:
                socketio.sleep(expected_time - elapsed)

            chunk = f.read(CHUNK_SIZE)

    broadcast_finished = True
    print("Producer: finished streaming file.")


@app.route("/")
def index():
    return render_template("template.html")


@app.route("/listeners")
def get_listeners():
    return jsonify({"count": len(listeners), "broadcast_started": broadcast_started, "broadcast_finished": broadcast_finished})


@socketio.on("connect")
def handle_connect():
    global broadcast_started
    sid = request.sid
    listeners.add(sid)
    print(f"Client {sid} connected. Listeners: {len(listeners)}")

    # start producer exactly once when first client joins
    if not broadcast_started:
        broadcast_started = True
        socketio.start_background_task(producer)


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    listeners.discard(sid)
    print(f"Client {sid} disconnected. Listeners: {len(listeners)}")


if __name__ == "__main__":
    # run with eventlet (socketio.run will select eventlet because async_mode is "eventlet")
    socketio.run(app, host="0.0.0.0", port=8000, debug=True)
