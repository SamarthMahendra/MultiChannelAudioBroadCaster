import asyncio
import websockets
import threading
import pyaudio
import time
import os

# Global set to track connected clients
connected_clients = set()
audio_queue = asyncio.Queue()  # Shared queue for audio streaming


def clear_terminal():
    """Clear the terminal screen for a clean startup display."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    """Prints a stylish ASCII art banner with server info."""
    clear_terminal()
    banner = r"""
    
 $$$$$$\                  $$\ $$\                  $$$$$$\                                                                                  
$$  __$$\                 $$ |\__|                $$  __$$\                                                                                 
$$ /  $$ |$$\   $$\  $$$$$$$ |$$\  $$$$$$\        $$ /  \__| $$$$$$$\  $$$$$$\   $$$$$$\   $$$$$$\  $$$$$$\$$$$\   $$$$$$\   $$$$$$\        
$$$$$$$$ |$$ |  $$ |$$  __$$ |$$ |$$  __$$\       \$$$$$$\  $$  _____|$$  __$$\ $$  __$$\  \____$$\ $$  _$$  _$$\ $$  __$$\ $$  __$$\       
$$  __$$ |$$ |  $$ |$$ /  $$ |$$ |$$ /  $$ |       \____$$\ $$ /      $$ |  \__|$$$$$$$$ | $$$$$$$ |$$ / $$ / $$ |$$$$$$$$ |$$ |  \__|      
$$ |  $$ |$$ |  $$ |$$ |  $$ |$$ |$$ |  $$ |      $$\   $$ |$$ |      $$ |      $$   ____|$$  __$$ |$$ | $$ | $$ |$$   ____|$$ |            
$$ |  $$ |\$$$$$$  |\$$$$$$$ |$$ |\$$$$$$  |      \$$$$$$  |\$$$$$$$\ $$ |      \$$$$$$$\ \$$$$$$$ |$$ | $$ | $$ |\$$$$$$$\ $$ |            
\__|  \__| \______/  \_______|\__| \______/        \______/  \_______|\__|       \_______| \_______|\__| \__| \__| \_______|\__|            
                                                                                                                                            
                                                                                                                                            
                                                                                                                                            
 
    """
    print(banner)
    print("=" * 70)
    print("  🚀 Audio Scream Server | Real-Time Audio Streaming Over WebSockets")
    print("  🎧 Capturing audio from BlackHole and broadcasting to connected clients")
    print("  🌐 WebSocket Server: ws://0.0.0.0:8765")
    print("  🛠  Tech Stack: Python | asyncio | websockets | pyaudio | threading")
    print("=" * 70)
    print("\n[Starting] Initializing audio pipeline & network stack...\n")


async def ws_handler(websocket):
    """Handle WebSocket connections."""
    print(f"[WS] Client connected: {websocket.remote_address}")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    except Exception as e:
        print(f"[WS] Error with client {websocket.remote_address}: {e}")
    finally:
        connected_clients.remove(websocket)
        print(f"[WS] Client disconnected: {websocket.remote_address}")


async def audio_sender():
    """Fetch audio from queue and send it in batches to connected clients."""
    while True:
        data = await audio_queue.get()
        if connected_clients:
            await asyncio.gather(*(ws.send(data) for ws in connected_clients), return_exceptions=True)


def find_blackhole_index():
    """Find the index of BlackHole device for audio capture."""
    p = pyaudio.PyAudio()
    blackhole_index = None
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"[Device] {i}: {info['name']}, Max Input: {info['maxInputChannels']}")
        if "BlackHole" in info["name"]:
            blackhole_index = i
            break
    p.terminate()
    return blackhole_index


def audio_capture(chunk=1024, channels=2, rate=44100):
    """Capture audio and send it to the queue."""
    p = pyaudio.PyAudio()
    device_index = find_blackhole_index()

    if device_index is None:
        print("[Audio] BlackHole not found. Using default device.")

    try:
        stream = p.open(format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        input=True,
                        frames_per_buffer=chunk,
                        input_device_index=device_index)
    except Exception as e:
        print(f"[Audio] Error opening stream: {e}")
        p.terminate()
        return

    print("[Audio] 🎤 Capturing started...")

    try:
        while True:
            data = stream.read(chunk, exception_on_overflow=False)
            asyncio.run_coroutine_threadsafe(audio_queue.put(data), loop)
    except Exception as e:
        print(f"[Audio] Capture error: {e}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


async def main():
    """Start WebSocket server and audio sender."""
    asyncio.create_task(audio_sender())  # Start audio sender in background
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        print("\n[Server] 🔥 WebSocket server is live! Listening for connections...")
        await asyncio.Future()  # Run forever.


if __name__ == '__main__':
    print_banner()

    loop = asyncio.get_event_loop()
    print("[Main] 🚀 Launching audio processing thread...\n")

    t = threading.Thread(target=audio_capture, daemon=True)
    t.start()

    print("[Main] 🔌 Bootstrapping WebSocket server...\n")
    loop.run_until_complete(main())