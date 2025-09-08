from flask import Flask, Response, render_template_string
import os
import time

app = Flask(__name__)

AUDIO_FILE = "input.mp3"
CHUNK_SIZE = 1024

def audio_stream():
    """
    Infinite generator that yields audio chunks from file as if it were live.
    Loops the file endlessly. No rewind.
    """
    while True:
        if not os.path.exists(AUDIO_FILE):
            time.sleep(1)
            continue

        with open(AUDIO_FILE, "rb") as f:
            chunk = f.read(CHUNK_SIZE)
            while chunk:
                yield chunk
                chunk = f.read(CHUNK_SIZE)
                time.sleep(0.02)  # throttle so it's "live-ish"
        # restart when file ends (loop)
        time.sleep(0.1)

@app.route("/")
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Live Audio Stream</title>
    </head>
    <body>
        <h1>Live Radio</h1>
        <audio id="player" autoplay>
            <source src="/live" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
        <script>
            const player = document.getElementById("player");
            // Disable pause/seek
            player.addEventListener("pause", () => player.play());
            player.addEventListener("seeking", () => player.currentTime = player.duration);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/live")
def live():
    return Response(audio_stream(), mimetype="audio/mpeg")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
