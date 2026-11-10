#!/usr/bin/env python3
"""Auditoría SEO de un sitio web (Brandia 360 · brandia-seo).

Rastrea la home y hasta N páginas internas (20 por defecto) y revisa SEO
técnico, on-page, datos estructurados, SEO local y rendimiento (PageSpeed
Insights si existe la variable de entorno PAGESPEED_API_KEY).

Uso:
    python3 seo_audit.py https://ejemplo.com
    python3 seo_audit.py https://ejemplo.com --max-paginas 20 --salida brandia/seo-datos.json

Salida: JSON con los resultados crudos, puntuación por categoría y lista de
problemas con prioridad (critico/alto/medio/bajo). Imprime un resumen.
Códigos de salida: 0 = ok, 2 = no se pudo acceder al sitio, 3 = faltan dependencias.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover
    print("Faltan dependencias. Instala con: pip install requests beautifulsoup4", file=sys.stderr)
    sys.exit(3)

UA = "Mozilla/5.0 (compatible; Brandia360-SEO-Audit/1.0; +https://brandia360.com)"
TIMEOUT = 15
PESO = {"critico": 25, "alto": 15, "medio": 7, "bajo": 3}
ORDEN = {"critico": 0, "alto": 1, "medio": 2, "bajo": 3}
SKIP_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg|avif|pdf|zip|rar|mp4|mp3|mov|webm|css|js|ico|xml|txt|docx?|xlsx?)$", re.I)
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}")


class Auditor:
    def __init__(self, url: str, max_paginas: int, max_enlaces: int, max_imagenes: int):
        if not urlparse(url).scheme:
            url = "https://" + url
        self.inicio = url
        self.max_paginas = max_paginas
        self.max_enlaces = max_enlaces
        self.max_imagenes = max_imagenes
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "es,en;q=0.8"})
        self.problemas: list[dict] = []
        self.paginas: list[dict] = []
        self.host = ""
        self.estado_enlaces: dict[str, int | str] = {}

    # ------------------------------------------------------------ utilidades
    def get(self, url, **kw):
        kw.setdefault("timeout", TIMEOUT)
        kw.setdefault("allow_redirects", True)
        return self.s.get(url, **kw)

    def problema(self, categoria, prioridad, problema, como_arreglar, urls=None, detalle=""):
        self.problemas.append({
            "categoria": categoria, "prioridad": prioridad, "problema": problema,
            "detalle": detalle, "como_arreglar": como_arreglar, "urls": sorted(set(urls or []))[:15],
        })

    def interno(self, url: str) -> bool:
        h = urlparse(url).netloc.lower()
        return h == self.host or h == "www." + self.host or "www." + h == self.host

    # ------------------------------------------------------------ rastreo
    def rastrear(self) -> bool:
        try:
            r = self.get(self.inicio)
        except requests.RequestException as e:
            self.error_acceso = str(e)
            return False
        self.home_resp = r
        self.home_url = r.url
        self.host = urlparse(r.url).netloc.lower()
        self.redirecciones_home = [{"url": h.url, "estado": h.status_code} for h in r.history]
        cola = deque([r.url])
        vistos = {self.normalizar(r.url)}
        primera = True
        while cola and len(self.paginas) < self.max_paginas + 1:
            url = cola.popleft()
            if primera:
                resp, primera = r, False
            else:
                try:
                    resp = self.get(url)
                except requests.RequestException as e:
                    self.paginas.append({"url": url, "error": str(e)})
                    continue
            ctype = resp.headers.get("Content-Type", "")
            if "html" not in ctype:
                continue
            pag = self.analizar_pagina(url, resp)
            self.paginas.append(pag)
            for enlace in pag["_enlaces_internos"]:
                n = self.normalizar(enlace)
                if n not in vistos and not SKIP_EXT.search(urlparse(n).path):
                    vistos.add(n)
                    cola.append(n)
        return True

    @staticmethod
    def normalizar(url: str) -> str:
        url, _ = urldefrag(url)
        p = urlparse(url)
        path = p.path or "/"
        return f"{p.scheme}://{p.netloc.lower()}{path}" + (f"?{p.query}" if p.query else "")

    def analizar_pagina(self, url: str, resp) -> dict:
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        base = resp.url

        def meta(name=None, prop=None):
            tag = soup.find("meta", attrs={"name": name}) if name else soup.find("meta", attrs={"property": prop})
            return (tag.get("content") or "").strip() if tag else None

        title = soup.title.get_text(strip=True) if soup.title else None
        canonical = None
        for l in soup.find_all("link", rel=True):
            rels = [x.lower() for x in l.get("rel", [])]
            if "canonical" in rels:
                canonical = urljoin(base, l.get("href", ""))
        hreflang = [{"lang": l.get("hreflang"), "href": l.get("href")}
                    for l in soup.find_all("link", hreflang=True)]
        encabezados = [(int(h.name[1]), h.get_text(" ", strip=True)[:120])
                       for h in soup.find_all(re.compile(r"^h[1-6]$"))]
        saltos = []
        prev = 0
        for nivel, texto in encabezados:
            if prev and nivel > prev + 1:
                saltos.append(f"H{prev} → H{nivel} ({texto[:50]})")
            prev = nivel
        imagenes = []
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src") or ""
            if not src or src.startswith("data:"):
                continue
            imagenes.append({"src": urljoin(base, src), "alt": img.get("alt"),
                             "nombre": os.path.basename(urlparse(src).path)})
        internos, externos = [], []
        tels, maps, whatsapp, sociales = set(), set(), set(), set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            low = href.lower()
            if low.startswith("tel:"):
                tels.add(re.sub(r"[^\d+]", "", href[4:]))
                continue
            if low.startswith(("mailto:", "javascript:", "#")):
                continue
            absu = urljoin(base, href)
            if not absu.startswith("http"):
                continue
            if re.search(r"(wa\.me|api\.whatsapp\.com|whatsapp\.com/send)", low):
                whatsapp.add(absu)
            if re.search(r"(google\.[a-z.]+/maps|maps\.app\.goo\.gl|goo\.gl/maps|g\.page|maps\.google|business\.google)", low):
                maps.add(absu)
            if re.search(r"(instagram|facebook|tiktok|youtube|linkedin|x\.com|twitter)\.com", low):
                sociales.add(absu)
            (internos if self.interno(absu) else externos).append(absu)
        for ifr in soup.find_all("iframe", src=True):
            if "google.com/maps" in ifr["src"]:
                maps.add(ifr["src"])

        jsonld, tipos, errores_jsonld = [], [], 0
        for s in soup.find_all("script", type=lambda t: t and "ld+json" in t.lower()):
            try:
                data = json.loads(s.string or s.get_text() or "")
            except (json.JSONDecodeError, TypeError):
                errores_jsonld += 1
                continue
            jsonld.append(data)
            tipos.extend(extraer_tipos(data))

        og = {m.get("property"): m.get("content") for m in soup.find_all("meta", property=re.compile(r"^og:"))}
        tw = {m.get("name"): m.get("content") for m in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")})}

        for t in soup(["script", "style", "noscript", "template", "svg"]):
            t.decompose()
        texto = soup.get_text(" ", strip=True)
        palabras = len(re.findall(r"\w+", texto))
        direccion = [a.get_text(" ", strip=True)[:200] for a in soup.find_all("address")]
        tels_texto = set()
        for m in PHONE_RE.findall(texto):
            digitos = re.sub(r"\D", "", m)
            if 8 <= len(digitos) <= 15:
                tels_texto.add(digitos)

        path = urlparse(resp.url).path
        return {
            "url": url, "url_final": resp.url, "estado": resp.status_code,
            "redirecciones": [h.status_code for h in resp.history],
            "https": resp.url.startswith("https://"),
            "tamano_html_kb": round(len(resp.content) / 1024, 1),
            "title": title, "title_largo": len(title) if title else 0,
            "meta_description": meta(name="description"),
            "meta_robots": meta(name="robots"), "x_robots_tag": resp.headers.get("X-Robots-Tag"),
            "viewport": meta(name="viewport"), "canonical": canonical, "hreflang": hreflang,
            "h1": [t for n, t in encabezados if n == 1], "encabezados": len(encabezados), "saltos_encabezados": saltos,
            "imagenes": len(imagenes), "imagenes_sin_alt": [i["src"] for i in imagenes if not (i["alt"] or "").strip()],
            "_imagenes": imagenes, "palabras": palabras,
            "enlaces_internos": len(internos), "enlaces_externos": len(externos),
            "_enlaces_internos": internos, "_enlaces_externos": externos,
            "url_amigable": url_amigable(path), "path": path,
            "jsonld_tipos": sorted(set(tipos)), "jsonld_errores": errores_jsonld, "_jsonld": jsonld,
            "open_graph": og, "twitter": tw,
            "telefonos_enlace": sorted(tels), "telefonos_texto": sorted(tels_texto)[:10],
            "direccion_html": direccion, "maps": sorted(maps), "whatsapp": sorted(whatsapp), "redes": sorted(sociales),
        }

    # ------------------------------------------------------------ checks globales
    def robots_y_sitemap(self) -> dict:
        res = {"robots_txt": None, "bloquea_todo": False, "sitemaps_declarados": [], "sitemap": None}
        base = f"{urlparse(self.home_url).scheme}://{self.host}"
        try:
            r = self.get(base + "/robots.txt")
            if r.status_code == 200 and "html" not in r.headers.get("Content-Type", ""):
                res["robots_txt"] = r.text[:3000]
                agente = None
                for linea in r.text.splitlines():
                    l = linea.split("#")[0].strip()
                    if l.lower().startswith("user-agent:"):
                        agente = l.split(":", 1)[1].strip()
                    elif l.lower().startswith("disallow:") and agente == "*" and l.split(":", 1)[1].strip() == "/":
                        res["bloquea_todo"] = True
                    elif l.lower().startswith("sitemap:"):
                        res["sitemaps_declarados"].append(l.split(":", 1)[1].strip())
        except requests.RequestException:
            pass
        candidatos = res["sitemaps_declarados"] + [base + "/sitemap.xml", base + "/sitemap_index.xml", base + "/wp-sitemap.xml"]
        for c in candidatos:
            try:
                r = self.get(c)
            except requests.RequestException:
                continue
            if r.status_code == 200 and ("<urlset" in r.text or "<sitemapindex" in r.text):
                res["sitemap"] = {"url": r.url, "tipo": "indice" if "<sitemapindex" in r.text else "urlset",
                                  "entradas": len(re.findall(r"<loc>", r.text))}
                break
        return res

    def comprobar_enlaces(self):
        todos = []
        for p in self.paginas:
            for u in p.get("_enlaces_internos", []) + p.get("_enlaces_externos", []):
                u = urldefrag(u)[0]
                if u not in todos:
                    todos.append(u)
        conocidos = {self.normalizar(p["url"]): p.get("estado") for p in self.paginas if "estado" in p}
        revisados = 0
        for u in todos:
            n = self.normalizar(u)
            if n in conocidos:
                self.estado_enlaces[u] = conocidos[n]
                continue
            if revisados >= self.max_enlaces:
                break
            revisados += 1
            try:
                r = self.s.head(u, timeout=10, allow_redirects=True)
                if r.status_code in (403, 405, 501) or r.status_code >= 500:
                    r = self.s.get(u, timeout=10, allow_redirects=True, stream=True)
                    r.close()
                self.estado_enlaces[u] = r.status_code
            except requests.RequestException as e:
                self.estado_enlaces[u] = f"error: {type(e).__name__}"
        rotos = {}
        for u, st in self.estado_enlaces.items():
            if isinstance(st, str) or st in (404, 410) or (isinstance(st, int) and st >= 500):
                # Redes sociales suelen bloquear bots: no las contamos como rotas.
                if re.search(r"(instagram|facebook|linkedin|tiktok|x\.com|twitter)\.com", u):
                    continue
                rotos[u] = st
        return {"revisados": len(self.estado_enlaces), "total_enlaces_unicos": len(todos), "rotos": rotos}

    def peso_imagenes(self):
        vistas, resultado = [], []
        for p in self.paginas:
            for img in p.get("_imagenes", []):
                if img["src"] not in vistas:
                    vistas.append(img["src"])
        for src in vistas[: self.max_imagenes]:
            try:
                r = self.s.head(src, timeout=10, allow_redirects=True)
                tam = r.headers.get("Content-Length")
                if not tam or r.status_code >= 400:
                    r = self.s.get(src, timeout=15)
                    tam = len(r.content) if r.status_code < 400 else None
                resultado.append({"src": src, "kb": round(int(tam) / 1024, 1) if tam else None,
                                  "estado": r.status_code, "formato": os.path.splitext(urlparse(src).path)[1].lower()})
            except requests.RequestException:
                resultado.append({"src": src, "kb": None, "estado": "error"})
        return {"total_unicas": len(vistas), "revisadas": len(resultado), "detalle": resultado}

    def pagespeed(self):
        key = os.environ.get("PAGESPEED_API_KEY", "").strip()
        if not key:
            return {"medido": False, "motivo": "No hay API key en la variable PAGESPEED_API_KEY; rendimiento no medido."}
        try:
            r = requests.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
                             params={"url": self.home_url, "strategy": "mobile", "category": "performance", "key": key},
                             timeout=120)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            return {"medido": False, "motivo": f"Error consultando PageSpeed: {e}"}
        if "error" in data:
            return {"medido": False, "motivo": data["error"].get("message", "error desconocido")}
        lh = data.get("lighthouseResult", {})
        audits = lh.get("audits", {})
        campo = data.get("loadingExperience", {}).get("metrics", {})

        def lab(k):
            a = audits.get(k, {})
            return {"valor": a.get("numericValue"), "texto": a.get("displayValue")} if a else None

        def field(k):
            m = campo.get(k)
            return {"p75": m.get("percentile"), "categoria": m.get("category")} if m else None

        score = lh.get("categories", {}).get("performance", {}).get("score")
        return {
            "medido": True, "estrategia": "mobile",
            "puntuacion": round(score * 100) if score is not None else None,
            "laboratorio": {"LCP": lab("largest-contentful-paint"), "CLS": lab("cumulative-layout-shift"),
                            "TBT": lab("total-blocking-time"), "FCP": lab("first-contentful-paint")},
            "campo_usuarios_reales": {"LCP": field("LARGEST_CONTENTFUL_PAINT_MS"), "CLS": field("CUMULATIVE_LAYOUT_SHIFT_SCORE"),
                                      "INP": field("INTERACTION_TO_NEXT_PAINT")},
            "nota_inp": None if field("INTERACTION_TO_NEXT_PAINT") else
            "INP solo existe con datos de usuarios reales (CrUX); este sitio no tiene suficientes visitas registradas.",
        }

    # ------------------------------------------------------------ evaluación
    def evaluar(self, rs, enlaces, imgs, ps):
        pags = [p for p in self.paginas if "estado" in p]
        home = pags[0]
        T, O, D, L, R = "tecnico", "on_page", "datos_estructurados", "seo_local", "rendimiento"

        # --- Técnico
        if home["estado"] >= 400:
            self.problema(T, "critico", f"La página principal responde {home['estado']}", "Revisa el servidor/hosting: la home debe responder 200.", [home["url"]])
        if not home["https"]:
            self.problema(T, "critico", "El sitio no usa HTTPS", "Instala un certificado SSL (Let's Encrypt es gratis) y redirige todo HTTP → HTTPS con 301.", [home["url_final"]])
        else:
            try:
                r = self.s.get("http://" + self.host + "/", timeout=TIMEOUT, allow_redirects=True)
                if not r.url.startswith("https://"):
                    self.problema(T, "alto", "La versión http:// no redirige a https://", "Añade una redirección 301 de http a https (en .htaccess, Nginx o el panel del hosting).", ["http://" + self.host + "/"])
            except requests.RequestException:
                pass
        if len(self.redirecciones_home) > 1:
            self.problema(T, "medio", f"Cadena de {len(self.redirecciones_home)} redirecciones para llegar a la home",
                          "Redirige en un solo salto (301) a la URL final.", [x["url"] for x in self.redirecciones_home])
        if not rs["robots_txt"]:
            self.problema(T, "medio", "No hay robots.txt", "Crea /robots.txt con 'User-agent: *', 'Allow: /' y la línea 'Sitemap: <url del sitemap>'.")
        elif rs["bloquea_todo"]:
            self.problema(T, "critico", "robots.txt bloquea todo el sitio (Disallow: /)", "Quita 'Disallow: /' del bloque 'User-agent: *'.")
        if not rs["sitemap"]:
            self.problema(T, "alto", "No se encontró sitemap.xml", "Genera un sitemap (Yoast/Rank Math en WordPress o el generador de tu plataforma), declaralo en robots.txt y envíalo en Google Search Console.")
        elif not rs["sitemaps_declarados"] and rs["robots_txt"]:
            self.problema(T, "bajo", "El sitemap no está declarado en robots.txt", f"Añade 'Sitemap: {rs['sitemap']['url']}' al final de robots.txt.")
        sin_can = [p["url_final"] for p in pags if not p["canonical"]]
        if sin_can:
            self.problema(T, "medio", f"{len(sin_can)} página(s) sin etiqueta canonical", "Añade <link rel=\"canonical\" href=\"URL-propia\"> en el <head> de cada página.", sin_can)
        noindex = [p["url_final"] for p in pags if "noindex" in ((p["meta_robots"] or "") + (p["x_robots_tag"] or "")).lower()]
        if noindex:
            prio = "critico" if home["url_final"] in noindex else "alto"
            self.problema(T, prio, f"{len(noindex)} página(s) marcadas noindex", "Si deben aparecer en Google, quita 'noindex' del meta robots / cabecera X-Robots-Tag.", noindex)
        err = [p["url_final"] for p in pags if p["estado"] >= 400]
        if err:
            self.problema(T, "alto", f"{len(err)} página(s) internas con error HTTP", "Corrige o redirige (301) esas URLs y actualiza los enlaces que apuntan a ellas.", err)
        if enlaces["rotos"]:
            self.problema(T, "alto", f"{len(enlaces['rotos'])} enlace(s) roto(s)", "Actualiza o quita los enlaces que dan 404/errores.", list(enlaces["rotos"].keys()),
                          detalle="; ".join(f"{u} → {s}" for u, s in list(enlaces["rotos"].items())[:10]))
        sin_vp = [p["url_final"] for p in pags if not p["viewport"]]
        if sin_vp:
            self.problema(T, "critico" if home["url_final"] in sin_vp else "alto", "Falta meta viewport (no es apto para móvil)",
                          "Añade <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.", sin_vp)
        pesadas = [p["url_final"] for p in pags if p["tamano_html_kb"] > 500]
        if pesadas:
            self.problema(T, "medio", "HTML muy pesado (>500 KB)", "Reduce el HTML: quita CSS/JS en línea, plugins de constructor innecesarios y contenido oculto.", pesadas)
        hl = [p for p in pags if p["hreflang"]]
        if hl:
            malos = [p["url_final"] for p in hl if not any((h["lang"] or "").lower() == "x-default" for h in p["hreflang"])]
            if malos:
                self.problema(T, "bajo", "hreflang sin x-default", "Añade <link rel=\"alternate\" hreflang=\"x-default\" href=\"...\">.", malos)
        img_pesadas = [i for i in imgs["detalle"] if i.get("kb") and i["kb"] > 200]
        if img_pesadas:
            self.problema(T, "alto" if any(i["kb"] > 1000 for i in img_pesadas) else "medio",
                          f"{len(img_pesadas)} imagen(es) de más de 200 KB",
                          "Comprímelas y conviértelas a WebP/AVIF (Squoosh, TinyPNG o un plugin como ShortPixel); usa ancho máximo ~1600 px.",
                          [i["src"] for i in img_pesadas], detalle=", ".join(f"{os.path.basename(urlparse(i['src']).path)} {i['kb']} KB" for i in img_pesadas[:10]))

        # --- On-page
        sin_title = [p["url_final"] for p in pags if not p["title"]]
        if sin_title:
            self.problema(O, "critico", f"{len(sin_title)} página(s) sin <title>", "Escribe un title único de 30–60 caracteres con la palabra clave principal y la marca.", sin_title)
        largos = [p["url_final"] for p in pags if p["title"] and not 30 <= p["title_largo"] <= 60]
        if largos:
            self.problema(O, "medio", f"{len(largos)} title(s) fuera de 30–60 caracteres", "Ajusta el largo para que Google no lo corte ni quede vacío de contexto.", largos)
        dup_t = [t for t, c in Counter(p["title"] for p in pags if p["title"]).items() if c > 1]
        if dup_t:
            self.problema(O, "alto", f"{len(dup_t)} title(s) duplicados", "Cada página necesita un title distinto que describa su contenido.",
                          [p["url_final"] for p in pags if p["title"] in dup_t], detalle=" | ".join(dup_t[:5]))
        sin_desc = [p["url_final"] for p in pags if not p["meta_description"]]
        if sin_desc:
            self.problema(O, "alto", f"{len(sin_desc)} página(s) sin meta description", "Escribe una description de 120–155 caracteres con beneficio + llamada a la acción.", sin_desc)
        desc_mal = [p["url_final"] for p in pags if p["meta_description"] and not 70 <= len(p["meta_description"]) <= 160]
        if desc_mal:
            self.problema(O, "bajo", f"{len(desc_mal)} meta description(s) muy cortas o largas", "Déjalas entre 120 y 155 caracteres.", desc_mal)
        dup_d = [d for d, c in Counter(p["meta_description"] for p in pags if p["meta_description"]).items() if c > 1]
        if dup_d:
            self.problema(O, "medio", f"{len(dup_d)} meta description(s) duplicadas", "Escribe una description propia para cada página.",
                          [p["url_final"] for p in pags if p["meta_description"] in dup_d])
        sin_h1 = [p["url_final"] for p in pags if not p["h1"]]
        if sin_h1:
            self.problema(O, "alto", f"{len(sin_h1)} página(s) sin H1", "Cada página debe tener un único H1 con el tema principal.", sin_h1)
        multi_h1 = [p["url_final"] for p in pags if len(p["h1"]) > 1]
        if multi_h1:
            self.problema(O, "medio", f"{len(multi_h1)} página(s) con más de un H1", "Deja un solo H1 y convierte los demás en H2.", multi_h1)
        saltos = [p["url_final"] for p in pags if p["saltos_encabezados"]]
        if saltos:
            self.problema(O, "bajo", "Jerarquía de encabezados con saltos (ej. H2 → H4)", "Usa los niveles en orden: H1 → H2 → H3.", saltos)
        alt = {u for p in pags for u in p["imagenes_sin_alt"]}
        if alt:
            self.problema(O, "medio", f"{len(alt)} imagen(es) sin texto alternativo (alt)", "Añade un alt descriptivo (qué se ve + contexto del negocio).", list(alt))
        finas = [p["url_final"] for p in pags if p["palabras"] < 300 and p["estado"] < 400]
        if finas:
            self.problema(O, "medio" if home["url_final"] in finas else "bajo", f"{len(finas)} página(s) con poco texto (<300 palabras)",
                          "Amplía con texto útil: qué ofreces, para quién, preguntas frecuentes, zona de servicio.", finas)
        feas = [p["url_final"] for p in pags if not p["url_amigable"]]
        if feas:
            self.problema(O, "bajo", f"{len(feas)} URL(s) poco amigables", "Usa URLs cortas, en minúsculas, con guiones y sin parámetros (ej. /servicios/corte-de-pelo).", feas)
        sin_int = [p["url_final"] for p in pags if p["enlaces_internos"] < 3]
        if sin_int:
            self.problema(O, "bajo", "Páginas con muy pocos enlaces internos", "Enlaza entre servicios, blog y contacto para repartir autoridad.", sin_int)

        # --- Datos estructurados
        tipos = {t for p in pags for t in p["jsonld_tipos"]}
        negocio = {"LocalBusiness", "Organization", "Corporation", "Store", "ProfessionalService", "Restaurant",
                   "BeautySalon", "HealthAndBeautyBusiness", "MedicalBusiness", "Dentist", "HairSalon", "DaySpa"}
        if not tipos:
            self.problema(D, "alto", "No hay datos estructurados JSON-LD", "Añade un bloque JSON-LD LocalBusiness u Organization en la home (ver bloque listo en el informe).")
        elif not tipos & negocio and not any(t.endswith("Business") for t in tipos):
            self.problema(D, "alto", "Falta JSON-LD LocalBusiness/Organization", "Añade el bloque LocalBusiness u Organization con nombre, dirección, teléfono, horario y redes.")
        if sum(p["jsonld_errores"] for p in pags):
            self.problema(D, "alto", "Bloques JSON-LD con errores de sintaxis", "Valídalos en https://validator.schema.org y corrige el JSON.",
                          [p["url_final"] for p in pags if p["jsonld_errores"]])
        if "FAQPage" not in tipos:
            self.problema(D, "bajo", "No hay FAQ marcada con datos estructurados", "Si tienes preguntas frecuentes, márcalas con FAQPage.")
        og_falt = [p["url_final"] for p in pags if not all(k in p["open_graph"] for k in ("og:title", "og:description", "og:image"))]
        if og_falt:
            self.problema(D, "medio" if home["url_final"] in og_falt else "bajo", f"{len(og_falt)} página(s) con Open Graph incompleto",
                          "Añade og:title, og:description, og:image (1200×630) y og:url para que se vea bien al compartir en WhatsApp/Facebook.", og_falt)
        tw_falt = [p["url_final"] for p in pags if "twitter:card" not in p["twitter"]]
        if tw_falt:
            self.problema(D, "bajo", f"{len(tw_falt)} página(s) sin Twitter Card", "Añade <meta name=\"twitter:card\" content=\"summary_large_image\">.", tw_falt)

        # --- SEO local
        tels_enlace = {t for p in pags for t in p["telefonos_enlace"]}
        tels_ld = set()
        dirs_ld = []
        nombres = set()
        for p in pags:
            for bloque in p["_jsonld"]:
                for nodo in iterar_nodos(bloque):
                    if isinstance(nodo.get("telephone"), str):
                        tels_ld.add(re.sub(r"[^\d+]", "", nodo["telephone"]))
                    if nodo.get("address"):
                        dirs_ld.append(nodo["address"])
                    if isinstance(nodo.get("name"), str) and any(t in negocio or str(t).endswith("Business") for t in as_list(nodo.get("@type"))):
                        nombres.add(nodo["name"].strip())
        if home["open_graph"].get("og:site_name"):
            nombres.add(home["open_graph"]["og:site_name"].strip())
        dirs_html = {d for p in pags for d in p["direccion_html"]}
        if not tels_enlace and not tels_ld:
            self.problema(L, "alto", "No se encontró un teléfono clicable (tel:)", "Muestra el teléfono en cabecera/pie con <a href=\"tel:+...\">.")
        digitos = {re.sub(r"\D", "", t)[-9:] for t in tels_enlace | tels_ld if len(re.sub(r"\D", "", t)) >= 8}
        if len(digitos) > 1:
            self.problema(L, "medio", "Teléfonos distintos en el sitio", "Usa el mismo número (mismo formato) en web, JSON-LD y Perfil de Empresa de Google.",
                          detalle=", ".join(sorted(tels_enlace | tels_ld)))
        if not dirs_ld and not dirs_html:
            self.problema(L, "medio", "No se detectó una dirección visible ni en datos estructurados",
                          "Si atiendes en un local, muestra la dirección completa en el pie y en JSON-LD (si es servicio a domicilio, indica la zona).")
        if len(nombres) > 1:
            self.problema(L, "bajo", "El nombre del negocio aparece escrito de varias formas", "Unifica el nombre en web, JSON-LD, redes y Google.", detalle=", ".join(sorted(nombres)))
        if not any(p["maps"] for p in pags):
            self.problema(L, "medio", "No hay enlace a Google Maps / Perfil de Empresa", "Enlaza tu ficha de Google (o inserta el mapa) en la página de contacto.")
        if not any(p["whatsapp"] for p in pags):
            self.problema(L, "medio", "No hay botón/enlace de WhatsApp", "Añade un enlace https://wa.me/<número> con un mensaje predefinido.")

        # --- Rendimiento
        if ps.get("medido"):
            sc = ps.get("puntuacion")
            if sc is not None and sc < 50:
                self.problema(R, "alto", f"Rendimiento móvil bajo ({sc}/100)", "Optimiza imágenes, difiere JS, usa caché y un hosting/CDN más rápido.", [self.home_url])
            elif sc is not None and sc < 90:
                self.problema(R, "medio", f"Rendimiento móvil mejorable ({sc}/100)", "Revisa las oportunidades de PageSpeed Insights: imágenes, JS no usado, fuentes.", [self.home_url])
            lcp = (ps["laboratorio"].get("LCP") or {}).get("valor")
            if lcp and lcp > 2500:
                self.problema(R, "alto" if lcp > 4000 else "medio", f"LCP de {lcp/1000:.1f} s (meta < 2,5 s)", "Optimiza y precarga la imagen principal; evita sliders pesados arriba.")
            cls = (ps["laboratorio"].get("CLS") or {}).get("valor")
            if cls and cls > 0.1:
                self.problema(R, "medio", f"CLS de {cls:.2f} (meta < 0,1)", "Define width/height en imágenes y reserva espacio para banners.")
            inp = (ps["campo_usuarios_reales"].get("INP") or {}).get("p75")
            if inp and inp > 200:
                self.problema(R, "medio", f"INP de {inp} ms (meta < 200 ms)", "Reduce JS de terceros (chats, píxeles) y tareas largas.")

        return self.puntuar(ps)

    def puntuar(self, ps):
        cats = ["tecnico", "on_page", "datos_estructurados", "seo_local", "rendimiento"]
        out = {}
        for c in cats:
            if c == "rendimiento":
                out[c] = ps.get("puntuacion") if ps.get("medido") else None
                continue
            pen = sum(PESO[p["prioridad"]] for p in self.problemas if p["categoria"] == c)
            out[c] = max(0, 100 - pen)
        medidas = [v for v in out.values() if v is not None]
        out["global"] = round(sum(medidas) / len(medidas)) if medidas else None
        return out

    def ejecutar(self) -> dict:
        t0 = time.time()
        if not self.rastrear():
            return {"ok": False, "url": self.inicio, "error": f"No se pudo acceder al sitio: {self.error_acceso}"}
        rs = self.robots_y_sitemap()
        enlaces = self.comprobar_enlaces()
        imgs = self.peso_imagenes()
        ps = self.pagespeed()
        puntos = self.evaluar(rs, enlaces, imgs, ps)
        self.problemas.sort(key=lambda p: (ORDEN[p["prioridad"]], p["categoria"]))
        paginas = [{k: v for k, v in p.items() if not k.startswith("_")} for p in self.paginas]
        jsonld = []
        for p in self.paginas:
            for b in p.get("_jsonld", []):
                if b not in jsonld:
                    jsonld.append(b)
        return {
            "ok": True, "url": self.inicio, "url_final": self.home_url,
            "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duracion_s": round(time.time() - t0, 1),
            "paginas_rastreadas": len(paginas), "puntuacion": puntos,
            "resumen_problemas": dict(Counter(p["prioridad"] for p in self.problemas)),
            "problemas": self.problemas,
            "robots_sitemap": rs, "redirecciones_home": self.redirecciones_home,
            "enlaces": enlaces, "imagenes": imgs, "pagespeed": ps,
            "jsonld_encontrado": jsonld[:10], "paginas": paginas,
        }


def as_list(x):
    return x if isinstance(x, list) else [x] if x else []


def iterar_nodos(data):
    if isinstance(data, dict):
        yield data
        for v in data.values():
            yield from iterar_nodos(v)
    elif isinstance(data, list):
        for v in data:
            yield from iterar_nodos(v)


def extraer_tipos(data):
    return [str(t) for n in iterar_nodos(data) for t in as_list(n.get("@type"))]


def url_amigable(path: str) -> bool:
    if path in ("", "/"):
        return True
    if len(path) > 100 or "_" in path or re.search(r"[A-Z]", path):
        return False
    if re.search(r"(\?|\.php|\.aspx?|/\d{5,}|[%=&])", path):
        return False
    return True


def resumen_texto(res: dict) -> str:
    if not res.get("ok"):
        return res.get("error", "error")
    p = res["puntuacion"]
    lin = [f"Auditoría SEO: {res['url_final']} ({res['paginas_rastreadas']} páginas, {res['duracion_s']} s)",
           "Puntuación: " + ", ".join(f"{k}={'no medido' if v is None else v}" for k, v in p.items()),
           "Problemas: " + ", ".join(f"{k}={v}" for k, v in res["resumen_problemas"].items())]
    if not res["pagespeed"].get("medido"):
        lin.append("Rendimiento: " + res["pagespeed"]["motivo"])
    for pr in res["problemas"][:12]:
        lin.append(f"  [{pr['prioridad']}] ({pr['categoria']}) {pr['problema']}")
    return "\n".join(lin)


def main():
    ap = argparse.ArgumentParser(description="Auditoría SEO de Brandia 360")
    ap.add_argument("url")
    ap.add_argument("--max-paginas", type=int, default=20, help="páginas internas además de la home (def. 20)")
    ap.add_argument("--max-enlaces", type=int, default=150, help="enlaces a comprobar (def. 150)")
    ap.add_argument("--max-imagenes", type=int, default=60, help="imágenes a pesar (def. 60)")
    ap.add_argument("--salida", default="brandia/seo-datos.json")
    args = ap.parse_args()

    res = Auditor(args.url, args.max_paginas, args.max_enlaces, args.max_imagenes).ejecutar()
    os.makedirs(os.path.dirname(os.path.abspath(args.salida)), exist_ok=True)
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(resumen_texto(res))
    print(f"\nDatos guardados en {args.salida}")
    sys.exit(0 if res.get("ok") else 2)


if __name__ == "__main__":
    main()
