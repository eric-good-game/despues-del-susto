# Estado de implementación — Matching (Después del Susto)

_Última actualización: 2026-11-11. Documento de trabajo: qué está implementado, estado de los
datos y pendientes. No es una decisión de arquitectura (ver `decisions/0013`)._

## Resumen

El enriquecimiento pasó de un matching simple (búsqueda en un solo idioma, umbral 0.85) a un
sistema **multi-estrategia con procedencia**: busca varios títulos en ambos idiomas, elige entre
candidatos empatados con una cascada de reglas y registra *de dónde* salió cada match.

## Qué está implementado (en código, migraciones aplicadas)

**Búsqueda (`services/matching_enhanced.py`)**
- Busca **todos** los títulos extraídos como queries etiquetadas, en orden literal:
  `mentioned` > `corrected` > `probable` > `alternate`.
- Bilingüe (`es-MX` + `en-US`) para TMDB (movie y tv); IGDB para juegos.
- Variantes locales por query: eliminación de artículos, números finales, diccionario de
  traducciones conocidas. Sin fragmentos de palabras (creaban falsos empates).
- **Búsqueda sin filtro de año/país**: un año aproximado no debe descartar la obra correcta.

**Decisión (`services/matching.py`)**
- Puntuación = mejor similitud sobre las queries etiquetadas y sus variantes; el **origen**
  (`from_*`) es la etiqueta más literal que lo logra.
- Cascada de desempate (candidatos a ≤ 0.05): **tipo → género → era → país → año → popularidad**,
  con notas: `resolved_by_type|genre|era|country|year|hint_year|popularity`, y banderas
  `era_group`, `same_title_other_type`, `type_substituted`, `shorts_yielded`, `only_short`.
- Guards:
  - `low_confidence` va a revisión **salvo** match literal (`mentioned`/`corrected`/`alternate`)
    o que la `disambiguation` resuelva la versión.
  - `uncertain_title` solo para match **probable-only** con confianza < high y parecido < 0.5;
    se **releva** si el probable resuelve a obra real con score ≥ 0.90 (`probable_strong`).
- **Familia de terror** para desempate por género: `terror, horror, misterio, mystery, suspenso,
  suspense, thriller`. País (→ `origin_country`): coreana, japonesa, española, argentina, mexicana,
  inglesa/británica, francesa, americana/estadounidense. Era (vieja vs nueva): "más viejita",
  "clásica", "en blanco y negro" / "nueva", "remake", etc.

**Extracción (`steps/extract.py`) + modelo**
- Campos nuevos por recomendación: `corrected_title` (arreglo de transcripción, con piso de
  similitud 0.70 vs el mencionado), `year` (solo si se dice explícito), `disambiguation` (frase del
  host que distingue la versión; los años coloquiales "la del 2007" van aquí, no a `year`),
  `alternate_titles` (alias/traducciones del **mismo** título que se digan).
- Review (`services/review.py`, `cli.py`) muestra corrected/also called/disambiguation y el origen.

**Migraciones aplicadas:** `0008` (year), `0009` (disambiguation + origin en works), `0010`
(corrected_title), `0011` (alternate_titles). **Versión de la BD: `0011`.**

## Estado de los datos

| Métrica | Valor |
|---|---|
| Episodios | 50 |
| Recomendaciones | 116 |
| Obras (works) | 101 |
| Estados | 107 `confirmed` · 3 `needs_review` · 3 `no_match` · 3 `manual_pending` |
| Tipos | 59 movie · 50 videogame · 4 series · 2 other · 1 book |
| Paso `extract` `done` | 50 / 50 |

**Importante — campos nuevos parcialmente poblados:** `alternate_titles` en 1, `disambiguation` en
15, `corrected_title` en 14. La mayoría de episodios se extrajeron con prompts anteriores, así que
**no** aprovecharon aún las señales nuevas. Para poblarlas hace falta re-extracción
(`dds ingest --all --limit 5`, o `dds ingest <video_id> --redo extract` por episodio).

Tasa de autoconfirmación ~92% (107/116); la exactitud de los confirmados **no está validada por
humano salvo una revisión parcial** (ver pendientes).

## Pendientes

1. **Re-extraer** los episodios con el prompt actual para llenar `corrected_title` /
   `disambiguation` / `alternate_titles` y aplicar la cascaда completa a todo el catálogo.
2. **Auditar los `confirmed`**, sobre todo los 45 `resolved_by_popularity` (eligieron *versión*, no
   obra). Validación en curso por el autor.
3. **Decidir política de películas/series** según la validación (p. ej. no confirmar por popularidad
   cuando hay colisión homónima sin año/pista).
4. **Videojuegos** (próximo frente): selección de versión/año por popularidad falla en re-releases
   (ej. *Silent Hill 3* → eligió 2012 en vez de 2003); juegos episódicos y ports.
5. **Hardening del prompt**: reemplazar el ejemplo real "Madre Siniestra" por un placeholder neutro
   para evitar que el modelo lo eche de más (posible sesgo por ejemplificación).
6. **Cortos (Capa C)** en pausa: TMDB devuelve cortos como `movie` y el candidate no trae `runtime`,
   así que el tipo no los separa; requeriría traer runtime/credits.
7. **Fase 2 (IA de desambiguación)** en pausa; solo si la validación muestra que el automático
   no basta.
8. **Tests unitarios** del matching nuevo (aún no escritos).

## Comandos útiles

**Revisar qué obra se eligió por episodio:**

```bash
dds review --episode <video_id> --all
```

**Listado de pelis/series con obra elegida, año, pista y nota (desde la raíz):**

```bash
source .venv/bin/activate
python - <<'PY'
import sys
sys.path.insert(0, 'pipeline/src')
from despues_del_susto.config import Settings
from despues_del_susto.db import session_scope
from sqlalchemy import select
from despues_del_susto.db.models import Episode

s = Settings()
with session_scope(s) as ses:
    for ep in ses.scalars(select(Episode).order_by(Episode.playlist_position)):
        for r in ep.recommendations:
            if r.type not in ('movie', 'series'):
                continue
            dest = f"{r.work.official_title} ({r.work.year})" if r.work else f"[{r.state}]"
            print(f"{ep.video_id} | {r.type} | {r.mentioned_title!r} -> {dest} | {r.match_note}")
PY
```

**Estado de revisión:**

```bash
dds review status
```

## Reglas relacionadas

Ver `docs/rules.md` (BR-26, BR-33 a BR-44, BR-39) y `docs/decisions/0013-enrichment.md`.
