"""OpenAlex client backed by openalex-py (import ``openalexpy``).

Isolated behind this thin wrapper so the library can be swapped without
touching the pipeline. Falls back to raw httpx against the OpenAlex REST API
if openalexpy is unavailable at runtime (defensive: the package is young).
"""

from __future__ import annotations

import logging

from open_referee.config import OpenAlexConfig
from open_referee.literature.context import LiteratureItem

logger = logging.getLogger(__name__)


class OpenAlexClient:
    def __init__(self, cfg: OpenAlexConfig):
        self.cfg = cfg
        self._api_key = cfg.resolved_api_key()
        self._client = None

    async def __aenter__(self) -> OpenAlexClient:
        try:
            import openalexpy

            openalexpy.config.api_key = self._api_key
            self._client = openalexpy
            self._mode = "openalexpy"
        except ImportError:
            logger.warning("openalex-py not installed; falling back to raw REST client")
            self._http = __import__("httpx").AsyncClient(
                base_url="https://api.openalex.org", timeout=30.0
            )
            self._mode = "rest"
        return self

    async def __aexit__(self, *exc) -> None:
        if self._mode == "rest":
            await self._http.aclose()

    # ------------------------------------------------------------------ api --

    async def search_works(self, query: str, limit: int = 10) -> list[LiteratureItem]:
        if self._mode == "openalexpy":
            return await self._search_openalexpy(query, limit)
        return await self._search_rest(query, limit)

    async def get_work_by_doi(self, doi: str) -> LiteratureItem | None:
        doi = doi.lower().replace("https://doi.org/", "")
        if self._mode == "openalexpy":
            try:
                work = await self._client.Works().get_by_id(f"doi:{doi}")
                return _work_to_item(work)
            except Exception:
                return None
        try:
            r = await self._http.get(f"/works/doi:{doi}", params=_params(self._api_key))
            r.raise_for_status()
            return _rest_work_to_item(r.json())
        except Exception:
            return None

    async def _search_openalexpy(self, query: str, limit: int) -> list[LiteratureItem]:
        try:
            results = await self._client.Works().search(query).get(per_page=limit)
            items = []
            for w in results:
                items.append(_work_to_item(w))
            return items
        except Exception as e:
            logger.warning("openalexpy search failed (%s); trying REST fallback", e)
            return await self._search_rest(query, limit)

    async def _search_rest(self, query: str, limit: int) -> list[LiteratureItem]:
        try:
            r = await self._http.get(
                "/works",
                params=_params(self._api_key, {"search": query, "per-page": str(limit)}),
            )
            r.raise_for_status()
            return [_rest_work_to_item(w) for w in r.json().get("results", [])]
        except Exception as e:
            logger.warning("OpenAlex REST search failed: %s", e)
            return []


def _params(api_key: str | None, extra: dict[str, str] | None = None) -> dict[str, str]:
    p = dict(extra or {})
    if api_key:
        p["api_key"] = api_key
    return p


def _work_to_item(w) -> LiteratureItem:  # openalexpy Work model
    return LiteratureItem(
        source="openalex",
        title=w.title or "",
        authors=list(getattr(w, "authors", []) or []),
        year=getattr(w, "year", None),
        doi=(w.doi.rsplit("/", 1)[-1] if w.doi else None),
        venue=(
            w.primary_location.source.display_name
            if getattr(w, "primary_location", None)
            and w.primary_location
            and w.primary_location.source
            else None
        ),
        cited_by=getattr(w, "citations", None),
        abstract=getattr(w, "abstract", None),
        url=w.id,
    )


def _rest_work_to_item(w: dict) -> LiteratureItem:
    authorships = w.get("authorships") or []
    return LiteratureItem(
        source="openalex",
        title=w.get("display_name") or "",
        authors=[a.get("author", {}).get("display_name", "") for a in authorships[:6]],
        year=w.get("publication_year"),
        doi=(w.get("doi") or "").rsplit("/", 1)[-1] or None,
        venue=((w.get("primary_location") or {}).get("source") or {}).get("display_name"),
        cited_by=w.get("cited_by_count"),
        abstract=_rest_abstract(w),
        url=w.get("id"),
    )


def _rest_abstract(w: dict) -> str | None:
    inv = w.get("abstract_inverted_index")
    if not inv:
        return None
    pos: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    return " ".join(word for _, word in sorted(pos))
