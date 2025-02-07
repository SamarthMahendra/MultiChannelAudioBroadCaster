import asyncio
import websockets
import sounddevice as sd
import numpy as np
import ffmpeg
import signal
import sys
from datetime import datetime

# ASCII Art Logo
LOGO = """
╔══════════════════════════════════════════════════════════╗
║     WebSocket Audio Broadcasting Server                 ║
║     Streaming Opus (in WebM) for Web Clients            ║
╚══════════════════════════════════════════════════════════╝
"""

# Audio settings
SAMPLE_RATE = 48000  # WebRTC default (Opus works well at this rate)
CHANNELS = 2
BUFFER_SIZE = 1024  # Adjust for latency vs. quality

clients = set()
shutdown_event = asyncio.Event()
server = None

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log_message(message, message_type="INFO"):
    print(f"[{get_timestamp()}] [{message_type}] {message}")

def find_blackhole_device():
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if "BlackHole" in device['name']:
            return i
    raise RuntimeError("BlackHole virtual audio device not found")

async def audio_broadcaster():
    """
    Captures raw PCM audio via sounddevice, pipes it into FFmpeg,
    which outputs WebM with Opus audio. Sends the resulting segments
    over the WebSocket.
    """
    log_message("Starting audio broadcast loop...")
    device_index = find_blackhole_device()

    # 1) Read 16-bit PCM from stdin (pipe:0)
    # 2) Encode to Opus and wrap in WebM (-f webm)
    # 3) Write to stdout (pipe:1)
    process = (
        ffmpeg
        .input('pipe:0', format='s16le', ac=CHANNELS, ar=SAMPLE_RATE)
        .output(
            'pipe:1',
            **{
                'c:a': 'libopus',
                'b:a': '128k',
                'f': 'webm',
                # The following help produce real-time friendly chunks:
                'cluster_size_limit': '1M',
                'cluster_time_limit': '1000'
                # You can tweak these further as needed.
            }
        )
        .run_async(
            pipe_stdin=True,
            pipe_stdout=True,
            pipe_stderr=True,
            # Optionally set buffering to 0 for less delay:
            # bufsize=0
        )
    )

    with sd.InputStream(
        device=device_index,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype='int16',
        blocksize=BUFFER_SIZE
    ) as stream:
        while not shutdown_event.is_set():
            data, overflowed = stream.read(BUFFER_SIZE)
            if overflowed:
                log_message("Audio buffer overflowed", "WARNING")

            # Write raw PCM to FFmpeg stdin
            process.stdin.write(data.tobytes())

            # Read encoded WebM/Opus data from FFmpeg stdout in small chunks.
            # read1(...) ensures we get whatever is immediately available.
            encoded_audio = process.stdout.read1(4096)

            # Forward to all connected clients (if any)
            if encoded_audio:
                if clients:
                    await asyncio.gather(
                        *[client.send(encoded_audio) for client in clients],
                        return_exceptions=True
                    )

            # Yield control back to the event loop
            await asyncio.sleep(0)

async def handle_connection(websocket):
    remote_addr = websocket.remote_address
    clients.add(websocket)
    log_message(f"Client connected from {remote_addr}")

    try:
        await websocket.wait_closed()
    finally:
        clients.remove(websocket)
        log_message(f"Client disconnected from {remote_addr}")

async def shutdown(signal_num, frame):
    log_message("Shutdown signal received. Cleaning up...", "SHUTDOWN")
    shutdown_event.set()

    # Close any open client connections
    if clients:
        log_message(f"Closing {len(clients)} client connections...", "SHUTDOWN")
        await asyncio.gather(*[client.close() for client in clients])

    if server:
        server.close()
        await server.wait_closed()

    loop = asyncio.get_event_loop()
    loop.stop()

async def main():
    global server

    # Clear screen and print logo in green
    print("\033[H\033[J", end="")
    print("\033[92m" + LOGO + "\033[0m")

    # Register signal handlers for graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, None))
        )

    log_message("Starting server...")
    log_message("Press Ctrl+C to stop the server")

    # Start the WebSocket server
    server = await websockets.serve(handle_connection, "0.0.0.0", 6677, origins=["*"])


    # Create audio broadcaster task
    broadcaster_task = asyncio.create_task(audio_broadcaster())

    try:
        # Wait until we get a shutdown event
        await shutdown_event.wait()
    finally:
        # Wait for broadcaster to complete
        await broadcaster_task
        log_message("Server shutdown complete", "SHUTDOWN")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_message("Server stopped by user", "SHUTDOWN")
    except Exception as e:
        log_message(f"Unexpected error: {e}", "ERROR")
        sys.exit(1)
