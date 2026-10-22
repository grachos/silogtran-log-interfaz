"""Login con un navegador real (Playwright) cuando el WAF de Silogtran exige JavaScript.

El navegador solo se usa para iniciar sesion: ejecuta el desafio del AWS WAF como lo
haria cualquier Chromium (sin camuflar la huella ni resolver CAPTCHAs), completa usuario,
contrasena y centro de costo, y devuelve las cookies para el cliente HTTP liviano.
Se cierra enseguida para no ocupar memoria (Render gratuito: 512 MB).
"""
import logging

from app.core.config import Settings
from app.core.exceptions import AppError, SessionUnavailable, SilogtranTimeout

log = logging.getLogger(__name__)

PASSWORD = "input[type=password]"
LOGIN_BUTTON = "input[type=submit][value='Iniciar Sesión'], input[name$='BtnIngresar']"


class WafCaptcha(AppError):
    code, status_code = "SILOGTRAN_WAF_CAPTCHA", 503


async def browser_login(s: Settings) -> tuple[list[dict], str]:
    """Devuelve (cookies de la sesion iniciada, incluida aws-waf-token; User-Agent del navegador)."""
    try:
        from playwright.async_api import Error as PwError
        from playwright.async_api import TimeoutError as PwTimeout
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise SessionUnavailable("Playwright no esta instalado en este entorno.") from e

    timeout_ms = int(s.request_timeout_seconds * 1000)
    async with async_playwright() as pw:
        launch = {"headless": True, "args": ["--disable-dev-shm-usage", "--no-sandbox"]}
        if s.playwright_executable_path:
            launch["executable_path"] = s.playwright_executable_path
        browser = await pw.chromium.launch(**launch)
        try:
            ctx = await browser.new_context(locale="es-CO")
            page = await ctx.new_page()
            page.set_default_timeout(timeout_ms)
            await page.goto(s.silogtran_login_url, wait_until="domcontentloaded")
            try:
                # El desafio del WAF recarga la pagina sola al resolverse.
                await page.wait_for_selector(PASSWORD, state="visible")
            except PwTimeout as e:
                if await page.locator("#captcha-container, .amzn-captcha-modal, [id*=captcha]").count():
                    raise WafCaptcha(
                        "El firewall de Silogtran exige CAPTCHA; se requiere que permitan la IP del servicio."
                    ) from e
                raise SilogtranTimeout("El formulario de login no aparecio (desafio del WAF sin resolver).") from e

            await page.fill("input[name$='$Usuario']", s.silogtran_username)
            await page.fill(PASSWORD, s.silogtran_password)
            async with page.expect_navigation(wait_until="domcontentloaded"):
                await page.click(LOGIN_BUTTON)

            await _pick_cost_center(page, s.silogtran_cost_center)

            if await page.locator(PASSWORD).count():
                raise SessionUnavailable("Silogtran rechazo el login.")
            log.info("login por navegador ok; titulo=%s", (await page.title())[:50])
            return await ctx.cookies(), await page.evaluate("navigator.userAgent")
        except PwTimeout as e:
            raise SilogtranTimeout("Silogtran no respondio a tiempo (navegador).") from e
        except PwError as e:
            raise SessionUnavailable(f"Fallo del navegador: {str(e).splitlines()[0][:120]}") from e
        finally:
            await browser.close()


async def _pick_cost_center(page, cost_center: str) -> None:
    """Pantalla 'Selecciona tu centro de costo': <select> + boton 'Continuar'."""
    for sel in await page.locator("select").all():
        labels = [t.strip() for t in await sel.locator("option").all_inner_texts()]
        match = next((t for t in labels if cost_center.lower() in t.lower()), None)
        if match is None:
            continue
        await sel.select_option(label=match)
        btn = page.locator("input[type=submit][value='Continuar'], button:has-text('Continuar')").first
        async with page.expect_navigation(wait_until="domcontentloaded"):
            await btn.click()
        return
    log.info("sin selector de centro de costo tras el login")
