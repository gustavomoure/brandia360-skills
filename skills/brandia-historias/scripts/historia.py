#!/usr/bin/env python3
"""Genera historias verticales 1080x1920 (Brandia 360 · brandia-historias).

Estilos:
  dinamica   escenas cortas con una palabra grande (amarillo/blanco) sobre el
             material y cierre con CTA (por defecto "RESERVA POR DM").
  resultados antes → proceso → después (con reveal tipo cortina) y una
             cuadrícula final con CTA.

Todo se lee y escribe en ./brandia/ (o las rutas que pases). Usa ffmpeg para
el video y Pillow para las tarjetas de texto. Si existe
brandia/perfil-marca.md, toma de ahí los colores (sección "## Colores").

Ejemplos:
  python3 historia.py --estilo dinamica --guion brandia/guiones/dia-05.json
  python3 historia.py --estilo dinamica --material brandia/material --textos "HOY|CORTE|NUEVO|LOOK"
  python3 historia.py --estilo resultados --material brandia/material   # usa antes_*, proceso_*, despues_*
  python3 historia.py --demo    # crea imágenes de prueba y genera los dos estilos

Formato del guion JSON (todas las claves opcionales salvo escenas/textos):
  {"estilo": "dinamica", "cta": "RESERVA POR DM", "subcta": "@tu_negocio",
   "escenas": [{"texto": "HOY", "media": "foto1.jpg", "duracion": 1.2}, ...]}
  Para "resultados": {"antes": [...], "proceso": [...], "despues": [...],
   "titulo": "RESULTADOS REALES", "cta": "AGENDA TU CITA"}
También acepta un .txt/.md con una frase por línea (una escena por línea).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except ImportError:  # pragma: no cover
    print("Falta Pillow: pip install Pillow", file=sys.stderr)
    sys.exit(3)

W, H, FPS = 1080, 1920, 30
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"}
VID_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
AMARILLO, BLANCO, NEGRO = "#FFD60A", "#FFFFFF", "#111111"

INSTALAR_FFMPEG = """No se encontró ffmpeg. Instálalo y vuelve a ejecutar:
  macOS:          brew install ffmpeg
  Ubuntu/Debian:  sudo apt install ffmpeg
  Windows:        winget install Gyan.FFmpeg   (o choco install ffmpeg)
