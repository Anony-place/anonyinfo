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

# --- Massive Social Media Platforms List (100+ for World Best OSINT) ---
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
    "Roblox": "https://www.roblox.com/user.aspx?username={}",
    "TradingView": "https://www.tradingview.com/u/{}/",
    "Snapchat": "https://www.snapchat.com/add/{}",
    "Telegram": "https://t.me/{}",
    "TikTok": "https://www.tiktok.com/@{}",
    "Fiverr": "https://www.fiverr.com/{}",
    "Upwork": "https://www.upwork.com/freelancers/~{}",
    "Freelancer": "https://www.freelancer.com/u/{}",
    "Chess.com": "https://www.chess.com/member/{}",
    "Duolingo": "https://www.duolingo.com/profile/{}",
    "Strava": "https://www.strava.com/athletes/{}",
    "AllTrails": "https://www.alltrails.com/members/{}",
    "BuyMeACoffee": "https://www.buymeacoffee.com/{}",
    "Gumroad": "https://gumroad.com/{}",
    "Linktree": "https://linktr.ee/{}",
    "OnlyFans": "https://onlyfans.com/{}",
    "ProductHunt": "https://www.producthunt.com/@{}",
    "TripAdvisor": "https://www.tripadvisor.com/members/{}",
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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
}

def is_domain_or_ip(target):
    domain_pattern = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$'
    ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    return re.match(domain_pattern, target.lower()) or re.match(ip_pattern, target)

def get_network_info(target):
    info = {}
    try:
        ip_addr = socket.gethostbyname(target)
        info["IP Address"] = ip_addr
        try:
            rdns = socket.gethostbyaddr(ip_addr)
            info["Reverse DNS"] = rdns[0]
        except: pass
        try:
            geo_res = requests.get(f"http://ip-api.com/json/{ip_addr}", timeout=5).json()
            if geo_res.get("status") == "success":
                info["Location"] = f"{geo_res.get('city')}, {geo_res.get('country')}"
                info["ISP"] = geo_res.get("isp")
        except: pass
    except Exception as e:
        info["error"] = f"Resolution failed: {str(e)}"
    return info

def search_web_free(target_name):
    try:
        with DDGS() as ddgs:
            return [r for r in ddgs.text(target_name, max_results=10)]
    except Exception as e:
        return {"error": f"Web search failed: {str(e)}"}

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
                        else:
                            result = (platform, str(response.url))
        except: pass

    progress['count'] += 1
    sys.stdout.write(f"\r{CYAN}[*] Progress: {progress['count']}/{progress['total']} platforms checked...{RESET}")
    sys.stdout.flush()
    if result:
        sys.stdout.write(f"\n{GREEN}[+] Found: {result[0]}{RESET}\n")
    return result

async def check_social_media_async(target_name):
    total = len(SOCIAL_PLATFORMS)
    progress = {'count': 0, 'total': total}
    semaphore = asyncio.Semaphore(20) # Limit concurrency to avoid rate limiting
    print(f"{CYAN}[*] Starting Deep Async Social Discovery for '{target_name}'...{RESET}")
    found = {}
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks = []
        for platform, url_template in SOCIAL_PLATFORMS.items():
            tasks.append(check_platform(session, semaphore, platform, url_template, target_name, progress))
        results = await asyncio.gather(*tasks)
        for res in results:
            if res: found[res[0]] = res[1]
    print(f"\n{CYAN}[*] Social Discovery Completed.{RESET}")
    return found

def generate_dorking_links(target_name):
    dorks = {
        "LinkedIn Profiles": f"https://www.google.com/search?q=site:linkedin.com/in+%22{target_name}%22",
        "Public Documents": f"https://www.google.com/search?q=%22{target_name}%22+filetype:pdf+OR+filetype:doc+OR+filetype:xlsx",
        "Email Leak Search": f"https://www.google.com/search?q=%22{target_name}%22+%40gmail.com+OR+%40outlook.com+OR+%40yahoo.com",
        "Directory Listings": f"https://www.google.com/search?q=intitle:%22index+of%22+%22{target_name}%22",
        "Pastebin/Github Gists": f"https://www.google.com/search?q=site:pastebin.com+OR+site:gist.github.com+%22{target_name}%22",
    }
    # Add phone dorking only if target looks like a number
    if re.sub(r'[^0-9]', '', target_name).isdigit() and len(re.sub(r'[^0-9]', '', target_name)) >= 7:
        clean_num = re.sub(r'[^0-9]', '', target_name)
        dorks["Phone Number OSINT"] = f"https://www.google.com/search?q=%22{target_name}%22+OR+%22{clean_num[:3]}-{clean_num[3:6]}-{clean_num[6:]}%22"
    return dorks

