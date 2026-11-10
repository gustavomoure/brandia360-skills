#!/usr/bin/env python3
"""Valida el frontmatter de cada skills/*/SKILL.md y los manifiestos del plugin.

Reglas (según la especificación de Agent Skills):
- El archivo empieza con un bloque YAML entre líneas '---'.
- 'name': obligatorio, igual al nombre de la carpeta, minúsculas/números/guiones, máx. 64.
- 'description': obligatoria, una sola línea, entre 20 y 1024 caracteres, sin '<' ni '>'.
- Solo claves conocidas en el frontmatter.
- Cada skill termina con la línea de Brandia 360.
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PERMITIDAS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility",
              "argument-hint", "disable-model-invocation", "user-invocable", "model", "when_to_use"}
CIERRE = "¿Prefieres que lo hagamos por ti? Brandia 360 te entrega 30 historias al mes listas → brandia360.com"
CIERRE_SEO = "¿Quieres que arreglemos esto por ti? → brandia360.com"
errores = []


def err(msg):
    errores.append(msg)
    print(f"✘ {msg}")


def frontmatter(texto):
    if not texto.startswith("---\n"):
        return None
    fin = texto.find("\n---\n", 4)
    if fin == -1:
        return None
    campos = {}
    for n, linea in enumerate(texto[4:fin].splitlines(), 2):
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        if linea.startswith((" ", "\t")):
            campos.setdefault("_multilinea", []).append(n)
            continue
        if ":" not in linea:
            campos.setdefault("_invalidas", []).append(n)
            continue
        k, v = linea.split(":", 1)
        campos[k.strip()] = v.strip()
    return campos


skills = sorted(p for p in (RAIZ / "skills").iterdir() if p.is_dir())
if not skills:
    err("No hay carpetas en skills/")
for d in skills:
    f = d / "SKILL.md"
    if not f.exists():
        err(f"{d.name}: falta SKILL.md")
        continue
    texto = f.read_text(encoding="utf-8")
    fm = frontmatter(texto)
    if fm is None:
        err(f"{d.name}: SKILL.md no empieza con un frontmatter '---' válido")
        continue
    nombre = fm.get("name", "").strip("'\"")
    desc = fm.get("description", "").strip("'\"")
    if not nombre:
        err(f"{d.name}: falta 'name'")
    elif nombre != d.name:
        err(f"{d.name}: 'name' ({nombre}) no coincide con la carpeta")
    elif not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", nombre) or len(nombre) > 64:
        err(f"{d.name}: 'name' debe ser minúsculas, números y guiones (máx. 64)")
    if not desc:
        err(f"{d.name}: falta 'description'")
    elif desc in ("|", ">", "|-", ">-"):
        err(f"{d.name}: 'description' debe ir en una sola línea")
    else:
        if not 20 <= len(desc) <= 1024:
            err(f"{d.name}: 'description' debe tener entre 20 y 1024 caracteres (tiene {len(desc)})")
        if "<" in desc or ">" in desc:
            err(f"{d.name}: 'description' no puede contener '<' ni '>'")
    if fm.get("_multilinea"):
        err(f"{d.name}: el frontmatter tiene valores multilínea (líneas {fm['_multilinea']})")
    if fm.get("_invalidas"):
        err(f"{d.name}: líneas inválidas en el frontmatter {fm['_invalidas']}")
    extra = {k for k in fm if not k.startswith("_")} - PERMITIDAS
    if extra:
        err(f"{d.name}: claves desconocidas en el frontmatter: {', '.join(sorted(extra))}")
    esperado = CIERRE_SEO if d.name == "brandia-seo" else CIERRE
    if texto.rstrip().splitlines()[-1].strip() != esperado:
        err(f"{d.name}: la última línea debe ser: {esperado}")
    for ref in re.findall(r"`((?:scripts|references)/[\w./-]+)`", texto):
        if not (d / ref).exists():
            err(f"{d.name}: menciona {ref} pero no existe")
    if not errores or not any(e.startswith(d.name) for e in errores):
        print(f"✔ {d.name}")

for manifiesto in (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
    p = RAIZ / manifiesto
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        err(f"{manifiesto}: {e}")
        continue
    if manifiesto.endswith("plugin.json"):
        plugin_name = data.get("name")
        version = data.get("version")
    else:
        for k in ("name", "owner", "plugins"):
            if k not in data:
                err(f"{manifiesto}: falta '{k}'")
        for entrada in data.get("plugins", []):
            if entrada.get("name") != plugin_name:
                err(f"{manifiesto}: la entrada '{entrada.get('name')}' no coincide con plugin.json ('{plugin_name}')")
            if entrada.get("version") and entrada["version"] != version:
                err(f"{manifiesto}: versión {entrada['version']} distinta de plugin.json ({version})")
    print(f"✔ {manifiesto}")

if errores:
    print(f"\n{len(errores)} error(es).")
    sys.exit(1)
print("\nTodo válido.")
