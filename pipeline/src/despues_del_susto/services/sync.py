"""Discover episodes in the podcast playlist and keep their metadata fresh.

The playlist is the source of truth for which episodes exist. A sync upserts by
``video_id``, never deletes, and only marks an episode unavailable after a
listing that the safety check accepted.
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select

from despues_del_susto.config import Settings
from despues_del_susto.db import Episode, ensure_schema, session_scope
from despues_del_susto.db.models import utcnow

logger = logging.getLogger(__name__)


class DiscoveryNotConfigured(RuntimeError):
    """Neither the option nor the environment provides a playlist URL."""


class SyncError(RuntimeError):
    """The playlist could not be read or parsed."""


class SuspiciousListingError(SyncError):
    """The listing is empty or much smaller than the catalog; refusing to apply it."""


@dataclass(frozen=True)
class PlaylistEntry:
    """One item of the flat playlist listing."""

    video_id: str
    title: str
    position: int


@dataclass(frozen=True)
class FullMetadata:
    """The fields that need a per-episode extraction.

    The title is not here: the flat listing already provides it, and letting two
    sources write the same column makes consecutive syncs fight each other.
    """

    published_at: datetime | None
    duration_s: int | None
    thumbnail_url: str | None


@dataclass
class SyncReport:
    """What a sync changed, or would change under ``--dry-run``."""

    dry_run: bool = False
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unavailable: list[str] = field(default_factory=list)
    reactivated: list[str] = field(default_factory=list)
    metadata_pending: list[str] = field(default_factory=list)
    metadata_fetched: list[str] = field(default_factory=list)
    metadata_failed: dict[str, str] = field(default_factory=dict)
    unchanged: int = 0


def sync_playlist(
    settings: Settings,
    playlist_url: str | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> SyncReport:
    """Compare the playlist with the database and apply the differences."""
    url = playlist_url or settings.playlist_url
    if not url:
        raise DiscoveryNotConfigured(
            "no playlist configured; set DDS_PLAYLIST_URL or pass --playlist-url"
        )

    entries = fetch_flat_listing(settings, url)
    if not entries:
        raise SuspiciousListingError("the playlist returned no entries; nothing was changed")

    ensure_schema(settings)
    now = utcnow()
    report = SyncReport(dry_run=dry_run)

    with session_scope(settings) as session:
        known = {episode.video_id: episode for episode in session.scalars(select(Episode))}
        _check_listing_size(settings, known, entries, force=force)
        present = {entry.video_id for entry in entries}

        for entry in entries:
            episode = known.get(entry.video_id)
            if episode is None:
                episode = Episode(
                    video_id=entry.video_id,
                    title=entry.title,
                    playlist_position=entry.position,
                    availability="available",
                    first_seen_at=now,
                    last_seen_at=now,
                )
                session.add(episode)
                known[entry.video_id] = episode
                report.added.append(entry.video_id)
                report.metadata_pending.append(entry.video_id)
                continue

            changed = False
            if entry.title and episode.title != entry.title:
                episode.title = entry.title
                changed = True
            if episode.playlist_position != entry.position:
                episode.playlist_position = entry.position
                changed = True
            if episode.availability == "unavailable":
                episode.availability = "available"
                report.reactivated.append(entry.video_id)
                changed = True
            episode.last_seen_at = now
            if changed:
                report.updated.append(entry.video_id)
            else:
                report.unchanged += 1
            if episode.metadata_fetched_at is None:
                report.metadata_pending.append(entry.video_id)

        for video_id, episode in known.items():
            if video_id not in present and episode.availability == "available":
                episode.availability = "unavailable"
                report.unavailable.append(video_id)

        if dry_run:
            session.rollback()
            return report
        session.commit()

    _fetch_pending_metadata(settings, report)
    return report


def _check_listing_size(
    settings: Settings,
    known: dict[str, Episode],
    entries: list[PlaylistEntry],
    *,
    force: bool,
) -> None:
    """Refuse a listing that looks truncated instead of marking episodes unavailable."""
    if force:
        return
    available = {video_id for video_id, ep in known.items() if ep.availability == "available"}
    if len(available) < 2:
        return
    present = {entry.video_id for entry in entries}
    kept = len(available & present)
    if kept < len(available) * settings.sync_min_ratio:
        raise SuspiciousListingError(
            f"the listing contains {kept} of {len(available)} known episodes; "
            "nothing was changed. Use --force if the playlist really shrank"
        )


def _fetch_pending_metadata(settings: Settings, report: SyncReport) -> None:
    """Fill the metadata of episodes that do not have it yet.

    One failure does not stop the sync: it is recorded on the episode and
    retried on the next run.
    """
    for index, video_id in enumerate(report.metadata_pending):
        if index:
            time.sleep(settings.sync_delay_s)
        try:
            metadata = fetch_full_metadata(settings, video_id)
        except SyncError as exc:
            report.metadata_failed[video_id] = str(exc)
            _save_metadata_error(settings, video_id, str(exc))
            continue
        _save_metadata(settings, video_id, metadata)
        report.metadata_fetched.append(video_id)


def _save_metadata(settings: Settings, video_id: str, metadata: FullMetadata) -> None:
    with session_scope(settings) as session:
        episode = session.scalar(select(Episode).where(Episode.video_id == video_id))
        if episode is None:
            return
        episode.published_at = metadata.published_at
        episode.duration_s = metadata.duration_s
        episode.thumbnail_url = metadata.thumbnail_url
        episode.metadata_fetched_at = utcnow()
        episode.metadata_error = None
        session.commit()


def _save_metadata_error(settings: Settings, video_id: str, message: str) -> None:
    with session_scope(settings) as session:
        episode = session.scalar(select(Episode).where(Episode.video_id == video_id))
        if episode is None:
            return
        episode.metadata_error = message[:2000]
        session.commit()


def fetch_flat_listing(settings: Settings, playlist_url: str) -> list[PlaylistEntry]:
    """Read the playlist without per-video extraction."""
    data = _run_yt_dlp(settings, ["--flat-playlist", playlist_url])
    entries: list[PlaylistEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(data.get("entries") or [], start=1):
        video_id = raw.get("id")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        entries.append(
            PlaylistEntry(
                video_id=video_id,
                title=raw.get("title") or "",
                position=index,
            )
        )
    return entries


def fetch_full_metadata(settings: Settings, video_id: str) -> FullMetadata:
    """Extract the fields that the flat listing does not provide."""
    data = _run_yt_dlp(settings, [f"https://www.youtube.com/watch?v={video_id}"])
    published_at = _parse_upload_date(data.get("upload_date"))
    duration = data.get("duration")
    return FullMetadata(
        published_at=published_at,
        duration_s=int(duration) if isinstance(duration, int | float) else None,
        thumbnail_url=data.get("thumbnail"),
    )


def _parse_upload_date(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _run_yt_dlp(settings: Settings, arguments: list[str]) -> dict:
    command = [settings.yt_dlp_path, "--no-warnings", "--dump-single-json", *arguments]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.yt_dlp_timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SyncError(
            f"{settings.yt_dlp_path} not found; install it with `brew install yt-dlp`"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise SyncError(f"yt-dlp timed out after {settings.yt_dlp_timeout_s}s") from exc

    if result.returncode != 0:
        lines = (result.stderr or result.stdout).strip().splitlines()
        detail = lines[-1] if lines else f"exit code {result.returncode}"
        raise SyncError(f"yt-dlp failed: {detail}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SyncError("yt-dlp returned invalid JSON") from exc
