"""Dynamic XML Sitemap (sitemap.xml) and robots.txt generator for SEO indexability."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.opportunities.directory import _slugify
from app.modules.opportunities.models import Opportunity, OpportunityStatus


def generate_sitemap_xml(
    session: Session,
    *,
    base_url: str = "https://scholarshipai.app",
) -> str:
    """Generate a standard sitemap.xml conforming to the sitemaps.org protocol."""
    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    now_iso = datetime.now(UTC).strftime("%Y-%m-%d")

    # 1. Main Static Hub Pages
    static_routes = [
        ("/", "1.0", "daily"),
        ("/scholarships", "0.9", "daily"),
        ("/matches", "0.8", "weekly"),
        ("/calendar", "0.8", "daily"),
    ]

    for path, priority, freq in static_routes:
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = f"{base_url}{path}"
        ET.SubElement(url_el, "lastmod").text = now_iso
        ET.SubElement(url_el, "changefreq").text = freq
        ET.SubElement(url_el, "priority").text = priority

    # 2. Dynamic Country & Degree Category Hubs
    opportunities = list(
        session.scalars(select(Opportunity).where(Opportunity.status == OpportunityStatus.ACTIVE))
    )

    countries = sorted(list(set(opp.country for opp in opportunities if opp.country)))
    for country in countries:
        country_slug = _slugify(country)
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = f"{base_url}/scholarships/country/{country_slug}"
        ET.SubElement(url_el, "lastmod").text = now_iso
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.8"

    # 3. Individual 500+ Scholarship Landing Pages
    for opp in opportunities:
        country_name = opp.country or "International"
        country_slug = _slugify(country_name)
        opp_slug = _slugify(opp.name)
        opp_url = f"{base_url}/scholarships/{country_slug}/{opp_slug}"

        lastmod = opp.last_verified_at.strftime("%Y-%m-%d") if opp.last_verified_at else now_iso

        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = opp_url
        ET.SubElement(url_el, "lastmod").text = lastmod
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.7"

    xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content = ET.tostring(urlset, encoding="utf-8").decode("utf-8")
    return xml_declaration + xml_content


def generate_robots_txt(*, base_url: str = "https://scholarshipai.app") -> str:
    """Generate standard robots.txt for search engines."""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /scholarships\n"
        "Allow: /scholarships/*\n"
        "Allow: /sitemap.xml\n"
        "Disallow: /api/\n"
        "Disallow: /dashboard\n"
        "Disallow: /admin\n"
        "Disallow: /auth/\n"
        "\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
