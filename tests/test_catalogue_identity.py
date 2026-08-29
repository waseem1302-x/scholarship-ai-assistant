from app.modules.opportunities.catalogue_identity import (
    CATALOGUE_IDENTITY_POLICY_VERSION,
    build_catalogue_identity,
    normalize_catalogue_alias,
)


def _identity(
    *,
    family: str,
    route: str,
    host: str | None,
    country: str,
    degree: str,
    cycle: str,
):
    return build_catalogue_identity(
        provider_canonical_id="official-provider",
        programme_family_id=family,
        programme_route_id=route,
        host_institution=host,
        destination_country=country,
        degree_level=degree,
        cycle_id=cycle,
    )


def test_identity_key_is_stable_and_cycle_is_scoped_below_timeless_route() -> None:
    first = _identity(
        family="daad-epos",
        route="development-studies",
        host="Example University",
        country="DE",
        degree="masters",
        cycle="2027",
    )
    retry = _identity(
        family="DAAD EPOS",
        route="Development Studies",
        host="example university",
        country="de",
        degree="MASTERS",
        cycle="2027",
    )
    next_cycle = _identity(
        family="daad-epos",
        route="development-studies",
        host="Example University",
        country="DE",
        degree="masters",
        cycle="2028",
    )

    assert first == retry
    assert first.policy_version == CATALOGUE_IDENTITY_POLICY_VERSION
    assert first.family_key == next_cycle.family_key
    assert first.route_key == next_cycle.route_key
    assert first.identity_key != next_cycle.identity_key


def test_legitimate_family_routes_remain_distinct() -> None:
    csc_a = _identity(
        family="csc",
        route="university-route",
        host="University A",
        country="CN",
        degree="masters",
        cycle="2027",
    )
    csc_b = _identity(
        family="csc",
        route="university-route",
        host="University B",
        country="CN",
        degree="masters",
        cycle="2027",
    )
    daad_a = _identity(
        family="daad-epos",
        route="development-studies",
        host=None,
        country="DE",
        degree="masters",
        cycle="2027",
    )
    daad_b = _identity(
        family="daad-epos",
        route="public-policy",
        host=None,
        country="DE",
        degree="masters",
        cycle="2027",
    )
    erasmus_a = _identity(
        family="erasmus-mundus",
        route="joint-master-data-science",
        host=None,
        country="EU",
        degree="masters",
        cycle="2027",
    )
    erasmus_b = _identity(
        family="erasmus-mundus",
        route="joint-master-public-health",
        host=None,
        country="EU",
        degree="masters",
        cycle="2027",
    )

    assert len(
        {
            csc_a.identity_key,
            csc_b.identity_key,
            daad_a.identity_key,
            daad_b.identity_key,
            erasmus_a.identity_key,
            erasmus_b.identity_key,
        }
    ) == 6
    assert csc_a.family_key == csc_b.family_key
    assert daad_a.family_key == daad_b.family_key
    assert erasmus_a.family_key == erasmus_b.family_key


def test_alias_normalization_is_conservative() -> None:
    assert normalize_catalogue_alias("  DAAD—EPOS Programme ") == "daad-epos"
    assert normalize_catalogue_alias("DAAD EPOS Scholarships") == "daad-epos"
    assert normalize_catalogue_alias("DAAD EPOS Public Policy") != normalize_catalogue_alias(
        "DAAD EPOS Development Studies"
    )
