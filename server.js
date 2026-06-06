const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const state = { content: '', lang: 'markdown' };
const clients = new Set();

function broadcast(sender, msg) {
  const data = JSON.stringify(msg);
  for (const c of clients) {
    if (c !== sender && c.readyState === 1) c.send(data);
  }
}

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/html' });
  res.end(fs.readFileSync(path.join(__dirname, 'index.html')));
});

const wss = new WebSocketServer({ server });

wss.on('connection', (ws) => {
  clients.add(ws);
  ws.send(JSON.stringify({ type: 'init', content: state.content, lang: state.lang }));

  ws.on('message', (data) => {
    let msg;
    try { msg = JSON.parse(data); } catch { return; }
    if (msg.type === 'update') {
      state.content = msg.content;
      broadcast(ws, { type: 'update', content: msg.content });
    } else if (msg.type === 'lang') {
      state.lang = msg.lang;
      broadcast(ws, { type: 'lang', lang: msg.lang });
    }
  });

  ws.on('close', () => clients.delete(ws));
});

server.listen(3000, () => console.log('http://localhost:3000'));