Luego comprueba con: ffmpeg -version"""

FUENTES = [
    "brandia/fuentes",  # el usuario puede dejar aquí su .ttf/.otf de marca
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


# ---------------------------------------------------------------- utilidades
def ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("\n".join(r.stderr.splitlines()[-15:]) + "\n")
        raise SystemExit(f"ffmpeg falló ejecutando: {' '.join(cmd[:6])} ...")
    return r


def duracion_video(path: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def es_video(p: Path) -> bool:
    return p.suffix.lower() in VID_EXT


def buscar_fuente(preferida: str | None) -> str | None:
    rutas = ([preferida] if preferida else []) + FUENTES
    for r in rutas:
        p = Path(r)
        if p.is_dir():
            for f in sorted(p.iterdir()):
                if f.suffix.lower() in (".ttf", ".otf"):
                    return str(f)
        elif p.is_file():
            return str(p)
    try:
        import matplotlib  # noqa: F401  (trae DejaVu)
        from matplotlib import font_manager
        return font_manager.findfont("DejaVu Sans:bold")
    except Exception:
        return None


def fuente(ruta: str | None, tam: int):
    if ruta:
        return ImageFont.truetype(ruta, tam)
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminancia(h: str) -> float:
    r, g, b = hex_rgb(h)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def colores_perfil(perfil: Path) -> dict:
    """Lee brandia/perfil-marca.md y devuelve {'primario','secundario','acento'}."""
    res = {}
    if not perfil.exists():
        return res
    texto = perfil.read_text(encoding="utf-8")
    m = re.search(r"^##\s*Colores.*?$(.*?)(?=^##\s|\Z)", texto, re.S | re.M | re.I)
    bloque = m.group(1) if m else texto
    for linea in bloque.splitlines():
        hx = re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", linea)
        if not hx:
            continue
        l = linea.lower()
        for clave in ("primario", "secundario", "acento"):
            if clave in l and clave not in res:
                res[clave] = hx[0]
                break
        else:
            for clave in ("primario", "secundario", "acento"):
                if clave not in res:
                    res[clave] = hx[0]
                    break
    return res


# ---------------------------------------------------------------- tarjetas Pillow
def envolver(draw, texto, fnt, ancho_max):
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if draw.textlength(prueba, font=fnt) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def texto_ajustado(draw, texto, ruta_fuente, ancho_max, alto_max, tam_max=260, tam_min=60):
    tam = tam_max
    while tam >= tam_min:
        f = fuente(ruta_fuente, tam)
        lineas = envolver(draw, texto, f, ancho_max)
        alto = len(lineas) * tam * 1.12
        if alto <= alto_max and all(draw.textlength(l, font=f) <= ancho_max for l in lineas):
            return f, lineas, tam
        tam -= 8
    f = fuente(ruta_fuente, tam_min)
    return f, envolver(draw, texto, f, ancho_max), tam_min


def tarjeta_palabra(texto, color, ruta_fuente, salida: Path, posicion="centro", etiqueta=None, color_etiqueta=None):
    """PNG transparente con la palabra grande, contorno y sombra."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # degradado oscuro para legibilidad
    grad = Image.new("L", (1, H))
    for y in range(H):
        if posicion == "centro":
            a = int(110 * (1 - abs(y - H / 2) / (H / 2)) ** 1.5)
        else:
            a = int(170 * max(0, (y - H * 0.45) / (H * 0.55)))
        grad.putpixel((0, y), a)
    img.paste(Image.new("RGBA", (W, H), (0, 0, 0, 255)), (0, 0), grad.resize((W, H)))
    d = ImageDraw.Draw(img)
    if texto:
        f, lineas, tam = texto_ajustado(d, texto.upper(), ruta_fuente, W - 140, 900)
        alto_total = int(len(lineas) * tam * 1.12)
        y0 = (H - alto_total) // 2 if posicion == "centro" else int(H * 0.68) - alto_total // 2
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dc = ImageDraw.Draw(capa)
        for i, l in enumerate(lineas):
            x = (W - d.textlength(l, font=f)) / 2
            dc.text((x + 8, y0 + i * tam * 1.12 + 10), l, font=f, fill=(0, 0, 0, 150))
        img = Image.alpha_composite(img, capa.filter(ImageFilter.GaussianBlur(10)))
        d = ImageDraw.Draw(img)
        for i, l in enumerate(lineas):
            x = (W - d.textlength(l, font=f)) / 2
            d.text((x, y0 + i * tam * 1.12), l, font=f, fill=color, stroke_width=max(4, tam // 22), stroke_fill=NEGRO)
    if etiqueta:
        pill(d, etiqueta, ruta_fuente, color_etiqueta or AMARILLO, y=150)
    img.save(salida)


def pill(d, texto, ruta_fuente, fondo, y):
    f = fuente(ruta_fuente, 64)
    tw = d.textlength(texto, font=f)
    x0, pad = (W - tw) / 2 - 44, 26
    d.rounded_rectangle([x0, y, x0 + tw + 88, y + 64 + pad * 2], radius=60, fill=fondo)
    color_txt = NEGRO if luminancia(fondo) > 140 else BLANCO
    d.text(((W - tw) / 2, y + pad - 4), texto, font=f, fill=color_txt)


def tarjeta_cta(cta, subcta, fondo, color_txt, acento, ruta_fuente, salida: Path, fondo_img: Path | None = None):
    if fondo_img:
        base = cubrir(Image.open(fondo_img).convert("RGB")).filter(ImageFilter.GaussianBlur(18))
        base = Image.blend(base, Image.new("RGB", (W, H), hex_rgb(fondo)), 0.72)
    else:
        base = Image.new("RGB", (W, H), hex_rgb(fondo))
    img = base.convert("RGBA")
    d = ImageDraw.Draw(img)
    f, lineas, tam = texto_ajustado(d, cta.upper(), ruta_fuente, W - 160, 700, tam_max=200)
    alto = int(len(lineas) * tam * 1.12)
    y0 = (H - alto) // 2 - 80
    for i, l in enumerate(lineas):
        x = (W - d.textlength(l, font=f)) / 2
        d.text((x, y0 + i * tam * 1.12), l, font=f, fill=color_txt)
    d.rectangle([W / 2 - 120, y0 + alto + 50, W / 2 + 120, y0 + alto + 66], fill=acento)
    if subcta:
        fs = fuente(ruta_fuente, 60)
        tw = d.textlength(subcta, font=fs)
        d.text(((W - tw) / 2, y0 + alto + 110), subcta, font=fs, fill=color_txt)
    img.convert("RGB").save(salida)


def cubrir(im: Image.Image) -> Image.Image:
    return ImageOps.fit(ImageOps.exif_transpose(im), (W, H), Image.LANCZOS, centering=(0.5, 0.45))


def cuadricula(medias: list[Path], cta, subcta, fondo, color_txt, acento, ruta_fuente, salida: Path, tmp: Path, titulo=None):
    img = Image.new("RGB", (W, H), hex_rgb(fondo))
    d = ImageDraw.Draw(img)
    fotos = []
    for i, m in enumerate(medias[:6]):
        if es_video(m):
            fr = tmp / f"frame_{i}.jpg"
            dur = duracion_video(m)
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, dur * 0.8):.2f}", "-i", str(m), "-frames:v", "1", str(fr)])
            fotos.append(Image.open(fr).convert("RGB"))
        else:
            fotos.append(ImageOps.exif_transpose(Image.open(m)).convert("RGB"))
    n = len(fotos)
    cols = 1 if n == 1 else 2
    filas = (n + cols - 1) // cols
    margen, sep, top = 50, 24, 260
    alto_zona = H - top - 520
    cw = (W - 2 * margen - (cols - 1) * sep) // cols
    ch = (alto_zona - (filas - 1) * sep) // filas
    for i, f in enumerate(fotos):
        r, c = divmod(i, cols)
        celda = ImageOps.fit(f, (cw, ch), Image.LANCZOS)
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw, ch], radius=28, fill=255)
        img.paste(celda, (margen + c * (cw + sep), top + r * (ch + sep)), mask)
    if titulo:
        ft, lt, _ = texto_ajustado(d, titulo.upper(), ruta_fuente, W - 2 * margen - 40, 110, tam_max=84, tam_min=40)
        tw = d.textlength(lt[0], font=ft)
        d.text(((W - tw) / 2, 120), lt[0], font=ft, fill=color_txt)
    f, lineas, tam = texto_ajustado(d, cta.upper(), ruta_fuente, W - 160, 260, tam_max=130)
    y0 = H - 470
    for i, l in enumerate(lineas):
        x = (W - d.textlength(l, font=f)) / 2
        d.text((x, y0 + i * tam * 1.12), l, font=f, fill=acento, stroke_width=3, stroke_fill=NEGRO)
    if subcta:
        fs = fuente(ruta_fuente, 56)
        tw = d.textlength(subcta, font=fs)
        d.text(((W - tw) / 2, H - 150), subcta, font=fs, fill=color_txt)
    img.save(salida)


