import argparse
import requests
import json
import re
import socket
import asyncio
import aiohttp
from ddgs import DDGS
from datetime import datetime
import sys
import os
import dns.resolver
import phonenumbers
from phonenumbers import geocoder, carrier

# --- Configuration & Social Platform Database (80+) ---
SOCIAL_PLATFORMS = {
    "GitHub": "https://github.com/{}",
    "YouTube": "https://www.youtube.com/@{}",
    "Twitch": "https://www.twitch.tv/{}",
    "Reddit": "https://www.reddit.com/user/{}",
    "Medium": "https://medium.com/@{}",
    "Pinterest": "https://www.pinterest.com/{}",
    "SoundCloud": "https://soundcloud.com/{}",
    "Steam": "https://steamcommunity.com/id/{}",
    "Behance": "https://www.behance.net/{}",
    "Flickr": "https://www.flickr.com/people/{}",
    "Vimeo": "https://vimeo.com/{}",
    "Dribbble": "https://dribbble.com/{}",
    "Tumblr": "https://{}.tumblr.com",
    "DeviantArt": "https://www.deviantart.com/{}",
    "About.me": "https://about.me/{}",
    "SlideShare": "https://www.slideshare.net/{}",
    "Keybase": "https://keybase.io/{}",
    "OpenStreetMap": "https://www.openstreetmap.org/user/{}",
    "Spotify": "https://open.spotify.com/user/{}",
    "Mastodon": "https://mastodon.social/@{}",
    "CodePen": "https://codepen.io/{}",
    "Letterboxd": "https://letterboxd.com/{}",
    "Patreon": "https://www.patreon.com/{}",
    "Substack": "https://{}.substack.com",
    "Snapchat": "https://www.snapchat.com/add/{}",
    "Telegram": "https://t.me/{}",
    "TikTok": "https://www.tiktok.com/@{}",
    "Roblox": "https://www.roblox.com/user.aspx?username={}",
    "TradingView": "https://www.tradingview.com/u/{}/",
    "Fiverr": "https://www.fiverr.com/{}",
    "Upwork": "https://www.upwork.com/freelancers/~{}",
    "Freelancer": "https://www.freelancer.com/u/{}",
    "Chess.com": "https://www.chess.com/member/{}",
    "Duolingo": "https://www.duolingo.com/profile/{}",
    "Strava": "https://www.strava.com/athletes/{}",
    "BuyMeACoffee": "https://www.buymeacoffee.com/{}",
    "Gumroad": "https://gumroad.com/{}",
    "Linktree": "https://linktr.ee/{}",
    "OnlyFans": "https://onlyfans.com/{}",
    "ProductHunt": "https://www.producthunt.com/@{}",
    "WordPress": "https://{}.wordpress.com",
    "Blogspot": "https://{}.blogspot.com",
    "Codechef": "https://www.codechef.com/users/{}",
    "Hackerrank": "https://www.hackerrank.com/{}",
    "LeetCode": "https://leetcode.com/{}",
    "Kaggle": "https://www.kaggle.com/{}",
    "TryHackMe": "https://tryhackme.com/p/{}",
    "HackTheBox": "https://www.hackthebox.eu/home/users/profile/{}",
    "Badoo": "https://badoo.com/en/profile/{}",
    "Tinder": "https://tinder.com/@{}",
    "Bumble": "https://bumble.com/en/profile/{}",
    "OkCupid": "https://www.okcupid.com/profile/{}",
    "Match": "https://www.match.com/profile/{}",
    "POF": "https://www.pof.com/viewprofile.aspx?profile_id={}",
    "VK": "https://vk.com/{}",
    "OK.ru": "https://ok.ru/{}",
    "Quora": "https://www.quora.com/profile/{}",
    "Ask.fm": "https://ask.fm/{}",
    "Wattpad": "https://www.wattpad.com/user/{}",
    "Canva": "https://www.canva.com/{}",
    "CreativeMarket": "https://creativemarket.com/{}",
    "Envato": "https://{}.envato.com",
    "EyeEm": "https://www.eyeem.com/u/{}",
    "500px": "https://500px.com/p/{}",
    "VSCO": "https://vsco.co/{}",
    "Bandcamp": "https://bandcamp.com/{}",
    "Mixcloud": "https://www.mixcloud.com/{}",
    "Last.fm": "https://www.last.fm/user/{}",
    "ReverbNation": "https://www.reverbnation.com/{}",
    "Splice": "https://splice.com/{}",
    "Discogs": "https://www.discogs.com/user/{}",
    "Goodreads": "https://www.goodreads.com/{}",
    "LibraryThing": "https://www.librarything.com/profile/{}",
    "Listography": "https://listography.com/{}",
    "MyAnimeList": "https://myanimelist.net/profile/{}",
    "Anilist": "https://anilist.co/user/{}",
    "Trakt": "https://trakt.tv/users/{}",
    "Metacritic": "https://www.metacritic.com/user/{}",
    "GOG": "https://www.gog.com/u/{}",
    "Itch.io": "https://{}.itch.io",
    "Speedrun": "https://www.speedrun.com/user/{}",
    "NexusMods": "https://www.nexusmods.com/users/{}",
    "EpicGames": "https://www.epicgames.com/id/{}",
}

