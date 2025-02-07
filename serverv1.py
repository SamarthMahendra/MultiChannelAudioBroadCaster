import asyncio
import websockets
import sounddevice as sd
import numpy as np
import signal
import sys
from datetime import datetime

# ASCII Art Logo
LOGO = """
╔══════════════════════════════════════════════════════════╗
║     ╔═╗┬ ┬┌┬┐┬┌─┐  ╔═╗┌┬┐┬─┐┌─┐┌─┐┌┬┐┌─┐┬─┐              ║
║     ╠═╣│ │ │││║ ║  ╚═╗│││├┬┘├┤ ├─┤│││├┤ ├┬┘              ║
║     ╩ ╩└─┘─┴┘┴└─┘  ╚═╝┴ ┴┴└─└─┘┴ ┴┴ ┴└─┘┴└─              ║
║                                                          ║
║    WebSocket Audio Broadcasting Server                   ║
║    Listening on ws://0.0.0.0:8765 author@samarthmahendra ║
╚══════════════════════════════════════════════════════════╝
"""

# Audio settings
SAMPLE_RATE = 44100  # CD quality
CHANNELS = 2  # Stereo (BlackHole supports stereo)
BUFFER_SIZE = 1024  # Adjust for latency vs quality

# Global variables
clients = set()
shutdown_event = asyncio.Event()
server = None


def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")


def log_message(message, message_type="INFO"):
    print(f"[{get_timestamp()}] [{message_type}] {message}")


def find_blackhole_device():
    device_info = sd.query_devices()
    device_index = next(
        (index for index, device in enumerate(device_info) if "BlackHole" in device['name']),
        None
    )
    if device_index is None:
        raise RuntimeError("BlackHole virtual audio device not found")
    return device_index


async def audio_broadcaster():
    log_message("Starting audio broadcast loop...")
    try:
        device_index = find_blackhole_device()
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

                audio_bytes = data.tobytes()
                if clients:
                    await asyncio.gather(
                        *[client.send(audio_bytes) for client in clients],
                        return_exceptions=True
                    )
                await asyncio.sleep(0)
    except Exception as e:
        log_message(f"Error in audio broadcaster: {e}", "ERROR")


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
    """Handle graceful shutdown of the server"""
    log_message("Shutdown signal received. Cleaning up...", "SHUTDOWN")
    shutdown_event.set()

    # Close all client connections
    if clients:
        log_message(f"Closing {len(clients)} client connections...", "SHUTDOWN")
        await asyncio.gather(*[client.close() for client in clients])

    # Stop the server
    if server:
        server.close()
        await server.wait_closed()

    # Stop the event loop
    loop = asyncio.get_event_loop()
    loop.stop()


async def main():
    global server

    # Clear screen and display logo
    print("\033[H\033[J", end="")  # Clear screen
    print("\033[92m" + LOGO + "\033[0m")  # Print logo in green

    # Setup signal handlers for graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, None))
        )

    log_message("Starting server...")
    log_message("Press Ctrl+C to stop the server")

    # Start the WebSocket server
    server = await websockets.serve(handle_connection, "0.0.0.0", 8765)

    # Start the audio broadcaster
    broadcaster_task = asyncio.create_task(audio_broadcaster())

    try:
        await shutdown_event.wait()
    finally:
        await broadcaster_task
        log_message("Server shutdown complete", "SHUTDOWN")


if __name__ == "__main__":
    print("\nInstall BlackHole and set it as your output device:")
    print("brew install blackhole-2ch\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_message("Server stopped by user", "SHUTDOWN")
    except Exception as e:
        log_message(f"Unexpected error: {e}", "ERROR")
        sys.exit(1)