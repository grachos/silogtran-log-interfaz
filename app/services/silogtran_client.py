"""Cliente de Silogtran: login PRADO + centro de costo + sesion persistente."""
import asyncio
import logging
import time
from urllib.parse import urljoin

import httpx

from app.core.config import Settings
from app.core.exceptions import AppError, SessionUnavailable, SilogtranTimeout, UnexpectedFormat
from app.services import prado_parser as p

log = logging.getLogger(__name__)
LOGIN_BUTTONS = ("ingresar", "entrar", "iniciar sesion", "login", "aceptar", "acceder")


class SilogtranClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.s = settings
        self.http = httpx.AsyncClient(
            follow_redirects=True,
            timeout=settings.request_timeout_seconds,
            transport=transport,
            headers={"User-Agent": "Mozilla/5.0 (compatible; silogtran-log-interfaz)"},
        )
        self.lock = asyncio.Lock()  # la sesion PRADO es por usuario: una consulta a la vez
        self.logged_at = 0.0
        self.trace: list[str] = []

    async def aclose(self) -> None:
        await self.http.aclose()

    # -- HTTP -----------------------------------------------------------------
    last_summary: dict | None = None

    async def _request(self, method: str, url: str, **kw) -> tuple[str, str]:
        try:
            r = await self.http.request(method, url, **kw)
        except httpx.TimeoutException as e:
            raise SilogtranTimeout("Silogtran no respondio a tiempo.") from e
        except httpx.HTTPError as e:
            raise SessionUnavailable("No se pudo contactar a Silogtran.") from e
        html = p.decode_html(r.content)
        self.trace.append(f"{method} {r.status_code} {p.page_title(p.soup_of(html))[:50]}")
        self.last_summary = p.page_summary(html, str(r.url), r.status_code)
        return html, str(r.url)

    async def _submit(self, html: str, url: str, extra: dict[str, str], button=None) -> tuple[str, str]:
        form = p.main_form(p.soup_of(html))
        if form is None:
            raise UnexpectedFormat("La pagina no trae formulario.")
        data = p.default_payload(form)
        data.update(extra)
        if button is not None and p.control_name(button):
            data[p.control_name(button)] = p.button_text(button)
            data["PRADO_POSTBACK_TARGET"] = p.control_name(button)
        action = urljoin(url, form.get("action") or url)
        return await self._request("POST", action, data=data)

    # -- Sesion ---------------------------------------------------------------
    def session_valid(self) -> bool:
        return time.monotonic() - self.logged_at < self.s.silogtran_session_lifetime_seconds and self.logged_at > 0

    @staticmethod
    def expired(html: str) -> bool:
        return p.has_password_field(p.soup_of(html))

    async def login(self) -> None:
        if not self.s.silogtran_username or not self.s.silogtran_password:
            raise SessionUnavailable("Credenciales de Silogtran no configuradas.")
        self.trace = []
        html, url = await self._request("GET", self.s.silogtran_login_url)
        form = p.main_form(p.soup_of(html))
        pwd = form.find("input", attrs={"type": "password"}) if form else None
        if form is None or pwd is None:
            raise UnexpectedFormat("No se encontro el formulario de login.", details=self.last_summary)
        user = next(
            (c for c in pwd.find_all_previous("input") if (c.get("type") or "text").lower() == "text"), None
        )
        if user is None:
            raise UnexpectedFormat("No se encontro el campo de usuario.", details=self.last_summary)
        btn = next((b for b in p.buttons(form) if p.norm(p.button_text(b)) in LOGIN_BUTTONS), None)
        btn = btn or (p.buttons(form) or [None])[0]
        html, url = await self._submit(
            html,
            url,
            {p.control_name(user): self.s.silogtran_username, p.control_name(pwd): self.s.silogtran_password},
            btn,
        )
        if self.expired(html) and not self._cost_center_select(html):
            raise SessionUnavailable("Silogtran rechazo el login.", details=self.last_summary)
        html, url = await self._pick_cost_center(html, url)
        if self.expired(html):
            raise SessionUnavailable("Silogtran rechazo el login.", details=self.last_summary)
        self.logged_at = time.monotonic()
        log.info("login ok; pasos=%s", self.trace)

    def _cost_center_select(self, html: str):
        form = p.main_form(p.soup_of(html))
        if form is None:
            return None
        target = p.norm(self.s.silogtran_cost_center)
        for sel in form.find_all("select"):
            if any(target in p.norm(txt) for _, txt in p.select_options(sel)):
                return sel
        return None

    async def _pick_cost_center(self, html: str, url: str) -> tuple[str, str]:
        sel = self._cost_center_select(html)
        if sel is None:
            self.trace.append("sin selector de centro de costo")
            return html, url
        target = p.norm(self.s.silogtran_cost_center)
        value = next(v for v, txt in p.select_options(sel) if target in p.norm(txt))
        form = p.main_form(p.soup_of(html))
        btn = (p.buttons(form) or [None])[0]
        return await self._submit(html, url, {p.control_name(sel): value}, btn)

    async def ensure_session(self) -> None:
        if not self.session_valid():
            await self.login()

    async def keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(self.s.silogtran_keepalive_seconds)
            try:
                async with self.lock:
                    if self.logged_at:
                        html, _ = await self._request("GET", self.s.silogtran_log_url)
                        if self.expired(html):
                            await self.login()
                        else:
                            self.logged_at = time.monotonic()
            except AppError as e:
                log.warning("keepalive fallo: %s", e.code)
                self.logged_at = 0.0
            except Exception:
                log.exception("keepalive error inesperado")

    # -- Diagnostico ----------------------------------------------------------
    async def diagnose_log_form(self) -> dict:
        """Estructura del formulario del log, sin valores ni datos sensibles."""
        async with self.lock:
            await self.ensure_session()
            html, url = await self._request("GET", self.s.silogtran_log_url)
            if self.expired(html):
                await self.login()
                html, url = await self._request("GET", self.s.silogtran_log_url)
            soup = p.soup_of(html)
            form = p.main_form(soup)
            if form is None:
                raise UnexpectedFormat("La pagina del log no trae formulario.")
            labels = ["Interfaz", "Datos de Entrada", "Fecha Inicial", "Verbo"]
            detected = {}
            for lb in labels:
                c = p.find_control_by_label(form, lb)
                detected[lb] = {"name": p.control_name(c), "tag": c.name} if c is not None else None
            return {
                "title": p.page_title(soup),
                "pasos_login": list(self.trace),
                "url_final_es_log": "BuscarLogInterfaz" in url,
                "campos_ocultos": sorted(k for k in p.default_payload(form) if k.startswith("PRADO") or "Hidden" in k),
                "controles": p.describe_controls(form),
                "deteccion_por_etiqueta": detected,
                "botones": [{"name": p.control_name(b), "text": p.button_text(b)[:40]} for b in p.buttons(form)],
                "boton_buscar": bool(p.find_button(form, text="Buscar", name=self.s.silogtran_log_search_button)),
            }
