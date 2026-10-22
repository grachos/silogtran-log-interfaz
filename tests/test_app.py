import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logging import MaskingFilter
from app.services import prado_parser as p
from app.services.silogtran_client import SilogtranClient

LOGIN = """<html><head><title>Login</title></head><body><form action="index.php?page=Login" method="post">
<input type="hidden" name="PRADO_PAGESTATE" value="abc">
<input type="text" name="ctl0$user"><input type="password" name="ctl0$pass">
<input type="submit" name="ctl0$go" value="Ingresar"></form></body></html>"""
CENTRO = """<html><head><title>Centro</title></head><body><form action="index.php?page=Centro" method="post">
<input type="hidden" name="PRADO_PAGESTATE" value="s2">
<select name="ctl0$cc"><option value="1">OTRO</option><option value="7">CONSTRUPROYEC-PRINCIPAL</option></select>
<input type="submit" name="ctl0$salir" value="Salir"><input type="submit" name="ctl0$ok" value="Continuar"></form></body></html>"""
LOGFORM = """<html><head><title>Log</title></head><body>
<div id="menu"><input type="text" name="menu$buscar" placeholder="Buscar"><span>Financiero</span></div>
<form action="index.php?page=Maestros.Interfaz.BuscarLogInterfaz" method="post">
<input type="hidden" name="PRADO_PAGESTATE" value="s3">
<table><tr><td>Interfaz</td><td><input type="checkbox" name="ctl0$chk"><input type="text" name="ctl0$interfaz"></td></tr>
<tr><td>Datos de Entrada</td><td><textarea name="ctl0$entrada"></textarea></td></tr>
<tr><td>Fecha Inicial-Final</td><td><input type="text" name="ctl0$fi"><input type="text" name="ctl0$ff"></td></tr>
<tr><td>Verbo</td><td><select name="ctl0$verbo"><option value="POST" selected>POST</option><option>GET</option></select></td></tr></table>
<span style="display:none">La fecha ingresada no es válida!</span>
<input type="submit" name="ctl0$buscar" value="Buscar"></form></body></html>"""


def handler(request: httpx.Request) -> httpx.Response:
    q = str(request.url)
    if request.method == "GET" and "page=Login" in q:
        return httpx.Response(200, text=LOGIN)
    if request.method == "POST" and "page=Login" in q:
        assert b"ctl0%24user=u" in request.content and b"ctl0%24go=Ingresar" in request.content
        return httpx.Response(200, text=CENTRO)
    if request.method == "POST" and "page=Centro" in q:
        assert b"ctl0%24cc=7" in request.content and b"ctl0%24ok=Continuar" in request.content and b"salir" not in request.content
        return httpx.Response(200, text=LOGFORM)
    return httpx.Response(200, text=LOGFORM)


def settings(**kw):
    return Settings(silogtran_username="u", silogtran_password="secreto", api_token="tok", **kw)


def test_decode_cp1252():
    assert p.decode_html("Matrícula".encode("cp1252")) == "Matrícula"
    assert p.decode_html("Matrícula".encode()) == "Matrícula"


def test_label_detection_ignores_header_search():
    form = p.main_form(p.soup_of(LOGFORM))
    assert p.control_name(p.find_control_by_label(form, "Datos de Entrada")) == "ctl0$entrada"
    assert p.control_name(p.find_control_by_label(form, "Fecha Inicial")) == "ctl0$fi"
    assert p.control_name(p.find_button(form, text="Buscar")) == "ctl0$buscar"


def test_default_payload_has_hidden_and_selected():
    d = p.default_payload(p.main_form(p.soup_of(LOGFORM)))
    assert d["PRADO_PAGESTATE"] == "s3" and d["ctl0$verbo"] == "POST" and "ctl0$chk" not in d


def test_hidden_validation_message_is_flagged_hidden():
    span = p.soup_of(LOGFORM).find("span", style=True)
    assert p.is_hidden_by_style(span)


async def test_login_and_diagnose():
    c = SilogtranClient(settings(), transport=httpx.MockTransport(handler))
    d = await c.diagnose_log_form()
    assert d["boton_buscar"]
    assert d["deteccion_por_etiqueta"]["Verbo"]["name"] == "ctl0$verbo"
    assert "secreto" not in str(d)
    await c.aclose()


async def test_login_rejected():
    c = SilogtranClient(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, text=LOGIN)))
    with pytest.raises(Exception) as e:
        await c.login()
    assert e.value.code == "SILOGTRAN_SESSION_UNAVAILABLE"
    await c.aclose()


def test_endpoint_auth_and_health(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "tok")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as cl:
        assert cl.get("/health").json() == {"status": "ok"}
        r = cl.post("/api/v1/diagnostico/formulario")
        assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHORIZED"
        assert cl.post("/api/v1/diagnostico/formulario", headers={"Authorization": "Bearer mal"}).status_code == 401
    get_settings.cache_clear()


def test_masking():
    import logging

    rec = logging.LogRecord("x", 20, "", 0, "password=abc123 x-api-key: K9", (), None)
    MaskingFilter().filter(rec)
    assert "abc123" not in rec.msg and "K9" not in rec.msg


async def test_login_error_carries_diagnostic_without_secrets():
    page = "<html><head><title>Hola</title></head><body><div>Cargando</div><script>1</script></body></html>"
    c = SilogtranClient(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, text=page)))
    with pytest.raises(Exception) as e:
        await c.login()
    d = e.value.details
    assert d["title"] == "Hola" and d["forms"] == 0 and d["scripts"] == 1 and "secreto" not in str(d)
    await c.aclose()


async def test_login_with_real_login_page_structure():
    from pathlib import Path

    page = (Path(__file__).parent / "fixtures" / "login_real.html").read_text(encoding="utf-8")
    seen = {}

    def h(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            seen["body"] = request.content.decode()
            return httpx.Response(200, text=LOGFORM)
        return httpx.Response(200, text=page)

    c = SilogtranClient(settings(), transport=httpx.MockTransport(h))
    await c.login()
    body = seen["body"]
    assert "MainModule%24Usuario=u" in body and "MainModule%24Clave=secreto" in body
    assert "BtnIngresar=Iniciar" in body and "BtnRecordar" not in body.replace("IDLockHidden_ctl0_MainModule_BtnRecordar", "")
    assert "IDLockHidden_ctl0_MainModule_BtnIngresar=true" in body
    assert "PRADO_POSTBACK_TARGET=ctl0%24MainModule%24BtnIngresar" in body
    await c.aclose()


async def test_empty_202_reports_headers_for_waf_diagnosis():
    resp = httpx.Response(202, content=b"", headers={"x-amzn-waf-action": "challenge", "set-cookie": "s=1"})
    c = SilogtranClient(settings(silogtran_login_mode="http"), transport=httpx.MockTransport(lambda r: resp))
    with pytest.raises(Exception) as e:
        await c.login()
    assert e.value.code == "SILOGTRAN_WAF_CHALLENGE"
    d = e.value.details
    assert d["status"] == 202 and d["bytes"] == 0
    assert d["headers"] == {"x-amzn-waf-action": "challenge"}
    await c.aclose()
