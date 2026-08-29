"""Deterministic claim validation, conflict handling, and MEXT completeness gates."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable

from app.modules.catalogue_ingestion.claim_schemas import (
    SUPPORTED_CLAIM_FIELDS,
    ClaimEntityType,
    ClaimExtractionLineage,
    ClaimResolution,
    ExtractedClaim,
    ResolvedClaim,
)
from app.modules.catalogue_ingestion.models import CatalogueSourceArtifact


def resolve_claims(
    extracted: Iterable[
        tuple[CatalogueSourceArtifact, int, list[ExtractedClaim]]
        | tuple[
            CatalogueSourceArtifact,
            int,
            list[ExtractedClaim],
            ClaimExtractionLineage,
        ]
    ],
    *,
    require_detail: bool = False,
    objective_coverage: dict[str, str] | None = None,
) -> ClaimResolution:
    extracted_items = list(extracted)
    programme_aliases = _programme_aliases(extracted_items)
    spurious_programme_keys = _scholarship_umbrella_programme_keys(extracted_items)
    cycle_aliases = _cycle_aliases(extracted_items)
    candidates: dict[tuple[str, str, str, str], list[ResolvedClaim]] = defaultdict(list)
    rejected: list[str] = []
    for item in extracted_items:
        artifact, trust_tier, claims = item[:3]
        extraction = item[3] if len(item) == 4 else None
        for claim in claims:
            if (
                claim.entity_type is ClaimEntityType.PROGRAMME
                and claim.entity_key in spurious_programme_keys
            ):
                rejected.append(
                    f"{artifact.id}:programme:{claim.entity_key}:{claim.field_path}:"
                    "scholarship_umbrella_misclassified"
                )
                continue
            original_programme_key = (
                claim.entity_key if claim.entity_type is ClaimEntityType.PROGRAMME else None
            )
            claim = _canonicalize_programme_aliases(claim, programme_aliases)
            if (
                original_programme_key in programme_aliases
                and claim.field_path in {"name", "degree_levels"}
            ):
                continue
            if claim.field_path not in SUPPORTED_CLAIM_FIELDS[claim.entity_type]:
                rejected.append(
                    f"{artifact.id}:{claim.entity_type.value}:{claim.entity_key}:"
                    f"{claim.field_path}:unsupported_field_path"
                )
                continue
            if not _valid_evidence_span(artifact.normalized_text, claim):
                rejected.append(
                    f"{artifact.id}:{claim.entity_type.value}:{claim.entity_key}:"
                    f"{claim.field_path}:evidence_span_invalid"
                )
                continue
            semantic_error = _semantic_claim_error(claim, artifact=artifact)
            if semantic_error is not None:
                rejected.append(
                    f"{artifact.id}:{claim.entity_type.value}:{claim.entity_key}:"
                    f"{claim.field_path}:{semantic_error}"
                )
                continue
            claim = _canonicalize_cycle_aliases(claim, cycle_aliases)
            scope_key = json.dumps(claim.scope.model_dump(), sort_keys=True)
            key = (claim.entity_type.value, claim.entity_key, claim.field_path, scope_key)
            candidates[key].append(
                ResolvedClaim(
                    claim=claim,
                    artifact_id=str(artifact.id),
                    source_id=str(artifact.source_id),
                    source_url=artifact.final_url,
                    content_hash=artifact.content_hash,
                    trust_tier=trust_tier,
                    extraction=extraction,
                )
            )

    resolved: list[ResolvedClaim] = []
    conflicts: list[str] = []
    for key in sorted(candidates):
        values = candidates[key]
        best_tier = min(item.trust_tier for item in values)
        best = [item for item in values if item.trust_tier == best_tier]
        by_value: dict[str, list[ResolvedClaim]] = defaultdict(list)
        for item in best:
            normalized = _resolution_value_key(item.claim)
            by_value[normalized].append(item)
        if len(by_value) > 1 and not _allows_multiple_values(best[0].claim):
            conflicts.append(":".join(key[:3]) + ":same_tier_conflict")
            continue
        selected_groups = (
            by_value.values() if len(by_value) > 1 else [next(iter(by_value.values()))]
        )
        for group in selected_groups:
            # Duplicate evidence should collapse only within one normalized value.
            # Different additive values (for example masters and doctoral) may be
            # explicitly supported by the same sentence and must both survive.
            seen_evidence: set[tuple[str, int, int]] = set()
            for item in group:
                evidence_key = (
                    item.artifact_id,
                    item.claim.excerpt_start,
                    item.claim.excerpt_end,
                )
                if evidence_key not in seen_evidence:
                    resolved.append(item)
                    seen_evidence.add(evidence_key)

    scoped_types = {
        ClaimEntityType.DEADLINE,
        ClaimEntityType.FUNDING,
        ClaimEntityType.DOCUMENT,
        ClaimEntityType.STEP,
    }
    scopes_by_key: dict[tuple[ClaimEntityType, str, str], set[str]] = defaultdict(set)
    for item in resolved:
        claim = item.claim
        if claim.entity_type in scoped_types:
            scopes_by_key[(claim.entity_type, claim.entity_key, claim.field_path)].add(
                json.dumps(claim.scope.model_dump(), sort_keys=True)
            )
    if not require_detail:
        for key, scopes in sorted(
            scopes_by_key.items(), key=lambda item: tuple(str(value) for value in item[0])
        ):
            if len(scopes) > 1:
                conflicts.append(f"{key[0].value}:{key[1]}:{key[2]}:ambiguous_scope_key")

    intake_years = {
        str(item.claim.value.primitive())
        for item in resolved
        if item.claim.entity_type is ClaimEntityType.CYCLE
        and item.claim.field_path == "intake_year"
    }
    scoped_cycles = {
        item.claim.scope.cycle_key for item in resolved if item.claim.scope.cycle_key is not None
    }
    if len(intake_years) > 1:
        conflicts.append("cycle:intake_year:multiple_cycles")
    if len(scoped_cycles) > 1:
        conflicts.append("cycle:scope:multiple_cycles")

    completeness = (
        detail_completeness_errors(resolved, objective_coverage or {})
        if require_detail
        else mext_completeness_errors(resolved)
    )
    return ClaimResolution(
        resolved=resolved,
        conflicts=sorted(set(conflicts)),
        rejected=rejected,
        completeness_errors=completeness,
        objective_coverage=objective_coverage or {},
    )


def _cycle_aliases(
    extracted: list[
        tuple[CatalogueSourceArtifact, int, list[ExtractedClaim]]
        | tuple[
            CatalogueSourceArtifact,
            int,
            list[ExtractedClaim],
            ClaimExtractionLineage,
        ]
    ],
) -> dict[str, int]:
    years_by_alias: dict[str, set[int]] = defaultdict(set)
    for item in extracted:
        artifact, _trust_tier, claims = item[:3]
        for claim in claims:
            if (
                claim.entity_type is ClaimEntityType.CYCLE
                and claim.field_path == "intake_year"
                and _valid_evidence_span(artifact.normalized_text, claim)
                and _semantic_claim_error(claim) is None
            ):
                value = claim.value.primitive()
                if isinstance(value, int):
                    years_by_alias[claim.entity_key].add(value)
    return {alias: next(iter(years)) for alias, years in years_by_alias.items() if len(years) == 1}


def _canonicalize_cycle_aliases(
    claim: ExtractedClaim, cycle_aliases: dict[str, int]
) -> ExtractedClaim:
    entity_key = (
        "scholarship" if claim.entity_type is ClaimEntityType.SCHOLARSHIP else claim.entity_key
    )
    if claim.entity_type is ClaimEntityType.CYCLE and entity_key in cycle_aliases:
        entity_key = f"intake_{cycle_aliases[entity_key]}"
    scope = claim.scope
    if scope.cycle_key in cycle_aliases:
        scope = scope.model_copy(update={"cycle_key": f"intake_{cycle_aliases[scope.cycle_key]}"})
    elif scope.cycle_key is not None and len(set(cycle_aliases.values())) == 1:
        intake_year = next(iter(cycle_aliases.values()))
        scope_years = {int(value) for value in re.findall(r"(?:19|20)\d{2}", scope.cycle_key)}
        if intake_year in scope_years:
            scope = scope.model_copy(update={"cycle_key": f"intake_{intake_year}"})
    elif (
        scope.cycle_key is not None
        and scope.cycle_key.isdigit()
        and int(scope.cycle_key) in cycle_aliases.values()
    ):
        scope = scope.model_copy(update={"cycle_key": f"intake_{int(scope.cycle_key)}"})
    if entity_key == claim.entity_key and scope is claim.scope:
        return claim
    return claim.model_copy(update={"entity_key": entity_key, "scope": scope})


def _programme_aliases(
    extracted: list[
        tuple[CatalogueSourceArtifact, int, list[ExtractedClaim]]
        | tuple[
            CatalogueSourceArtifact,
            int,
            list[ExtractedClaim],
            ClaimExtractionLineage,
        ]
    ],
) -> dict[str, str]:
    fields_by_key: dict[str, set[str]] = defaultdict(set)
    degree_levels_by_key: dict[str, set[str]] = defaultdict(set)
    best_trust_by_key: dict[str, int] = {}
    referenced_keys: set[str] = set()
    for item in extracted:
        artifact, trust_tier, claims = item[:3]
        for claim in claims:
            if claim.entity_type is ClaimEntityType.PROGRAMME:
                referenced_keys.add(claim.entity_key)
                if (
                    claim.field_path in {"name", "degree_levels"}
                    and _valid_evidence_span(artifact.normalized_text, claim)
                    and _semantic_claim_error(claim, artifact=artifact) is None
                ):
                    fields_by_key[claim.entity_key].add(claim.field_path)
                    best_trust_by_key[claim.entity_key] = min(
                        trust_tier,
                        best_trust_by_key.get(claim.entity_key, trust_tier),
                    )
                    if claim.field_path == "degree_levels":
                        degree_levels = claim.value.primitive()
                        if isinstance(degree_levels, list):
                            degree_levels_by_key[claim.entity_key].update(
                                _normalized_degree_level(value) for value in degree_levels
                            )
            if claim.scope.programme_key:
                referenced_keys.add(claim.scope.programme_key)
    canonical_keys = {
        key
        for key, fields in fields_by_key.items()
        if {"name", "degree_levels"}.issubset(fields)
    }
    aliases: dict[str, str] = {}
    for degree_level in ("bachelors", "masters", "phd"):
        same_degree = [
            key
            for key in canonical_keys
            if degree_levels_by_key[key] == {degree_level}
        ]
        if len(same_degree) < 2:
            continue
        canonical = min(
            same_degree,
            key=lambda key: (best_trust_by_key.get(key, 1_000_000), len(key), key),
        )
        aliases.update({key: canonical for key in same_degree if key != canonical})

    surviving_canonical_keys = canonical_keys - aliases.keys()
    for key in referenced_keys - surviving_canonical_keys:
        if key in aliases:
            continue
        alias_tokens = _programme_key_tokens(key)
        matches = [
            canonical
            for canonical in surviving_canonical_keys
            if alias_tokens
            and (
                alias_tokens.issubset(_programme_key_tokens(canonical))
                or _programme_key_tokens(canonical).issubset(alias_tokens)
            )
        ]
        if len(matches) == 1:
            aliases[key] = matches[0]
            continue
        inferred_levels = _programme_key_degree_levels(key)
        degree_matches = [
            canonical
            for canonical in surviving_canonical_keys
            if inferred_levels & degree_levels_by_key[canonical]
        ]
        if len(degree_matches) == 1:
            aliases[key] = degree_matches[0]
    return aliases


def _programme_key_tokens(value: str) -> frozenset[str]:
    ignored = {"degree", "programme", "program", "scholarship", "student"}
    return frozenset(
        token.removesuffix("s")
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if token.removesuffix("s") not in ignored
    )


def _scholarship_umbrella_programme_keys(
    extracted: list[
        tuple[CatalogueSourceArtifact, int, list[ExtractedClaim]]
        | tuple[
            CatalogueSourceArtifact,
            int,
            list[ExtractedClaim],
            ClaimExtractionLineage,
        ]
    ],
) -> set[str]:
    scholarship_names: set[str] = set()
    programme_names: dict[str, set[str]] = defaultdict(set)
    programme_degree_keys: set[str] = set()
    for item in extracted:
        artifact, _trust_tier, claims = item[:3]
        for claim in claims:
            if not _valid_evidence_span(artifact.normalized_text, claim):
                continue
            primitive = claim.value.primitive()
            if (
                claim.entity_type is ClaimEntityType.SCHOLARSHIP
                and claim.field_path == "name"
                and isinstance(primitive, str)
            ):
                scholarship_names.add(_normalized_entity_name(primitive))
            elif claim.entity_type is ClaimEntityType.PROGRAMME:
                if claim.field_path == "name" and isinstance(primitive, str):
                    programme_names[claim.entity_key].add(_normalized_entity_name(primitive))
                elif claim.field_path == "degree_levels" and isinstance(primitive, list):
                    programme_degree_keys.add(claim.entity_key)
    return {
        key
        for key, names in programme_names.items()
        if key not in programme_degree_keys and names.intersection(scholarship_names)
    }


def _normalized_entity_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _normalized_degree_level(value: object) -> str:
    normalized = re.sub(r"[^a-z]+", "", str(value).casefold())
    aliases = {
        "bachelor": "bachelors",
        "bachelors": "bachelors",
        "undergraduate": "bachelors",
        "master": "masters",
        "masters": "masters",
        "postgraduate": "masters",
        "doctoral": "phd",
        "doctorate": "phd",
        "phd": "phd",
        "research": "phd",
    }
    return aliases.get(normalized, normalized)


def _programme_key_degree_levels(value: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", value.casefold())
    return {
        normalized
        for token in tokens
        if (normalized := _normalized_degree_level(token)) in {"bachelors", "masters", "phd"}
    }


def _canonicalize_programme_aliases(
    claim: ExtractedClaim, aliases: dict[str, str]
) -> ExtractedClaim:
    entity_key = claim.entity_key
    if claim.entity_type is ClaimEntityType.PROGRAMME:
        entity_key = aliases.get(entity_key, entity_key)
    scope = claim.scope
    if scope.programme_key in aliases:
        scope = scope.model_copy(update={"programme_key": aliases[scope.programme_key]})
    if entity_key == claim.entity_key and scope is claim.scope:
        return claim
    return claim.model_copy(update={"entity_key": entity_key, "scope": scope})


def mext_completeness_errors(claims: list[ResolvedClaim]) -> list[str]:
    present = {(item.claim.entity_type, item.claim.field_path) for item in claims}
    errors: list[str] = []
    required = {
        (ClaimEntityType.SCHOLARSHIP, "name"),
        (ClaimEntityType.SCHOLARSHIP, "provider_name"),
        (ClaimEntityType.SCHOLARSHIP, "country_code"),
        (ClaimEntityType.SCHOLARSHIP, "degree_levels"),
        (ClaimEntityType.CYCLE, "intake_year"),
    }
    for entity_type, field_path in sorted(required, key=lambda item: (item[0].value, item[1])):
        if (entity_type, field_path) not in present:
            errors.append(f"missing:{entity_type.value}.{field_path}")

    track_keys = {
        item.claim.entity_key
        for item in claims
        if item.claim.entity_type is ClaimEntityType.TRACK and item.claim.field_path == "name"
    }
    for route in ("embassy_recommendation", "university_recommendation"):
        if route not in track_keys:
            errors.append(f"missing:track.{route}")

    for entity_type in (
        ClaimEntityType.FUNDING,
        ClaimEntityType.DOCUMENT,
        ClaimEntityType.STEP,
    ):
        if not any(item.claim.entity_type is entity_type for item in claims):
            errors.append(f"missing:{entity_type.value}")
    return errors


def detail_completeness_errors(
    claims: list[ResolvedClaim], objective_coverage: dict[str, str]
) -> list[str]:
    present = {(item.claim.entity_type, item.claim.field_path) for item in claims}
    errors: list[str] = []
    required_fields = {
        (ClaimEntityType.SCHOLARSHIP, "name"),
        (ClaimEntityType.SCHOLARSHIP, "provider_name"),
        (ClaimEntityType.SCHOLARSHIP, "country_code"),
        (ClaimEntityType.CYCLE, "intake_year"),
        (ClaimEntityType.PROGRAMME, "name"),
        (ClaimEntityType.PROGRAMME, "degree_levels"),
        (ClaimEntityType.TRACK, "name"),
        (ClaimEntityType.ELIGIBILITY, "rule_type"),
        (ClaimEntityType.ELIGIBILITY, "value"),
        (ClaimEntityType.FUNDING, "component_type"),
        (ClaimEntityType.DOCUMENT, "name"),
        (ClaimEntityType.DEADLINE, "deadline_type"),
        (ClaimEntityType.STEP, "title"),
    }
    for entity_type, field_path in sorted(
        required_fields, key=lambda item: (item[0].value, item[1])
    ):
        if (entity_type, field_path) not in present:
            errors.append(f"missing:{entity_type.value}.{field_path}")

    programme_fields: dict[str, set[str]] = defaultdict(set)
    for item in claims:
        if (
            item.claim.entity_type is ClaimEntityType.PROGRAMME
            and item.claim.scope.programme_family_key is None
        ):
            programme_fields[item.claim.entity_key].add(item.claim.field_path)
    identified_programme_keys = {
        programme_key
        for programme_key, fields in programme_fields.items()
        if {"name", "degree_levels"} & fields
    }
    for programme_key in sorted(identified_programme_keys):
        fields = programme_fields[programme_key]
        for field_path in ("name", "degree_levels"):
            if field_path not in fields:
                errors.append(f"missing:programme.{programme_key}.{field_path}")

    if len(identified_programme_keys) > 1:
        scoped_requirements = {
            ClaimEntityType.ELIGIBILITY: "eligibility",
            ClaimEntityType.DOCUMENT: "document",
            ClaimEntityType.FUNDING: "funding",
            ClaimEntityType.STEP: "step",
        }
        for programme_key in sorted(identified_programme_keys):
            for entity_type, label in scoped_requirements.items():
                if not any(
                    item.claim.entity_type is entity_type
                    and item.claim.scope.programme_key in {None, programme_key}
                    for item in claims
                ):
                    errors.append(f"missing:programme.{programme_key}.{label}")

    for objective in (
        "identity",
        "programmes",
        "programme_details",
        "routes",
        "eligibility",
        "eligibility_context",
        "documents_core",
        "documents_requirements",
        "documents_counts",
        "documents_format",
        "funding",
        "application_timeline",
    ):
        if objective_coverage.get(objective) not in {"complete", "not_applicable"}:
            errors.append(f"incomplete_objective:{objective}")
    return errors


def _valid_evidence_span(text: str, claim: ExtractedClaim) -> bool:
    return (
        claim.excerpt_end <= len(text)
        and text[claim.excerpt_start : claim.excerpt_end] == claim.excerpt
    )


def _semantic_claim_error(
    claim: ExtractedClaim, *, artifact: CatalogueSourceArtifact | None = None
) -> str | None:
    excerpt = claim.excerpt.casefold()
    primitive = claim.value.primitive()
    if claim.entity_type is ClaimEntityType.PROGRAMME and claim.field_path in {
        "duration",
        "fields_of_study",
        "application_route_keys",
    }:
        values = primitive if isinstance(primitive, list) else [primitive]
        normalized_values = {
            re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()
            for value in values
        }
        if normalized_values and normalized_values <= {
            "not applicable",
            "not available",
            "not specified",
            "not stated",
            "unknown",
        }:
            return "placeholder_not_evidence"
    if claim.entity_type is ClaimEntityType.CYCLE and claim.field_path == "intake_year":
        value = claim.value.primitive()
        if not isinstance(value, int) or str(value) not in excerpt:
            return "intake_year_evidence_mismatch"
        if not re.search(
            r"\b(?:academic|application|arrival|arrive|arriving|enrol\w*|fiscal|fy|intake|"
            r"programmes?|programs?|recruit|scholarships?\s+(?:are\s+)?for|"
            r"study\s+(?:beginning|starting))",
            excerpt,
        ):
            return "intake_year_context_missing"
    if claim.entity_type is ClaimEntityType.TRACK and claim.field_path == "name":
        if claim.entity_key == "embassy_recommendation" and not (
            "embassy" in excerpt and "recommend" in excerpt
        ):
            return "embassy_route_evidence_mismatch"
        if claim.entity_key == "university_recommendation" and not (
            "university" in excerpt and "recommend" in excerpt
        ):
            return "university_route_evidence_mismatch"
    if claim.entity_type is ClaimEntityType.TRACK and claim.field_path == "track_type":
        if claim.entity_key == "embassy_recommendation" and not (
            ("embassy" in excerpt and "recommend" in excerpt) or "diplomatic mission" in excerpt
        ):
            return "embassy_route_evidence_mismatch"
        if claim.entity_key == "university_recommendation" and not (
            "university" in excerpt and "recommend" in excerpt
        ):
            return "university_route_evidence_mismatch"
    if (
        claim.entity_type is ClaimEntityType.PROGRAMME
        and claim.field_path == "duration"
        and re.search(
            r"\b(?:physical examination|foreigner physical examination|"
            r"submit (?:a )?(?:copy|photocopy)|form (?:is )?valid|"
            r"(?:medical|examination|certificate)\w*[^.]{0,40}\bvalid for)\b",
            excerpt,
        )
    ):
        return "programme_duration_context_mismatch"
    if (
        claim.entity_type is ClaimEntityType.PROGRAMME
        and claim.field_path == "fields_of_study"
        and re.search(
            r"\b(?:hsk|language proficiency|language requirement|proficiency test|"
            r"test score|ielts|toefl)\b",
            excerpt,
        )
    ):
        return "programme_field_context_mismatch"
    if claim.entity_type is ClaimEntityType.PROGRAMME and claim.field_path == "fields_of_study":
        values = primitive if isinstance(primitive, list) else [primitive]
        normalized_values = {
            re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()
            for value in values
        }
        if normalized_values and normalized_values <= {
            "degree",
            "degree program",
            "degree programs",
            "degree programme",
            "degree programmes",
        }:
            return "programme_field_not_a_discipline"
    if (
        claim.entity_type is ClaimEntityType.PROGRAMME
        and claim.field_path == "application_route_keys"
        and isinstance(primitive, list)
        and (
            any(
                re.search(r"\b(?:language|preparatory|hsk|ielts|toefl)\b", str(value), re.I)
                for value in primitive
            )
            or re.search(
                r"\b(?:appl(?:y|ication)|submit|portal|route|embassy|"
                r"nominat(?:e|ed|ion)|recommend(?:ed|ation)?)\b",
                excerpt,
            )
            is None
        )
    ):
        return "programme_route_context_mismatch"
    if claim.entity_type is ClaimEntityType.FUNDING:
        funding_terms = re.compile(
            r"\b(?:tuition|fees?|stipend|allowance|funding|funded|financial(?:ly)?|"
            r"accommodation|dormitor(?:y|ies)|housing|insurance|medical cover|"
            r"travel|airfare|air ticket|subsid(?:y|ised|ized)|grant|living expenses?|"
            r"monthly payment|award (?:amount|value))\b|[$€£¥]\s*\d|"
            r"\b(?:usd|eur|gbp|cny|rmb|pkr|jpy)\s*\d",
        )
        if funding_terms.search(excerpt) is None:
            return "funding_context_missing"
    if claim.entity_type is ClaimEntityType.DEADLINE:
        event_terms = (
            "arriv",
            "depart",
            "first screening",
            "second screening",
            "notification of result",
            "scholarship period",
            "study period",
            "test date",
            "test will",
            "exam date",
            "examination date",
            "assessment date",
        )
        deadline_evidence = re.search(
            r"\b(?:deadline|cut[ -]?off|closing date|last date|due date|"
            r"applications? close[sd]?|application period|no later than|"
            r"on or before|before the application deadline|"
            r"(?:submit(?:ted)?|reach(?:ed)?)\s+(?:it\s+)?(?:on or before|by|before)\s+"
            r"(?:\d{1,2}\s+)?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|"
            r"apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|"
            r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?))\b",
            excerpt,
        )
        if (
            any(term in excerpt for term in event_terms)
            and deadline_evidence is None
        ):
            return "non_deadline_event_misclassified"
        if deadline_evidence is None:
            return "deadline_evidence_missing"
    if claim.entity_type is ClaimEntityType.EVENT and claim.field_path in {
        "starts_at",
        "ends_at",
        "date_text",
    }:
        event_subject = re.search(
            r"\b(?:arriv\w*|depart\w*|screening|result(?:s)?(?: announcement)?|"
            r"orientation|interview|enrol\w*|registration|"
            r"test|exam(?:ination)?|assessment|scholarship period|study period)\b",
            excerpt,
        )
        temporal_marker = re.search(
            r"\b(?:date|dates|held|scheduled|announced|"
            r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
            r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
            r"dec(?:ember)?|(?:19|20)\d{2})\b",
            excerpt,
        )
        if event_subject is None or temporal_marker is None:
            return "event_evidence_missing"
    if (
        claim.entity_type is ClaimEntityType.RESOURCE
        and claim.field_path == "url"
        and artifact is not None
    ):
        value = str(claim.value.primitive())
        links = artifact.fetch_metadata.get("links", [])
        allowed = {
            str(item.get("url")) for item in links if isinstance(item, dict) and item.get("url")
        }
        # PDFs and some government pages expose application URLs as plain text
        # rather than hyperlink annotations. Exact inclusion in the already
        # validated evidence span is sufficient provenance; an invented URL is
        # still rejected.
        cited_verbatim = value in claim.excerpt
        if value not in allowed and value != artifact.final_url and not cited_verbatim:
            return "resource_url_not_in_fetched_links"
    if claim.field_path in {
        "application_route_keys",
        "degree_levels",
        "fields_of_study",
    } and not isinstance(primitive, list):
        return "string_list_value_required"
    if (
        claim.entity_type is ClaimEntityType.PROGRAMME
        and claim.field_path == "duration"
        and not isinstance(primitive, str)
    ):
        return "single_duration_value_required"
    if claim.field_path in {
        "copy_count",
        "display_order",
        "form_year",
        "original_count",
    } and (not isinstance(primitive, int) or isinstance(primitive, bool)):
        return "integer_value_required"
    if claim.field_path in {"is_exclusion", "required"} and not isinstance(primitive, bool):
        return "boolean_value_required"
    return None


def _allows_multiple_values(claim: ExtractedClaim) -> bool:
    return (claim.entity_type, claim.field_path) in {
        (ClaimEntityType.TRACK, "application_method"),
        (ClaimEntityType.PROGRAMME, "degree_levels"),
        (ClaimEntityType.PROGRAMME, "description"),
        (ClaimEntityType.PROGRAMME, "duration"),
        (ClaimEntityType.PROGRAMME, "fields_of_study"),
        (ClaimEntityType.PROGRAMME, "application_route_keys"),
        (ClaimEntityType.ELIGIBILITY, "condition"),
        (ClaimEntityType.ELIGIBILITY, "notes"),
        (ClaimEntityType.FUNDING, "description"),
        (ClaimEntityType.DOCUMENT, "certification_requirement"),
        (ClaimEntityType.DOCUMENT, "condition"),
        (ClaimEntityType.DOCUMENT, "notes"),
        (ClaimEntityType.DOCUMENT, "translation_requirement"),
        (ClaimEntityType.DEADLINE, "notes"),
        (ClaimEntityType.EVENT, "notes"),
        (ClaimEntityType.STEP, "description"),
        (ClaimEntityType.RESOURCE, "notes"),
    }


def _resolution_value_key(claim: ExtractedClaim) -> str:
    value = claim.value.primitive()
    if (
        claim.entity_type is ClaimEntityType.SCHOLARSHIP
        and claim.field_path == "name"
        and isinstance(value, str)
    ):
        ignored = {"application", "for", "guideline", "guidelines", "programme", "the"}
        tokens = sorted(
            token
            for token in re.findall(r"[a-z0-9]+", value.casefold())
            if token not in ignored
        )
        return "scholarship-name:" + " ".join(tokens)
    return json.dumps(
        claim.value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