# ---------------------------------------------------------------- clips ffmpeg
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
       "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart"]
SILENCIO = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
COVER = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"


def entrada_fondo(media: Path, dur: float, zoom=True) -> tuple[list[str], str]:
    """Devuelve (args de entrada, filtro) para el fondo, siempre 1080x1920 a 30 fps."""
    if es_video(media):
        total = duracion_video(media)
        ss = max(0.0, min(total * 0.25, total - dur)) if total > dur else 0.0
        return ["-ss", f"{ss:.2f}", "-t", f"{dur:.2f}", "-i", str(media)], f"{COVER},fps={FPS},trim=duration={dur:.2f},setpts=PTS-STARTPTS"
    frames = int(round(dur * FPS))
    if zoom:
        filtro = (f"scale={int(W*1.5)}:{int(H*1.5)}:force_original_aspect_ratio=increase,crop={int(W*1.5)}:{int(H*1.5)},"
                  f"zoompan=z='1+0.10*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1")
    else:
        filtro = f"{COVER},loop=loop={frames}:size=1:start=0,fps={FPS},trim=duration={dur:.2f}"
    return ["-i", str(media)], filtro


def clip_con_texto(media: Path, overlay: Path, dur: float, salida: Path):
    ent, filtro = entrada_fondo(media, dur)
    fc = (f"[0:v]{filtro}[bg];[1:v]format=rgba,fade=t=in:st=0:d=0.12:alpha=1,"
          f"scale=w='{W}*(1+0.06*max(0,1-t/0.25))':h=-1:eval=frame,crop={W}:{H}[tx];"
          f"[bg][tx]overlay=(W-w)/2:(H-h)/2:shortest=1[v]")
    run(["ffmpeg", "-y", "-v", "error", *ent, "-loop", "1", "-t", f"{dur:.2f}", "-i", str(overlay), *SILENCIO,
         "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-t", f"{dur:.2f}", *ENC, str(salida)])


