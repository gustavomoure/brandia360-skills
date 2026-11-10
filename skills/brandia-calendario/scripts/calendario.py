#!/usr/bin/env python3
"""Calendario de 30 historias (Brandia 360 · brandia-calendario).

Dos modos:
  esqueleto  Reparte 30 fechas del mes con el pilar sugerido
             (40% valor, 30% prueba social, 20% oferta, 10% personal/marca)
             intercalados para que no se repitan seguidos.
               python3 calendario.py esqueleto 2026-12 [--inicio 1] [--sin-domingos]
  exportar   Toma un JSON con las 30 historias y escribe
             brandia/calendario-AAAA-MM.md y .csv, validando campos y mezcla.
               python3 calendario.py exportar brandia/calendario-2026-12.json

Campos de cada historia en el JSON: fecha (AAAA-MM-DD), pilar, objetivo,
formato, texto_pantalla, caption, cta. Opcional: notas.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

PILARES = {"valor": 12, "prueba social": 9, "oferta": 6, "personal/marca": 3}
CAMPOS = ["fecha", "pilar", "objetivo", "formato", "texto_pantalla", "caption", "cta"]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def secuencia_pilares() -> list[str]:
    """30 pilares intercalados: nunca el mismo dos días seguidos y las ofertas espaciadas."""
    restantes = dict(PILARES)
    seq: list[str] = []
    for i in range(30):
        candidatos = sorted(restantes, key=lambda p: (-restantes[p] / PILARES[p], list(PILARES).index(p)))
        for p in candidatos:
            if restantes[p] and (not seq or seq[-1] != p) and not (p == "oferta" and "oferta" in seq[-2:]):
                break
        else:
            p = next(x for x in candidatos if restantes[x])
        seq.append(p)
        restantes[p] -= 1
    return seq


def fechas(mes: str, inicio: int, sin_domingos: bool) -> list[date]:
    a, m = map(int, mes.split("-"))
    d = date(a, m, max(1, min(inicio, calendar.monthrange(a, m)[1])))
    out = []
    while len(out) < 30:
        if not (sin_domingos and d.weekday() == 6):
            out.append(d)
        d += timedelta(days=1)
    return out


def cmd_esqueleto(a):
    seq = secuencia_pilares()
    filas = [{"fecha": f.isoformat(), "dia": DIAS[f.weekday()], "pilar": p} for f, p in zip(fechas(a.mes, a.inicio, a.sin_domingos), seq)]
    print(json.dumps(filas, ensure_ascii=False, indent=2))
    print(f"\nMezcla: {dict(Counter(seq))}", file=sys.stderr)


def esc(t: str) -> str:
    return str(t).replace("|", "\\|").replace("\n", "<br>")


def cmd_exportar(a):
    ruta = Path(a.json)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    historias = datos["historias"] if isinstance(datos, dict) else datos
    errores = []
    if len(historias) != 30:
        errores.append(f"Hay {len(historias)} historias; deben ser 30.")
    for i, h in enumerate(historias, 1):
        falt = [c for c in CAMPOS if not str(h.get(c, "")).strip()]
        if falt:
            errores.append(f"Historia {i}: faltan {', '.join(falt)}")
        try:
            date.fromisoformat(h.get("fecha", ""))
        except ValueError:
            errores.append(f"Historia {i}: fecha inválida {h.get('fecha')!r} (usa AAAA-MM-DD)")
    if errores:
        print("No se exportó. Corrige:\n- " + "\n- ".join(errores), file=sys.stderr)
        sys.exit(1)
    historias.sort(key=lambda h: h["fecha"])
    mes = a.mes or historias[0]["fecha"][:7]
    meta = datos if isinstance(datos, dict) else {}
    mezcla = Counter(h["pilar"].strip().lower() for h in historias)
    salida = Path(a.carpeta)
    salida.mkdir(parents=True, exist_ok=True)

    with open(salida / f"calendario-{mes}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["#", "Fecha", "Día", "Pilar", "Objetivo", "Formato", "Texto en pantalla", "Caption", "CTA", "Notas"])
        for i, h in enumerate(historias, 1):
            d = date.fromisoformat(h["fecha"])
            w.writerow([i, h["fecha"], DIAS[d.weekday()], h["pilar"], h["objetivo"], h["formato"],
                        h["texto_pantalla"], h["caption"], h["cta"], h.get("notas", "")])

    lin = [f"# Calendario de historias — {meta.get('marca', '')} {mes}".replace("—  ", "— "), ""]
    if meta.get("objetivo_mes"):
        lin += [f"**Objetivo del mes:** {meta['objetivo_mes']}", ""]
    lin += ["## Mezcla de contenido", "", "| Pilar | Historias | % | Sugerido |", "|---|---|---|---|"]
    for p, n in PILARES.items():
        lin.append(f"| {p} | {mezcla.get(p, 0)} | {round(mezcla.get(p, 0) / 30 * 100)}% | {round(n / 30 * 100)}% |")
    otros = {k: v for k, v in mezcla.items() if k not in PILARES}
    for p, n in otros.items():
        lin.append(f"| {p} | {n} | {round(n / 30 * 100)}% | — |")
    lin += ["", "## Historias", "", "| # | Fecha | Pilar | Objetivo | Formato | Texto en pantalla | Caption | CTA |",
            "|---|---|---|---|---|---|---|---|"]
    for i, h in enumerate(historias, 1):
        d = date.fromisoformat(h["fecha"])
        lin.append(f"| {i} | {DIAS[d.weekday()]} {d.day:02d}/{d.month:02d} | {esc(h['pilar'])} | {esc(h['objetivo'])} | "
                   f"{esc(h['formato'])} | {esc(h['texto_pantalla'])} | {esc(h['caption'])} | {esc(h['cta'])} |")
    if meta.get("notas"):
        lin += ["", "## Notas", "", meta["notas"]]
    (salida / f"calendario-{mes}.md").write_text("\n".join(lin) + "\n", encoding="utf-8")

    print(f"Exportado: {salida}/calendario-{mes}.md y .csv")
    desvio = {p: mezcla.get(p, 0) - n for p, n in PILARES.items() if abs(mezcla.get(p, 0) - n) > 2}
    if desvio:
        print(f"Aviso: la mezcla se aleja de la sugerida (diferencia en historias): {desvio}")


def main():
    ap = argparse.ArgumentParser(description="Calendario de 30 historias de Brandia 360")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("esqueleto")
    e.add_argument("mes", help="AAAA-MM")
    e.add_argument("--inicio", type=int, default=1, help="día del mes en que empieza (def. 1)")
    e.add_argument("--sin-domingos", action="store_true")
    e.set_defaults(fn=cmd_esqueleto)
    x = sub.add_parser("exportar")
    x.add_argument("json")
    x.add_argument("--mes", help="AAAA-MM (def. el de la primera fecha)")
    x.add_argument("--carpeta", default="brandia")
    x.set_defaults(fn=cmd_exportar)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
