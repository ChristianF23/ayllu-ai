#!/usr/bin/env python3
"""Validador y generador de índices para bundles OKF v0.2.

Uso:
    python okf.py validar <bundle>      # exit 1 si hay errores
    python okf.py indices <bundle>      # (re)genera los index.md

Solo requiere PyYAML. Los errores rompen la conformidad con la spec o filtran
secretos; las advertencias son guía (la spec pide tolerancia con ellas).
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

RESERVADOS = {"index.md", "log.md"}
ESTADOS = {"draft", "stable", "deprecated"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
CERCA = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
ENLACE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
NOTA_USO = re.compile(r"\[\^([^\]\s]+)\](?!:)")
NOTA_DEF = re.compile(r"^\[\^([^\]\s]+)\]:", re.MULTILINE)
_VALOR = r"""\s*[=:]\s*["']?(?!\*\*\*|<oculto>)[^;\s"']+"""
SECRETOS = [
    re.compile(r"\b(password|pwd|user id|uid)" + _VALOR, re.I),
    re.compile(r"\b(secret|api[_-]?key|access[_-]?token)" + _VALOR, re.I),
    re.compile(r"\bsqlcmd\b[^\n]*\s-[PU]\s+\S+"),
    re.compile(r"\bdtexec\b[^\n]*/(Decrypt|User|Password)\b[:\s]\S+", re.I),
]


class _Loader(yaml.SafeLoader):
    """SafeLoader que deja las fechas como texto para validar el formato ISO."""


_Loader.yaml_implicit_resolvers = {
    k: [(t, r) for t, r in v if t != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def separar(texto: str):
    m = FRONTMATTER.match(texto)
    if not m:
        return None, texto
    return yaml.load(m.group(1), Loader=_Loader), texto[m.end():]


def conceptos(bundle: Path):
    return sorted(p for p in bundle.rglob("*.md") if p.name not in RESERVADOS)


def _fecha_ok(valor) -> bool:
    return isinstance(valor, str) and bool(ISO.match(valor))


def _parse_fecha(valor: str) -> datetime:
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def validar_concepto(ruta: Path, bundle: Path):
    errores, avisos = [], []
    texto = ruta.read_text(encoding="utf-8")
    try:
        fm, cuerpo = separar(texto)
    except yaml.YAMLError as e:
        return [f"frontmatter YAML inválido: {e}"], []
    if not isinstance(fm, dict):
        return ["falta el frontmatter YAML delimitado por ---"], []

    if not isinstance(fm.get("type"), str) or not fm["type"].strip():
        errores.append("falta `type` (único campo obligatorio)")

    estado = fm.get("status")
    if estado is not None and estado not in ESTADOS:
        errores.append(f"`status: {estado}` no es válido; usar draft|stable|deprecated")
    for legado in ("timestamp", "trust_tier"):
        if legado in fm:
            avisos.append(f"`{legado}` no existe en v0.2 (usar generated/verified)")

    gen = fm.get("generated")
    if gen is None:
        avisos.append("falta `generated: {by, at}`")
    elif not isinstance(gen, dict) or not gen.get("by"):
        errores.append("`generated` requiere `by`")
    elif "at" in gen and not _fecha_ok(gen["at"]):
        errores.append("`generated.at` no es ISO 8601 con zona (ej. 2026-06-30T14:00:00Z)")

    ver = fm.get("verified")
    if ver is not None:
        for v in ver if isinstance(ver, list) else [ver]:
            if not isinstance(v, dict) or not v.get("by") or not _fecha_ok(v.get("at")):
                errores.append("cada `verified` requiere `by` y `at` ISO 8601 con zona")

    if "stale_after" in fm:
        if not _fecha_ok(fm["stale_after"]):
            errores.append("`stale_after` no es ISO 8601 con zona")
        elif datetime.now(timezone.utc) >= _parse_fecha(fm["stale_after"]):
            avisos.append("el concepto está vencido (`stale_after` ya pasó)")

    ids = []
    for s in fm.get("sources") or []:
        if not isinstance(s, dict) or not s.get("resource"):
            errores.append("cada entrada de `sources` requiere `resource`")
            continue
        if s.get("id"):
            ids.append(s["id"])
        if "last_modified" in s and not _fecha_ok(s["last_modified"]):
            errores.append(f"`sources[{s.get('id', '?')}].last_modified` no es ISO 8601 con zona")
    if len(ids) != len(set(ids)):
        errores.append("hay `sources[].id` repetidos")

    if fm.get("type") == "Attested Computation" and not fm.get("runtime"):
        errores.append("`Attested Computation` requiere `runtime`")

    sin_codigo = CERCA.sub("", cuerpo)
    defs = set(NOTA_DEF.findall(cuerpo))
    for uso in sorted(set(NOTA_USO.findall(sin_codigo))):
        if uso not in defs:
            errores.append(f"nota al pie [^{uso}] sin definición")
        if uso not in ids:
            avisos.append(f"nota al pie [^{uso}] no corresponde a ningún `sources[].id`")

    for destino in ENLACE.findall(sin_codigo):
        if re.match(r"^(https?:|mailto:|#)", destino):
            continue
        sin_ancla = destino.split("#")[0]
        if not sin_ancla.endswith(".md"):
            continue
        base = bundle if sin_ancla.startswith("/") else ruta.parent
        if not (base / sin_ancla.lstrip("/")).resolve().exists():
            avisos.append(f"enlace roto: {destino}")

    for patron in SECRETOS:
        for m in patron.finditer(texto):
            errores.append(f"posible secreto/credencial (`{m.group(0)[:12]}...`); redactar como ***")
    return errores, avisos


def validar(bundle: Path) -> int:
    total_err = total_avi = 0
    archivos = conceptos(bundle)
    for ruta in archivos:
        errores, avisos = validar_concepto(ruta, bundle)
        rel = ruta.relative_to(bundle)
        for e in errores:
            print(f"ERROR  {rel}: {e}")
        for a in avisos:
            print(f"AVISO  {rel}: {a}")
        total_err += len(errores)
        total_avi += len(avisos)
    for idx in bundle.rglob("index.md"):
        if idx.parent != bundle and idx.read_text(encoding="utf-8").startswith("---"):
            print(f"ERROR  {idx.relative_to(bundle)}: index.md no raíz no lleva frontmatter")
            total_err += 1
    print(f"\n{len(archivos)} conceptos, {total_err} errores, {total_avi} avisos")
    return 1 if total_err else 0


def _resumen(ruta: Path):
    try:
        fm, _ = separar(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        print(f"AVISO  {ruta.name}: YAML inválido, se omite su resumen (correr `validar`)")
        fm = None
    fm = fm if isinstance(fm, dict) else {}
    return fm.get("type", "Sin tipo"), fm.get("title") or ruta.stem, fm.get("description", "")


def _tiene_conceptos(carpeta: Path) -> bool:
    return any(p.name not in RESERVADOS for p in carpeta.rglob("*.md"))


def indices(bundle: Path) -> int:
    carpetas = [bundle] + sorted(p for p in bundle.rglob("*") if p.is_dir() and _tiene_conceptos(p))
    for carpeta in carpetas:
        lineas = []
        if carpeta == bundle:
            lineas += ["---", 'okf_version: "0.2"', "---", ""]
        subs = sorted(p for p in carpeta.iterdir() if p.is_dir() and _tiene_conceptos(p))
        if subs:
            lineas.append("# Subdirectories\n")
            for s in subs:
                n = sum(1 for p in s.rglob("*.md") if p.name not in RESERVADOS)
                lineas.append(f"* [{s.name}]({s.name}/index.md) - {n} conceptos")
            lineas.append("")
        por_tipo = {}
        for p in sorted(carpeta.glob("*.md")):
            if p.name in RESERVADOS:
                continue
            tipo, titulo, desc = _resumen(p)
            por_tipo.setdefault(str(tipo), []).append(f"* [{titulo}]({p.name})" + (f" - {desc}" if desc else ""))
        for tipo, items in sorted(por_tipo.items()):
            lineas += [f"# {tipo}\n", *items, ""]
        (carpeta / "index.md").write_text("\n".join(lineas).rstrip() + "\n", encoding="utf-8")
        print(f"escrito {(carpeta / 'index.md').relative_to(bundle.parent)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("accion", choices=["validar", "indices"])
    ap.add_argument("bundle", type=Path)
    args = ap.parse_args()
    if not args.bundle.is_dir():
        sys.exit(f"no existe el directorio {args.bundle}")
    sys.exit((validar if args.accion == "validar" else indices)(args.bundle.resolve()))


if __name__ == "__main__":
    main()