# --- ANSI Colors ---
GREEN, CYAN, YELLOW, RED, BOLD, RESET = '\033[92m', '\033[96m', '\033[93m', '\033[91m', '\033[1m', '\033[0m'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'}

# --- Core Modules ---

def detect_input_type(target):
    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', target): return "EMAIL"
    if re.match(r'^https?://', target):
        if any(target.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']): return "IMAGE"
        return "URL"
    clean_target = re.sub(r'[^0-9+]', '', target)
    if (clean_target.startswith('+') and clean_target[1:].isdigit()) or (clean_target.isdigit() and 7 <= len(clean_target) <= 15): return "PHONE"
    domain_pattern = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$'
    ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.match(domain_pattern, target.lower()) or re.match(ip_pattern, target): return "NETWORK"
    return "USER"

def get_network_info(target):
    info = {}
    try:
        ip_addr = socket.gethostbyname(target)
        info["IP Address"] = ip_addr
        try:
            rdns = socket.gethostbyaddr(ip_addr)
            info["Reverse DNS"] = rdns[0]
        except: pass
        for rtype in ['MX', 'TXT', 'A', 'NS']:
            try:
                answers = dns.resolver.resolve(target, rtype)
                info[f"DNS {rtype}"] = [str(rdata) for rdata in answers]
            except: pass
        try:
            geo_res = requests.get(f"http://ip-api.com/json/{ip_addr}", timeout=5).json()
            if geo_res.get("status") == "success":
                info["Location"] = f"{geo_res.get('city')}, {geo_res.get('country')}"
                info["ISP"] = geo_res.get("isp")
        except: pass
    except Exception as e: info["error"] = str(e)
    return info

def get_phone_info(target):
    info = {}
    try:
        parsed_num = phonenumbers.parse(target if target.startswith('+') else "+" + target)
        if phonenumbers.is_valid_number(parsed_num):
            info["Valid"] = "Yes"
            info["International"] = phonenumbers.format_number(parsed_num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            info["Country"] = geocoder.description_for_number(parsed_num, "en")
            info["Carrier"] = carrier.name_for_number(parsed_num, "en")
        else: info["Valid"] = "Invalid Format"
    except Exception as e: info["error"] = str(e)
    return info

async def check_platform(session, semaphore, platform, url_template, target, progress):
    url = url_template.format(target)
    result = None
    async with semaphore:
        try:
            async with session.get(url, timeout=10, allow_redirects=True) as response:
                if response.status == 200:
                    final_url = str(response.url).lower()
                    if any(x in final_url for x in ["login", "signup", "register", "404"]): pass
                    else:
                        text = (await response.text()).lower()
                        if "pinterest.com" in url and "404" in text: pass
                        elif "reddit.com" in url and "nobody on reddit goes by that name" in text: pass
                        elif "github.com" in url and "find any users matching" in text: pass
                        else: result = (platform, str(response.url))
        except: pass
    progress['count'] += 1
    sys.stdout.write(f"\r{CYAN}[*] Searching social media: {progress['count']}/{progress['total']}...{RESET}")
    sys.stdout.flush()
    if result: sys.stdout.write(f"\n{GREEN}[+] Found: {result[0]}{RESET}\n")
    return result

async def check_social_media_async(target_name):
    total = len(SOCIAL_PLATFORMS)
    progress = {'count': 0, 'total': total}
    semaphore = asyncio.Semaphore(20)
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = [check_platform(session, semaphore, p, u, target_name, progress) for p, u in SOCIAL_PLATFORMS.items()]
        results = await asyncio.gather(*tasks)
    return {res[0]: res[1] for res in results if res}

def get_osint_links(target, input_type):
    links = {}
    if input_type == "USER":
        links["LinkedIn"] = f"https://www.google.com/search?q=site:linkedin.com/in+%22{target}%22"
        links["Leaks/Pastes"] = f"https://www.google.com/search?q=site:pastebin.com+OR+site:gist.github.com+%22{target}%22"
    elif input_type == "EMAIL":
        links["Data Leaks"] = f"https://www.google.com/search?q=%22{target}%22+leak+OR+password"
        links["Social Search"] = f"https://www.google.com/search?q=%22{target}%22"
    elif input_type == "PHONE":
        clean = re.sub(r'[^0-9]', '', target)
        links["Caller ID Check"] = f"https://www.google.com/search?q=%22{clean}%22+OR+%22{target}%22"
    elif input_type == "IMAGE":
        links["Google Lens"] = f"https://lens.google.com/uploadbyurl?url={target}"
        links["Yandex"] = f"https://yandex.com/images/search?rpt=imageview&url={target}"
        links["Bing Visual Search"] = f"https://www.bing.com/images/searchbyimage?cbir=sbi&imgurl={target}"
    elif input_type == "NETWORK":
        links["Shodan"] = f"https://www.shodan.io/search?query={target}"
        links["Whois"] = f"https://who.is/whois/{target}"
        links["Censys"] = f"https://censys.io/ipv4/{target}"
    return links

def print_banner():
    print(f"{GREEN}{BOLD}")
    print("    █████╗ ███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗██╗███╗   ██╗███████╗ ██████╗ ")
    print("    ██╔══██╗████╗  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝██║████╗  ██║██╔════╝██╔═══██╗")
    print("    ███████║██╔██╗ ██║██║   ██║██╔██╗ ██║ ╚████╔╝ ██║██╔██╗ ██║█████╗  ██║   ██║")
    print("    ██╔══██║██║╚██╗██║██║   ██║██║╚██╗██║  ╚██╔╝  ██║██║╚██╗██║██╔══╝  ██║   ██║")
    print("    ██║  ██║██║ ╚████║╚██████╔╝██║ ╚████║   ██║   ██║██║ ╚████║██║     ╚██████╔╝")
    print("    ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝ ")
    print(f"    {CYAN}--- ANONYINFO: THE UNIVERSAL OPEN-SOURCE OSINT TOOL v4.0 ---{RESET}")

async def run_tool(target, report=False):
    print_banner()
    input_type = detect_input_type(target)
    print(f"{YELLOW}{BOLD}Target: {target} (Type: {input_type}){RESET}\n")
    results = {"target": target, "type": input_type, "timestamp": str(datetime.now())}

    if input_type == "NETWORK":
        print(f"{CYAN}[*] Gathering Network Details...{RESET}")
        results["network"] = get_network_info(target)
        for k, v in results["network"].items(): print(f"    - {k}: {v}")
        print()
    elif input_type == "PHONE":
        print(f"{CYAN}[*] Gathering Phone Details...{RESET}")
        results["phone"] = get_phone_info(target)
        for k, v in results["phone"].items(): print(f"    - {k}: {v}")
        print()
    elif input_type == "IMAGE":
        print(f"{GREEN}[+] Reverse Search Links Ready.{RESET}")

    # Web Search (Always)
    print(f"{CYAN}[*] Searching the web...{RESET}")
    try:
        with DDGS() as ddgs:
            results["web"] = [r for r in ddgs.text(target, max_results=10)]
            print(f"{GREEN}[+] Found {len(results['web'])} Web Results.{RESET}")
            for r in results["web"]: print(f"    - {BOLD}{r.get('title', 'No Title')}{RESET}: {r.get('href', 'No URL')}")
    except Exception as e:
        results["web"] = []
        print(f"{RED}[!] Web search failed: {e}{RESET}")

    # Social Discovery
    if input_type in ["USER", "EMAIL"]:
        results["social"] = await check_social_media_async(target.split('@')[0])
        print(f"\n\n{GREEN}[+] Discovered {len(results['social'])} Social Profiles.{RESET}")
        for p, u in results["social"].items(): print(f"    - {CYAN}{p}{RESET}: {u}")

    # Dorks
    results["links"] = get_osint_links(target, input_type)
    print(f"\n{GREEN}[+] Deep Investigation Links:{RESET}")
    for name, link in results["links"].items(): print(f"    - {CYAN}{name}{RESET}: {link}")

    if report:
        fname = f"report_{re.sub(r'[^a-zA-Z0-9]', '_', target)}.json"
        with open(fname, "w") as f: json.dump(results, f, indent=2)
        print(f"\n{YELLOW}[!] Report saved to: {fname}{RESET}")
    print(f"\n{GREEN}{BOLD}Universal Search Complete.{RESET}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo OSINT")
    parser.add_argument("target", help="Email, Phone, Name, Domain, or Image URL")
    parser.add_argument("--report", action="store_true", help="JSON report")
    asyncio.run(run_tool(parser.parse_args().target, parser.parse_args().report))
