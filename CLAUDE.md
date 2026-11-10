# CLAUDE.md

## Flujo de trabajo con PRs

- **Mergear siempre al terminar**: cuando el trabajo esté listo y el PR esté
  limpio (sin conflictos, CI en verde y sin comentarios de revisión
  pendientes), mergéalo a `main` sin volver a preguntar. El dueño del repo
  (gustavomoure) lo autoriza de forma duradera. Método: merge commit estándar.
- Envía siempre el enlace del PR al terminar.
- Merge a `main` publica la release con los zips (`.github/workflows/skills.yml`). Antes de mergear: `python3 scripts/validate_skills.py`.
