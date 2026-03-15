"""GDELT processor: fetches/caches adverse media news and returns Evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from osint_swarm.data_sources import gdelt
from osint_swarm.entities import Evidence
from osint_swarm.utils.io import read_json, write_json

from mcp_layer.base import DataSourceProcessor

if TYPE_CHECKING:
    from osint_swarm.entities import Entity


def _articles_to_evidence(
    articles: List[Dict[str, Any]],
    entity_id: str,
    entity_name: str,
    raw_location: Optional[str] = None,
) -> List[Evidence]:
    """Convert GDELT article records to Evidence list."""
    out: List[Evidence] = []
    for i, article in enumerate(articles):
        if not isinstance(article, dict):
            continue

        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        seen_date = (article.get("seendate") or "").strip()
        domain = (article.get("domain") or "").strip()
        language = (article.get("language") or "").strip()
        source_country = (article.get("sourcecountry") or "").strip()

        if not url or not title:
            continue

        # Parse date: GDELT format is "20240615T120000Z" or "20240615000000"
        date_str = ""
        if seen_date:
            raw = seen_date.replace("T", "").replace("Z", "").replace("-", "")
            if len(raw) >= 8:
                date_str = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

        # Deterministic ID from URL hash (first 12 hex chars)
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        ev_id = f"{entity_id.split('_')[0]}_gdelt_{url_hash}"

        summary = title if title else f"News article about {entity_name}"

        out.append(
            Evidence(
                evidence_id=ev_id,
                entity_id=entity_id,
                date=date_str,
                source_type="news_article",
                risk_category="network",
                summary=summary[:5000],
                source_uri=url,
                raw_location=raw_location,
                confidence=0.6,
                attributes={
                    "domain": domain,
                    "language": language,
                    "source_country": source_country,
                    "gdelt_rank": i + 1,
                },
            )
        )
    return out


class GdeltProcessor(DataSourceProcessor):
    """MCP processor for GDELT adverse media; uses osint_swarm.data_sources.gdelt."""

    def __init__(self, data_root: Optional[Path] = None):
        self.data_root = Path(data_root) if data_root else Path("data")
        self._raw_dir = self.data_root / "raw" / "gdelt"

    @property
    def source_id(self) -> str:
        return "gdelt"

    def _slug_for_entity(self, entity: "Entity") -> str:
        """Filesystem-safe slug from entity name."""
        return entity.name.lower().split(",")[0].strip().replace(" ", "_").replace(".", "")

    def get_evidence_for_entity(self, entity: "Entity") -> List[Evidence]:
        entity_id = entity.entity_id
        slug = self._slug_for_entity(entity)

        cache_path = self._raw_dir / f"news_{slug}.json"
        if cache_path.exists():
            payload = read_json(cache_path)
            raw_location = str(cache_path)
        else:
            try:
                payload = gdelt.fetch_news_for_entity(entity.name)
                self._raw_dir.mkdir(parents=True, exist_ok=True)
                write_json(cache_path, payload)
                raw_location = str(cache_path)
            except gdelt.GdeltError:
                return []

        articles = gdelt.extract_article_records(payload)
        return _articles_to_evidence(articles, entity_id, entity.name, raw_location=raw_location)
