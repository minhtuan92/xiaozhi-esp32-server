"""Realtime debug monitor for the translator robot (stdlib only).

Run:  python scripts/debug_monitor.py   then open http://localhost:8090
Shows: device connections on :8000, live mic level + VAD (needs `debug_monitor: true`
in data/.config.yaml, sent by the server over UDP :8091), and [NGHE]/[DICH]/[LOC]/errors
tailed from tmp/server.log.
"""
import json
import os
import queue
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(ROOT, "tmp", "server.log")
HTTP_PORT, UDP_PORT, WS_PORT = 8090, 8091, 8000
ANSI = re.compile(r"\x1b\[[0-9;]*m")
KEEP = re.compile(r"\[NGHE\]|\[DICH\]|\[LOC\]|ERROR|Traceback|WARNING|失败|Headers:|连接资源已释放")

clients, lock = [], threading.Lock()


def broadcast(obj):
    data = f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()
    with lock:
        for q in list(clients):
            try:
                q.put_nowait(data)
            except queue.Full:
                pass


def udp_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", UDP_PORT))
    while True:
        try:
            broadcast({"k": "mic", **json.loads(s.recv(2048))})
        except Exception:
            pass


def log_loop():
    pos = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    while True:
        try:
            size = os.path.getsize(LOG)
            if size < pos:
                pos = 0
            if size > pos:
                with open(LOG, "rb") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                for line in chunk.decode("utf-8", "replace").splitlines():
                    line = ANSI.sub("", line)
                    if KEEP.search(line):
                        m = re.search(r"(\d\d:\d\d:\d\d)", line)
                        txt = re.sub(r"^\d+ [\d:]+\[[^\]]*\]\[[^\]]*\]-", "", line)
                        txt = re.sub(r"^[\d-]+ [\d:]+ - \S+ - \S+ - (\w+) - (\S+ - )?", r"\1 ", txt)
                        if "Headers:" in txt:
                            m2 = re.search(r"^(\S+) conn", txt)
                            txt = f"thiet bi ket noi: {m2.group(1) if m2 else ''}"
                        broadcast({"k": "log", "t": m.group(1) if m else "", "msg": txt[:240]})
        except Exception:
            pass
        time.sleep(0.3)


def conn_loop():
    while True:
        try:
            out = subprocess.run(["netstat", "-an"], capture_output=True, text=True, timeout=5).stdout
            peers = sorted({l.split()[2].rsplit(":", 1)[0] for l in out.splitlines()
                            if f":{WS_PORT} " in l and "ESTABLISHED" in l})
            broadcast({"k": "conn", "peers": peers})
        except Exception:
            pass
        time.sleep(2)


PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Robot debug</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--mut:#666;--card:#f4f4f2;--ok:#1a7f37;--bad:#c62828;--acc:#2057d6}
@media(prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#999;--card:#222;--ok:#4cc16a;--bad:#ef5350;--acc:#6b9bff}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;max-width:900px;margin:auto}
h1{font-size:18px;margin:0 0 12px}.row{display:flex;gap:12px;flex-wrap:wrap}
.card{background:var(--card);border-radius:10px;padding:12px;flex:1;min-width:240px}
.l{color:var(--mut);font-size:12px}.big{font-size:20px;font-weight:600}
canvas{width:100%;height:120px;display:block;margin-top:8px}
#log{background:var(--card);border-radius:10px;padding:8px;height:320px;overflow:auto;font:13px ui-monospace,Consolas,monospace;margin-top:12px}
#log div{padding:2px 0;border-bottom:1px solid rgba(128,128,128,.15)}
.NGHE{color:var(--acc)}.DICH{color:var(--ok)}.LOC{color:#b8860b}.ERR{color:var(--bad)}
</style>
<h1>Robot debug - realtime</h1>
<div class=row>
<div class=card><div class=l>Thiet bi (cong 8000)</div><div class=big id=peers>-</div></div>
<div class=card><div class=l>VAD</div><div class=big id=vad>-</div></div>
<div class=card><div class=l>Mic RMS / peak</div><div class=big id=lvl>-</div></div>
</div>
<div class=card style="margin-top:12px"><div class=l>Muc mic (RMS, 16-bit) - vach xanh = VAD co tieng</div><canvas id=cv width=860 height=120></canvas>
<div class=l id=hint>Chua nhan du lieu mic. Can debug_monitor: true trong data/.config.yaml va khoi dong lai server.</div></div>
<div id=log></div>
<script>
const cv=document.getElementById('cv'),g=cv.getContext('2d'),H=[],N=170;let last=0;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n);
function draw(){g.clearRect(0,0,cv.width,cv.height);const w=cv.width/N;
H.forEach((p,i)=>{const h=Math.min(1,Math.sqrt(p.rms/6000))*cv.height;g.fillStyle=p.vad?css('--ok'):css('--mut');g.fillRect(i*w,cv.height-h,w-1,h)})}
const es=new EventSource('/events');
es.onmessage=e=>{const d=JSON.parse(e.data);
if(d.k=='mic'){last=Date.now();H.push(d);if(H.length>N)H.shift();draw();
vad.textContent=d.vad?'CO TIENG':'im';vad.style.color=d.vad?css('--ok'):'';
lvl.textContent=d.rms+' / '+d.peak;hint.textContent=d.peak>=32000?'CANH BAO: mic bi bao hoa (clipping)':d.rms<30?'Mic rat nho - kiem tra gain':'';}
else if(d.k=='conn'){peers.textContent=d.peers.length?d.peers.join(', '):'khong co';peers.style.color=d.peers.length?css('--ok'):css('--bad')}
else if(d.k=='log'){const m=d.msg;const c=/\\[NGHE\\]/.test(m)?'NGHE':/\\[DICH\\]/.test(m)?'DICH':/\\[LOC\\]/.test(m)?'LOC':/ERROR|Traceback|失败/.test(m)?'ERR':'';
const el=document.createElement('div');el.className=c;el.textContent=d.t+'  '+m;log.appendChild(el);log.scrollTop=log.scrollHeight}};
setInterval(()=>{if(last&&Date.now()-last>2000){vad.textContent='-';lvl.textContent='khong co du lieu'}},1000);
</script>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = queue.Queue(maxsize=500)
            with lock:
                clients.append(q)
            try:
                while True:
                    try:
                        self.wfile.write(q.get(timeout=15))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                with lock:
                    clients.remove(q)
        else:
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


if __name__ == "__main__":
    for fn in (udp_loop, log_loop, conn_loop):
        threading.Thread(target=fn, daemon=True).start()
    print(f"Debug monitor: http://localhost:{HTTP_PORT}")
    ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), H).serve_forever()
