# Brandia 360 Skills

Skills gratis para Claude, en español, para crear **tú mismo** el contenido mensual
de tu negocio: perfil de marca, auditoría SEO, investigación de nicho, ganchos y
guiones, calendario de 30 historias y videos verticales listos para Instagram,
WhatsApp y TikTok.

## ¿Qué es Brandia 360?

[Brandia 360](https://brandia360.com) prepara cada mes el contenido de tu negocio,
pensado para tu nicho: **30 historias para Instagram/WhatsApp/TikTok, shorts, frases
y plantillas**, con tu logo, tus colores y tus datos, por **$100 al mes**.

Estas skills son la versión "hazlo tú mismo": el mismo método, para que lo apliques
con Claude. Si un día prefieres no hacerlo tú, escríbenos a
[soporte@brandia360.com](mailto:soporte@brandia360.com).

## Skills incluidas

| Skill | Qué hace | Guarda |
|---|---|---|
| `brandia-leer-sitio` | Lee tu web y/o Instagram y saca negocio, servicios, cliente ideal, propuesta de valor, tono, colores, tipografías, ciudad y CTA | `brandia/perfil-marca.md` |
| `brandia-seo` | Audita el SEO de tu web (técnico, on-page, datos estructurados, local y rendimiento), propone 15 palabras clave y te da textos listos para pegar | `brandia/seo-informe.md`, `brandia/seo-datos.json` |
| `brandia-investigar-nicho` | Investiga competidores y referentes, qué temas, formatos, ganchos y CTAs funcionan, y propone 10 ideas con fuentes | `brandia/nicho.md` |
| `brandia-ganchos-guiones` | 20 ganchos de 3 segundos y guiones por escenas, con checklist y pasada anti-IA | `brandia/ganchos.md`, `brandia/guiones/*.json` |
| `brandia-calendario` | Calendario de 30 historias del mes (40% valor, 30% prueba social, 20% oferta, 10% personal) | `brandia/calendario-AAAA-MM.md` y `.csv` |
| `brandia-historias` | Videos verticales 1080×1920 con tus fotos y videos, estilos "dinámica" y "resultados" | `brandia/historias/*.mp4` |

Todas leen y escriben en la carpeta `./brandia/` del proyecto donde trabajes.

## Instalación

### En Claude Code (plugin)

```bash
/plugin marketplace add gustavomoure/brandia360-skills
/plugin install brandia360@brandia360-skills
```

O desde la terminal:

```bash
claude plugin marketplace add gustavomoure/brandia360-skills
claude plugin install brandia360@brandia360-skills
```

Las skills quedan disponibles como `/brandia360:brandia-leer-sitio`,
`/brandia360:brandia-seo`, etc. También se activan solas cuando pides algo que
encaja con su descripción ("audita el SEO de mi web", "arma mi calendario de
diciembre"…).

Dependencias para los scripts (Python 3.9+):

```bash
pip install -r requirements.txt
```

Y para los videos, **ffmpeg**: `brew install ffmpeg` (macOS), `sudo apt install ffmpeg`
(Ubuntu/Debian) o `winget install Gyan.FFmpeg` (Windows).

Para medir el rendimiento en la auditoría SEO (opcional), crea una API key gratis de
PageSpeed Insights en Google Cloud y expórtala:

```bash
export PAGESPEED_API_KEY=tu_clave
```

### En claude.ai (subir zip)

1. Descarga el `.zip` de cada skill desde la página de
   [Releases](https://github.com/gustavomoure/brandia360-skills/releases)
   (o genéralos tú con `./scripts/build-zips.sh`, quedan en `dist/`).
2. En claude.ai ve a **Configuración → Capacidades** y activa la **ejecución de código
   y creación de archivos**.
3. En la sección **Skills**, pulsa **Subir skill** y elige el `.zip`. Repite con cada skill.
4. Abre un chat y pide, por ejemplo: "Lee mi web https://minegocio.com y crea mi perfil de marca".

En claude.ai los archivos se entregan para descargar; adjunta `perfil-marca.md` en
los chats siguientes para que las demás skills lo usen. Si el entorno de código no
tiene acceso a internet, `brandia-seo` y `brandia-leer-sitio` hacen el análisis con
lectura web en lugar del script.

## Flujo recomendado

```
leer sitio → SEO → investigar nicho → ganchos → calendario → historias
```

1. **Leer sitio**: crea el perfil de marca que usan todas las demás.
2. **SEO**: arregla lo que impide que te encuentren y obtén tus palabras clave.
3. **Investigar nicho**: qué funciona en tu rubro (cruzado con tus palabras clave).
4. **Ganchos**: los primeros 3 segundos de cada historia.
5. **Calendario**: las 30 historias del mes, con fecha, texto y CTA.
6. **Historias**: los videos, uno por día del calendario.

## Ejemplos de uso

**brandia-leer-sitio**
> Lee https://peluquerialuna.com y @peluquerialuna y crea mi perfil de marca.

**brandia-seo**
> Haz una auditoría SEO de mi web.  *(usa la web del perfil de marca)*

Directamente con el script:

```bash
python3 skills/brandia-seo/scripts/seo_audit.py https://brandia360.com --salida brandia/seo-datos.json
```

**brandia-investigar-nicho**
> Investiga qué publican las peluquerías de Valencia y los referentes del nicho, y dame 10 ideas.

**brandia-ganchos-guiones**
> Dame 20 ganchos y 5 guiones para promocionar el alisado de keratina.

**brandia-calendario**
> Arma mi calendario de historias de diciembre 2026. El 15 tenemos 20% en cortes.

Script de apoyo:

```bash
python3 skills/brandia-calendario/scripts/calendario.py esqueleto 2026-12
python3 skills/brandia-calendario/scripts/calendario.py exportar brandia/calendario-2026-12.json
```

**brandia-historias**
> Con las fotos de brandia/material haz la historia del día 5 en estilo dinámica.

```bash
# Prueba rápida con imágenes de ejemplo generadas por el script
python3 skills/brandia-historias/scripts/historia.py --demo

# Con tu material y un guion
python3 skills/brandia-historias/scripts/historia.py --guion brandia/guiones/guion-01.json

# Atajo sin guion
python3 skills/brandia-historias/scripts/historia.py --estilo dinamica --textos "HOY|CORTE|NUEVO|LOOK" --subcta "@minegocio"

# Antes / después (nombra los archivos antes_1.jpg, proceso_1.mp4, despues_1.jpg)
python3 skills/brandia-historias/scripts/historia.py --estilo resultados --cta "AGENDA TU CITA"
```

## Estructura

```
.claude-plugin/
  marketplace.json      # catálogo para /plugin marketplace add
  plugin.json           # manifiesto del plugin "brandia360"
skills/
  brandia-leer-sitio/   SKILL.md · scripts/extraer_marca.py
  brandia-seo/          SKILL.md · scripts/seo_audit.py · references/
  brandia-investigar-nicho/ SKILL.md
  brandia-ganchos-guiones/  SKILL.md · references/
  brandia-calendario/   SKILL.md · scripts/calendario.py
  brandia-historias/    SKILL.md · scripts/historia.py
scripts/
  build-zips.sh         # un .zip por skill en dist/
  validate_skills.py    # valida frontmatter y manifiestos (lo usa la GitHub Action)
requirements.txt
```

## Desarrollo

```bash
python3 scripts/validate_skills.py   # valida todas las skills
./scripts/build-zips.sh              # genera dist/*.zip
claude plugin validate .             # valida el plugin y el marketplace
```

La GitHub Action (`.github/workflows/skills.yml`) valida cada `SKILL.md` en cada push
y PR, y al llegar a `main` (o al crear un tag `v*`) publica los zips en una release con
la versión de `plugin.json`. Para sacar una versión nueva, sube `version` en
`.claude-plugin/plugin.json` y en `.claude-plugin/marketplace.json`.

## Licencia

[MIT](LICENSE) © Brandia 360

---

¿Prefieres que lo hagamos por ti? Brandia 360 te entrega 30 historias al mes listas → [brandia360.com](https://brandia360.com)
