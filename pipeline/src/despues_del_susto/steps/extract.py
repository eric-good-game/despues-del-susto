"""The ``extract`` step: pull the recommendations out of the transcript."""

import json
import logging
import re
import time
from dataclasses import dataclass, replace

from openai import OpenAI
from sqlalchemy import delete

from despues_del_susto.config import LlmSettings, Settings
from despues_del_susto.db import Recommendation, session_scope
from despues_del_susto.db.models import Episode, utcnow
from despues_del_susto.services.processing import get_or_create
from despues_del_susto.steps.errors import StopBatch

logger = logging.getLogger(__name__)

RETRY_WAITS = (5, 15, 45, 90)
ALLOWED_TYPES = {"videogame", "movie", "series", "book", "other"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}

PROMPT = """Te paso la transcripción del final de un episodio de un podcast en español.
Cada línea trae su segundo desde el inicio del episodio: [t=123] texto.
Al final del episodio recomiendan 1 videojuego y 1 película, a veces una serie, un libro u otras
obras.

Extrae SOLO las obras que se recomiendan de forma explícita. No incluyas obras mencionadas
de pasada ni adaptaciones que solo se comentan. Devuelve únicamente JSON válido con esta forma:

{"declared_count": null,
 "recommendations": [
   {"type": "videogame | movie | series | book | other",
    "mentioned_title": "como aparece en la transcripción",
    "probable_title": "título oficial si estás seguro, o null",
    "related_mentions": "obras derivadas nombradas junto a esta, o null",
    "mention_s": 0,
    "mentioned_platform": "plataforma que dicen en el audio, o null",
    "confidence": "high | medium | low"}
 ]}

Reglas:
- Si el nombre pudo transcribirse mal, pon en mentioned_title lo que aparece y en
  probable_title tu mejor estimación con confidence medium o low. Si no estás seguro, null.
- mention_s es el segundo de la línea donde empieza la recomendación (por ejemplo, la pregunta
  del presentador).
- No inventes obras ni datos que no estén en el texto.
- declared_count: si alguien dice cuántas recomendaciones tiene ("tengo dos"), pon ese número.
  Si no se dice, null.
- Una secuela, spin-off o serie derivada que se nombra junto a una obra NO es otra recomendación:
  ponla en related_mentions. Solo es una recomendación aparte si se ofrece con una nueva oferta.
- Quien habla puede equivocarse al decir si algo es película o serie. Pon en type lo que crees que
  es la obra realmente; si dudas, usa confidence medium o low.
- Ignora las calificaciones que se dan a las obras.
"""


class ExtractionError(RuntimeError):
    """The transcript could not be turned into recommendations."""


class InvalidResponse(ValueError):
    """The model returned valid JSON with an unusable shape."""


@dataclass(frozen=True)
class RecommendationDraft:
    type: str
    mentioned_title: str
    probable_title: str | None
    related_mentions: str | None
    mention_s: int | None
    mentioned_platform: str | None
    confidence: str
    role: str = "additional"


@dataclass(frozen=True)
class ExtractionResult:
    provider: str
    model: str
    declared_count: int | None
    recommendations: list[RecommendationDraft]


@dataclass(frozen=True)
class LlmProvider:
    name: str
    base_url: str
    api_key: str
    models: tuple[str, ...]


def resolve_provider() -> LlmProvider:
    """Read the configured chat provider from the environment."""
    settings = LlmSettings()
    name = settings.provider

    if name == "gemini":
        key = settings.gemini_api_key
        model = settings.gemini_model
        fallbacks = settings.gemini_fallback_models
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    elif name == "groq":
        key = settings.groq_api_key
        model = settings.groq_chat_model
        fallbacks = settings.groq_chat_fallback_models
        base_url = "https://api.groq.com/openai/v1"
    elif name == "opencode":
        key = settings.opencode_api_key
        model = settings.opencode_model
        fallbacks = settings.opencode_fallback_models
        base_url = settings.opencode_base_url
    else:
        raise ExtractionError(
            f"unknown provider {name!r}; expected gemini, groq or opencode"
        )

    if not key:
        raise ExtractionError(f"{name} API key is not set")
    if not model:
        raise ExtractionError(f"{name} model is not set")

    models = (model,) + tuple(
        part.strip() for part in fallbacks.split(",") if part.strip()
    )
    return LlmProvider(name=name, base_url=base_url, api_key=key, models=models)


