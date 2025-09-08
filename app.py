# live_server.py
import asyncio
from typing import Set
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Simple Live Audio Broadcaster")

# Allow your frontend origin or use ["*"] for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
LISTENERS: Set[asyncio.Queue] = set()
LISTENERS_LOCK = asyncio.Lock()

# Settings
LISTENER_QUEUE_MAXSIZE = 50       # how many recent chunks we keep per-listener
CHUNK_LOG_INTERVAL = 100          # log every N chunks
MEDIA_TYPE = "audio/mpeg"         # change if you use ogg/aac/etc.


async def broadcast_chunk(chunk: bytes):
    """Push chunk to all connected listeners (non-blocking-ish)."""
    if not chunk:
        return
    async with LISTENERS_LOCK:
        to_remove = []
        for q in list(LISTENERS):
            try:
                q.put_nowait(chunk)
            except asyncio.QueueFull:
                # Drop oldest to make room
                try:
                    _ = q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(chunk)
                except Exception:
                    to_remove.append(q)
        # Cleanup dead listeners
        for q in to_remove:
            if q in LISTENERS:
                LISTENERS.remove(q)


@app.get("/")
async def homepage():
    """Serve a simple HTML player to test streaming."""
    return FileResponse("index.html")


@app.post("/source")
async def source(request: Request):
    """
    POST raw audio bytes (e.g. mp3).
    Example:
      ffmpeg -re -i input.mp3 -f mp3 - | \
      curl -N -X POST --data-binary @- http://localhost:8000/source
    """
    chunk_count = 0
    try:
        async for chunk in request.stream():
            if not chunk:
                continue
            await broadcast_chunk(chunk)
            chunk_count += 1
            if chunk_count % CHUNK_LOG_INTERVAL == 0:
                print(f"[source] broadcasted {chunk_count} chunks")
    except Exception as exc:
        print("Source connection closed / error:", exc)
    finally:
        print("[source] ended streaming")
    return {"status": "source disconnected", "chunks": chunk_count}


@app.get("/live")
async def live():
    """
    Listener connects here to receive the live stream.
    Use <audio> in a browser or VLC.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=LISTENER_QUEUE_MAXSIZE)

    # Register listener
    async with LISTENERS_LOCK:
        LISTENERS.add(q)
    print(f"[listener] connected (total={len(LISTENERS)})")

    async def generator():
        try:
            while True:
                chunk = await q.get()
                if chunk is None:
                    break
                yield chunk
        except asyncio.CancelledError:
            pass
        finally:
            # Remove listener on disconnect
            async with LISTENERS_LOCK:
                if q in LISTENERS:
                    LISTENERS.remove(q)
            print(f"[listener] disconnected (total={len(LISTENERS)})")

    return StreamingResponse(generator(), media_type=MEDIA_TYPE)