def print_banner():
    banner = f"""{GREEN}{BOLD}
    █████╗ ███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗██╗███╗   ██╗███████╗ ██████╗
    ██╔══██╗████╗  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝██║████╗  ██║██╔════╝██╔═══██╗
    ███████║██╔██╗ ██║██║   ██║██╔██╗ ██║ ╚████╔╝ ██║██╔██╗ ██║█████╗  ██║   ██║
    ██╔══██║██║╚██╗██║██║   ██║██║╚██╗██║  ╚██╔╝  ██║██║╚██╗██║██╔══╝  ██║   ██║
    ██║  ██║██║ ╚████║╚██████╔╝██║ ╚████║   ██║   ██║██║ ╚████║██║     ╚██████╔╝
    ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝
    {CYAN}--- ANONYINFO WORLD BEST FREE OSINT TOOL v3.0 (ULTIMATE) ---{RESET}
    """
    print(banner)

def save_report(target, social, web, dorks, network):
    safe_target = re.sub(r'[^a-zA-Z0-9]', '_', target)
    filename = f"report_{safe_target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"ANONYINFO OSINT REPORT - {target.upper()}\n")
        f.write("="*50 + "\n\n")
        if network:
            f.write("[NETWORK INFO]\n")
            for k, v in network.items(): f.write(f" - {k}: {v}\n")
            f.write("\n")
        f.write("[SOCIAL MEDIA PROFILES]\n")
        for p, u in social.items(): f.write(f" - {p}: {u}\n")
        f.write("\n[WEB RESULTS]\n")
        if isinstance(web, list):
            for r in web: f.write(f" - {r.get('title')}: {r.get('href')}\n")
        f.write("\n[DORKING LINKS]\n")
        for n, l in dorks.items(): f.write(f" - {n}: {l}\n")
    return filename

async def run_tool(target, report=False):
    print_banner()
    print(f"{YELLOW}{BOLD}Target: {target}{RESET}\n")

    net_info = {}
    if is_domain_or_ip(target):
        print(f"{CYAN}[*] Gathering Network Details...{RESET}")
        net_info = get_network_info(target)
        if "error" not in net_info:
            print(f"{GREEN}[+] Network Details:{RESET}")
            for k, v in net_info.items(): print(f"    - {k}: {v}")
        print()

    social_results = await check_social_media_async(target)

    print(f"\n{CYAN}[*] Searching web results...{RESET}")
    web_results = search_web_free(target)
    if isinstance(web_results, list) and web_results:
        print(f"{GREEN}[+] Top Web Results:{RESET}")
        for r in web_results: print(f"    - {BOLD}{r.get('title', 'No Title')}{RESET}: {r.get('href', 'No URL')}")

    dorks = generate_dorking_links(target)
    print(f"\n{GREEN}[+] Deep Investigation Dorks:{RESET}")
    for name, link in dorks.items(): print(f"    - {CYAN}{name}{RESET}: {link}")

    if report:
        fname = save_report(target, social_results, web_results if isinstance(web_results, list) else [], dorks, net_info)
        print(f"\n{YELLOW}[!] Report saved to: {fname}{RESET}")

    print(f"\n{GREEN}{BOLD}Search complete. Happy hunting!{RESET}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo - World Best Free OSINT Tool")
    parser.add_argument("target", help="Enter name, username, domain, or IP")
    parser.add_argument("--report", action="store_true", help="Generate a text report file")
    args = parser.parse_args()
    asyncio.run(run_tool(args.target, args.report))
