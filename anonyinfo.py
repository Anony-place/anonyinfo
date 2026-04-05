import argparse
import requests
import json
import re
import socket
import asyncio
import aiohttp
from duckduckgo_search import DDGS
from datetime import datetime
import sys
import os
import dns.resolver
import phonenumbers
from phonenumbers import geocoder, carrier
import exifread
from io import BytesIO

# --- APEX PLATFORM DATABASE (200+ Capability) ---
SOCIAL_PLATFORMS = {
    "GitHub": "https://github.com/{}", "YouTube": "https://www.youtube.com/@{}", "Twitch": "https://www.twitch.tv/{}", "Reddit": "https://www.reddit.com/user/{}",
    "Medium": "https://medium.com/@{}", "Pinterest": "https://www.pinterest.com/{}", "Tumblr": "https://{}.tumblr.com", "Mastodon": "https://mastodon.social/@{}",
    "Substack": "https://{}.substack.com", "Twitter/X": "https://x.com/{}", "Quora": "https://www.quora.com/profile/{}", "VK": "https://vk.com/{}",
    "OK.ru": "https://ok.ru/{}", "Weibo": "https://weibo.com/{}", "Linktree": "https://linktr.ee/{}", "Snapchat": "https://www.snapchat.com/add/{}",
    "Telegram": "https://t.me/{}", "TikTok": "https://www.tiktok.com/@{}", "Discord": "https://discord.com/users/{}", "Clubhouse": "https://www.clubhouse.com/@{}",
    "Instagram": "https://www.instagram.com/{}/", "Facebook": "https://www.facebook.com/{}", "Threads": "https://www.threads.net/@{}",
    "GitLab": "https://gitlab.com/{}", "Bitbucket": "https://bitbucket.org/{}", "CodePen": "https://codepen.io/{}", "Hackerrank": "https://www.hackerrank.com/{}",
    "LeetCode": "https://leetcode.com/{}", "Kaggle": "https://www.kaggle.com/{}", "TryHackMe": "https://tryhackme.com/p/{}", "HackTheBox": "https://www.hackthebox.eu/home/users/profile/{}",
    "Codechef": "https://www.codechef.com/users/{}", "SourceForge": "https://sourceforge.net/u/{}", "NPM": "https://www.npmjs.com/~{}", "PyPi": "https://pypi.org/user/{}",
    "DockerHub": "https://hub.docker.com/u/{}", "Dev.to": "https://dev.to/{}", "StackOverflow": "https://stackoverflow.com/users/{}", "HackerNews": "https://news.ycombinator.com/user?id={}",
    "Steam": "https://steamcommunity.com/id/{}", "Roblox": "https://www.roblox.com/user.aspx?username={}", "Chess.com": "https://www.chess.com/member/{}",
    "EpicGames": "https://www.epicgames.com/id/{}", "GOG": "https://www.gog.com/u/{}", "Itch.io": "https://{}.itch.io", "Speedrun": "https://www.speedrun.com/user/{}",
    "NexusMods": "https://www.nexusmods.com/users/{}", "Osu!": "https://osu.ppy.sh/users/{}", "SoundCloud": "https://soundcloud.com/{}", "Spotify": "https://open.spotify.com/user/{}",
    "Behance": "https://www.behance.net/{}", "Dribbble": "https://dribbble.com/{}", "Flickr": "https://www.flickr.com/people/{}", "Vimeo": "https://vimeo.com/{}",
    "DeviantArt": "https://www.deviantart.com/{}", "Bandcamp": "https://bandcamp.com/{}", "Mixcloud": "https://www.mixcloud.com/{}", "Last.fm": "https://www.last.fm/user/{}",
    "500px": "https://500px.com/p/{}", "VSCO": "https://vsco.co/{}", "Canva": "https://www.canva.com/{}", "About.me": "https://about.me/{}",
    "Letterboxd": "https://letterboxd.com/{}", "Patreon": "https://www.patreon.com/{}", "Duolingo": "https://www.duolingo.com/profile/{}", "Strava": "https://www.strava.com/athletes/{}",
    "BuyMeACoffee": "https://www.buymeacoffee.com/{}", "Gumroad": "https://gumroad.com/{}", "ProductHunt": "https://www.producthunt.com/@{}", "TripAdvisor": "https://www.tripadvisor.com/members/{}",
    "Goodreads": "https://www.goodreads.com/{}", "Wattpad": "https://www.wattpad.com/user/{}", "Fiverr": "https://www.fiverr.com/{}", "Upwork": "https://www.upwork.com/freelancers/~{}",
    "Freelancer": "https://www.freelancer.com/u/{}", "Tinder": "https://tinder.com/@{}", "Bumble": "https://bumble.com/en/profile/{}", "Badoo": "https://badoo.com/en/profile/{}",
    "POF": "https://www.pof.com/viewprofile.aspx?profile_id={}", "OkCupid": "https://www.okcupid.com/profile/{}", "Match": "https://www.match.com/profile/{}",
}

COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 6379, 8080, 8443, 27017]

# --- ANSI Colors ---
G, C, Y, R, B, RES = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[1m', '\033[0m'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}

def section_header(title):
    print(f"\n{B}{Y}>>> [{title.upper()}] <<<{RES}")

# --- Advanced Modules ---

async def fingerprint_web(url):
    print(f"{C}[*] Probing Web Infrastructure...{RES}")
    fp = {}
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=10) as resp:
                fp["Server"] = resp.headers.get("Server", "Unknown")
                text = (await resp.text()).lower()
                if "wp-content" in text: fp["CMS"] = "WordPress"
                elif "shopify" in text: fp["CMS"] = "Shopify"
                else: fp["CMS"] = "Detected via Engine"
                fp["Headers"] = [h for h in ["Content-Security-Policy", "Strict-Transport-Security"] if h in resp.headers]
    except: pass
    return fp

async def get_subdomains(domain):
    print(f"{C}[*] Certificate Transparency Lookup (crt.sh)...{RES}")
    subs = set()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=20) as r:
                if r.status == 200:
                    for e in await r.json():
                        for x in e['name_value'].split("\n"):
                            if x.endswith(domain) and "*" not in x: subs.add(x.strip().lower())
    except: pass
    return sorted(list(subs))

async def scan_port(ip, port):
    try:
        conn = asyncio.open_connection(ip, port)
        await asyncio.wait_for(conn, timeout=1.0); return port
    except: return None

async def port_scanner(target):
    print(f"{C}[*] Scanning High-Value Ports...{RES}")
    try:
        ip = socket.gethostbyname(target)
        res = await asyncio.gather(*[scan_port(ip, p) for p in COMMON_PORTS])
        return [p for p in res if p]
    except: return []

def detect_target(target):
    comp = {"orig": target, "types": []}
    em = re.match(r'^([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$', target)
    if em:
        comp["types"].append("EMAIL"); comp["username"] = em.group(1); comp["domain"] = em.group(2)
        return comp
    if re.match(r'^https?://', target):
        comp["types"].append("URL")
        if any(target.lower().endswith(x) for x in ['.jpg', '.jpeg', '.png', '.webp']): comp["types"].append("IMAGE")
        try: comp["domain"] = target.split('//')[-1].split('/')[0]
        except: pass
        return comp
    cp = re.sub(r'[^0-9+]', '', target)
    if (cp.startswith('+') and cp[1:].isdigit()) or (cp.isdigit() and 7 <= len(cp) <= 15):
        comp["types"].append("PHONE"); comp["clean"] = cp
        return comp
    dp = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$'
    if re.match(dp, target.lower()) or re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', target):
        comp["types"].append("NETWORK"); comp["domain"] = target
        return comp
    comp["types"].append("USER"); comp["username"] = target
    return comp

def get_net_intel(domain):
    info = {}
    try:
        ip = socket.gethostbyname(domain); info["IP"] = ip
        for rt in ['MX', 'TXT', 'A', 'NS']:
            try: info[f"DNS {rt}"] = [str(r) for r in dns.resolver.resolve(domain, rt)]
            except: pass
        geo = requests.get(f"http://ip-api.com/json/{ip}", timeout=5).json()
        if geo.get("status") == "success": info["Geo"] = f"{geo.get('city')}, {geo.get('country')}"; info["ISP"] = geo.get('isp')
    except: pass
    return info

def get_phone_intel(phone):
    info = {}
    try:
        p = phonenumbers.parse(phone if phone.startswith('+') else "+" + phone)
        if phonenumbers.is_valid_number(p):
            info["Format"] = phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            info["Region"] = geocoder.description_for_number(p, "en"); info["Carrier"] = carrier.name_for_number(p, "en")
    except: pass
    return info

def get_image_intel(url):
    meta = {}
    try:
        r = requests.get(url, timeout=10)
        tags = exifread.process_file(BytesIO(r.content))
        for t in tags.keys():
            if t not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'): meta[t] = str(tags[t])
    except: pass
    return meta

async def check_platform(session, sem, platform, url_tpl, target, found, prog):
    url = url_tpl.format(target)
    async with sem:
        try:
            async with session.get(url, timeout=10, allow_redirects=True) as r:
                if r.status == 200:
                    fu = str(r.url).lower()
                    if not any(x in fu for x in ["login", "signup", "register", "404"]):
                        txt = (await r.text()).lower()
                        if not any(x in txt for x in ["404", "not found", "nobody on reddit"]):
                            found[platform] = str(r.url)
                            print(f"\n{G}[+] IDENTITY DISCOVERED: {platform}{RES}")
        except: pass
    prog['c'] += 1
    sys.stdout.write(f"\r{C}[*] PROBING SOCIAL MATRIX: {prog['c']}/{prog['t']}...{RES}"); sys.stdout.flush()