def request_extraction(
    settings: Settings, transcript_text: str, video_id: str
) -> ExtractionResult:
    """Ask the model for the recommendations and parse its JSON."""
    provider = resolve_provider()
    client = OpenAI(
        base_url=provider.base_url,
        api_key=provider.api_key,
        timeout=settings.extract_timeout_s,
    )

    last: Exception | None = None
    for model in provider.models:
        for attempt, wait in enumerate((0, *RETRY_WAITS), start=1):
            if wait:
                time.sleep(wait)
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": transcript_text},
                    ],
                    temperature=0,
                    extra_headers=(
                        {"x-opencode-session": video_id}
                        if provider.name == "opencode"
                        else None
                    ),
                )
                content = response.choices[0].message.content or ""
                return _normalize(_parse_json(content), provider.name, model)
            except (json.JSONDecodeError, InvalidResponse) as exc:
                last = exc
                logger.warning(
                    "invalid extraction JSON from %s (attempt %s): %s",
                    model,
                    attempt,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001 - classified below
                last = exc
                if not _is_transient(exc):
                    raise ExtractionError(f"extraction failed: {exc}") from exc
                logger.warning(
                    "transient extraction error from %s (attempt %s): %s",
                    model,
                    attempt,
                    exc,
                )
        logger.warning("model %s failed, trying the next one", model)

    if last is not None and _is_rate_limit(last):
        raise StopBatch(
            "LLM rate limit or quota exhausted; run the batch again later"
        ) from last
    raise ExtractionError(f"extraction failed after retries: {last}") from last


def assign_roles(
    recommendations: list[RecommendationDraft],
) -> list[RecommendationDraft]:
    """One videogame and one movie are primary; everything else is additional."""
    roles: list[RecommendationDraft] = []
    primary_types: set[str] = set()
    for recommendation in recommendations:
        role = "additional"
        if recommendation.type in ("videogame", "movie") and (
            recommendation.type not in primary_types
        ):
            role = "primary"
            primary_types.add(recommendation.type)
        roles.append(replace(recommendation, role=role))

    if "movie" not in primary_types:
        for index, recommendation in enumerate(roles):
            if recommendation.type == "series":
                roles[index] = replace(recommendation, role="primary")
                break
    return roles


def completeness(
    recommendations: list[RecommendationDraft], declared_count: int | None
) -> tuple[bool, list[str]]:
    """Whether the episode has the expected primary works, plus warning codes."""
    warnings: list[str] = []
    if not recommendations:
        warnings.append("no_recommendations")

    primary_types = {
        recommendation.type
        for recommendation in recommendations
        if recommendation.role == "primary"
    }
    if "videogame" not in primary_types:
        warnings.append("missing_videogame")
    if "movie" not in primary_types:
        if "series" in primary_types:
            warnings.append("series_in_place_of_movie")
        else:
            warnings.append("missing_movie")
    if sum(1 for item in recommendations if item.type == "videogame") > 1:
        warnings.append("more_than_one_videogame")
    if sum(1 for item in recommendations if item.type == "movie") > 1:
        warnings.append("more_than_one_movie")
    if declared_count is not None and len(recommendations) < declared_count:
        warnings.append("fewer_than_declared")

    blocking = {
        "no_recommendations",
        "missing_videogame",
        "missing_movie",
        "fewer_than_declared",
    }
    return not (blocking & set(warnings)), warnings


def run(episode: Episode, settings: Settings) -> None:
    transcript_path = settings.data_dir / "transcripts" / f"{episode.video_id}.json"
    if not transcript_path.exists():
        raise ExtractionError(
            f"transcript not found for {episode.video_id}; run the transcribe step first"
        )
    entries = json.loads(transcript_path.read_text(encoding="utf-8"))
    if not entries:
        raise ExtractionError(f"the transcript for {episode.video_id} is empty")

    transcript_text = "\n".join(
        f"[t={entry['t']}] {entry['text']}" for entry in entries
    )
    result = request_extraction(settings, transcript_text, episode.video_id)
    recommendations = assign_roles(result.recommendations)
    complete, warnings = completeness(recommendations, result.declared_count)
    extracted_at = utcnow()

    artifact = {
        "provider": result.provider,
        "model": result.model,
        "extracted_at": extracted_at.isoformat(),
        "declared_count": result.declared_count,
        "complete": complete,
        "warnings": warnings,
        "recommendations": [
            {
                "type": item.type,
                "role": item.role,
                "state": "extracted",
                "mentioned_title": item.mentioned_title,
                "probable_title": item.probable_title,
                "related_mentions": item.related_mentions,
                "mention_s": item.mention_s,
                "mentioned_platform": item.mentioned_platform,
                "confidence": item.confidence,
            }
            for item in recommendations
        ],
    }
    _write_artifact(settings, episode.video_id, artifact)

    with session_scope(settings) as session:
        session.execute(
            delete(Recommendation).where(
                Recommendation.episode_id == episode.id,
                Recommendation.decided_by == "automatic",
            )
        )
        for item in recommendations:
            session.add(
                Recommendation(
                    episode_id=episode.id,
                    type=item.type,
                    role=item.role,
                    state="extracted",
                    mentioned_title=item.mentioned_title,
                    probable_title=item.probable_title,
                    related_mentions=item.related_mentions,
                    confidence=item.confidence,
                    mention_s=item.mention_s,
                    mentioned_platform=item.mentioned_platform,
                    decided_by="automatic",
                )
            )
        row = get_or_create(session, episode.id)
        row.extraction_model = result.model
        row.extracted_at = extracted_at
        row.declared_count = result.declared_count
        row.extraction_complete = complete
        row.extraction_warnings = ",".join(warnings) or None
        session.commit()


def _parse_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _normalize(data: object, provider: str, model: str) -> ExtractionResult:
    if not isinstance(data, dict):
        raise InvalidResponse("expected a JSON object")

    declared = data.get("declared_count")
    declared_count = declared if isinstance(declared, int) and declared >= 0 else None
    raw_recommendations = data.get("recommendations")
    if not isinstance(raw_recommendations, list):
        raise InvalidResponse("recommendations must be a list")

    recommendations: list[RecommendationDraft] = []
    for raw in raw_recommendations:
        if not isinstance(raw, dict):
            continue
        title = _text(raw.get("mentioned_title"))
        if not title:
            continue
        type_ = _text(raw.get("type"), "other").lower()
        if type_ not in ALLOWED_TYPES:
            type_ = "other"
        confidence = _text(raw.get("confidence"), "low").lower()
        if confidence not in ALLOWED_CONFIDENCE:
            confidence = "low"
        mention = raw.get("mention_s")
        mention_s = int(mention) if isinstance(mention, int | float) else None
        recommendations.append(
            RecommendationDraft(
                type=type_,
                mentioned_title=title,
                probable_title=_optional_text(raw.get("probable_title")),
                related_mentions=_optional_text(raw.get("related_mentions")),
                mention_s=mention_s,
                mentioned_platform=_optional_text(raw.get("mentioned_platform")),
                confidence=confidence,
            )
        )

    return ExtractionResult(
        provider=provider,
        model=model,
        declared_count=declared_count,
        recommendations=recommendations,
    )


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None


def _is_transient(exc: Exception) -> bool:
    status = _status_code(exc)
    if status in (429, 500, 502, 503, 504):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in ("overloaded", "rate limit", "timeout", "connection")
    )


def _is_rate_limit(exc: Exception) -> bool:
    if _status_code(exc) == 429:
        return True
    message = str(exc).lower()
    return "rate limit" in message or "quota" in message


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _write_artifact(settings: Settings, video_id: str, artifact: dict) -> None:
    directory = settings.data_dir / "extractions"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{video_id}.json"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    temporary.replace(path)
