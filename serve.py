"""serve.py — Local portfolio server with one-click refresh.

Usage:
    python3 serve.py

Then open: http://localhost:8765

Click "Refresh" on the page to pull fresh IBKR positions + prices + TA + Telegram.
Server stays running in Terminal — close Terminal to stop it.
"""
import http.server
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

PORT = 8765
ROOT = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(ROOT, "outputs", "portfolio.html")

_refresh_state = {"running": False, "last": None, "log": []}
_lock = threading.Lock()


def _run_refresh(mode: str):
    with _lock:
        if _refresh_state["running"]:
            return
        _refresh_state["running"] = True
        _refresh_state["log"] = []

    args = []
    if mode == "no-ibkr":
        args = ["--no-ibkr"]
    elif mode == "no-ai":
        args = ["--no-ai", "--no-ibkr"]

    cmd = [sys.executable, os.path.join(ROOT, "refresh.py")] + args
    env = {**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")}

    def stream():
        proc = subprocess.Popen(
            cmd, cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            line = line.rstrip()
            with _lock:
                _refresh_state["log"].append(line)
            print(line)
        proc.wait()
        with _lock:
            _refresh_state["running"] = False
            _refresh_state["last"] = datetime.now().strftime("%H:%M:%S")

    threading.Thread(target=stream, daemon=True).start()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access logs

    def _send(self, code, ctype, body):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/portfolio":
            # Inject refresh UI into portfolio.html
            try:
                with open(PORTFOLIO_FILE, encoding="utf-8") as f:
                    html = f.read()
                html = html.replace("</body>", REFRESH_UI + "</body>")
                self._send(200, "text/html; charset=utf-8", html)
            except FileNotFoundError:
                self._send(404, "text/plain", "No portfolio.html — run python3 refresh.py first")

        elif self.path == "/status":
            with _lock:
                state = dict(_refresh_state)
            self._send(200, "application/json", json.dumps(state))

        else:
            self._send(404, "text/plain", "not found")

    def do_POST(self):
        if self.path.startswith("/refresh"):
            mode = "full"
            if "no-ai" in self.path:
                mode = "no-ai"
            elif "no-ibkr" in self.path:
                mode = "no-ibkr"
            _run_refresh(mode)
            self._send(200, "application/json", json.dumps({"started": True}))
        else:
            self._send(404, "text/plain", "not found")


REFRESH_UI = """
<div id="refresh-bar" style="
  position:fixed;bottom:20px;right:20px;z-index:9999;
  display:flex;flex-direction:column;align-items:flex-end;gap:8px">

  <div id="refresh-log" style="
    display:none;
    background:#0d0f14;border:1px solid rgba(255,255,255,0.1);
    border-radius:10px;padding:12px 14px;
    max-height:220px;overflow-y:auto;
    font-family:monospace;font-size:11px;color:#8a8c98;
    width:360px;line-height:1.6;
  "></div>

  <div style="display:flex;gap:8px;align-items:center">
    <button onclick="doRefresh('no-ai')" style="
      background:#1e2030;border:1px solid rgba(255,255,255,0.12);
      color:#8a8c98;font-size:11px;padding:7px 12px;
      border-radius:8px;cursor:pointer">⚡ Fast</button>

    <button onclick="doRefresh('full')" id="refresh-btn" style="
      background:#2563eb;border:none;color:#fff;
      font-size:13px;font-weight:600;padding:9px 18px;
      border-radius:10px;cursor:pointer;
      box-shadow:0 4px 14px rgba(37,99,235,0.4)">
      🔄 Refresh
    </button>
  </div>

  <div id="refresh-status" style="font-size:10px;color:#5a5c6e;text-align:right"></div>
</div>

<script>
let _polling = null;

function doRefresh(mode) {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = '⏳ Running…';
  btn.disabled = true;
  document.getElementById('refresh-log').style.display = 'block';
  document.getElementById('refresh-log').innerHTML = '';
  fetch('/refresh/' + mode, {method:'POST'})
    .then(() => { _polling = setInterval(pollStatus, 1000); });
}

function pollStatus() {
  fetch('/status').then(r=>r.json()).then(d => {
    const log = document.getElementById('refresh-log');
    log.innerHTML = d.log.slice(-30).map(l =>
      '<div style="color:' + (l.includes('✅') ? '#34d399' : l.includes('❌') ? '#f87171' : '#8a8c98') + '">' +
      l.replace(/</g,'&lt;') + '</div>'
    ).join('');
    log.scrollTop = log.scrollHeight;

    if (d.last) {
      document.getElementById('refresh-status').textContent = 'Last: ' + d.last;
    }

    if (!d.running) {
      clearInterval(_polling);
      const btn = document.getElementById('refresh-btn');
      btn.textContent = '🔄 Refresh';
      btn.disabled = false;
      // Reload page after 1.5s to show fresh data
      setTimeout(() => location.reload(), 1500);
    }
  });
}
</script>
"""


def main():
    print(f"""
╔══════════════════════════════════════╗
  📊 Portfolio Server — localhost:{PORT}
╚══════════════════════════════════════╝
  Open: http://localhost:{PORT}

  🔄 Refresh  — full (IBKR + prices + AI + Telegram)
  ⚡ Fast     — skip IBKR sync + skip AI (TA only, ~2 min)

  Press Ctrl+C to stop.
""")
    server = http.server.HTTPServer(("localhost", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
