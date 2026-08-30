"""Version identities for the routed paid catalogue extraction pipeline."""

BUNDLE_PROVIDER_PARSER_VERSION = "catalogue-provider-parser.v1.claim-bundle.v1"
BUNDLE_NORMALIZER_VERSION = "catalogue-provider-normalizer.v1.claim-bundle.v1"
BUNDLE_RESOLVER_VERSION = "catalogue-claim-resolution.v1"
BUNDLE_VALIDATOR_VERSION = "catalogue-claim-bundle-validation.v1"

__all__ = [
    "BUNDLE_NORMALIZER_VERSION",
    "BUNDLE_PROVIDER_PARSER_VERSION",
    "BUNDLE_RESOLVER_VERSION",
    "BUNDLE_VALIDATOR_VERSION",
]
