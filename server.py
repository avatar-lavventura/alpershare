#!/usr/bin/env python3
"""
codeshare sync server — serves the HTML and syncs code via WebSocket.
Usage: python3 server.py [port]
Then: ngrok http <port>
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from aiohttp import web, WSMsgType

PORT = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 3000))
ROOM_ID = os.environ.get("ROOM_ID", "")
HTML = (Path(__file__).parent / "index.html").read_bytes()

rooms: dict[str, dict] = {}


def get_room(room_id: str) -> dict:
    if room_id not in rooms:
        rooms[room_id] = {"content": "", "lang": "markdown", "clients": set()}
    return rooms[room_id]


async def handler(request):
    if request.headers.get("Upgrade", "").lower() != "websocket":
        if ROOM_ID and request.rel_url.query.get("room") != ROOM_ID:
            raise web.HTTPNotFound()
        return web.Response(body=HTML, content_type="text/html")
    return await ws_handler(request)


async def ws_handler(request):
    room_id = request.rel_url.query.get("room", "default")
    r = get_room(room_id)

    ws = web.WebSocketResponse()
    await ws.prepare(request)
    r["clients"].add(ws)

    await ws.send_json({"type": "init", "content": r["content"], "lang": r["lang"]})

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            try:
                data = json.loads(msg.data)
            except Exception:
                continue
            if data.get("type") == "update":
                r["content"] = data.get("content", "")
                out = json.dumps({"type": "update", "content": r["content"]})
            elif data.get("type") == "lang":
                r["lang"] = data.get("lang", "javascript")
                out = json.dumps({"type": "lang", "lang": r["lang"]})
            else:
                continue
            for c in list(r["clients"]):
                if c is not ws and not c.closed:
                    await c.send_str(out)
        elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
            break

    r["clients"].discard(ws)
    return ws


async def html_handler(request):
    return web.Response(body=HTML, content_type="text/html")


app = web.Application()
app.router.add_get("/", handler)
app.router.add_get("/index.html", html_handler)

if __name__ == "__main__":
    print(f"codeshare running  ->  http://localhost:{PORT}")
    print(f"share via ngrok    ->  ngrok http {PORT}")
    web.run_app(app, port=PORT, print=None)
