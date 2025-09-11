import os
import time
import threading
from flask import Flask, Response, render_template, abort, jsonify


app = Flask(__name__, template_folder="temp")

AUDIO_FILE = "input.mp3"
CHUNK_SIZE = 1024

broadcast_started = False
broadcast_finished = False
listeners = set()
lock = threading.Lock()

# shared state for broadcasting
latest_chunk = None
latest_seq = 0
chunk_event = threading.Event()


def producer():
    """Reads the audio file once and pushes chunks live in real-time."""
    global broadcast_finished, latest_chunk, latest_seq

    if not os.path.exists(AUDIO_FILE):
        broadcast_finished = True
        return

    # crude pacing assumption (~128 kbps MP3)
    bytes_per_sec = 128_000 // 8

    with open(AUDIO_FILE, "rb") as f:
        start_time = time.time()
        bytes_sent = 0

        chunk = f.read(CHUNK_SIZE)
        while chunk:
            with lock:
                latest_chunk = chunk
                latest_seq += 1
                chunk_event.set()
                chunk_event.clear()

            bytes_sent += len(chunk)

            # throttle playback speed to feel like real-time
            expected_time = bytes_sent / bytes_per_sec
            elapsed = time.time() - start_time
            if expected_time > elapsed:
                time.sleep(expected_time - elapsed)

            chunk = f.read(CHUNK_SIZE)

    # mark as finished
    broadcast_finished = True
    with lock:
        latest_chunk = None
        chunk_event.set()  # release all waiting clients


def client_generator():
    """Yields chunks in sync with the current parent timeline."""
    global broadcast_finished, latest_seq

    last_seq = latest_seq  # skip past chunks → join "live"

    while True:
        if broadcast_finished:
            break

        chunk_event.wait()

        with lock:
            if latest_chunk is None:  # EOF
                break
            if latest_seq == last_seq:
                # no new data yet
                continue
            last_seq = latest_seq
            chunk = latest_chunk

        yield chunk


@app.route("/")
def index():
    return render_template("template.html")


@app.route("/live")
def live():
    global broadcast_started, broadcast_finished

    if broadcast_finished:
        abort(404)

    with lock:
        listeners.add(threading.get_ident())
        if not broadcast_started:
            broadcast_started = True
            threading.Thread(target=producer, daemon=True).start()

    def stream():
        try:
            yield from client_generator()
        finally:
            with lock:
                listeners.discard(threading.get_ident())

    return Response(stream(), mimetype="audio/mpeg")


@app.route("/listeners")
def get_listeners():
    with lock:
        return jsonify({"count": len(listeners)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
