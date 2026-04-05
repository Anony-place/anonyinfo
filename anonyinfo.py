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
import logging
from logging.handlers import RotatingFileHandler
from database import init_db, save_intel, get_cached_intel
from engine import analyze_relationships

# --- Logging Setup ---
LOG_FILE = "anonyinfo_mission.log"
logger = logging.getLogger("AnonyInfo")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=1000000, backupCount=5)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

# --- APEX PLATFORM DATABASE ---
SOCIAL_PLATFORMS = {
    "GitHub": "https://github.com/{}", "YouTube": "https://www.youtube.com/@{}", "Twitch": "https://www.twitch.tv/{}", "Reddit": "https://www.reddit.com/user/{}",
    "Medium": "https://medium.com/@{}", "Pinterest": "https://www.pinterest.com/{}", "Tumblr": "https://{}.tumblr.com", "Mastodon": "https://mastodon.social/@{}",
    "Substack": "https://{}.substack.com", "Twitter/X": "https://x.com/{}", "Quora": "https://www.quora.com/profile/{}", "VK": "https://vk.com/{}",
    "OK.ru": "https://ok.ru/{}", "Weibo": "https://weibo.com/{}", "Linktree": "https://linktr.ee/{}", "Snapchat": "https://www.snapchat.com/add/{}",
    "Telegram": "https://t.me/{}", "TikTok": "https://www.tiktok.com/@{}", "Discord": "https://discord.com/users/{}", "Clubhouse": "https://www.clubhouse.com/@{}",
    "Instagram": "https://www.instagram.com/{}/", "Facebook": "https://www.facebook.com/{}", "Threads": "https://www.threads.net/@{}",
    "LinkedIn": "https://www.linkedin.com/in/{}", "Crunchbase": "https://www.crunchbase.com/person/{}", "AngelList": "https://angel.co/u/{}",
    "Fiverr": "https://www.fiverr.com/{}", "Upwork": "https://www.upwork.com/freelancers/~{}", "Freelancer": "https://www.freelancer.com/u/{}",
    "About.me": "https://about.me/{}", "Behance": "https://www.behance.net/{}", "Dribbble": "https://dribbble.com/{}", "Canva": "https://www.canva.com/{}",
    "ProductHunt": "https://www.producthunt.com/@{}", "Goodreads": "https://www.goodreads.com/{}", "Wattpad": "https://www.wattpad.com/user/{}",
    "TripAdvisor": "https://www.tripadvisor.com/members/{}", "Duolingo": "https://www.duolingo.com/profile/{}", "Strava": "https://www.strava.com/athletes/{}",
    "HackTheBox": "https://www.hackthebox.eu/home/users/profile/{}", "TryHackMe": "https://tryhackme.com/p/{}", "Bugcrowd": "https://bugcrowd.com/{}",
    "HackerOne": "https://hackerone.com/{}", "LeetCode": "https://leetcode.com/{}", "Hackerrank": "https://www.hackerrank.com/{}",
    "Kaggle": "https://www.kaggle.com/{}", "StackOverflow": "https://stackoverflow.com/users/{}", "HackerNews": "https://news.ycombinator.com/user?id={}",
    "GitLab": "https://gitlab.com/{}", "Bitbucket": "https://bitbucket.org/{}", "CodePen": "https://codepen.io/{}", "PyPi": "https://pypi.org/user/{}",
    "Steam": "https://steamcommunity.com/id/{}", "Roblox": "https://www.roblox.com/user.aspx?username={}", "Chess.com": "https://www.chess.com/member/{}",
    "EpicGames": "https://www.epicgames.com/id/{}", "GOG": "https://www.gog.com/u/{}", "Itch.io": "https://{}.itch.io", "Speedrun": "https://www.speedrun.com/user/{}",
    "NexusMods": "https://www.nexusmods.com/users/{}", "Osu!": "https://osu.ppy.sh/users/{}", "BattleNet": "https://worldofwarcraft.com/en-us/character/us/{}/",
}

COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432, 6379, 8080, 8443, 27017]
PENTEST_FILES = [".git/config", ".env", "phpinfo.php", "config.php", "wp-config.php", "robots.txt", "sitemap.xml", ".htaccess", "admin/", "backup.sql", "dump.sql"]

