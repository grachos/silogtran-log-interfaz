"""Login por navegador contra un servidor local que imita el desafio del AWS WAF."""
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from app.core.config import Settings
from app.services.silogtran_client import SilogtranClient

pytest.importorskip("playwright")
EXE = os.environ.get("PLAYWRIGHT_EXECUTABLE_PATH", "/opt/pw-browsers/chromium")
if not Path(EXE).exists():
    pytest.skip("sin Chromium local", allow_module_level=True)

LOGIN = (Path(__file__).parent / "fixtures" / "login_real.html").read_text(encoding="utf-8")
CHALLENGE = "<html><body>JavaScript is disabled<script>document.cookie='aws-waf-token=ok; path=/';location.reload()</script></body></html>"
CENTRO = """<html><head><title>Centro</title></head><body><form method="post" action="/index.php?page=Centro">
<select name="ctl0$cc"><option value="">Seleccione un centro de costo</option><option value="7">CONSTRUPROYEC-PRINCIPAL</option>
<option value="8">CONSTRUPROYEC-CONSORCIO</option></select><input type="submit" name="ctl0$ok" value="Continuar"></form></body></html>"""
HOME = "<html><head><title>Inicio</title></head><body><form method='post'><input type='hidden' name='PRADO_PAGESTATE' value='h'></form></body></html>"


class Handler(BaseHTTPRequestHandler):
    posts: list[dict] = []

    def log_message(self, *a):
        pass

    def _send(self, code, body, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode())

    def _challenged(self):
        if "aws-waf-token=ok" not in (self.headers.get("Cookie") or ""):
            self._send(202, CHALLENGE, {"x-amzn-waf-action": "challenge"})
            return True
        return False

    def do_GET(self):
        if self._challenged():
            return
        if "LoginPage" in self.path:
            self._send(200, LOGIN.replace("https://construproyec.colombiasoftware.net", ""))
        else:
            self._send(200, HOME if "session=1" in self.headers.get("Cookie", "") else LOGIN)

    def do_POST(self):
        if self._challenged():
            return
        data = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        Handler.posts.append(data)
        if "LoginPage" in self.path:
            self._send(200, CENTRO)
        else:
            self._send(200, HOME, {"Set-Cookie": "session=1; path=/"})


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


async def test_auto_mode_falls_back_to_browser_and_reuses_cookies(server):
    Handler.posts = []
    s = Settings(
        silogtran_username="u",
        silogtran_password="secreto",
        silogtran_login_url=f"{server}/index.php?page=LoginPage",
        silogtran_log_url=f"{server}/index.php?page=Maestros.Interfaz.BuscarLogInterfaz",
        playwright_executable_path=EXE,
        request_timeout_seconds=20,
    )
    c = SilogtranClient(s)
    await c.login()
    assert "WAF challenge -> navegador" in c.trace
    login_post, centro_post = Handler.posts
    assert login_post["ctl0$MainModule$Usuario"] == ["u"] and login_post["ctl0$MainModule$Clave"] == ["secreto"]
    assert centro_post["ctl0$cc"] == ["7"]
    # El cliente HTTP liviano sigue con las cookies del navegador (sin nuevo desafio).
    assert c.http.cookies.get("aws-waf-token") == "ok" and c.session_valid()
    assert "HeadlessChrome" in c.http.headers["User-Agent"] or "Chrome" in c.http.headers["User-Agent"]
    await c.aclose()
