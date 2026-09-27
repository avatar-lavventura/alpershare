# alpershare

A tiny shared scratchpad in the browser. Open the same URL on two machines and type; both windows stay in sync. No accounts, no database, no build step.

It is meant for the small jobs: moving a snippet from your laptop to a remote box, keeping shared notes during a call, or pasting something long between devices without emailing yourself.

## Features

- Monaco editor (the engine behind VS Code) with a Dracula theme
- Markdown and Org-mode highlighting
- Emacs keybindings, toggled from the toolbar
- Live sync over WebSocket, with a "typing..." hint when another window is editing
- Separate rooms by URL: `/?room=standup` and `/?room=scratch` never see each other
- Undo and redo buttons, and a connection status light
- One small server, in Python or Node, your choice
- Heartbeats keep the socket open behind proxies such as ngrok and Render

## Quick start

Python (aiohttp):

```
pip install -r requirements.txt
python server.py 3000
```

Node (ws):

```
npm install
node server.js
```

Open http://localhost:3000. To share it outside your machine:

```
ngrok http 3000
```

## Rooms and access

Every distinct `?room=name` is its own document. With no room, you get `default`.

To lock the server to a single room, set `ROOM_ID`. Requests for any other room get a 404, so the room name works as a shared secret.

```
ROOM_ID=my-secret-room python server.py
```

Then share `http://host:3000/?room=my-secret-room`.

## Deploy to Render

`render.yaml` describes a Python web service. Connect the repo as a Blueprint and Render runs `pip install -r requirements.txt` then `python server.py`. Render supplies `PORT` itself.

To give an uptime monitor something to ping, set `HEALTH_TOKEN` and request `/health-<token>`. It returns `ok`.

## Configuration

Both servers read the same environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | 3000 | Port to listen on |
| `ROOM_ID` | empty | If set, only this room is served |
| `HEALTH_TOKEN` | empty | If set, enables `/health-<token>` |

## Limits

- Text lives in server memory. Restarting the server clears every room.
- The last edit wins. The whole document is sent on each change, so two people typing in the same spot at once will overwrite each other. It suits taking turns, not pair editing in real time.
- Anyone who knows a room name can read and write it. Use `ROOM_ID` and HTTPS if the content matters.
- The editor loads Monaco from the jsdelivr CDN, so the browser needs internet access.

## License

ISC