# --- ANSI Colors ---
G, C, Y, R, B, RES = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[1m', '\033[0m'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}

def section_header(title):
    print(f"\n{B}{Y}>>> [{title.upper()}] <<<{RES}")

# --- Advanced Modules ---

async def probe_vulnerabilities(base_url):
    logger.info(f"Probing vulnerabilities for {base_url}")
    found = []
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        for f in PENTEST_FILES:
            url = f"{base_url.rstrip('/')}/{f}"
            try:
                async with session.get(url, timeout=5, allow_redirects=False) as resp:
                    if resp.status == 200:
                        print(f"{R}[!] VULNERABILITY DETECTED: {f} is exposed!{RES}")
                        found.append(url)
            except Exception as e:
                logger.error(f"Error probing {url}: {e}")
    return found

async def fingerprint_web(url):
    logger.info(f"Fingerprinting {url}")
    fp = {}
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(url, timeout=10) as resp:
                fp["Server"] = resp.headers.get("Server", "Unknown")
                text = (await resp.text()).lower()
                if "wp-content" in text: fp["CMS"] = "WordPress"
                elif "shopify" in text: fp["CMS"] = "Shopify"
                else: fp["CMS"] = "Unknown"
                fp["Headers"] = [h for h in ["Content-Security-Policy", "Strict-Transport-Security"] if h in resp.headers]
    except Exception as e:
        logger.error(f"Fingerprint failed for {url}: {e}")
    return fp

async def get_subdomains(domain):
    logger.info(f"Enumerate subdomains for {domain}")
    subs = set()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://crt.sh/?q=%25.{domain}&output=json", timeout=20) as r:
                if r.status == 200:
                    for e in await r.json():
                        for x in e['name_value'].split("\n"):
                            if x.endswith(domain) and "*" not in x: subs.add(x.strip().lower())
    except Exception as e:
        logger.error(f"crt.sh failed for {domain}: {e}")
    return sorted(list(subs))

async def scan_port(ip, port):
    try:
        conn = asyncio.open_connection(ip, port)
        await asyncio.wait_for(conn, timeout=1.0); return port
    except: return None

async def port_scanner(target):
    logger.info(f"Port scanning {target}")
    try:
        ip = socket.gethostbyname(target)
        res = await asyncio.gather(*[scan_port(ip, p) for p in COMMON_PORTS])
        return [p for p in res if p]
    except Exception as e:
        logger.error(f"Port scan failed for {target}: {e}")
        return []

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
        ip = socket.gethostbyname(domain); info["IP Address"] = ip
        for rt in ['MX', 'TXT', 'A', 'NS']:
            try: info[f"DNS {rt}"] = [str(r) for r in dns.resolver.resolve(domain, rt)]
            except: pass
        geo = requests.get(f"http://ip-api.com/json/{ip}", timeout=5).json()
        if geo.get("status") == "success": info["Location"] = f"{geo.get('city')}, {geo.get('country')}"; info["ISP"] = geo.get('isp')
    except Exception as e:
        logger.error(f"Net intel failed for {domain}: {e}")
    return info

def get_phone_intel(phone):
    info = {}
    try:
        p = phonenumbers.parse(phone if phone.startswith('+') else "+" + phone)
        if phonenumbers.is_valid_number(p):
            info["Format"] = phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            info["Region"] = geocoder.description_for_number(p, "en"); info["Carrier"] = carrier.name_for_number(p, "en")
    except Exception as e:
        logger.error(f"Phone intel failed: {e}")
    return info

def get_image_intel(url):
    meta = {}
    try:
        r = requests.get(url, timeout=10)
        tags = exifread.process_file(BytesIO(r.content))
        for t in tags.keys():
            if t not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'): meta[t] = str(tags[t])
    except Exception as e:
        logger.error(f"Image intel failed: {e}")
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
        except Exception as e:
            logger.debug(f"Probing {platform} failed: {e}")
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
    if "EMAIL" in comp["types"]: dorks["Credential Breaches"] = f"https://www.google.com/search?q=%22{target}%22+password+OR+leak"
    if "domain" in comp:
        d = comp["domain"]
        dorks["Subdomain Discovery"] = f"https://www.google.com/search?q=site:*.{d}+-www"
        dorks["Cloud Intelligence"] = f"https://www.google.com/search?q=site:s3.amazonaws.com+%22{d}%22"
    if "IMAGE" in comp["types"]: dorks["Visual AI Search"] = f"https://lens.google.com/uploadbyurl?url={target}"
    return dorks

def print_banner():
    print(f"{G}{B}")
    print("    █████╗ ███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗██╗███╗   ██╗███████╗ ██████╗ ")
    print("    ██╔══██╗████╗  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝██║████╗  ██║██╔════╝██╔═══██╗")
    print("    ███████║██╔██╗ ██║██║   ██║██╔██╗ ██║ ╚████╔╝ ██║██╔██╗ ██║█████╗  ██║   ██║")
    print("    ██╔══██║██║╚██╗██║██║   ██║██║╚██╗██║  ╚██╔╝  ██║██║╚██╗██║██╔══╝  ██║   ██║")
    print("    ██║  ██║██║ ╚████║╚██████╔╝██║ ╚████║   ██║   ██║██║ ╚████║██║     ╚██████╔╝")
    print("    ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝ ")
    print(f"    {C}--- ANONYINFO: THE ULTRA-GOD OSINT & PENTEST SUITE v7.0 ---{RES}")

async def run_tool(target, report=False, nocache=False):
    init_db()
    logger.info(f"Starting mission for target: {target}")
    if not nocache:
        cached = get_cached_intel(target)
        if cached:
            print(f"{G}[+] LOADED FROM VAULT (CACHED DATA):{RES}")
            print(json.dumps(cached, indent=4)); return

    print_banner()
    comp = detect_target(target); results = {"target": target, "ts": str(datetime.now()), "data": {}}

    if "IMAGE" in comp["types"]:
        section_header("Image Intelligence"); results["data"]["meta"] = get_image_intel(target)
        for k, v in results["data"]["meta"].items(): print(f"    - {k}: {v}")

    if "URL" in comp["types"] and "IMAGE" not in comp["types"]:
        section_header("Web Fingerprinting"); results["data"]["fingerprint"] = await fingerprint_web(target)
        for k, v in results["data"]["fingerprint"].items(): print(f"    - {k}: {v}")
        results["data"]["vulns"] = await probe_vulnerabilities(target)

    if "PHONE" in comp["types"]:
        section_header("Telecommunication Analysis"); results["data"]["phone"] = get_phone_intel(comp["clean"])
        for k, v in results["data"]["phone"].items(): print(f"    - {k}: {v}")

    if "domain" in comp:
        d = comp["domain"]
        section_header(f"Infrastructure Mapping: {d}"); results["data"]["net"] = get_net_intel(d)
        for k, v in results["data"]["net"].items(): print(f"    - {k}: {v}")
        results["data"]["subs"] = await get_subdomains(d)
        if results["data"]["subs"]:
            print(f"{G}[+] Subdomains Found ({len(results['data']['subs'])}):{RES}")
            for s in results["data"]["subs"][:10]: print(f"    - {s}")
        results["data"]["ports"] = await port_scanner(d)
        if results["data"]["ports"]: print(f"{G}[+] Open Ports Detected: {', '.join(map(str, results['data']['ports']))}{RES}")
        if "URL" not in comp["types"]: results["data"]["vulns"] = await probe_vulnerabilities(f"http://{d}")

    if "username" in comp:
        u = comp["username"]; results["data"]["social"] = await discover_identities(u)
        print(f"\n{G}[+] RECAP: Found {len(results['data']['social'])} matching nodes for '{u}'.{RES}")

    section_header("Surface Web Crawler")
    try:
        with DDGS() as ddgs:
            results["data"]["web"] = [r for r in ddgs.text(target, max_results=10)]
            print(f"{G}[+] Discovered {len(results['data']['web'])} Global Intel Nodes.{RES}")
    except: pass

    section_header("Apex Investigation Links")
    results["data"]["links"] = get_apex_links(target, comp)
    for n, l in results["data"]["links"].items(): print(f"    - {C}{n}{RES}: {l}")

    results["relationships"] = analyze_relationships(target, results["data"])
    if results["relationships"]:
        section_header("Relationship Intelligence")
        for r in results["relationships"]: print(f"    - {Y}{r['from']}{RES} --({r['type']})--> {C}{r['to']}{RES}")

    save_intel(target, ", ".join(comp["types"]), results)
    if report:
        fn = f"ANONYINFO_INTEL_{re.sub(r'[^a-zA-Z0-9]', '_', target)}.json"
        with open(fn, "w") as f: json.dump(results, f, indent=4)
        print(f"\n{Y}[!] REPORT SAVED: {fn}{RES}")
    print(f"\n{G}{B}MISSION ACCOMPLISHED.{RES}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo God-Mode")
    parser.add_argument("target", help="Target Input")
    parser.add_argument("--report", action="store_true", help="JSON Intel Report")
    parser.add_argument("--nocache", action="store_true", help="Force fresh scan")
    asyncio.run(run_tool(parser.parse_args().target, parser.parse_args().report, parser.parse_args().nocache))
