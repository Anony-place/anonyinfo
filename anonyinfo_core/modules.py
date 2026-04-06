from __future__ import annotations

import asyncio
import socket
import time
from abc import ABC, abstractmethod
from io import BytesIO
from urllib.parse import urlparse
from typing import Dict, Iterable, List, Sequence

import aiohttp
import dns.resolver
import exifread
import phonenumbers
import requests
from phonenumbers import carrier, geocoder

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from .models import Artifact, Entity, Finding, ModuleResult, Relationship


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

SOCIAL_PLATFORMS = {
    "GitHub": "https://github.com/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Twitch": "https://www.twitch.tv/{}",
    "Reddit": "https://www.reddit.com/user/{}",
    "Medium": "https://medium.com/@{}",
    "Pinterest": "https://www.pinterest.com/{}",
    "Tumblr": "https://{}.tumblr.com",
    "Twitter/X": "https://x.com/{}",
    "Telegram": "https://t.me/{}",
    "TikTok": "https://www.tiktok.com/@{}",
    "Instagram": "https://www.instagram.com/{}/",
    "Facebook": "https://www.facebook.com/{}",
    "Threads": "https://www.threads.net/@{}",
    "LinkedIn": "https://www.linkedin.com/in/{}",
    "Behance": "https://www.behance.net/{}",
    "Dribbble": "https://dribbble.com/{}",
    "ProductHunt": "https://www.producthunt.com/@{}",
    "Goodreads": "https://www.goodreads.com/{}",
    "Strava": "https://www.strava.com/athletes/{}",
    "HackerOne": "https://hackerone.com/{}",
    "LeetCode": "https://leetcode.com/{}",
    "StackOverflow": "https://stackoverflow.com/users/{}",
    "GitLab": "https://gitlab.com/{}",
    "Bitbucket": "https://bitbucket.org/{}",
    "Steam": "https://steamcommunity.com/id/{}",
    "Chess.com": "https://www.chess.com/member/{}",
}

COMMON_PORTS = [21, 22, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 6379, 8080, 8443]
PENTEST_FILES = [
    ".git/config",
    ".env",
    "phpinfo.php",
    "config.php",
    "wp-config.php",
    "robots.txt",
    "sitemap.xml",
    ".htaccess",
    "admin/",
]


class BaseModule(ABC):
    name = "base"
    supported_types: Sequence[str] = ()
    cache_ttl_seconds = 3600
    timeout_seconds = 20
    tier = "public_passive"
    source_family = "public"
    source_reputation = 0.6

    def supports(self, entity: Entity) -> bool:
        return entity.entity_type in self.supported_types

    @abstractmethod
    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        raise NotImplementedError


class SocialDiscoveryModule(BaseModule):
    name = "social"
    supported_types = ("username",)
    timeout_seconds = 30
    source_reputation = 0.72

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        semaphore = asyncio.Semaphore(10 if depth == "standard" else 20)
        found: Dict[str, str] = {}

        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async def check(platform: str, url_tpl: str) -> None:
                async with semaphore:
                    try:
                        async with session.get(url_tpl.format(entity.value), timeout=10, allow_redirects=True) as response:
                            if response.status != 200:
                                return
                            final_url = str(response.url)
                            lowered = final_url.lower()
                            if any(flag in lowered for flag in ("login", "signup", "register", "404")):
                                return
                            text = (await response.text()).lower()
                            if any(flag in text for flag in ("not found", "page doesn't exist", "nobody on reddit")):
                                return
                            confidence = self._platform_confidence(platform, entity.value, final_url, text)
                            if confidence < 0.55:
                                return
                            found[platform] = {"url": final_url, "confidence": confidence}
                    except Exception:
                        return

            await asyncio.gather(*(check(platform, url) for platform, url in SOCIAL_PLATFORMS.items()))

        for platform, payload in sorted(found.items()):
            url = payload["url"]
            confidence = payload["confidence"]
            result.findings.append(
                Finding(
                    module=self.name,
                    title=f"Profile discovered on {platform}",
                    summary=f"Matching username found on {platform}.",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.value,
                    category="identity",
                    severity="medium",
                    confidence=confidence,
                    evidence=url,
                    source_label=platform,
                    source_url=url,
                    why="URL pattern and page content both resemble the target username.",
                    data={"platform": platform, "url": url, "match_confidence": confidence},
                )
            )
            result.artifacts.append(Artifact(self.name, "url", platform, url, entity.entity_id, source_url=url))
        result.raw = {"profiles": found}
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result

    @staticmethod
    def _platform_confidence(platform: str, username: str, final_url: str, text: str) -> float:
        username = username.lower().strip("@")
        parsed = urlparse(final_url)
        path = parsed.path.lower()
        text_hits = sum(
            1 for token in (f"@{username}", username, f"/{username}") if token and token in text
        )
        path_hit = username in path
        exact_tail = path.rstrip("/").split("/")[-1] == username
        if path_hit and exact_tail:
            return 0.9
        if path_hit and text_hits:
            return 0.8
        if path_hit:
            return 0.66
        # Reject known redirect-heavy platforms when the final profile URL no longer resembles the username.
        if platform in {"Goodreads", "Strava", "StackOverflow", "Bitbucket"}:
            return 0.4
        if text_hits >= 2:
            return 0.62
        return 0.45


