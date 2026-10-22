"""Utilidades para leer paginas PRADO sin asumir nombres de controles."""
import re
import unicodedata

from bs4 import BeautifulSoup, Tag


def decode_html(raw: bytes) -> str:
    """UTF-8 estricto; si falla, Windows-1252."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text).strip().lower()


def is_hidden_by_style(tag: Tag) -> bool:
    for el in [tag, *tag.parents]:
        style = norm(el.get("style", "")).replace(" ", "") if hasattr(el, "get") else ""
        if "display:none" in style or "visibility:hidden" in style:
            return True
    return False


def page_title(soup: BeautifulSoup) -> str:
    return soup.title.get_text(strip=True) if soup.title else ""


def has_password_field(soup: BeautifulSoup) -> bool:
    return soup.find("input", attrs={"type": "password"}) is not None


def main_form(soup: BeautifulSoup) -> Tag | None:
    """PRADO renderiza una sola <form>; si hay varias, la que mas controles tiene."""
    forms = soup.find_all("form")
    if not forms:
        return None
    return max(forms, key=lambda f: len(f.find_all(["input", "select", "textarea"])))


def control_name(c: Tag) -> str:
    return c.get("name") or ""


def default_payload(form: Tag) -> dict[str, str]:
    """Lo que enviaria el navegador sin tocar nada: ocultos, defaults, seleccionados."""
    data: dict[str, str] = {}
    for c in form.find_all(["input", "select", "textarea"]):
        name = control_name(c)
        if not name:
            continue
        if c.name == "input":
            t = (c.get("type") or "text").lower()
            if t in ("submit", "button", "image", "reset", "file"):
                continue
            if t in ("checkbox", "radio"):
                if c.has_attr("checked"):
                    data[name] = c.get("value", "on")
                continue
            data[name] = c.get("value", "")
        elif c.name == "textarea":
            data[name] = c.get_text() or ""
        else:
            opts = c.find_all("option")
            chosen = next((o for o in opts if o.has_attr("selected")), opts[0] if opts else None)
            if chosen is not None:
                data[name] = chosen.get("value", chosen.get_text(strip=True))
    return data


def select_options(select: Tag) -> list[tuple[str, str]]:
    return [(o.get("value", o.get_text(strip=True)), o.get_text(strip=True)) for o in select.find_all("option")]


def buttons(form: Tag) -> list[Tag]:
    out = []
    for c in form.find_all(["input", "button"]):
        t = (c.get("type") or ("submit" if c.name == "button" else "text")).lower()
        if t in ("submit", "button", "image"):
            out.append(c)
    return out


def button_text(b: Tag) -> str:
    return b.get("value") or b.get_text(strip=True) or ""


def find_button(form: Tag, text: str = "", name: str = "") -> Tag | None:
    """Por nombre exacto del control o por texto exacto (sin acentos/mayusculas)."""
    for b in buttons(form):
        if name and control_name(b) == name:
            return b
        if text and norm(button_text(b)) == norm(text):
            return b
    return None


def find_control_by_label(form: Tag, label: str) -> Tag | None:
    """Primer control visible que aparece despues de un texto corto que empieza por `label`."""
    target = norm(label)
    for el in form.find_all(["td", "th", "label", "span", "div", "b", "strong"]):
        own = norm("".join(el.find_all(string=True, recursive=False)))
        if not own or len(own) > 60 or not own.startswith(target):
            continue
        for c in el.find_all_next(["input", "select", "textarea"]):
            if c.name == "input" and (c.get("type") or "text").lower() in ("hidden", "submit", "button", "image"):
                continue
            return c
    return None


def describe_controls(form: Tag) -> list[dict]:
    """Estructura del formulario SIN valores (solo nombres, tipos y etiquetas)."""
    out = []
    for c in form.find_all(["input", "select", "textarea"]):
        t = (c.get("type") or "text").lower() if c.name == "input" else c.name
        item = {"tag": c.name, "type": t, "name": control_name(c), "id": c.get("id", "")}
        if t == "hidden":
            out.append(item)
            continue
        item["visible"] = not is_hidden_by_style(c)
        if c.name == "select":
            opts = select_options(c)
            item["options"] = [txt for _, txt in opts[:15]]
            item["options_total"] = len(opts)
        if t in ("submit", "button", "image"):
            item["text"] = button_text(c)[:40]
        out.append(item)
    return out


def page_summary(html: str, url: str = "", status: int | None = None) -> dict:
    """Resumen estructural para diagnostico (sin valores de campos ni cookies)."""
    soup = soup_of(html)
    forms = soup.find_all("form")
    return {
        "status": status,
        "url_final": url,
        "title": page_title(soup),
        "bytes": len(html),
        "forms": len(forms),
        "iframes": len(soup.find_all("iframe")),
        "scripts": len(soup.find_all("script")),
        "inputs": [
            {"type": (c.get("type") or c.name).lower(), "name": control_name(c)[:80]}
            for c in soup.find_all(["input", "select", "textarea", "button"])
        ][:40],
        "texto_inicio": re.sub(r"\s+", " ", soup.get_text(" ", strip=True))[:300],
    }
