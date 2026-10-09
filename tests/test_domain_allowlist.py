import pytest

from utils.domain_allowlist import is_url_allowed, normalize_domain

PERMITIDOS = ["mercadolibre.com.co"]


# --- normalize_domain ---

@pytest.mark.parametrize("valor, esperado", [
    ("mercadolibre.com.co", "mercadolibre.com.co"),
    ("  MercadoLibre.COM.co  ", "mercadolibre.com.co"),
    ("mercadolibre.com.co.", "mercadolibre.com.co"),
    ("listado.mercadolibre.com.co", "listado.mercadolibre.com.co"),
    ("xn--tienda-gata-9db.com", "xn--tienda-gata-9db.com"),
    ("mi-tienda.co", "mi-tienda.co"),
])
def test_normalize_domain_validos(valor, esperado):
    assert normalize_domain(valor) == esperado


@pytest.mark.parametrize("valor", [
    "",
    "   ",
    ".",
    "https://mercadolibre.com.co",
    "mercadolibre.com.co/ofertas",
    "mercadolibre.com.co:443",
    "mercado libre.com.co",
    "mercadolibre..com.co",
    ".mercadolibre.com.co",
    "mercadolibre.com.co..",
    "127.0.0.1",
    "::1",
    "[::1]",
    "2130706433",
    "localhost",
    "-malo.com",
    "malo-.com",
    "mercado_libre.com.co",
    "user@mercadolibre.com.co",
    "mercadolíbre.com.co",
    "a\n.com",
    "evil\n.com",
    "a\t.com",
    "a .com",
    "a" * 64 + ".com",
    ".".join(["a" * 60] * 5),  # > 253 caracteres
    None,
    123,
])
def test_normalize_domain_invalidos(valor):
    with pytest.raises(ValueError):
        normalize_domain(valor)


# --- is_url_allowed: casos permitidos ---

@pytest.mark.parametrize("url", [
    "https://mercadolibre.com.co",
    "https://mercadolibre.com.co/",
    "https://mercadolibre.com.co/ofertas?q=comida+gato#x",
    "https://listado.mercadolibre.com.co/comida-gato",
    "https://a.b.mercadolibre.com.co/",
    "https://MercadoLibre.COM.CO/",
    "HTTPS://mercadolibre.com.co/",
    "https://mercadolibre.com.co:443/",
    "https://mercadolibre.com.co./",
    "https://mercadolibre.com.co.:443/",
])
def test_url_permitida(url):
    assert is_url_allowed(url, PERMITIDOS) is True


def test_dominios_permitidos_se_normalizan():
    assert is_url_allowed("https://mercadolibre.com.co/", ["  MERCADOLIBRE.com.co. "])


# --- is_url_allowed: intentos de bypass ---

@pytest.mark.parametrize("url", [
    # Coincidencia sin límite de etiqueta
    "https://evilmercadolibre.com.co/",
    "https://mercadolibre.com.co.evil.com/",
    "https://mercadolibre.com.coevil.com/",
    "https://xmercadolibre.com.co/",
    # Credenciales / userinfo
    "https://mercadolibre.com.co@evil.com/",
    "https://user:pass@mercadolibre.com.co/",
    "https://user@mercadolibre.com.co/",
    "https://evil.com@mercadolibre.com.co/",
    "https://evil.com\\@mercadolibre.com.co/",
    "https://evil.com\\.mercadolibre.com.co/",
    # Puertos
    "https://mercadolibre.com.co:8443/",
    "https://mercadolibre.com.co:80/",
    "https://mercadolibre.com.co:/",
    "https://mercadolibre.com.co:abc/",
    "https://mercadolibre.com.co:99999/",
    # Esquemas
    "http://mercadolibre.com.co/",
    "ftp://mercadolibre.com.co/",
    "javascript://mercadolibre.com.co/%0aalert(1)",
    "//mercadolibre.com.co/",
    "mercadolibre.com.co",
    "https:mercadolibre.com.co",
    "https:/mercadolibre.com.co",
    # IPs literales
    "https://127.0.0.1/",
    "https://192.168.0.1:443/",
    "https://[::1]/",
    "https://[::ffff:127.0.0.1]/",
    "https://2130706433/",
    "https://0x7f000001/",
    "https://0x7f.0.0.1/",
    "https://017700000001/",
    # Punycode / IDN que no es el dominio permitido
    "https://xn--mercadolibr-xyz.com.co/",
    "https://mercadolíbre.com.co/",
    # Puntos raros y etiquetas vacías
    "https://mercadolibre..com.co/",
    "https://.mercadolibre.com.co/",
    "https://mercadolibre.com.co../",
    "https://%6dercadolibre.com.co/",
    # Espacios, tabs y saltos de línea
    "https://mercadolibre.com.co /",
    " https://mercadolibre.com.co/",
    "https://mercadolibre.com.co/\n",
    "https://merca\tdolibre.com.co/",
    "https://evil.com\t.mercadolibre.com.co/",
    "https://mercado\nlibre.com.co/",
    "https://mercadolibre.com.co\x00.evil.com/",
    # Vacíos y malformados
    "",
    "https://",
    "https:///",
    "https://:443/",
    "https://[mercadolibre.com.co/",
])
def test_url_bypass_rechazado(url):
    assert is_url_allowed(url, PERMITIDOS) is False


@pytest.mark.parametrize("url", [None, 123, b"https://mercadolibre.com.co/", [], object()])
def test_url_no_texto_rechazada(url):
    assert is_url_allowed(url, PERMITIDOS) is False


@pytest.mark.parametrize("permitidos", [
    [],
    (),
    set(),
    "mercadolibre.com.co",  # un str suelto no es una lista
    ["", "   ", "https://mercadolibre.com.co", "127.0.0.1"],  # todos inválidos
    None,
    123,
])
def test_lista_vacia_o_invalida_falla_cerrado(permitidos):
    assert is_url_allowed("https://mercadolibre.com.co/", permitidos) is False


def test_dominio_invalido_en_lista_no_rompe_los_validos():
    assert is_url_allowed("https://mercadolibre.com.co/", [None, "mercadolibre.com.co"])


def test_sufijo_publico_se_acepta_comportamiento_documentado():
    # La defensa real es el adaptador registrado por tienda en search_service
    # (docs/fase-1-egreso-buscador.md §2); esta capa no valida sufijos públicos.
    # Si alguien registra "com.co", cualquier *.com.co pasa este filtro.
    assert normalize_domain("com.co") == "com.co"
    assert is_url_allowed("https://evil.com.co/", ["com.co"]) is True


def test_sufijo_publico_no_amplia_permiso():
    # Que se permita mercadolibre.com.co no permite otro *.com.co
    assert is_url_allowed("https://evil.com.co/", PERMITIDOS) is False