class NetworkIntelModule(BaseModule):
    name = "network"
    supported_types = ("domain", "ip")
    tier = "public_enriched"
    source_reputation = 0.88

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        target = entity.value
        try:
            ip = target if entity.entity_type == "ip" else socket.gethostbyname(target)
            dns_records = {}
            if entity.entity_type == "domain":
                for record_type in ("MX", "TXT", "A", "NS"):
                    try:
                        dns_records[record_type] = [str(item) for item in dns.resolver.resolve(target, record_type)]
                    except Exception:
                        continue
            geo = requests.get(f"http://ip-api.com/json/{ip}", timeout=5).json()
            geo_data = geo if geo.get("status") == "success" else {}
            result.raw = {"ip": ip, "dns": dns_records, "geo": geo_data}
            if entity.entity_type == "domain":
                ip_entity = Entity(entity_type="ip", value=ip, source="network_resolution", confidence=0.95)
                result.entities.append(ip_entity)
                result.relationships.append(
                    Relationship(
                        from_entity_id=entity.entity_id,
                        to_entity_id=ip_entity.entity_id,
                        rel_type="resolves_to",
                        source=self.name,
                        confidence=0.95,
                        evidence=ip,
                        reason="DNS resolution linked the domain to this IP.",
                    )
                )
            result.findings.append(
                Finding(
                    module=self.name,
                    title="Infrastructure resolved",
                    summary=f"{target} resolves to {ip}.",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.value,
                    category="network",
                    severity="info",
                    confidence=0.9,
                    evidence=ip,
                    source_label="DNS / IP geolocation",
                    source_url=f"http://ip-api.com/json/{ip}",
                    why="Direct host resolution returned this IP.",
                    data={"ip": ip, "dns": dns_records, "geo": geo_data},
                )
            )
            result.artifacts.append(Artifact(self.name, "ip", "Resolved IP", ip, entity.entity_id, source_url=f"http://ip-api.com/json/{ip}"))
            if geo_data:
                location = ", ".join(filter(None, [geo_data.get("city"), geo_data.get("country")]))
                result.findings.append(
                    Finding(
                        module=self.name,
                        title="Geo and ISP metadata",
                        summary=f"Location: {location or 'Unknown'}, ISP: {geo_data.get('isp', 'Unknown')}.",
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="network",
                        severity="info",
                        confidence=0.75,
                        source_label="ip-api",
                        source_url=f"http://ip-api.com/json/{ip}",
                        why="Public IP intelligence service returned geo/ISP context.",
                        data=geo_data,
                    )
                )
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class SubdomainIntelModule(BaseModule):
    name = "subdomains"
    supported_types = ("domain",)
    timeout_seconds = 25
    tier = "public_enriched"
    source_reputation = 0.74

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        domain = entity.value
        subdomains = set()
        if entity.source == "crtsh_subdomain":
            result.raw = {"subdomains": []}
            result.runtime_ms = int((time.perf_counter() - start) * 1000)
            return result
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=20) as response:
                    if response.status == 200:
                        payload = await response.json(content_type=None)
                        for row in payload:
                            for item in row.get("name_value", "").splitlines():
                                normalized = item.strip().lower()
                                if normalized.endswith(domain) and "*" not in normalized:
                                    subdomains.add(normalized)
            limited = sorted(subdomains)[: (15 if depth == "standard" else 40)]
            for subdomain in limited:
                sub_entity = Entity(entity_type="domain", value=subdomain, source="crtsh_subdomain", confidence=0.74)
                result.entities.append(sub_entity)
                result.relationships.append(
                    Relationship(
                        from_entity_id=entity.entity_id,
                        to_entity_id=sub_entity.entity_id,
                        rel_type="subdomain_of",
                        source=self.name,
                        confidence=0.74,
                        evidence=subdomain,
                        reason="Certificate transparency entry lists this hostname under the parent domain.",
                    )
                )
                result.artifacts.append(Artifact(self.name, "domain", "Subdomain", subdomain, entity.entity_id, source_url=f"https://crt.sh/?q=%25.{domain}"))
            if limited:
                result.findings.append(
                    Finding(
                        module=self.name,
                        title="Subdomains discovered",
                        summary=f"Found {len(limited)} certificate-linked subdomains.",
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="infrastructure",
                        severity="info",
                        confidence=0.74,
                        source_label="crt.sh",
                        source_url=f"https://crt.sh/?q=%25.{domain}",
                        why="Certificate transparency data linked these hostnames to the parent domain.",
                        data={"subdomains": limited},
                    )
                )
            result.raw = {"subdomains": limited}
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class RegistrationIntelModule(BaseModule):
    name = "registration"
    supported_types = ("domain", "ip")
    timeout_seconds = 25
    tier = "public_enriched"
    source_reputation = 0.76

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        try:
            payload = self._lookup_registration(entity)
            result.raw = payload
            if payload:
                title = "Domain registration intel" if entity.entity_type == "domain" else "IP registration intel"
                summary = self._summary(entity, payload)
                result.findings.append(
                    Finding(
                        module=self.name,
                        title=title,
                        summary=summary,
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="registration",
                        severity="info",
                        confidence=0.76,
                        source_label="RDAP",
                        source_url=f"https://rdap.org/{'domain' if entity.entity_type == 'domain' else 'ip'}/{entity.value}",
                        why="Public RDAP registration data returned registrar/allocation context.",
                        data=payload,
                    )
                )
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result

    def _lookup_registration(self, entity: Entity) -> dict:
        if entity.entity_type == "domain":
            response = requests.get(f"https://rdap.org/domain/{entity.value}", timeout=12, headers=HEADERS)
            response.raise_for_status()
            data = response.json()
            events = {item.get("eventAction"): item.get("eventDate") for item in data.get("events", [])}
            nameservers = [item.get("ldhName") for item in data.get("nameservers", []) if item.get("ldhName")]
            return {
                "handle": data.get("handle"),
                "registrar": self._extract_entity_name(data, ("registrar", "registrant")),
                "status": data.get("status", []),
                "created": events.get("registration"),
                "updated": events.get("last changed"),
                "expires": events.get("expiration"),
                "nameservers": nameservers[:10],
            }
        response = requests.get(f"https://rdap.org/ip/{entity.value}", timeout=12, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return {
            "handle": data.get("handle"),
            "name": data.get("name"),
            "country": data.get("country"),
            "start_address": data.get("startAddress"),
            "end_address": data.get("endAddress"),
            "asn_like_name": self._extract_entity_name(data, ("registrant", "abuse", "technical")),
        }

    @staticmethod
    def _extract_entity_name(data: dict, roles: tuple[str, ...]) -> str | None:
        for entity in data.get("entities", []):
            entity_roles = set(entity.get("roles", []))
            if entity_roles.intersection(roles):
                vcard = entity.get("vcardArray", [])
                if len(vcard) > 1:
                    for row in vcard[1]:
                        if row and row[0] == "fn":
                            return row[3]
        return None

    @staticmethod
    def _summary(entity: Entity, payload: dict) -> str:
        if entity.entity_type == "domain":
            registrar = payload.get("registrar") or "Unknown registrar"
            created = payload.get("created") or "unknown creation date"
            return f"{entity.value} registration via {registrar}, created {created}."
        owner = payload.get("name") or payload.get("asn_like_name") or "Unknown owner"
        country = payload.get("country") or "Unknown country"
        return f"{entity.value} appears allocated to {owner} in {country}."


class PhoneIntelModule(BaseModule):
    name = "phone"
    supported_types = ("phone",)

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        try:
            phone_number = phonenumbers.parse(entity.value if entity.value.startswith("+") else "+" + entity.value)
            if not phonenumbers.is_valid_number(phone_number):
                raise ValueError("Phone number is not valid")
            phone_data = {
                "format": phonenumbers.format_number(phone_number, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
                "region": geocoder.description_for_number(phone_number, "en"),
                "carrier": carrier.name_for_number(phone_number, "en"),
            }
            result.raw = phone_data
            result.findings.append(
                Finding(
                    module=self.name,
                    title="Phone intelligence",
                    summary=f"Region {phone_data['region'] or 'Unknown'}, carrier {phone_data['carrier'] or 'Unknown'}.",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.value,
                    category="telecom",
                    severity="info",
                    confidence=0.88,
                    source_label="phonenumbers",
                    why="Phone parsing and regional metadata matched a valid international number.",
                    data=phone_data,
                )
            )
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class ImageIntelModule(BaseModule):
    name = "image"
    supported_types = ("image_url",)

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        try:
            response = requests.get(entity.value, timeout=10, headers=HEADERS)
            tags = exifread.process_file(BytesIO(response.content))
            metadata = {
                key: str(value)
                for key, value in tags.items()
                if key not in ("JPEGThumbnail", "TIFFThumbnail", "Filename", "EXIF MakerNote")
            }
            result.raw = {"exif": metadata}
            summary = "Image metadata extracted." if metadata else "No EXIF metadata found."
            result.findings.append(
                Finding(
                    module=self.name,
                    title="Image metadata scan",
                    summary=summary,
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.value,
                    category="image",
                    severity="info",
                    confidence=0.7 if metadata else 0.45,
                    source_label="EXIF",
                    source_url=entity.value,
                    why="Image bytes were inspected for embedded EXIF tags.",
                    data=metadata,
                )
            )
            result.artifacts.extend(
                [
                    Artifact(self.name, "url", "Google Lens", f"https://lens.google.com/uploadbyurl?url={entity.value}", entity.entity_id, source_url=entity.value),
                    Artifact(self.name, "url", "Yandex Images", f"https://yandex.com/images/search?rpt=imageview&url={entity.value}", entity.entity_id, source_url=entity.value),
                    Artifact(self.name, "url", "Bing Visual Search", f"https://www.bing.com/images/search?q=imgurl:{entity.value}&view=detailv2", entity.entity_id, source_url=entity.value),
                ]
            )
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class WebSearchModule(BaseModule):
    name = "web"
    supported_types = ("email", "username", "domain", "phone", "url", "ip", "image_url")
    source_reputation = 0.58

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        try:
            max_results = 6 if depth == "standard" else 12
            with DDGS() as ddgs:
                matches = list(ddgs.text(entity.value, max_results=max_results))
            result.raw = {"results": matches}
            if matches:
                top = matches[0]
                result.findings.append(
                    Finding(
                        module=self.name,
                        title="Surface web matches discovered",
                        summary=f"Found {len(matches)} search results for this entity.",
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="web",
                        severity="info",
                        confidence=0.6,
                        evidence=top.get("href") or top.get("url"),
                        source_label="DuckDuckGo/DDGS",
                        source_url=top.get("href") or top.get("url"),
                        why="Public web search returned multiple direct references to the query.",
                        data={"results": matches},
                    )
                )
                for match in matches[:5]:
                    url = match.get("href") or match.get("url")
                    if url:
                        result.artifacts.append(Artifact(self.name, "url", match.get("title", "Search result"), url, entity.entity_id, source_url=url))
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class WebFingerprintModule(BaseModule):
    name = "fingerprint"
    supported_types = ("url",)
    tier = "public_enriched"
    source_reputation = 0.68

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(entity.value, timeout=10) as response:
                    text = (await response.text()).lower()
                    cms = "WordPress" if "wp-content" in text else "Shopify" if "shopify" in text else "Unknown"
                    fingerprint = {
                        "server": response.headers.get("Server", "Unknown"),
                        "cms": cms,
                        "security_headers": [
                            header
                            for header in ("Content-Security-Policy", "Strict-Transport-Security")
                            if header in response.headers
                        ],
                    }
            result.raw = fingerprint
            result.findings.append(
                Finding(
                    module=self.name,
                    title="Website fingerprinted",
                    summary=f"Server {fingerprint['server']} with CMS hint {fingerprint['cms']}.",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.value,
                    category="web",
                    severity="info",
                    confidence=0.68,
                    source_label="HTTP fingerprint",
                    source_url=entity.value,
                    why="Server headers and page content exposed technology hints.",
                    data=fingerprint,
                )
            )
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class ExposureModule(BaseModule):
    name = "exposure"
    supported_types = ("url", "domain")
    timeout_seconds = 25
    tier = "public_enriched"
    source_reputation = 0.84

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        base_url = entity.value if entity.entity_type == "url" else f"http://{entity.value}"
        hits = []
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            for item in PENTEST_FILES:
                url = f"{base_url.rstrip('/')}/{item}"
                try:
                    async with session.get(url, timeout=5, allow_redirects=False) as response:
                        if response.status == 200:
                            hits.append(url)
                except Exception:
                    continue

        if hits:
            for url in hits:
                result.findings.append(
                    Finding(
                        module=self.name,
                        title="Potential exposed file or endpoint",
                        summary=f"Publicly reachable path detected: {url}",
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="exposure",
                        severity="high",
                        confidence=0.84,
                        evidence=url,
                        source_label="Direct HTTP probe",
                        source_url=url,
                        why="A known sensitive path responded successfully without authentication.",
                        data={"url": url},
                    )
                )
                result.artifacts.append(Artifact(self.name, "url", "Exposed path", url, entity.entity_id, source_url=url))
        result.raw = {"hits": hits}
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class DorkingModule(BaseModule):
    name = "links"
    supported_types = ("email", "username", "domain", "phone", "url", "ip", "image_url")

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        value = entity.value
        links = {
            "Global Leaks": f'https://www.google.com/search?q=site:pastebin.com+OR+site:gist.github.com+"{value}"'
        }
        if entity.entity_type == "email":
            links["Credential Breaches"] = f'https://www.google.com/search?q="{value}"+password+OR+leak'
        if entity.entity_type in ("domain", "url"):
            domain = value.split("//")[-1].split("/")[0] if entity.entity_type == "url" else value
            links["Subdomain Discovery"] = f"https://www.google.com/search?q=site:*.{domain}+-www"
            links["Cloud Intelligence"] = f'https://www.google.com/search?q=site:s3.amazonaws.com+"{domain}"'
        if entity.entity_type == "image_url":
            links["Visual AI Search"] = f"https://lens.google.com/uploadbyurl?url={value}"
        for label, url in links.items():
            result.artifacts.append(Artifact(self.name, "url", label, url, entity.entity_id, source_url=url))
        result.findings.append(
            Finding(
                module=self.name,
                title="Investigation links prepared",
                summary=f"Generated {len(links)} lead links for follow-up.",
                entity_id=entity.entity_id,
                entity_type=entity.entity_type,
                entity_value=value,
                category="lead",
                severity="info",
                confidence=0.8,
                source_label="Generated investigation dorks",
                why="These links are derived pivots based on the entity type and commonly useful search patterns.",
                data={"links": links},
            )
        )
        result.raw = {"links": links}
        return result


class PortScanModule(BaseModule):
    name = "ports"
    supported_types = ("domain", "ip")
    timeout_seconds = 20
    tier = "public_enriched"
    source_reputation = 0.78

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        target = entity.value
        try:
            ip = target if entity.entity_type == "ip" else socket.gethostbyname(target)
            ports = await self._scan(ip)
            result.raw = {"ip": ip, "open_ports": ports}
            if ports:
                result.findings.append(
                    Finding(
                        module=self.name,
                        title="Open ports detected",
                        summary=f"Open ports on {ip}: {', '.join(map(str, ports))}",
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="network",
                        severity="medium",
                        confidence=0.78,
                        source_label="Direct TCP connect",
                        why="The socket completed a TCP connection on the listed ports.",
                        data={"ip": ip, "open_ports": ports},
                    )
                )
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result

    async def _scan(self, ip: str) -> List[int]:
        async def scan_port(port: int) -> int | None:
            try:
                reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=1.0)
                writer.close()
                await writer.wait_closed()
                return port
            except Exception:
                return None

        scanned = await asyncio.gather(*(scan_port(port) for port in COMMON_PORTS))
        return [port for port in scanned if port is not None]


class RelationshipModule(BaseModule):
    name = "relationships"
    supported_types = ("email", "username", "domain", "phone", "url", "ip", "image_url")
    tier = "public_enriched"
    source_reputation = 0.7

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        notes = []
        if entity.entity_type == "email":
            domain = entity.value.split("@", 1)[1]
            notes.append(("hosted_on", f"Email hosted on {domain}", 0.95))
        elif entity.entity_type == "username":
            notes.append(("alias_candidate", "Username can be correlated across platforms", 0.65))
        elif entity.entity_type in ("domain", "url"):
            notes.append(("infra_anchor", "Infrastructure entity can fan out to DNS, ports, and exposures", 0.72))
        elif entity.entity_type == "phone":
            notes.append(("telecom_anchor", "Phone number can correlate telecom and web leads", 0.6))

        for rel_type, summary, confidence in notes:
            result.findings.append(
                Finding(
                    module=self.name,
                    title=f"Relationship lead: {rel_type}",
                    summary=summary,
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.value,
                    category="relationship",
                    severity="info",
                    confidence=confidence,
                    source_label="Relationship heuristics",
                    why=f"Heuristic relationship signal: {rel_type}.",
                )
            )
        result.raw = {"notes": notes}
        return result


class ArchiveIntelModule(BaseModule):
    name = "archives"
    supported_types = ("domain", "url")
    tier = "public_enriched"
    timeout_seconds = 20
    source_reputation = 0.67

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        target = entity.value if entity.entity_type == "url" else f"http://{entity.value}"
        try:
            response = requests.get(
                "https://web.archive.org/cdx/search/cdx",
                params={"url": target, "output": "json", "limit": 5, "fl": "timestamp,original,statuscode"},
                timeout=10,
                headers=HEADERS,
            )
            response.raise_for_status()
            rows = response.json()[1:]
            snapshots = [
                {"timestamp": row[0], "original": row[1], "status": row[2], "archive_url": f"https://web.archive.org/web/{row[0]}/{row[1]}"}
                for row in rows
            ]
            if snapshots:
                result.findings.append(
                    Finding(
                        module=self.name,
                        title="Archived snapshots found",
                        summary=f"Wayback returned {len(snapshots)} archived snapshots.",
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="archive",
                        severity="info",
                        confidence=0.67,
                        source_label="Internet Archive CDX",
                        source_url="https://web.archive.org",
                        why="Historical archives may expose prior content and pivots.",
                        data={"snapshots": snapshots},
                    )
                )
                for snapshot in snapshots:
                    result.artifacts.append(Artifact(self.name, "url", "Archived snapshot", snapshot["archive_url"], entity.entity_id, source_url=snapshot["archive_url"]))
            result.raw = {"snapshots": snapshots}
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        return result


class ContentExtractionModule(BaseModule):
    name = "content"
    supported_types = ("url", "domain")
    tier = "public_enriched"
    timeout_seconds = 20
    source_reputation = 0.63

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        target = entity.value if entity.entity_type == "url" else f"http://{entity.value}"
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(target, timeout=10) as response:
                    text = await response.text()
            lowered = text.lower()
            title = self._extract_between(text, "<title>", "</title>")
            keywords = []
            for token in ("login", "contact", "support", "privacy", "terms", "about", "pricing", "dashboard"):
                if token in lowered:
                    keywords.append(token)
            preview = " ".join(" ".join(text.split()).split()[:80])
            result.findings.append(
                Finding(
                    module=self.name,
                    title="Page content extracted",
                    summary=f"Captured page title and text preview from {target}.",
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    entity_value=entity.value,
                    category="content",
                    severity="info",
                    confidence=0.63,
                    source_label="HTTP content extraction",
                    source_url=target,
                    why="Page text and metadata can reveal pivots, branding, and sensitive context.",
                    data={"title": title, "keywords": keywords, "preview": preview},
                )
            )
            result.artifacts.append(Artifact(self.name, "text", title or "Page preview", preview, entity.entity_id, source_url=target))
            result.raw = {"title": title, "keywords": keywords, "preview": preview}
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        return result

    @staticmethod
    def _extract_between(text: str, start: str, end: str) -> str:
        lower_text = text.lower()
        start_index = lower_text.find(start)
        end_index = lower_text.find(end)
        if start_index == -1 or end_index == -1 or end_index <= start_index:
            return ""
        return " ".join(text[start_index + len(start):end_index].split())[:200]


class BreachReferenceModule(BaseModule):
    name = "breach_refs"
    supported_types = ("email", "username", "domain")
    tier = "public_enriched"
    timeout_seconds = 20
    source_reputation = 0.55

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        result = ModuleResult(module=self.name, tier=self.tier, source_family=self.source_family)
        query = f'"{entity.value}" breach leak paste' if entity.entity_type == "email" else f'"{entity.value}" leak paste breach'
        try:
            with DDGS() as ddgs:
                rows = list(ddgs.text(query, max_results=5 if depth == "standard" else 8))
            if rows:
                result.findings.append(
                    Finding(
                        module=self.name,
                        title="Potential breach references discovered",
                        summary=f"Found {len(rows)} public search results mentioning leak or breach terms.",
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        entity_value=entity.value,
                        category="breach_reference",
                        severity="medium",
                        confidence=0.55,
                        source_label="Public search references",
                        why="Search results indicate public leak-oriented mentions that deserve manual review.",
                        data={"results": rows, "query": query},
                    )
                )
                for row in rows:
                    url = row.get("href") or row.get("url")
                    if url:
                        result.artifacts.append(Artifact(self.name, "url", row.get("title", "Breach reference"), url, entity.entity_id, source_url=url))
            result.raw = {"query": query, "results": rows if 'rows' in locals() else []}
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        return result


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: Dict[str, BaseModule] = {}

    def register(self, module: BaseModule) -> None:
        self._modules[module.name] = module

    def names(self) -> List[str]:
        return sorted(self._modules.keys())

    def get(self, name: str) -> BaseModule:
        return self._modules[name]

    def applicable(self, entity: Entity, selected: Iterable[str] | None = None) -> List[BaseModule]:
        allowed = set(selected or self._modules.keys())
        return [module for module in self._modules.values() if module.name in allowed and module.supports(entity)]


def build_default_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    for module in (
        SocialDiscoveryModule(),
        NetworkIntelModule(),
        RegistrationIntelModule(),
        SubdomainIntelModule(),
        PhoneIntelModule(),
        ImageIntelModule(),
        WebSearchModule(),
        WebFingerprintModule(),
        ArchiveIntelModule(),
        ContentExtractionModule(),
        BreachReferenceModule(),
        ExposureModule(),
        DorkingModule(),
        PortScanModule(),
        RelationshipModule(),
    ):
        registry.register(module)
    return registry
