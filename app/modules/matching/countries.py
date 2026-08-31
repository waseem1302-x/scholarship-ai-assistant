"""Country, nationality, and demonym resolution for intelligent scholarship matching."""

from __future__ import annotations

import re

# Comprehensive mapping: canonical_country_name -> (iso2, demonyms, aliases)
COUNTRY_DATABASE: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "Pakistan": ("PK", ("pakistani",), ("islamic republic of pakistan", "pak")),
    "United States": (
        "US",
        ("american", "us citizen"),
        ("usa", "united states of america", "u.s.", "u.s.a."),
    ),
    "United Kingdom": (
        "GB",
        ("british", "uk citizen"),
        ("uk", "great britain", "england", "scotland", "wales"),
    ),
    "Canada": ("CA", ("canadian",), ("can",)),
    "Australia": ("AU", ("australian",), ("aus",)),
    "Germany": ("DE", ("german",), ("deutschland", "deu", "ger")),
    "France": ("FR", ("french",), ("fra",)),
    "Japan": ("JP", ("japanese",), ("nippon", "nihon", "jpn")),
    "China": ("CN", ("chinese",), ("prc", "people's republic of china", "chn")),
    "India": ("IN", ("indian",), ("ind", "bharat")),
    "Bangladesh": ("BD", ("bangladeshi",), ("bgd",)),
    "Nigeria": ("NG", ("nigerian",), ("nga",)),
    "Ghana": ("GH", ("ghanaian",), ("gha",)),
    "Kenya": ("KE", ("kenyan",), ("ken",)),
    "South Africa": ("ZA", ("south african",), ("rsa", "zaf")),
    "Egypt": ("EG", ("egyptian",), ("egy",)),
    "Saudi Arabia": ("SA", ("saudi", "saudi arabian"), ("ksa", "sau")),
    "United Arab Emirates": ("AE", ("emirati", "uae citizen"), ("uae", "are")),
    "Turkey": ("TR", ("turkish",), ("turkiye", "tur")),
    "Indonesia": ("ID", ("indonesian",), ("idn",)),
    "Malaysia": ("MY", ("malaysian",), ("mys",)),
    "Singapore": ("SG", ("singaporean",), ("sgp",)),
    "South Korea": ("KR", ("korean", "south korean"), ("republic of korea", "kor")),
    "Italy": ("IT", ("italian",), ("ita",)),
    "Spain": ("ES", ("spanish",), ("esp", "espana")),
    "Netherlands": ("NL", ("dutch",), ("holland", "nld")),
    "Sweden": ("SE", ("swedish",), ("swe",)),
    "Switzerland": ("CH", ("swiss",), ("che",)),
    "Norway": ("NO", ("norwegian",), ("nor",)),
    "Denmark": ("DK", ("danish",), ("dnk",)),
    "Finland": ("FI", ("finnish",), ("fin",)),
    "Brazil": ("BR", ("brazilian",), ("bra", "brasil")),
    "Mexico": ("MX", ("mexican",), ("mex",)),
    "Argentina": ("AR", ("argentine", "argentinian"), ("arg",)),
    "Colombia": ("CO", ("colombian",), ("col",)),
    "New Zealand": ("NZ", ("new zealander", "kiwi"), ("nzl",)),
    "Ireland": ("IE", ("irish",), ("irl", "republic of ireland")),
    "Vietnam": ("VN", ("vietnamese",), ("vnm",)),
    "Thailand": ("TH", ("thai",), ("tha",)),
    "Philippines": ("PH", ("filipino", "philippine"), ("phl",)),
    "Sri Lanka": ("LK", ("sri lankan",), ("lka",)),
    "Nepal": ("NP", ("nepali", "nepalese"), ("npl",)),
    "Iran": ("IR", ("iranian",), ("persian", "irn")),
    "Iraq": ("IQ", ("iraqi",), ("irq",)),
    "Jordan": ("JO", ("jordanian",), ("jor",)),
    "Lebanon": ("LB", ("lebanese",), ("lbn",)),
    "Morocco": ("MA", ("moroccan",), ("mar",)),
    "Algeria": ("DZ", ("algerian",), ("dza",)),
}

# Reverse index: normalized string -> canonical (iso2, country_name)
_LOOKUP: dict[str, tuple[str, str]] = {}

for country_name, (iso2, demonyms, aliases) in COUNTRY_DATABASE.items():
    norm_name = country_name.lower().strip()
    _LOOKUP[norm_name] = (iso2, country_name)
    _LOOKUP[iso2.lower()] = (iso2, country_name)
    for demonym in demonyms:
        _LOOKUP[demonym.lower().strip()] = (iso2, country_name)
    for alias in aliases:
        _LOOKUP[alias.lower().strip()] = (iso2, country_name)


def resolve_canonical_country(value: str | None) -> tuple[str, str] | None:
    """Resolve a nationality string, demonym, ISO code, or country name to (ISO2, CountryName)."""
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value.lower().strip())
    if not cleaned:
        return None
    if cleaned in _LOOKUP:
        return _LOOKUP[cleaned]
    # Check word boundaries for demonyms (e.g. "Pakistani citizen" -> "Pakistani")
    for key, result in _LOOKUP.items():
        if len(key) >= 4 and (key == cleaned or key in cleaned or cleaned in key):
            return result
    return None


def match_nationality_or_country(
    student_val: str | None,
    required_val: list[str] | str,
    *,
    is_exclusion: bool = False,
) -> bool:
    """Match student nationality/country against allowed or excluded lists.

    Args:
        student_val: Student's nationality, country of residence, or ISO2 code.
        required_val: List of eligible countries/nationalities or a single country string.
        is_exclusion: True if this is an exclusion list (NOT_IN rule).

    Returns:
        Boolean indicating whether the nationality criteria is satisfied.
    """
    if not student_val:
        return False

    req_list = [required_val] if isinstance(required_val, str) else list(required_val)
    if not req_list:
        return not is_exclusion

    # Handle "any", "all", "international", "all countries"
    cleaned_req = [str(r).lower().strip() for r in req_list]
    if any(r in {"any", "all", "international", "all countries", "open"} for r in cleaned_req):
        return not is_exclusion

    student_res = resolve_canonical_country(student_val)
    student_iso2 = student_res[0] if student_res else None
    student_norm = student_val.lower().strip()

    matched = False
    for req in req_list:
        req_norm = str(req).lower().strip()
        req_res = resolve_canonical_country(req_norm)
        req_iso2 = req_res[0] if req_res else None

        if student_iso2 and req_iso2 and student_iso2 == req_iso2:
            matched = True
            break
        if student_norm == req_norm or student_norm in req_norm or req_norm in student_norm:
            matched = True
            break

    return not matched if is_exclusion else matched
