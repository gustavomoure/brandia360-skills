#!/usr/bin/env python3
"""Extrae señales de marca de un sitio web (Brandia 360 · brandia-leer-sitio).

Lee la home y hasta 5 páginas clave (servicios, nosotros, contacto...) y
devuelve en JSON: textos visibles, metadatos, colores (hex) más usados en el
HTML y CSS enlazado, tipografías, teléfonos, emails, WhatsApp, redes,
direcciones y botones/CTA. No interpreta: entrega datos para que Claude los
resuma en brandia/perfil-marca.md.

Uso:
    python3 extraer_marca.py https://ejemplo.com [--salida brandia/marca-datos.json]
Códigos de salida: 0 = ok, 2 = no se pudo acceder, 3 = faltan dependencias.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    print("Faltan dependencias: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(3)

UA = "Mozilla/5.0 (compatible; Brandia360-Brand-Reader/1.0; +https://brandia360.com)"
CLAVE = re.compile(r"(servicio|producto|tienda|shop|nosotros|about|quienes|contact|precio|tarifa|menu|carta|catalogo|planes)", re.I)
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
FONT = re.compile(r"font-family\s*:\s*([^;}{]+)", re.I)
GENERICAS = {"sans-serif", "serif", "monospace", "cursive", "system-ui", "inherit", "initial", "-apple-system",
             "blinkmacsystemfont", "segoe ui", "roboto", "helvetica neue", "arial", "helvetica", "ui-sans-serif",
             "apple color emoji", "segoe ui emoji", "segoe ui symbol", "noto color emoji", "var", "unset"}
CTA_RE = re.compile(r"(reserv|agend|compr|cotiz|contact|escrib|llam|pide|pedir|solicit|whatsapp|empez|comenz|suscrib|registr|descarg|ver |conoce|book|buy|shop)", re.I)


def norm_hex(h: str) -> str:
    h = h.lower()
    if len(h) == 4:
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def neutro(h: str) -> bool:
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b) < 18  # grises, blanco y negro


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--salida", default="brandia/marca-datos.json")
    ap.add_argument("--max-paginas", type=int, default=5)
    a = ap.parse_args()
    url = a.url if urlparse(a.url).scheme else "https://" + a.url
    s = requests.Session()
    s.headers["User-Agent"] = UA
    try:
        home = s.get(url, timeout=20)
        home.raise_for_status()
    except requests.RequestException as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(2)

    host = urlparse(home.url).netloc
    paginas, css_urls = [], []
    colores, fuentes = Counter(), Counter()
    datos = {"telefonos": set(), "emails": set(), "whatsapp": set(), "redes": set(), "direcciones": set(), "maps": set(), "ctas": Counter()}

    def procesar(resp):
        soup = BeautifulSoup(resp.text, "html.parser")
        for l in soup.find_all("link", href=True):
            rel = " ".join(l.get("rel", [])).lower()
            href = urljoin(resp.url, l["href"])
            if "stylesheet" in rel and href not in css_urls:
                css_urls.append(href)
            if "fonts.googleapis.com" in href:
                for fam in re.findall(r"family=([^&:]+)", href):
                    fuentes[fam.replace("+", " ")] += 5
        for st in soup.find_all("style"):
            analizar_css(st.get_text())
        for tag in soup.find_all(style=True):
            analizar_css(tag["style"])
        tc = soup.find("meta", attrs={"name": "theme-color"})
        if tc and tc.get("content", "").startswith("#"):
            colores[norm_hex(tc["content"])] += 20
        for el in soup.find_all(["a", "button"]):
            t = el.get_text(" ", strip=True)
            if t and len(t) <= 40 and CTA_RE.search(t):
                datos["ctas"][t] += 1
        for ael in soup.find_all("a", href=True):
            h = ael["href"]
            hl = h.lower()
            if hl.startswith("tel:"):
                datos["telefonos"].add(h[4:].strip())
            elif hl.startswith("mailto:"):
                datos["emails"].add(h[7:].split("?")[0].strip())
            elif re.search(r"wa\.me|whatsapp\.com", hl):
                datos["whatsapp"].add(h)
            elif re.search(r"(instagram|facebook|tiktok|youtube|linkedin|x|twitter|pinterest)\.com/", hl):
                datos["redes"].add(h.split("?")[0])
            elif re.search(r"google\.[a-z.]+/maps|maps\.app\.goo\.gl|g\.page", hl):
                datos["maps"].add(h)
        for ad in soup.find_all("address"):
            datos["direcciones"].add(ad.get_text(" ", strip=True)[:200])
        jsonld = []
        for sc in soup.find_all("script", type=lambda t: t and "ld+json" in t):
            try:
                jsonld.append(json.loads(sc.string or ""))
            except (json.JSONDecodeError, TypeError):
                pass
        meta = {m.get("property") or m.get("name"): m.get("content") for m in soup.find_all("meta")
                if (m.get("property") or m.get("name")) and m.get("content")}
        enlaces = [urljoin(resp.url, x["href"]) for x in soup.find_all("a", href=True)]
        for t in soup(["script", "style", "noscript", "svg"]):
            t.decompose()
        texto = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        for m in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", texto):
            datos["emails"].add(m)
        titulos = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])][:40]
        return {"url": resp.url, "title": soup.title.get_text(strip=True) if soup.title else None,
                "meta": {k: v for k, v in meta.items() if k in ("description", "og:title", "og:description", "og:site_name", "og:image", "keywords")},
                "titulos": titulos, "texto": texto[:5000], "jsonld": jsonld}, enlaces

    def analizar_css(css):
        for h in HEX.findall(css):
            colores[norm_hex(h)] += 1
        for r, g, b in RGB.findall(css):
            if max(map(int, (r, g, b))) <= 255:
                colores["#%02x%02x%02x" % (int(r), int(g), int(b))] += 1
        for f in FONT.findall(css):
            prim = f.split(",")[0].strip().strip("'\"")
            if prim and prim.lower() not in GENERICAS and not prim.lower().startswith("var("):
                fuentes[prim] += 1

    pag, enlaces = procesar(home)
    paginas.append(pag)
    candidatos = []
    for e in enlaces:
        p = urlparse(e)
        if p.netloc == host and CLAVE.search(p.path) and e.split("#")[0] not in candidatos and e.split("#")[0] != home.url:
            candidatos.append(e.split("#")[0])
    for c in candidatos[: a.max_paginas]:
        try:
            r = s.get(c, timeout=20)
            if r.ok and "html" in r.headers.get("Content-Type", ""):
                paginas.append(procesar(r)[0])
        except requests.RequestException:
            pass
    for c in css_urls[:8]:
        if any(x in c for x in ("fontawesome", "font-awesome", "bootstrap.min", "dashicons", "wp-block-library")):
            continue
        try:
            r = s.get(c, timeout=15)
            if r.ok:
                analizar_css(r.text)
        except requests.RequestException:
            pass

    marca = [(h, n) for h, n in colores.most_common(40) if not neutro(h)]
    neutros = [(h, n) for h, n in colores.most_common(40) if neutro(h)]
    res = {
        "ok": True, "url": home.url, "paginas": paginas,
        "colores_marca": [{"hex": h, "usos": n} for h, n in marca[:8]],
        "colores_neutros": [{"hex": h, "usos": n} for h, n in neutros[:4]],
        "tipografias": [{"nombre": f, "peso": n} for f, n in fuentes.most_common(5)],
        "telefonos": sorted(datos["telefonos"]), "emails": sorted(datos["emails"]),
        "whatsapp": sorted(datos["whatsapp"]), "redes": sorted(datos["redes"]),
        "maps": sorted(datos["maps"]), "direcciones": sorted(datos["direcciones"]),
        "ctas": [t for t, _ in datos["ctas"].most_common(8)],
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.salida)), exist_ok=True)
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"OK: {len(paginas)} páginas leídas. Colores: {', '.join(c['hex'] for c in res['colores_marca'][:5]) or 'ninguno detectado'}. "
          f"Tipografías: {', '.join(t['nombre'] for t in res['tipografias'][:3]) or 'no detectadas'}. CTA: {', '.join(res['ctas'][:3]) or 'no detectado'}.")
    print(f"Datos en {a.salida}")


if __name__ == "__main__":
    main()
