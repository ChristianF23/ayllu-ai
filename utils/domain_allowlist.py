"""
Lista de dominios permitidos: normalización y verificación de URLs.

Módulo puro (sin red ni BD). Todo falla cerrado: ante la duda, la URL
no se permite.
"""
import ipaddress
import logging
import re
from typing import Iterable
from urllib.parse import urlsplit

logger = logging.getLogger("AylluDomainAllowlist")

_LONGITUD_MAXIMA = 253
# Etiqueta DNS en ASCII (los IDN deben venir en punycode, "xn--...").
_ETIQUETA = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")  # usar con fullmatch
# Espacios, caracteres de control y la barra invertida: urlsplit descarta
# tabs/saltos de línea en silencio y los navegadores tratan "\" como "/",
# así que la URL que se verifica podría no ser la que se visita.
_CARACTERES_PROHIBIDOS = re.compile(r"[\s\x00-\x1f\x7f\\]")


def _es_ip_literal(valor: str) -> bool:
    try:
        ipaddress.ip_address(valor.strip("[]"))
        return True
    except ValueError:
        return False


def normalize_domain(valor: str) -> str:
    """
    Devuelve el dominio en minúsculas, sin espacios alrededor ni punto final.
    Lanza ValueError si no es un nombre de dominio válido (esquema, ruta,
    puerto, IP literal, etiquetas vacías, caracteres inválidos, etc.).
    No valida sufijos públicos ("com.co" se acepta): la defensa real es el
    adaptador registrado por tienda en search_service (docs/fase-1-egreso-buscador.md §2).
    """
    if not isinstance(valor, str):
        raise ValueError("El dominio debe ser texto.")

    dominio = valor.strip().lower()
    if dominio.endswith("."):
        dominio = dominio[:-1]

    if not dominio:
        raise ValueError("El dominio está vacío.")
    if len(dominio) > _LONGITUD_MAXIMA:
        raise ValueError("El dominio supera 253 caracteres.")

    if _es_ip_literal(dominio):
        raise ValueError(f"No se permiten IPs literales: {valor!r}")

    etiquetas = dominio.split(".")
    if len(etiquetas) < 2:
        raise ValueError(f"El dominio necesita al menos dos etiquetas: {valor!r}")
    for etiqueta in etiquetas:
        if not _ETIQUETA.fullmatch(etiqueta):
            raise ValueError(f"Dominio inválido: {valor!r}")
    # Un TLD puramente numérico delata una IP (ej. 127.0.0.1) o algo raro.
    if etiquetas[-1].isdigit():
        raise ValueError(f"Dominio inválido (TLD numérico): {valor!r}")

    return dominio


def is_url_allowed(url: str, allowed_domains: Iterable[str]) -> bool:
    """
    True solo si la URL es https, sin credenciales, con puerto ausente o 443,
    y su host es igual a un dominio permitido o subdominio suyo (coincidencia
    por límite de etiqueta). Nunca lanza: cualquier error devuelve False.
    """
    try:
        if not isinstance(url, str) or not url:
            return False
        if isinstance(allowed_domains, (str, bytes)):
            # Iterar un str daría caracteres sueltos: se trata como error.
            return False
        if _CARACTERES_PROHIBIDOS.search(url):
            return False

        partes = urlsplit(url)
        if partes.scheme != "https":
            return False

        netloc = partes.netloc
        if not netloc or "@" in netloc:
            return False

        puerto = partes.port  # lanza ValueError si es inválido
        if ":" in netloc and puerto != 443:
            # Cubre puertos distintos, "host:" vacío e IPv6 entre corchetes.
            return False

        if not partes.hostname:
            return False
        host = normalize_domain(partes.hostname)

        permitidos = set()
        for dominio in allowed_domains:
            try:
                permitidos.add(normalize_domain(dominio))
            except ValueError:
                logger.warning(f"Dominio permitido inválido ignorado: {dominio!r}")
        if not permitidos:
            return False

        return any(host == d or host.endswith("." + d) for d in permitidos)
    except Exception:
        return False
