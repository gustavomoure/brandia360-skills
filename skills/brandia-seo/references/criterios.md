# Criterios de la auditoría SEO (brandia-seo)

## Prioridades

| Prioridad | Significado | Penalización |
|---|---|---|
| Crítico | Impide que Google indexe o que el sitio funcione (noindex en home, robots bloquea todo, sin HTTPS, sin title, sin viewport en home, home con error) | 25 |
| Alto | Pierde posiciones o clics de forma clara (sin sitemap, sin meta description, sin H1, titles duplicados, enlaces rotos, sin JSON-LD de negocio, imágenes >1 MB, sin teléfono clicable) | 15 |
| Medio | Mejora notable con poco esfuerzo (canonical, Open Graph, alt, H1 múltiples, sin WhatsApp/Maps, sin dirección, imágenes >200 KB) | 7 |
| Bajo | Pulido (Twitter Card, FAQ schema, URLs poco amigables, jerarquía de encabezados, pocos enlaces internos) | 3 |

Cada categoría parte de 100 y resta la penalización de sus problemas (mínimo 0).
Un mismo problema se cuenta una vez aunque afecte a varias URLs (se listan todas).

## Umbrales

- Title: 30–60 caracteres, único por página.
- Meta description: 120–155 caracteres recomendado (se marca si <70 o >160), única.
- Un H1 por página; niveles sin saltos (H1 → H2 → H3).
- Contenido: aviso si una página tiene menos de 300 palabras.
- HTML: aviso si pesa más de 500 KB.
- Imágenes: aviso >200 KB; alto si alguna supera 1 MB.
- URL amigable: minúsculas, con guiones, sin `_`, sin parámetros, sin `.php`, ≤100 caracteres.
- Core Web Vitals (móvil): LCP < 2,5 s, CLS < 0,1, INP < 200 ms.

## Qué no se puede medir sin herramientas extra

- Volumen de búsquedas y dificultad de palabras clave (requiere Search Console,
  Google Ads Keyword Planner u otra herramienta). No se inventan.
- Posiciones actuales en Google y backlinks.
- INP: solo existe con datos de usuarios reales (CrUX); sitios con poco tráfico no lo tienen.
- Rendimiento sin `PAGESPEED_API_KEY`.

## SEO local (NAP)

NAP = Name, Address, Phone. Debe ser idéntico en la web, el JSON-LD, el Perfil de
Empresa de Google, Instagram y directorios. El script compara teléfonos `tel:` y del
JSON-LD (últimos 9 dígitos) y los nombres declarados en JSON-LD/`og:site_name`.
