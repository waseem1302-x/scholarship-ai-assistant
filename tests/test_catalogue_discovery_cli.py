import uuid

from app.cli.discover_catalogue_sources import parser


def test_discovery_cli_is_candidate_scoped_and_bounded_by_default() -> None:
    candidate_id = uuid.uuid4()

    args = parser().parse_args(["--candidate", str(candidate_id)])

    assert args.candidate == candidate_id
    assert args.resume is None
    assert args.max_queries == 1
    assert args.dry_run is True