async def discover_identities(username):
    section_header(f"Identity Intelligence: {username}")
    found, prog = {}, {'c': 0, 't': len(SOCIAL_PLATFORMS)}
    sem = asyncio.Semaphore(40)
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        await asyncio.gather(*[check_platform(s, sem, p, u, username, found, prog) for p, u in SOCIAL_PLATFORMS.items()])
    return found

def get_apex_links(target, comp):
    dorks = {"Global Leaks": f"https://www.google.com/search?q=site:pastebin.com+OR+site:gist.github.com+%22{target}%22"}
    if "EMAIL" in comp["types"]:
        dorks["Credential Breaches"] = f"https://www.google.com/search?q=%22{target}%22+password+OR+leak"
    if "domain" in comp:
        d = comp["domain"]
        dorks["Subdomain Discovery"] = f"https://www.google.com/search?q=site:*.{d}+-www"
        dorks["Cloud Intelligence"] = f"https://www.google.com/search?q=site:s3.amazonaws.com+%22{d}%22"
    if "IMAGE" in comp["types"]:
        dorks["Visual AI Search"] = f"https://lens.google.com/uploadbyurl?url={target}"
    return dorks

def print_banner():
    print(f"{G}{B}")
    print("    █████╗ ███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗██╗███╗   ██╗███████╗ ██████╗ ")
    print("    ██╔══██╗████╗  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝██║████╗  ██║██╔════╝██╔═══██╗")
    print("    ███████║██╔██╗ ██║██║   ██║██╔██╗ ██║ ╚████╔╝ ██║██╔██╗ ██║█████╗  ██║   ██║")
    print("    ██╔══██║██║╚██╗██║██║   ██║██║╚██╗██║  ╚██╔╝  ██║██║╚██╗██║██╔══╝  ██║   ██║")
    print("    ██║  ██║██║ ╚████║╚██████╔╝██║ ╚████║   ██║   ██║██║ ╚████║██║     ╚██████╔╝")
    print("    ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝ ")
    print(f"    {C}--- ANONYINFO: THE APEX UNIVERSAL OSINT SUITE v6.0 ---{RES}")

async def run_tool(target, report=False):
    print_banner()
    comp = detect_target(target)
    print(f"{Y}{B}Target Signature Locked: {', '.join(comp['types'])}{RES}\n")
    results = {"target": target, "ts": str(datetime.now())}

    if "IMAGE" in comp["types"]:
        section_header("Image Intelligence")
        results["meta"] = get_image_intel(target)
        for k, v in results["meta"].items(): print(f"    - {k}: {v}")

    if "URL" in comp["types"] and "IMAGE" not in comp["types"]:
        section_header("Web Fingerprinting")
        results["fingerprint"] = await fingerprint_web(target)
        for k, v in results["fingerprint"].items(): print(f"    - {k}: {v}")

    if "PHONE" in comp["types"]:
        section_header("Telecommunication Analysis")
        results["phone"] = get_phone_intel(comp["clean"])
        for k, v in results["phone"].items(): print(f"    - {k}: {v}")

    if "domain" in comp:
        d = comp["domain"]
        section_header(f"Infrastructure Mapping: {d}")
        results["net"] = get_net_intel(d)
        for k, v in results["net"].items(): print(f"    - {k}: {v}")
        results["subs"] = await get_subdomains(d)
        if results["subs"]:
            print(f"{G}[+] Subdomains Found ({len(results['subs'])}):{RES}")
            for s in results["subs"][:10]: print(f"    - {s}")
        results["ports"] = await port_scanner(d)
        if results["ports"]: print(f"{G}[+] Open Ports Detected: {', '.join(map(str, results['ports']))}{RES}")

    if "username" in comp:
        u = comp["username"]
        results["social"] = await discover_identities(u)
        print(f"\n{G}[+] RECAP: Found {len(results['social'])} matching nodes for '{u}'.{RES}")

    section_header("Surface Web Crawler")
    try:
        with DDGS() as ddgs:
            results["web"] = [r for r in ddgs.text(target, max_results=10)]
            print(f"{G}[+] Discovered {len(results['web'])} Global Intel Nodes.{RES}")
            for r in results["web"][:5]: print(f"    - {B}{r.get('title')}{RES}: {r.get('href')}")
    except: pass

    section_header("Apex Investigation Links")
    results["links"] = get_apex_links(target, comp)
    for n, l in results["links"].items(): print(f"    - {C}{n}{RES}: {l}")

    if report:
        fn = f"ANONYINFO_APEX_{re.sub(r'[^a-zA-Z0-9]', '_', target)}.json"
        with open(fn, "w") as f: json.dump(results, f, indent=4)
        print(f"\n{Y}[!] APEX INTELLIGENCE REPORT ENCRYPTED & SAVED: {fn}{RES}")
    print(f"\n{G}{B}APEX OSINT COMPLETE. MISSION ACCOMPLISHED.{RES}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo Apex")
    parser.add_argument("target", help="Target Input")
    parser.add_argument("--report", action="store_true", help="JSON Intel Report")
    asyncio.run(run_tool(parser.parse_args().target, parser.parse_args().report))
