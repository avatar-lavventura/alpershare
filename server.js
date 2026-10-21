const http = require('http');
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { WebSocketServer } = require('ws');

const PORT = parseInt(process.env.PORT || '3000', 10);
const ROOM_ID = process.env.ROOM_ID || '';
const HEALTH_TOKEN = process.env.HEALTH_TOKEN || '';
const HTML = fs.readFileSync(path.join(__dirname, 'index.html'));
const HTML_GZ = zlib.gzipSync(HTML);

const rooms = new Map();

function getRoom(roomId) {
  let r = rooms.get(roomId);
  if (!r) {
    r = { content: '', lang: 'markdown', images: [], clients: new Set() };
    rooms.set(roomId, r);
  }
  return r;
}

// data:image/png;base64,... -> { mime, body }, or null if malformed
function decodeImg(data) {
  const m = typeof data === 'string' && /^data:(image\/[\w.+-]+);base64,/.exec(data);
  return m ? { mime: m[1], body: Buffer.from(data.slice(m[0].length), 'base64') } : null;
}

function broadcast(room, sender, msg) {
  const data = JSON.stringify(msg);
  for (const c of room.clients) {
    if (c !== sender && c.readyState === 1) c.send(data);
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const pathname = url.pathname;
  if (HEALTH_TOKEN && pathname === `/health-${HEALTH_TOKEN}`) {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('ok');
    return;
  }
  if (pathname.startsWith('/img/')) {
    const roomId = url.searchParams.get('room') || 'default';
    let id;
    try { id = decodeURIComponent(pathname.slice(5)); } catch { id = null; }
    const img = (!ROOM_ID || roomId === ROOM_ID) && rooms.get(roomId)?.images.find(m => m.id === id);
    if (!img) {
      res.writeHead(404);
      res.end();
      return;
    }
    // ids are never reused, so the browser may cache forever; CSP sandbox stops an uploaded SVG running script
    res.writeHead(200, {
      'Content-Type': img.mime,
      'Cache-Control': 'private, max-age=31536000, immutable',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; sandbox",
      'X-Content-Type-Options': 'nosniff',
    });
    res.end(img.body);
    return;
  }
  const room = url.searchParams.get('room');
  if (ROOM_ID && room !== ROOM_ID) {
    res.writeHead(404);
    res.end();
    return;
  }
  if (/\bgzip\b/.test(req.headers['accept-encoding'] || '')) {
    res.writeHead(200, { 'Content-Type': 'text/html', 'Content-Encoding': 'gzip', 'Vary': 'Accept-Encoding' });
    res.end(HTML_GZ);
    return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html', 'Vary': 'Accept-Encoding' });
  res.end(HTML);
});

const wss = new WebSocketServer({ server, maxPayload: 8 * 1024 * 1024 }); // fits a 5 MB image as base64, same as server.py

wss.on('connection', (ws, req) => {
  const roomId = new URL(req.url, `http://${req.headers.host}`).searchParams.get('room') || 'default';
  if (ROOM_ID && roomId !== ROOM_ID) {
    ws.close(1008, 'forbidden');
    return;
  }
  const room = getRoom(roomId);
  room.clients.add(ws);
  // images go by id only; the browser fetches each from /img/<id> and can cache it
  ws.send(JSON.stringify({ type: 'init', content: room.content, lang: room.lang, images: room.images.map(m => ({ id: m.id })) }));

  ws.on('message', (data) => {
    let msg, img;
    try { msg = JSON.parse(data); } catch { return; }
    if (msg.type === 'ping') {
      ws.send('{"type":"pong"}');
    } else if (msg.type === 'update') {
      room.content = msg.content;
      broadcast(room, ws, { type: 'update', content: msg.content });
    } else if (msg.type === 'lang') {
      room.lang = msg.lang;
      broadcast(room, ws, { type: 'lang', lang: msg.lang });
    } else if (msg.type === 'img' && (img = decodeImg(msg.data))) {
      room.images = [...room.images, { id: msg.id, ...img }].slice(-20);
      broadcast(room, ws, { type: 'img', id: msg.id });
    } else if (msg.type === 'imgdel') {
      room.images = room.images.filter(m => m.id !== msg.id);
      broadcast(room, ws, { type: 'imgdel', id: msg.id });
    }
  });

  ws.on('close', () => room.clients.delete(ws));
});

// keep proxies from idling out sockets; terminate ones that stop answering
setInterval(() => {
  for (const c of wss.clients) {
    if (c.isAlive === false) { c.terminate(); continue; }
    c.isAlive = false;
    c.ping();
  }
}, 20000);
wss.on('connection', (ws) => { ws.isAlive = true; ws.on('pong', () => { ws.isAlive = true; }); });

server.listen(PORT, () => console.log(`http://localhost:${PORT}`));
