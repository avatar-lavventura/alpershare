#!/usr/bin/env python3
"""
codeshare sync server — serves the HTML and syncs code via WebSocket.
Usage: python3 server.py [port]
Then: ngrok http <port>
"""

import asyncio
import base64
import binascii
import json
import os
import re
import sys
from pathlib import Path

from aiohttp import WSMsgType, web

PORT = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 3000))
ROOM_ID = os.environ.get("ROOM_ID", "")
HEALTH_TOKEN = os.environ.get("HEALTH_TOKEN", "")
HTML = (Path(__file__).parent / "index.html").read_bytes()

rooms: dict[str, dict] = {}


def get_room(room_id: str) -> dict:
    if room_id not in rooms:
        rooms[room_id] = {"content": "", "lang": "markdown", "images": [], "clients": set()}
    return rooms[room_id]


def decode_img(data: str):
    """data:image/png;base64,... -> (mime, bytes), or None if malformed"""
    head, _, b64 = data.partition(",")
    m = re.fullmatch(r"data:(image/[\w.+-]+);base64", head)
    if not m:
        return None
    try:
        return m[1], base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        return None


def page():
    r = web.Response(body=HTML, content_type="text/html")
    r.enable_compression()
    return r


async def handler(request):
    if request.headers.get("Upgrade", "").lower() != "websocket":
        if ROOM_ID and request.rel_url.query.get("room") != ROOM_ID:
            raise web.HTTPNotFound()
        return page()
    return await ws_handler(request)


async def ws_handler(request):
    room_id = request.rel_url.query.get("room", "default")
    if ROOM_ID and room_id != ROOM_ID:
        raise web.HTTPNotFound()
    r = get_room(room_id)

    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=8 * 1024 * 1024)  # 8 MB fits a 5 MB image as base64; heartbeat keeps proxies from idling out, drops dead sockets
    await ws.prepare(request)
    r["clients"].add(ws)

    # images go by id only; the browser fetches each from /img/<id> and can cache it
    images = [{"id": m["id"]} for m in r["images"]]
    await ws.send_json({"type": "init", "content": r["content"], "lang": r["lang"], "images": images})

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
            except Exception:
                continue
            if data.get("type") == "ping":
                await ws.send_str('{"type":"pong"}')
                continue
            if data.get("type") == "update":
                r["content"] = data.get("content", "")
                out = json.dumps({"type": "update", "content": r["content"]})
            elif data.get("type") == "lang":
                r["lang"] = data.get("lang", "javascript")
                out = json.dumps({"type": "lang", "lang": r["lang"]})
            elif data.get("type") == "img" and (img := decode_img(str(data.get("data", "")))):
                r["images"] = (r["images"] + [{"id": data.get("id"), "mime": img[0], "body": img[1]}])[-20:]
                out = json.dumps({"type": "img", "id": data.get("id")})
            elif data.get("type") == "imgdel":
                r["images"] = [m for m in r["images"] if m["id"] != data.get("id")]
                out = json.dumps({"type": "imgdel", "id": data.get("id")})
            else:
                continue
            # send to all peers at once so one slow peer does not hold up the rest
            await asyncio.gather(
                *(c.send_str(out) for c in list(r["clients"]) if c is not ws and not c.closed),
                return_exceptions=True,
            )
        elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
            break

    r["clients"].discard(ws)
    return ws


async def img_handler(request):
    room_id = request.rel_url.query.get("room", "default")
    if ROOM_ID and room_id != ROOM_ID:
        raise web.HTTPNotFound()
    img_id = request.match_info["id"]
    for m in rooms.get(room_id, {}).get("images", []):
        if m["id"] == img_id:
            # ids are never reused, so the browser may cache forever; CSP sandbox stops an uploaded SVG running script
            return web.Response(body=m["body"], content_type=m["mime"], headers={
                "Cache-Control": "private, max-age=31536000, immutable",
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                "X-Content-Type-Options": "nosniff",
            })
    raise web.HTTPNotFound()


async def html_handler(request):
    return page()


async def health_handler(request):
    return web.Response(text="ok")


app = web.Application()
app.router.add_get("/", handler)
app.router.add_get("/index.html", html_handler)
app.router.add_get("/img/{id}", img_handler)
if HEALTH_TOKEN:
    app.router.add_get(f"/health-{HEALTH_TOKEN}", health_handler)

if __name__ == "__main__":
    print(f"codeshare running  ->  http://localhost:{PORT}")
    print(f"share via ngrok    ->  ngrok http {PORT}")
    web.run_app(app, port=PORT, print=None)
