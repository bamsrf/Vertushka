"""
Bulk rematch of store-native Records against the local discogs_releases_index.

Cascade (per record):
  1. barcode_norm exact match   → confidence 1.0  → immediate merge
  2. catalog_norm exact match   → confidence 0.9  → immediate merge
  3. fuzzy artist+title+year    → each field similarity >= 0.6 AND year ±1
                                   → confidence based on combined score
                                   → bump candidate/confirmations; merge when >= 2
                                      (or immediately with --auto-merge)

After merge:
  • store_listings.matched_record_id remapped (done by safe_merge_store_native_into)
  • collection_items.record_id remapped (skip if user already has target)
  • wishlist_items.record_id remapped (skip if user already has target)
  • source Record gets merged_into_id = target.id (soft-delete)

Usage:
  python -m app.scripts.rematch_store_native [options]

Options:
  --dry-run         Log potential merges; no DB writes.
  --limit N         Process at most N store-native records (default: all).
  --auto-merge      Merge on first confident hit regardless of confirmations.
  --fuzzy-only      Skip barcode/catalog; only run fuzzy matching.
  --batch-size N    Records per DB batch (default: 200).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

# Make sure app package is importable when run as -m app.scripts.rematch_store_native
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.database import async_session_maker
from app.models.record import Record
from app.services.listing_matcher import (
    _get_or_create_record_from_dump,
    _is_dump_available,
    safe_merge_store_native_into,
    STORE_NATIVE_MERGE_MIN_CONFIRMATIONS,
)
from app.services.scrapers.extractors import normalize_barcode, normalize_catalog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("rematch_store_native")

# Parenthetical annotations added by Russian stores to Discogs titles.
# Stripping these before fuzzy matching prevents trigram dilution that would
# push similarity below threshold for otherwise identical titles.
# e.g. "Dummy (Gatefold)" → "Dummy", "Wish You Were Here (Repress 2025)" → "Wish You Were Here"
# Fix 1: also covers generic "* vinyl" colour variants:
#   "clear vinyl", "bone vinyl", "red translucent vinyl", "pink & white marbled vinyl" etc.
_STORE_SUFFIX_RE = re.compile(
    r"\s*\(\s*(?:"
    r"\d{4}|"                               # year: (2025)
    r"[Rr]epress\b[^)]*|"                   # (Repress ...), (Reissue ...)
    r"[Rr]eissue\b[^)]*|"
    r"[Uu]sed\b[^)]*|"                      # (Used)
    r"Gatefold|gatefold|"
    r"\d\s*LP|"                             # (2LP), (3LP)
    r"[^)]*\b(?:vinyl|винил)\b[^)]*|"       # ANY * vinyl/винил * — clear, bone, оранжевый...
    r"пикчер\s*диск|picture\s*disc|"
    r"Mono|моно|Stereo|стерео|"
    r"буклет|booklet|"
    r"[Cc][Dd]|"                            # (CD)
    r"макси\s*сингл|maxi\s*single|"
    r"obi[^)]*|ОБИ[^)]*|"                  # (+ obi), (obi-strip)
    r"бокс[^)]*|box\s*set[^)]*|"
    r"\+[^)]*"                              # (+ буклет), (+ книга)
    r")[^)]*\)+\s*$",                       # \)+ — handle nested parens: (picture disc (пикчер диск))
    re.IGNORECASE,
)

# Bilingual "X = Y" titles where stores write both Latin and Cyrillic.
# Pick the part with more ASCII (Latin) chars — Discogs uses Latin canonical names.
def _pick_latin_part(s: str) -> str:
    """For 'Лед Зеппелин = Led Zeppelin' or 'Abba = Абба' → return the Latin part."""
    if " = " not in s:
        return s
    left, _, right = s.partition(" = ")
    left_ascii = sum(1 for c in left if ord(c) < 128 and c.isalpha())
    right_ascii = sum(1 for c in right if ord(c) < 128 and c.isalpha())
    return (right if right_ascii >= left_ascii else left).strip()

# Compilation artist synonyms → normalize to Discogs "Various"
_VA_RE = re.compile(r"^(?:V/A|VA|Various Artists?|Сборник)$", re.IGNORECASE)


def _normalize_store_title(title: str) -> str:
    """Strip store-added parenthetical suffixes for cleaner trgm matching.

    Fix 3: pick the Latin part from bilingual "X = Y" titles.
    Fix 1: generic vinyl/винил pattern + nested-paren support.
    """
    t = _pick_latin_part(title.strip())
    # Strip trailing parenthetical annotations iteratively (some have multiple)
    prev = None
    while prev != t:
        prev = t
        t = _STORE_SUFFIX_RE.sub("", t).strip()
    return t or title.strip()


def _normalize_store_artist(artist: str) -> str:
    a = artist.strip()
    if _VA_RE.match(a):
        return "Various"
    return _pick_latin_part(a)


# Strict fuzzy thresholds for records with no barcode/catalog signal.
# Each field must independently reach 0.6 (vs combined 1.4 in listing_matcher).
# Year tolerance is ±1 (tighter than listing_matcher's ±2) to avoid false positives
# on annual re-issues with the same artist+title.
FUZZY_ARTIST_THRESHOLD = 0.6
FUZZY_TITLE_THRESHOLD = 0.6
FUZZY_YEAR_TOLERANCE = 1
FUZZY_AUTO_MERGE_COMBINED = 1.6  # avg 0.8/field → high confidence, single-shot OK


async def _lookup_dump_barcode(db: AsyncSession, barcode: str) -> dict | None:
    row = (await db.execute(
        text(
            "SELECT discogs_id, master_id, artist, title, year, country, "
            "       format_type, label, cover_image_url "
            "FROM discogs_releases_index WHERE barcode_norm = :b LIMIT 1"
        ),
        {"b": barcode},
    )).mappings().first()
    return dict(row) if row else None


async def _lookup_dump_catalog(db: AsyncSession, catalog: str) -> dict | None:
    row = (await db.execute(
        text(
            "SELECT discogs_id, master_id, artist, title, year, country, "
            "       format_type, label, cover_image_url "
            "FROM discogs_releases_index WHERE catalog_norm = :c LIMIT 1"
        ),
        {"c": catalog},
    )).mappings().first()
    return dict(row) if row else None


async def _lookup_dump_fuzzy(
    db: AsyncSession,
    *,
    artist: str,
    title: str,
    year: int | None,
) -> tuple[dict, float] | None:
    """Strict fuzzy: both fields >= 0.6 independently, year ±1 or NULL."""
    # Use single `%` (pg_trgm similarity operator) to activate the GIN trgm index
    # for candidate retrieval, then post-filter with similarity() >= threshold.
    # Note: asyncpg uses $N placeholders so `%` is NOT a format character and
    # must be written as a single `%` (not `%%`). `%%` would be sent literally
    # to Postgres as `%%` which is not a valid operator.
    row = (await db.execute(
        text(
            "SELECT discogs_id, master_id, artist, title, year, country, "
            "       format_type, label, cover_image_url, "
            "       (similarity(artist, :a) + similarity(title, :t)) AS score "
            "FROM discogs_releases_index "
            "WHERE artist % :a AND title % :t "
            "  AND similarity(artist, :a) >= :ta "
            "  AND similarity(title, :t) >= :tt "
            "  AND (cast(:y as int) IS NULL OR year IS NULL OR ABS(year - cast(:y as int)) <= :tol) "
            "ORDER BY score DESC LIMIT 1"
        ),
        {
            "a": artist,
            "t": title,
            "ta": FUZZY_ARTIST_THRESHOLD,
            "tt": FUZZY_TITLE_THRESHOLD,
            "y": year,
            "tol": FUZZY_YEAR_TOLERANCE,
        },
    )).mappings().first()
    if row is None:
        return None
    return dict(row), float(row["score"])


async def _remap_user_items(
    db: AsyncSession,
    source_id,
    target_id,
    *,
    dry_run: bool,
) -> dict[str, int]:
    """Remap collection_items and wishlist_items from source to target record.

    Skips rows where the user already has the target record in the same list
    to avoid duplicate-constraint violations.
    """
    counts = {"collection": 0, "wishlist": 0}
    if dry_run:
        # Estimate only
        r = await db.execute(
            text("SELECT count(*) FROM collection_items WHERE record_id = :s"),
            {"s": source_id},
        )
        counts["collection"] = int(r.scalar() or 0)
        r = await db.execute(
            text("SELECT count(*) FROM wishlist_items WHERE record_id = :s"),
            {"s": source_id},
        )
        counts["wishlist"] = int(r.scalar() or 0)
        return counts

    # Remap collection_items: skip if target already in same collection
    r = await db.execute(
        text(
            "UPDATE collection_items SET record_id = :tgt "
            "WHERE record_id = :src "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM collection_items ci2 "
            "    WHERE ci2.collection_id = collection_items.collection_id "
            "      AND ci2.record_id = :tgt"
            "  )"
        ),
        {"src": source_id, "tgt": target_id},
    )
    counts["collection"] = r.rowcount or 0

    # Remap wishlist_items: skip if target already in same wishlist
    r = await db.execute(
        text(
            "UPDATE wishlist_items SET record_id = :tgt "
            "WHERE record_id = :src "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM wishlist_items wi2 "
            "    WHERE wi2.wishlist_id = wishlist_items.wishlist_id "
            "      AND wi2.record_id = :tgt"
            "  )"
        ),
        {"src": source_id, "tgt": target_id},
    )
    counts["wishlist"] = r.rowcount or 0

    return counts


async def _do_merge(
    db: AsyncSession,
    source: Record,
    dump_entry: dict,
    confidence: float,
    method: str,
    *,
    dry_run: bool,
) -> bool:
    """Create/find the Discogs record, run safe_merge, remap user items."""
    discogs_id = str(dump_entry["discogs_id"])
    if dry_run:
        item_counts = await _remap_user_items(db, source.id, None, dry_run=True)
        logger.info(
            "DRY-RUN merge: %s → discogs_id=%s  [%s / conf=%.3f] "
            "(collection_items=%d wishlist_items=%d artist=%r title=%r year=%s)",
            source.id, discogs_id, method, confidence,
            item_counts["collection"], item_counts["wishlist"],
            source.artist, source.title, source.year,
        )
        return True

    target = await _get_or_create_record_from_dump(db, dump_entry)
    if target is None:
        logger.warning("Could not create/find target Record for discogs_id=%s", discogs_id)
        return False

    merge_res = await safe_merge_store_native_into(
        source, discogs_id, db, merged_by="bulk_rematch"
    )
    if not merge_res["target_found"]:
        logger.warning(
            "safe_merge target_found=0 for source=%s discogs_id=%s",
            source.id, discogs_id,
        )
        return False

    item_counts = await _remap_user_items(db, source.id, target.id, dry_run=False)

    logger.info(
        "MERGED: %s → discogs_id=%s  [%s / conf=%.3f] "
        "listings=%d collection_items=%d wishlist_items=%d "
        "(artist=%r title=%r year=%s)",
        source.id, discogs_id, method, confidence,
        merge_res["listings_remapped"],
        item_counts["collection"], item_counts["wishlist"],
        source.artist, source.title, source.year,
    )
    return True


async def _update_candidate(
    db: AsyncSession,
    rec: Record,
    discogs_id: str,
    *,
    dry_run: bool,
) -> str:
    """Bump or set discogs_id_candidate. Returns 'confirmed'|'found'|'changed'."""
    if dry_run:
        action = (
            "would-confirm" if rec.discogs_id_candidate == discogs_id
            else "would-set" if rec.discogs_id_candidate is None
            else "would-change"
        )
        logger.info(
            "DRY-RUN candidate %s: source=%s discogs_id=%s (confirmations=%d)",
            action, rec.id, discogs_id, rec.discogs_id_candidate_confirmations,
        )
        return action.replace("would-", "")

    now = datetime.utcnow()
    if rec.discogs_id_candidate == discogs_id:
        rec.discogs_id_candidate_confirmations += 1
        return "confirmed"
    elif rec.discogs_id_candidate is None:
        rec.discogs_id_candidate = discogs_id
        rec.discogs_id_candidate_first_seen_at = now
        rec.discogs_id_candidate_confirmations = 1
        return "found"
    else:
        rec.discogs_id_candidate = discogs_id
        rec.discogs_id_candidate_first_seen_at = now
        rec.discogs_id_candidate_confirmations = 1
        return "changed"


async def run_rematch(
    *,
    dry_run: bool,
    limit: int | None,
    auto_merge: bool,
    fuzzy_only: bool,
    batch_size: int,
) -> dict[str, int]:
    counters = {
        "processed": 0,
        "merged": 0,
        "candidate_found": 0,
        "candidate_confirmed": 0,
        "candidate_changed": 0,
        "no_match": 0,
        "errors": 0,
        "skipped_dump_unavailable": 0,
    }

    offset = 0

    while True:
        fetch_limit = batch_size
        if limit is not None:
            remaining = limit - counters["processed"]
            if remaining <= 0:
                break
            fetch_limit = min(batch_size, remaining)

        async with async_session_maker() as db:
            if not await _is_dump_available(db):
                logger.error(
                    "discogs_releases_index is empty or not created — "
                    "run ingest_discogs_dump.py first"
                )
                counters["skipped_dump_unavailable"] = 1
                break

            # source='store' + аппрувнутые source='user' (§7). Pending/rejected
            # user-записи в Discogs не ищем — только общие.
            res = await db.execute(
                select(Record)
                .where(
                    or_(
                        Record.source == "store",
                        and_(
                            Record.source == "user",
                            Record.moderation_status == "approved",
                        ),
                    )
                )
                .where(Record.merged_into_id.is_(None))
                .order_by(Record.updated_at.asc())
                .offset(offset)
                .limit(fetch_limit)
            )
            records = list(res.scalars().all())

            if not records:
                break

            for rec in records:
                counters["processed"] += 1
                sp = await db.begin_nested()
                try:
                    merged = await _process_one(
                        db, rec,
                        dry_run=dry_run,
                        auto_merge=auto_merge,
                        fuzzy_only=fuzzy_only,
                        counters=counters,
                    )
                    await sp.commit()
                except Exception:
                    await sp.rollback()
                    counters["errors"] += 1
                    logger.exception("Error processing record %s (%s — %s)", rec.id, rec.artist, rec.title)

            if not dry_run:
                try:
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.exception("Commit failed for batch at offset=%d", offset)

        offset += len(records)
        if len(records) < fetch_limit:
            break

    return counters


async def _process_one(
    db: AsyncSession,
    rec: Record,
    *,
    dry_run: bool,
    auto_merge: bool,
    fuzzy_only: bool,
    counters: dict,
) -> bool:
    barcode = normalize_barcode(rec.barcode) if rec.barcode else None
    catalog = normalize_catalog(rec.catalog_number) if rec.catalog_number else None

    dump_entry: dict | None = None
    confidence: float = 0.0
    method: str = ""

    # 1) Barcode
    if not fuzzy_only and barcode:
        row = await _lookup_dump_barcode(db, barcode)
        if row:
            dump_entry, confidence, method = row, 1.0, "barcode"

    # 2) Catalog (if no barcode hit)
    if dump_entry is None and not fuzzy_only and catalog:
        row = await _lookup_dump_catalog(db, catalog)
        if row:
            dump_entry, confidence, method = row, 0.9, "catalog"

    # Normalize title/artist for fuzzy: strip store annotations like "(Gatefold)",
    # "(Repress 2025)", "(цветной винил)" which dilute trigram similarity vs the
    # canonical Discogs title. Normalization happens ONLY for lookup, original
    # record fields are never modified.
    fuzzy_artist = _normalize_store_artist(rec.artist) if rec.artist else None
    fuzzy_title = _normalize_store_title(rec.title) if rec.title else None

    # 3) Fuzzy artist+title+year (if no exact hit and we have artist+title)
    if dump_entry is None and fuzzy_artist and fuzzy_title:
        fuzzy_hit = await _lookup_dump_fuzzy(
            db, artist=fuzzy_artist, title=fuzzy_title, year=rec.year
        )
        if fuzzy_hit:
            row, score = fuzzy_hit
            # Scale confidence: combined 1.2 → 0.75, 2.0 → 0.95
            conf = min(0.95, round(0.375 + score * 0.275, 3))
            dump_entry, confidence, method = row, conf, "fuzzy"

    # 4) Discogs API fallback — for new releases not yet in the local dump.
    # Uses the existing rate-limited _try_discogs_fetch_by_text (2000 req/hr limit).
    # Only fires when dump lookup failed AND we have artist+title to search with.
    if dump_entry is None and fuzzy_artist and fuzzy_title and not dry_run:
        from app.services.listing_matcher import _try_discogs_fetch_by_text
        found = await _try_discogs_fetch_by_text(
            db,
            artist=fuzzy_artist,
            title=fuzzy_title,
            year=rec.year,
        )
        if found and found.discogs_id and found.id != rec.id:
            # We have a live Discogs Record — merge directly (skip dump_entry path)
            merge_res = await safe_merge_store_native_into(
                rec, found.discogs_id, db, merged_by="bulk_rematch_api"
            )
            if merge_res["target_found"]:
                item_counts = await _remap_user_items(db, rec.id, found.id, dry_run=False)
                logger.info(
                    "MERGED (API): %s → discogs_id=%s listings=%d "
                    "collection_items=%d wishlist_items=%d "
                    "(artist=%r title=%r year=%s)",
                    rec.id, found.discogs_id,
                    merge_res["listings_remapped"],
                    item_counts["collection"], item_counts["wishlist"],
                    rec.artist, rec.title, rec.year,
                )
                counters["merged"] += 1
                return True
            # target_found=0 means Record created but not found — shouldn't happen
            # after _try_discogs_fetch_by_text, log and fall through to no_match
            logger.warning(
                "API merge target_found=0 for source=%s discogs_id=%s",
                rec.id, found.discogs_id,
            )

    if dump_entry is None:
        counters["no_match"] += 1
        logger.debug("No match: %r — %r (%s)", rec.artist, rec.title, rec.year)
        return False

    discogs_id = str(dump_entry["discogs_id"])

    # Decide: merge now or just update candidate
    should_merge_now = (
        auto_merge
        or confidence >= 0.9  # barcode/catalog → always immediate
        or (
            # Fuzzy high-confidence or already confirmed enough times
            method == "fuzzy"
            and (
                confidence * 2 >= FUZZY_AUTO_MERGE_COMBINED  # score >= 1.6
                or (
                    rec.discogs_id_candidate == discogs_id
                    and rec.discogs_id_candidate_confirmations + 1 >= STORE_NATIVE_MERGE_MIN_CONFIRMATIONS
                )
            )
        )
    )

    if should_merge_now:
        ok = await _do_merge(db, rec, dump_entry, confidence, method, dry_run=dry_run)
        if ok:
            counters["merged"] += 1
        return ok
    else:
        action = await _update_candidate(db, rec, discogs_id, dry_run=dry_run)
        counters[f"candidate_{action}"] = counters.get(f"candidate_{action}", 0) + 1
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk rematch store-native records against local discogs_releases_index"
    )
    parser.add_argument("--dry-run", action="store_true", help="Log only, no DB writes")
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="Max records to process")
    parser.add_argument("--auto-merge", action="store_true", help="Merge on first hit regardless of confirmations")
    parser.add_argument("--fuzzy-only", action="store_true", help="Skip barcode/catalog; only fuzzy matching")
    parser.add_argument("--batch-size", type=int, default=200, metavar="N", help="Records per DB batch")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY-RUN mode — no writes ===")

    counters = asyncio.run(run_rematch(
        dry_run=args.dry_run,
        limit=args.limit,
        auto_merge=args.auto_merge,
        fuzzy_only=args.fuzzy_only,
        batch_size=args.batch_size,
    ))

    logger.info("=== Done ===")
    for k, v in counters.items():
        logger.info("  %-30s %d", k, v)

    would = "would be " if args.dry_run else ""
    logger.info(
        "Summary: %d processed → %d %smerged, %d candidate updates, %d no-match, %d errors",
        counters["processed"],
        counters["merged"],
        would,
        counters["candidate_found"] + counters["candidate_confirmed"] + counters["candidate_changed"],
        counters["no_match"],
        counters["errors"],
    )


if __name__ == "__main__":
    main()
