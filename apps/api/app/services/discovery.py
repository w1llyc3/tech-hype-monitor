"""Persist discovery results into tracked entities + metric observations."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.metrics import record_metrics, upsert_tracked_entity


def persist_github_discovery(db: Session, items: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for item in items:
        external_id = item.get("external_id")
        if not external_id:
            continue
        entity = upsert_tracked_entity(
            db,
            platform="github",
            entity_type="github_repo",
            external_id=str(external_id),
            canonical_url=item.get("url"),
            display_name=str(external_id),
            metadata={
                "owner": item.get("owner"),
                "name": item.get("name"),
                "description": item.get("description"),
                "language": item.get("language"),
                "topics": item.get("topics") or [],
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "pushed_at": item.get("pushed_at"),
            },
        )
        record_metrics(
            db,
            entity,
            {
                "stars": float(item["stars"]) if item.get("stars") is not None else None,
                "forks": float(item["forks"]) if item.get("forks") is not None else None,
            },
        )
        ids.append(entity.id)
    db.commit()
    return ids


def persist_hf_discovery(db: Session, items: list[dict[str, Any]]) -> list[int]:
    ids: list[int] = []
    for item in items:
        external_id = item.get("external_id") or item.get("repo_id")
        entity_type = item.get("entity_type") or "hf_model"
        if not external_id:
            continue
        entity = upsert_tracked_entity(
            db,
            platform="huggingface",
            entity_type=entity_type,
            external_id=str(external_id),
            canonical_url=item.get("url"),
            display_name=str(external_id),
            metadata={
                "author": item.get("author"),
                "tags": item.get("tags") or [],
                "pipeline_tag": item.get("pipeline_tag"),
                "sdk": item.get("sdk"),
                "last_modified": item.get("last_modified"),
            },
        )
        metrics: dict[str, float | None] = {
            "likes": float(item["likes"]) if item.get("likes") is not None else None,
        }
        if entity_type in {"hf_model", "hf_dataset"}:
            metrics["downloads"] = (
                float(item["downloads"]) if item.get("downloads") is not None else None
            )
        record_metrics(db, entity, metrics)
        ids.append(entity.id)
    db.commit()
    return ids
