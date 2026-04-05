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

# --- Categories: Social, Dev, Gaming, Creative, International, Lifestyle ---
SOCIAL_PLATFORMS = {
    "GitHub": "https://github.com/{}", "YouTube": "https://www.youtube.com/@{}", "Twitch": "https://www.twitch.tv/{}", "Reddit": "https://www.reddit.com/user/{}",
    "Medium": "https://medium.com/@{}", "Pinterest": "https://www.pinterest.com/{}", "Tumblr": "https://{}.tumblr.com", "Mastodon": "https://mastodon.social/@{}",
    "Substack": "https://{}.substack.com", "Twitter/X": "https://x.com/{}", "Quora": "https://www.quora.com/profile/{}", "VK": "https://vk.com/{}",
    "OK.ru": "https://ok.ru/{}", "Weibo": "https://weibo.com/{}", "Linktree": "https://linktr.ee/{}", "Snapchat": "https://www.snapchat.com/add/{}",
    "Telegram": "https://t.me/{}", "TikTok": "https://www.tiktok.com/@{}", "Discord": "https://discord.com/users/{}", "Clubhouse": "https://www.clubhouse.com/@{}",
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

# --- ANSI Colors ---
G, C, Y, R, B, RES = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[1m', '\033[0m'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}

def detect_target_components(target):
    comp = {"original": target, "types": []}
    em = re.match(r'^([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})$', target)
    if em:
        comp["types"].append("EMAIL"); comp["username"] = em.group(1); comp["domain"] = em.group(2)
        return comp
    if re.match(r'^https?://', target):
        comp["types"].append("URL")
        if any(target.lower().endswith(x) for x in ['.jpg', '.jpeg', '.png', '.gif', '.webp']): comp["types"].append("IMAGE")
        try: comp["domain"] = target.split('//')[-1].split('/')[0]
        except: pass
        return comp
    cp = re.sub(r'[^0-9+]', '', target)
    if (cp.startswith('+') and cp[1:].isdigit()) or (cp.isdigit() and 7 <= len(cp) <= 15):
        comp["types"].append("PHONE"); comp["clean_phone"] = cp
        return comp
    dp = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$'
    ip = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.match(dp, target.lower()) or re.match(ip, target):
        comp["types"].append("NETWORK"); comp["domain"] = target
        return comp
    comp["types"].append("USER"); comp["username"] = target
    return comp

def get_network_info(domain):
    info = {}
    try:
        ip = socket.gethostbyname(domain); info["IP Address"] = ip
        for rt in ['MX', 'TXT', 'A', 'NS']:
            try: info[f"DNS {rt}"] = [str(r) for r in dns.resolver.resolve(domain, rt)]
            except: pass
        geo = requests.get(f"http://ip-api.com/json/{ip}", timeout=5).json()
        if geo.get("status") == "success":
            info["Location"] = f"{geo.get('city')}, {geo.get('country')}"; info["ISP"] = geo.get('isp')
    except Exception as e: info["error"] = str(e)
    return info

def get_phone_info(phone):
    info = {}
    try:
        p = phonenumbers.parse(phone if phone.startswith('+') else "+" + phone)
        if phonenumbers.is_valid_number(p):
            info["Valid"] = "Yes"; info["Format"] = phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            info["Region"] = geocoder.description_for_number(p, "en"); info["Carrier"] = carrier.name_for_number(p, "en")
        else: info["Valid"] = "Invalid Format"
    except Exception as e: info["error"] = str(e)
    return info

def get_image_metadata(url):
    meta = {}
    try:
        r = requests.get(url, timeout=10)
        tags = exifread.process_file(BytesIO(r.content))
        for t in tags.keys():
            if t not in ('JPEGThumbnail', 'TIFFThumbnail', 'Filename', 'EXIF MakerNote'): meta[t] = str(tags[t])
    except Exception as e: meta["error"] = str(e)
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
                            print(f"\n{G}[+] Found: {platform}{RES}")
        except: pass
    prog['c'] += 1
    sys.stdout.write(f"\r{C}[*] OSINT Progress: {prog['c']}/{prog['t']} platforms probed...{RES}"); sys.stdout.flush()

async def discover_social(username):
    print(f"{C}[*] Triggering Global Identity Discovery for '{username}'...{RES}")
    found, prog = {}, {'c': 0, 't': len(SOCIAL_PLATFORMS)}
    sem = asyncio.Semaphore(40)
    async with aiohttp.ClientSession(headers=HEADERS) as s:
        await asyncio.gather(*[check_platform(s, sem, p, u, username, found, prog) for p, u in SOCIAL_PLATFORMS.items()])
    return found

def get_deep_dorks(target, comp):
    dorks = {"Leaks & Pastes": f"https://www.google.com/search?q=site:pastebin.com+OR+site:gist.github.com+%22{target}%22"}
    if "EMAIL" in comp["types"]: dorks["Database Leaks"] = f"https://www.google.com/search?q=%22{target}%22+filetype:sql+OR+filetype:txt+OR+filetype:csv"
    if "domain" in comp:
        d = comp["domain"]
        dorks["Subdomains"] = f"https://www.google.com/search?q=site:*.{d}+-www"
        dorks["Sensitive Configs"] = f"https://www.google.com/search?q=site:{d}+ext:env+OR+ext:yaml+OR+ext:sql"
    if "IMAGE" in comp["types"]:
        dorks["Google Lens"] = f"https://lens.google.com/uploadbyurl?url={target}"
        dorks["Yandex Visual"] = f"https://yandex.com/images/search?rpt=imageview&url={target}"
    return dorks

def print_banner():
    print(f"{G}{B}")
    print("    █████╗ ███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗██╗███╗   ██╗███████╗ ██████╗ ")
    print("    ██╔══██╗████╗  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝██║████╗  ██║██╔════╝██╔═══██╗")
    print("    ███████║██╔██╗ ██║██║   ██║██╔██╗ ██║ ╚████╔╝ ██║██╔██╗ ██║█████╗  ██║   ██║")
    print("    ██╔══██║██║╚██╗██║██║   ██║██║╚██╗██║  ╚██╔╝  ██║██║╚██╗██║██╔══╝  ██║   ██║")
    print("    ██║  ██║██║ ╚████║╚██████╔╝██║ ╚████║   ██║   ██║██║ ╚████║██║     ╚██████╔╝")
    print("    ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝ ")
    print(f"    {C}--- ANONYINFO: THE GOD-MODE UNIVERSAL OSINT SUITE v5.0 ---{RES}")

async def run_tool(target, report=False):
    print_banner()
    comp = detect_target_components(target)
    print(f"{Y}{B}Detected Target Signature: {', '.join(comp['types'])}{RES}\n")
    results = {"target": target, "analysis": comp, "timestamp": str(datetime.now())}

    if "IMAGE" in comp["types"]:
        print(f"{C}[*] Extracting Image Intelligence...{RES}"); results["meta"] = get_image_metadata(target)
        if results["meta"]:
            for k, v in results["meta"].items(): print(f"    - {k}: {v}")
        else: print(f"    {Y}[!] No metadata embedded in image.{RES}")

    if "PHONE" in comp["types"]:
        print(f"{C}[*] Analyzing Phone Telemetry...{RES}"); results["phone"] = get_phone_info(comp["clean_phone"])
        for k, v in results["phone"].items(): print(f"    - {k}: {v}")

    if "domain" in comp:
        d = comp["domain"]
        print(f"\n{C}[*] Mapping Network Infrastructure for '{d}'...{RES}"); results["net"] = get_network_info(d)
        for k, v in results["net"].items(): print(f"    - {k}: {v}")

    if "username" in comp:
        u = comp["username"]
        results["social"] = await discover_social(u)
        print(f"\n{G}[+] Discovered {len(results['social'])} Unique Profiles for identity '{u}'.{RES}")
        for p, url in results["social"].items(): print(f"    - {C}{p}{RES}: {url}")

    print(f"\n{C}[*] Crawling Web Surface...{RES}")
    try:
        with DDGS() as ddgs:
            results["web"] = [r for r in ddgs.text(target, max_results=10)]
            print(f"{G}[+] Found {len(results['web'])} Web Intelligence Nodes.{RES}")
            for r in results["web"]: print(f"    - {B}{r.get('title')}{RES}: {r.get('href')}")
    except: results["web"] = []

    results["dorks"] = get_deep_dorks(target, comp)
    print(f"\n{G}[+] God-Mode Investigation Links Generated:{RES}")
    for n, l in results["dorks"].items(): print(f"    - {C}{n}{RES}: {l}")

    if report:
        fn = f"ANONYINFO_INTEL_{re.sub(r'[^a-zA-Z0-9]', '_', target)}.json"
        with open(fn, "w") as f: json.dump(results, f, indent=4)
        print(f"\n{Y}[!] FULL INTELLIGENCE REPORT SAVED: {fn}{RES}")
    print(f"\n{G}{B}GOD-MODE OSINT COMPLETE. TARGET EXPOSED.{RES}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo God-Mode")
    parser.add_argument("target", help="Email, Phone, Name, Domain, IP, or Image URL")
    parser.add_argument("--report", action="store_true", help="Generate full JSON report")
    asyncio.run(run_tool(parser.parse_args().target, parser.parse_args().report))
