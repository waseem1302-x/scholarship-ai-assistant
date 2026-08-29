"""Safe cleanup of derived topology state before deterministic recomputation."""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.modules.catalogue_ingestion.models import CatalogueCandidateSource, CatalogueSourceArtifact
from app.modules.catalogue_ingestion.topology_models import (
    CatalogueCoverageCell,
    CatalogueScopeEdge,
    CatalogueScopeNode,
    CatalogueSourceScopeLink,
)

_DERIVED_TOPOLOGY_ORIGINS = {"resolved_claim", "candidate_source"}


def reset_derived_topology_for_artifacts(
    artifacts: Iterable[CatalogueSourceArtifact],
) -> uuid.UUID | None:
    """Remove only recomputable topology rows for the artifacts' candidate.

    Manual/reviewed topology and applicability rows are preserved. Coverage cells are always
    derived and are rebuilt from the current claims/topology snapshot.
    """

    artifact_list = list(artifacts)
    session, candidate_id = _candidate_context(artifact_list)
    if session is None or candidate_id is None:
        return None

    for cell in session.scalars(
        select(CatalogueCoverageCell).where(CatalogueCoverageCell.candidate_id == candidate_id)
    ):
        session.delete(cell)

    remaining_links: list[CatalogueSourceScopeLink] = []
    for link in session.scalars(
        select(CatalogueSourceScopeLink).where(
            CatalogueSourceScopeLink.candidate_id == candidate_id
        )
    ):
        provenance = link.provenance_json or {}
        if provenance.get("derived_from") in _DERIVED_TOPOLOGY_ORIGINS:
            session.delete(link)
        else:
            remaining_links.append(link)

    remaining_edges: list[CatalogueScopeEdge] = []
    for edge in session.scalars(
        select(CatalogueScopeEdge).where(CatalogueScopeEdge.candidate_id == candidate_id)
    ):
        provenance = edge.provenance_json or {}
        if provenance.get("derived_from") in _DERIVED_TOPOLOGY_ORIGINS:
            session.delete(edge)
        else:
            remaining_edges.append(edge)

    protected_node_ids = {link.scope_node_id for link in remaining_links}
    for edge in remaining_edges:
        protected_node_ids.add(edge.parent_node_id)
        protected_node_ids.add(edge.child_node_id)

    session.flush()
    for node in session.scalars(
        select(CatalogueScopeNode).where(CatalogueScopeNode.candidate_id == candidate_id)
    ):
        provenance = node.provenance_json or {}
        if _node_has_reviewed_state(node):
            protected_node_ids.add(node.id)
        if (
            provenance.get("derived_from") == "resolved_claim"
            and node.id not in protected_node_ids
        ):
            session.delete(node)
    session.flush()
    return candidate_id


def _node_has_reviewed_state(node: CatalogueScopeNode) -> bool:
    provenance = node.provenance_json or {}
    return bool(
        node.expected_child_counts
        or node.expectation_provenance
        or provenance.get("objective_applicability")
        or provenance.get("objective_applicability_provenance")
        or provenance.get("reviewed")
        or provenance.get("manual")
    )


def _candidate_context(
    artifacts: list[CatalogueSourceArtifact],
) -> tuple[Session | None, uuid.UUID | None]:
    sessions = {object_session(item) for item in artifacts if object_session(item) is not None}
    if len(sessions) != 1:
        return None, None
    session = next(iter(sessions))
    assert session is not None
    source_ids = {item.source_id for item in artifacts}
    if not source_ids:
        return session, None
    candidate_ids = set(
        session.scalars(
            select(CatalogueCandidateSource.candidate_id).where(
                CatalogueCandidateSource.id.in_(source_ids)
            )
        )
    )
    if len(candidate_ids) != 1:
        return session, None
    return session, next(iter(candidate_ids))