def clip_imagen(png: Path, dur: float, salida: Path, zoom=False):
    ent, filtro = entrada_fondo(png, dur, zoom=zoom)
    run(["ffmpeg", "-y", "-v", "error", *ent, *SILENCIO, "-filter_complex", f"[0:v]{filtro},fade=t=in:st=0:d=0.25[v]",
         "-map", "[v]", "-map", "1:a", "-t", f"{dur:.2f}", *ENC, str(salida)])


def clip_reveal(antes: Path, despues: Path, overlay_antes: Path, overlay_despues: Path, dur: float, salida: Path):
    """Antes (con etiqueta) → cortina → después (con etiqueta)."""
    mitad = dur / 2
    ea, fa = entrada_fondo(antes, mitad + 0.5)
    ed, fd = entrada_fondo(despues, mitad + 0.5)
    fc = (f"[0:v]{fa}[a0];[2:v]format=rgba[oa];[a0][oa]overlay=0:0:shortest=1[a];"
          f"[1:v]{fd}[d0];[3:v]format=rgba[od];[d0][od]overlay=0:0:shortest=1[d];"
          f"[a][d]xfade=transition=wiperight:duration=0.5:offset={mitad:.2f},format=yuv420p[v]")
    run(["ffmpeg", "-y", "-v", "error", *ea, *ed,
         "-loop", "1", "-t", f"{mitad + 0.5:.2f}", "-i", str(overlay_antes),
         "-loop", "1", "-t", f"{mitad + 0.5:.2f}", "-i", str(overlay_despues), *SILENCIO,
         "-filter_complex", fc, "-map", "[v]", "-map", "4:a", "-t", f"{dur + 0.5:.2f}", *ENC, str(salida)])


