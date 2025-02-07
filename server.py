import asyncio
import json
import sounddevice as sd
import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.signaling import TcpSocketSignaling
from aiohttp import web
import aiohttp_cors
import logging

logging.basicConfig(level=logging.DEBUG)

pcs = set()

# Audio settings
SAMPLE_RATE = 48000  # WebRTC prefers 48kHz
CHANNELS = 2
BUFFER_SIZE = 1024

# Find BlackHole Device
def find_blackhole_device():
    device_info = sd.query_devices()
    return next((index for index, device in enumerate(device_info) if "BlackHole" in device['name']), None)

class AudioStreamTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.device_index = find_blackhole_device()
        self.stream = sd.InputStream(device=self.device_index, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16', blocksize=BUFFER_SIZE)
        self.stream.start()

    async def recv(self):
        data, overflow = self.stream.read(BUFFER_SIZE)
        if overflow:
            print("Audio buffer overflowed!")
        audio_frame = np.frombuffer(data, dtype=np.int16)
        return audio_frame.tobytes()

import json
import pyaudio
import numpy as np
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.mediastreams import AudioStreamTrack

pcs = set()

# 🎤 Audio Capture from BlackHole
class BlackHoleAudioStreamTrack(AudioStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=2,  # BlackHole 2ch supports stereo
            rate=44100,  # Standard sample rate
            input=True,
            frames_per_buffer=1024,
            input_device_index=self.get_blackhole_device_index()
        )

    def get_blackhole_device_index(self):
        """Finds BlackHole in available audio devices."""
        for i in range(self.pa.get_device_count()):
            dev = self.pa.get_device_info_by_index(i)
            if "BlackHole" in dev["name"]:
                print(f"✅ Using BlackHole device: {dev['name']}")
                return i
        raise RuntimeError("❌ BlackHole device not found!")

    async def recv(self):
        """Reads live audio from BlackHole and converts it to numpy array."""
        audio_data = self.stream.read(1024, exception_on_overflow=False)
        samples = np.frombuffer(audio_data, dtype=np.int16)
        return samples

    def stop(self):
        """Closes the audio stream when done."""
        self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()


async def handle_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    # 🎤 Attach BlackHole Audio Stream to WebRTC
    audio_track = BlackHoleAudioStreamTrack()
    pc.addTrack(audio_track)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    print(f"✅ Generated Answer SDP:\n{pc.localDescription.sdp}")

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


app = web.Application()

# Enable CORS
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})

# Add CORS to routes
offer_route = app.router.add_post("/offer", handle_offer)
cors.add(offer_route)

root_route = app.router.add_get("/", lambda request: web.Response(text="WebRTC Audio Server"))
cors.add(root_route)

async def cleanup():
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)

web.run_app(app, host='10.0.0.110', port=8765)
