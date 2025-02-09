import asyncio
import json
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer

pcs = set()  # Store active peer connections

def get_audio_player():
    """Get system audio from BlackHole (MacOS)."""
    return MediaPlayer(":1", format="avfoundation")  # MacOS-specific audio capture

async def offer(request):
    """Handle WebRTC offer from clients and return an answer."""
    params = await request.json()
    pc = RTCPeerConnection()
    pcs.add(pc)

    # Add audio track
    audio_player = get_audio_player()
    pc.addTrack(audio_player.audio)

    # Handle ICE connection states
    @pc.on("iceconnectionstatechange")
    async def on_ice_state_change():
        if pc.iceConnectionState in ["failed", "closed", "disconnected"]:
            await pc.close()
            pcs.discard(pc)

    # Process offer and create answer
    await pc.setRemoteDescription(RTCSessionDescription(sdp=params["sdp"], type=params["type"]))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Return JSON response with SDP answer
    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    }, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    })

async def handle_options(request):
    """Handle CORS preflight requests."""
    return web.Response(headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    })

async def cleanup():
    """Periodically close unused peer connections."""
    while True:
        await asyncio.sleep(10)
        for pc in list(pcs):
            if pc.iceConnectionState in ["closed", "failed", "disconnected"]:
                await pc.close()
                pcs.discard(pc)

app = web.Application()
app.router.add_post("/offer", offer)
app.router.add_options("/offer", handle_options)

# Run server
web.run_app(app, host="0.0.0.0", port=8765)