def unir(clips: list[Path], salida: Path, musica: Path | None, tmp: Path):
    lista = tmp / "lista.txt"
    lista.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    salida.parent.mkdir(parents=True, exist_ok=True)
    if musica:
        unido = tmp / "unido.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(unido)])
        total = duracion_video(unido)
        run(["ffmpeg", "-y", "-v", "error", "-i", str(unido), "-stream_loop", "-1", "-i", str(musica),
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-af", f"afade=t=out:st={max(0, total - 1):.2f}:d=1", "-t", f"{total:.2f}", "-movflags", "+faststart", str(salida)])
    else:
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", "-movflags", "+faststart", str(salida)])


# ---------------------------------------------------------------- material y guion
def listar_material(carpeta: Path) -> list[Path]:
    if not carpeta.exists():
        return []
    return sorted(p for p in carpeta.iterdir() if p.suffix.lower() in IMG_EXT | VID_EXT and not p.name.startswith("."))


def leer_guion(ruta: Path) -> dict:
    if ruta.suffix.lower() == ".json":
        return json.loads(ruta.read_text(encoding="utf-8"))
    lineas = []
    for l in ruta.read_text(encoding="utf-8").splitlines():
        l = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", l).strip()
        l = re.sub(r"^(escena\s*\d+\s*[:\-–]\s*)", "", l, flags=re.I)
        if l and not l.startswith("#"):
            lineas.append(l.strip('"“”'))
    return {"escenas": [{"texto": t} for t in lineas]}


def resolver(media: str | None, carpeta: Path) -> Path | None:
    if not media:
        return None
    p = Path(media)
    for cand in (p, carpeta / media):
        if cand.exists():
            return cand
    raise SystemExit(f"No encuentro el archivo de material: {media}")


# ---------------------------------------------------------------- estilos
def estilo_dinamica(g: dict, material: list[Path], carpeta: Path, paleta: dict, fnt, tmp: Path) -> list[Path]:
    escenas = g.get("escenas") or []
    if not escenas:
        raise SystemExit("El guion no tiene escenas. Usa --textos 'PALABRA|PALABRA' o un --guion.")
    if not material and not any(e.get("media") for e in escenas):
        raise SystemExit(f"No hay fotos ni videos en {carpeta}. Copia tu material ahí o usa --demo.")
    clips = []
    for i, e in enumerate(escenas):
        media = resolver(e.get("media"), carpeta) or material[i % len(material)]
        color = paleta["texto_a"] if i % 2 == 0 else paleta["texto_b"]
        png = tmp / f"t{i:02d}.png"
        tarjeta_palabra(e.get("texto", ""), color, fnt, png)
        dur = float(e.get("duracion") or (1.6 if es_video(media) else 1.3))
        out = tmp / f"c{i:02d}.mp4"
        clip_con_texto(media, png, dur, out)
        clips.append(out)
        print(f"  escena {i + 1}/{len(escenas)}: {e.get('texto', '')!r} sobre {media.name}")
    cta_png = tmp / "cta.png"
    tarjeta_cta(g.get("cta") or "RESERVA POR DM", g.get("subcta"), paleta["fondo"], paleta["texto_cta"],
                paleta["acento"], fnt, cta_png, fondo_img=next((m for m in material if not es_video(m)), None))
    out = tmp / "c99.mp4"
    clip_imagen(cta_png, float(g.get("duracion_cta", 2.5)), out, zoom=True)
    clips.append(out)
    return clips


def clasificar(material: list[Path]) -> dict:
    grupos = {"antes": [], "proceso": [], "despues": []}
    for m in material:
        n = m.stem.lower()
        if n.startswith(("antes", "before")):
            grupos["antes"].append(m)
        elif n.startswith(("proceso", "process")):
            grupos["proceso"].append(m)
        elif n.startswith(("despues", "después", "after", "resultado")):
            grupos["despues"].append(m)
    if not grupos["antes"] or not grupos["despues"]:
        if len(material) < 2:
            raise SystemExit("El estilo 'resultados' necesita al menos 2 archivos (antes y después). "
                             "Nómbralos antes_1.jpg, proceso_1.mp4, despues_1.jpg o pásalos en el guion.")
        tercio = max(1, len(material) // 3)
        grupos = {"antes": material[:tercio], "proceso": material[tercio:-tercio] if len(material) > 2 else [],
                  "despues": material[-tercio:]}
        print("  Aviso: no encontré archivos antes_/proceso_/despues_; repartí el material en tercios por orden.")
    return grupos


def estilo_resultados(g: dict, material: list[Path], carpeta: Path, paleta: dict, fnt, tmp: Path) -> list[Path]:
    if any(k in g for k in ("antes", "proceso", "despues")):
        grupos = {k: [resolver(x, carpeta) for x in g.get(k, [])] for k in ("antes", "proceso", "despues")}
        if not grupos["antes"] or not grupos["despues"]:
            raise SystemExit("El guion de 'resultados' necesita al menos un archivo en 'antes' y otro en 'despues'.")
    else:
        grupos = clasificar(material)
    acento = paleta["acento"]
    clips, i = [], 0

    def siguiente():
        nonlocal i
        i += 1
        return tmp / f"r{i:02d}"

    # 1) gancho / título sobre el primer "antes"
    titulo = g.get("titulo") or "MIRA EL CAMBIO"
    b = siguiente()
    tarjeta_palabra(titulo, paleta["texto_a"], fnt, b.with_suffix(".png"))
    clip_con_texto(grupos["antes"][0], b.with_suffix(".png"), 1.6, b.with_suffix(".mp4"))
    clips.append(b.with_suffix(".mp4"))
    # 2) proceso
    textos_proceso = g.get("textos_proceso") or ["PROCESO"]
    for j, m in enumerate(grupos["proceso"]):
        b = siguiente()
        tarjeta_palabra(textos_proceso[j % len(textos_proceso)], paleta["texto_b"], fnt, b.with_suffix(".png"),
                        posicion="abajo", etiqueta="PROCESO", color_etiqueta=acento)
        clip_con_texto(m, b.with_suffix(".png"), 1.5 if es_video(m) else 1.2, b.with_suffix(".mp4"))
        clips.append(b.with_suffix(".mp4"))
    # 3) reveals antes → después (emparejados)
    pares = max(len(grupos["antes"]), len(grupos["despues"]))
    for j in range(pares):
        a = grupos["antes"][j % len(grupos["antes"])]
        d = grupos["despues"][j % len(grupos["despues"])]
        b = siguiente()
        oa, od = b.with_name(b.name + "_a.png"), b.with_name(b.name + "_d.png")
        tarjeta_palabra("", BLANCO, fnt, oa, posicion="abajo", etiqueta="ANTES", color_etiqueta="#FFFFFF")
        tarjeta_palabra(g.get("texto_despues", ""), paleta["texto_a"], fnt, od, posicion="abajo", etiqueta="DESPUÉS", color_etiqueta=acento)
        clip_reveal(a, d, oa, od, 2.4, b.with_suffix(".mp4"))
        clips.append(b.with_suffix(".mp4"))
    # 4) cuadrícula final con CTA
    b = siguiente()
    cuadricula(grupos["despues"] + grupos["antes"], g.get("cta") or "RESERVA POR DM", g.get("subcta"),
               paleta["fondo"], paleta["texto_cta"], acento, fnt, b.with_suffix(".png"), tmp, titulo=g.get("titulo_cuadricula") or "RESULTADOS REALES")
    clip_imagen(b.with_suffix(".png"), float(g.get("duracion_cta", 3.0)), b.with_suffix(".mp4"), zoom=True)
    clips.append(b.with_suffix(".mp4"))
    return clips


# ---------------------------------------------------------------- demo
def crear_demo(carpeta: Path, fnt) -> None:
    """Crea imágenes de prueba (gradientes con figuras) para probar sin material real."""
    carpeta.mkdir(parents=True, exist_ok=True)
    tonos = [("#1d3557", "#457b9d"), ("#6a040f", "#e85d04"), ("#283618", "#a7c957"),
             ("#3c096c", "#c77dff"), ("#003049", "#fcbf49"), ("#22223b", "#9a8c98")]
    nombres = ["foto_1", "foto_2", "foto_3", "foto_4", "antes_1", "proceso_1", "despues_1", "antes_2", "despues_2"]
    for k, nombre in enumerate(nombres):
        c1, c2 = tonos[k % len(tonos)]
        if nombre.startswith("despues"):
            c1, c2 = "#ffb703", "#fb8500"
        if nombre.startswith("antes"):
            c1, c2 = "#495057", "#adb5bd"
        img = Image.new("RGB", (1200, 1600), hex_rgb(c1))
        d = ImageDraw.Draw(img)
        r1, r2 = hex_rgb(c1), hex_rgb(c2)
        for y in range(1600):
            t = y / 1599
            d.line([(0, y), (1200, y)], fill=tuple(int(r1[i] + (r2[i] - r1[i]) * t) for i in range(3)))
        for j in range(6):
            x, y, r = 150 + (j * 197 + k * 53) % 900, 200 + (j * 331 + k * 97) % 1200, 60 + (j * 37) % 140
            d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255), width=10)
        f = fuente(fnt, 90)
        d.text((60, 1440), nombre.upper().replace("_", " "), font=f, fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0))
        img.save(carpeta / f"{nombre}.jpg", quality=90)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Historias verticales 1080x1920 de Brandia 360")
    ap.add_argument("--estilo", choices=["dinamica", "resultados"], help="estilo del video")
    ap.add_argument("--guion", help="JSON o TXT/MD con las escenas (ver docstring)")
    ap.add_argument("--textos", help="atajo: 'PALABRA|PALABRA|...' (una escena por palabra)")
    ap.add_argument("--material", default="brandia/material", help="carpeta con fotos/videos (def. brandia/material)")
    ap.add_argument("--salida", help="archivo .mp4 de salida (def. brandia/historias/<estilo>-<fecha>.mp4)")
    ap.add_argument("--perfil", default="brandia/perfil-marca.md", help="perfil de marca para los colores")
    ap.add_argument("--cta", help="texto del cierre (def. 'RESERVA POR DM')")
    ap.add_argument("--subcta", help="línea bajo el CTA, p. ej. @usuario o un teléfono")
    ap.add_argument("--musica", help="mp3/m4a opcional de fondo")
    ap.add_argument("--fuente", help="ruta a un .ttf/.otf (def. brandia/fuentes/ o una del sistema)")
    ap.add_argument("--demo", action="store_true", help="crea imágenes de prueba en brandia/demo/material y genera ambos estilos")
    a = ap.parse_args()

    if not ffmpeg_ok():
        print(INSTALAR_FFMPEG, file=sys.stderr)
        sys.exit(4)

    fnt = buscar_fuente(a.fuente)
    if not fnt:
        print("Aviso: no encontré una fuente TTF en negrita; usaré la fuente básica de Pillow. "
              "Deja tu tipografía de marca (.ttf) en brandia/fuentes/ para mejores resultados.", file=sys.stderr)

    perfil = colores_perfil(Path(a.perfil))
    primario = perfil.get("primario", NEGRO)
    acento = perfil.get("acento") or perfil.get("secundario") or AMARILLO
    paleta = {
        "texto_a": acento if luminancia(acento) > 110 else AMARILLO,  # palabra destacada
        "texto_b": BLANCO,
        "fondo": primario,
        "texto_cta": BLANCO if luminancia(primario) < 150 else NEGRO,
        "acento": acento,
    }
    if perfil:
        print(f"Colores del perfil de marca: {perfil}")

    trabajos = []
    if a.demo:
        demo = Path("brandia/demo/material")
        crear_demo(demo, fnt)
        print(f"Material de prueba creado en {demo}/")
        trabajos.append(("dinamica", {"escenas": [{"texto": t, "media": f"foto_{i % 4 + 1}.jpg"} for i, t in
                                                  enumerate(["HOY", "TU MEJOR", "VERSIÓN", "SIN ESPERAS"])],
                                      "subcta": "@tu_negocio"}, demo, Path("brandia/demo/historia-dinamica.mp4")))
        trabajos.append(("resultados", {"titulo": "MIRA EL CAMBIO", "subcta": "@tu_negocio"}, demo,
                         Path("brandia/demo/historia-resultados.mp4")))
    else:
        if a.guion:
            g = leer_guion(Path(a.guion))
        elif a.textos:
            g = {"escenas": [{"texto": t.strip()} for t in a.textos.split("|") if t.strip()]}
        else:
            g = {}
        estilo = a.estilo or g.get("estilo") or "dinamica"
        for k in ("cta", "subcta"):
            if getattr(a, k):
                g[k] = getattr(a, k)
        from datetime import date
        salida = Path(a.salida) if a.salida else Path(f"brandia/historias/{estilo}-{date.today().isoformat()}.mp4")
        trabajos.append((estilo, g, Path(a.material), salida))

    for estilo, g, carpeta, salida in trabajos:
        material = listar_material(carpeta)
        print(f"Generando '{estilo}' con {len(material)} archivo(s) de {carpeta} ...")
        with tempfile.TemporaryDirectory(prefix="brandia_") as td:
            tmp = Path(td)
            fn = estilo_dinamica if estilo == "dinamica" else estilo_resultados
            clips = fn(g, material, carpeta, paleta, fnt, tmp)
            unir(clips, salida, Path(a.musica) if a.musica else None, tmp)
        print(f"Listo: {salida} ({duracion_video(salida):.1f} s, {W}x{H})")


if __name__ == "__main__":
    main()
