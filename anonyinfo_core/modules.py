from __future__ import annotations

import asyncio
import socket
import time
from abc import ABC, abstractmethod
from io import BytesIO
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

    def supports(self, entity: Entity) -> bool:
        return entity.entity_type in self.supported_types

    @abstractmethod
    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        raise NotImplementedError


class SocialDiscoveryModule(BaseModule):
    name = "social"
    supported_types = ("username",)
    timeout_seconds = 30

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name)
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
                            found[platform] = final_url
                    except Exception:
                        return

            await asyncio.gather(*(check(platform, url) for platform, url in SOCIAL_PLATFORMS.items()))

        for platform, url in sorted(found.items()):
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
                    confidence=0.72,
                    evidence=url,
                    data={"platform": platform, "url": url},
                )
            )
            result.artifacts.append(Artifact(self.name, "url", platform, url, entity.entity_id))
        result.raw = {"profiles": found}
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class NetworkIntelModule(BaseModule):
    name = "network"
    supported_types = ("domain", "ip")

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name)
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
                    data={"ip": ip, "dns": dns_records, "geo": geo_data},
                )
            )
            result.artifacts.append(Artifact(self.name, "ip", "Resolved IP", ip, entity.entity_id))
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
                        data=geo_data,
                    )
                )
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class PhoneIntelModule(BaseModule):
    name = "phone"
    supported_types = ("phone",)

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name)
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
        result = ModuleResult(module=self.name)
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
                    data=metadata,
                )
            )
            result.artifacts.extend(
                [
                    Artifact(self.name, "url", "Google Lens", f"https://lens.google.com/uploadbyurl?url={entity.value}", entity.entity_id),
                    Artifact(self.name, "url", "Yandex Images", f"https://yandex.com/images/search?rpt=imageview&url={entity.value}", entity.entity_id),
                    Artifact(self.name, "url", "Bing Visual Search", f"https://www.bing.com/images/search?q=imgurl:{entity.value}&view=detailv2", entity.entity_id),
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

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name)
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
                        data={"results": matches},
                    )
                )
                for match in matches[:5]:
                    url = match.get("href") or match.get("url")
                    if url:
                        result.artifacts.append(Artifact(self.name, "url", match.get("title", "Search result"), url, entity.entity_id))
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class WebFingerprintModule(BaseModule):
    name = "fingerprint"
    supported_types = ("url",)

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name)
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

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name)
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
                        data={"url": url},
                    )
                )
                result.artifacts.append(Artifact(self.name, "url", "Exposed path", url, entity.entity_id))
        result.raw = {"hits": hits}
        result.runtime_ms = int((time.perf_counter() - start) * 1000)
        return result


class DorkingModule(BaseModule):
    name = "links"
    supported_types = ("email", "username", "domain", "phone", "url", "ip", "image_url")

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        result = ModuleResult(module=self.name)
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
            result.artifacts.append(Artifact(self.name, "url", label, url, entity.entity_id))
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
                data={"links": links},
            )
        )
        result.raw = {"links": links}
        return result


class PortScanModule(BaseModule):
    name = "ports"
    supported_types = ("domain", "ip")
    timeout_seconds = 20

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        start = time.perf_counter()
        result = ModuleResult(module=self.name)
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

    async def run(self, entity: Entity, depth: str) -> ModuleResult:
        result = ModuleResult(module=self.name)
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
                )
            )
        result.raw = {"notes": notes}
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
        PhoneIntelModule(),
        ImageIntelModule(),
        WebSearchModule(),
        WebFingerprintModule(),
        ExposureModule(),
        DorkingModule(),
        PortScanModule(),
        RelationshipModule(),
    ):
        registry.register(module)
    return registry
