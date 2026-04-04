import argparse
import requests
import json
import re
import socket
from ddgs import DDGS

# --- Social Media Platforms to check ---
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
}

# --- Browser Headers ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
}

# --- ANSI Colors for 'Hacker' Aesthetic ---
GREEN = '\033[92m'
CYAN = '\033[96m'
YELLOW = '\033[93m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'

def is_domain_or_ip(target):
    """Checks if the target looks like a domain name or IP address"""
    domain_pattern = r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$'
    ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    return re.match(domain_pattern, target.lower()) or re.match(ip_pattern, target)

def get_network_info(target):
    """Gathers basic DNS/IP info if target is a domain/IP"""
    info = {}
    try:
        ip_addr = socket.gethostbyname(target)
        info["IP Address"] = ip_addr
        try:
            rdns = socket.gethostbyaddr(ip_addr)
            info["Reverse DNS"] = rdns[0]
        except:
            pass

        try:
            geo_res = requests.get(f"http://ip-api.com/json/{ip_addr}", timeout=5).json()
            if geo_res.get("status") == "success":
                info["Location"] = f"{geo_res.get('city')}, {geo_res.get('country')}"
                info["ISP"] = geo_res.get("isp")
        except:
            pass

    except Exception as e:
        info["error"] = f"Could not resolve host: {str(e)}"
    return info

def search_web_free(target_name):
    """Searches using DuckDuckGo (Free & Open Source)"""
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(target_name, max_results=10)]
            return results
    except Exception as e:
        return {"error": f"Web search failed: {str(e)}"}

def check_social_media(target_name):
    """Checks for profiles across multiple platforms"""
    found = {}
    print(f"{CYAN}[*] Searching social media profiles for '{target_name}'...{RESET}")

    with requests.Session() as session:
        session.headers.update(HEADERS)
        for platform, url_template in SOCIAL_PLATFORMS.items():
            url = url_template.format(target_name)
            try:
                response = session.get(url, timeout=5, allow_redirects=True)
                if response.status_code == 200:
                    final_url = response.url.lower()
                    if any(x in final_url for x in ["login", "signup", "register", "404"]):
                        continue
                    # Content based filtering for false positives
                    text = response.text.lower()
                    if "pinterest.com" in url and "404" in text:
                        continue
                    if "reddit.com" in url and "nobody on reddit goes by that name" in text:
                        continue
                    if "github.com" in url and "find any users matching" in text:
                        continue

                    found[platform] = response.url
                    print(f"{GREEN}[+] Found: {platform}{RESET}")
            except Exception:
                continue
    return found

def generate_dorking_links(target_name):
    """Generates Google Dorking links for deeper investigation"""
    dorks = {
        "LinkedIn Profiles": f"https://www.google.com/search?q=site:linkedin.com/in+%22{target_name}%22",
        "Public Documents": f"https://www.google.com/search?q=%22{target_name}%22+filetype:pdf+OR+filetype:doc+OR+filetype:xlsx",
        "Email Leak Search": f"https://www.google.com/search?q=%22{target_name}%22+%40gmail.com+OR+%40outlook.com+OR+%40yahoo.com",
        "Directory Listings": f"https://www.google.com/search?q=intitle:%22index+of%22+%22{target_name}%22",
        "Pastebin/Github Gists": f"https://www.google.com/search?q=site:pastebin.com+OR+site:gist.github.com+%22{target_name}%22",
    }
    return dorks

def print_banner():
    banner = f"""{GREEN}{BOLD}
    █████╗ ███╗   ██╗ ██████╗ ███╗   ██╗██╗   ██╗██╗███╗   ██╗███████╗ ██████╗
    ██╔══██╗████╗  ██║██╔═══██╗████╗  ██║╚██╗ ██╔╝██║████╗  ██║██╔════╝██╔═══██╗
    ███████║██╔██╗ ██║██║   ██║██╔██╗ ██║ ╚████╔╝ ██║██╔██╗ ██║█████╗  ██║   ██║
    ██╔══██║██║╚██╗██║██║   ██║██║╚██╗██║  ╚██╔╝  ██║██║╚██╗██║██╔══╝  ██║   ██║
    ██║  ██║██║ ╚████║╚██████╔╝██║ ╚████║   ██║   ██║██║ ╚████║██║     ╚██████╔╝
    ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚═╝  ╚═══╝╚═╝      ╚═════╝
    {CYAN}--- The Ultimate Free & Open Source OSINT Tool v2.0 ---{RESET}
    """
    print(banner)

def run_tool(target):
    print_banner()

    print(f"{YELLOW}{BOLD}Target: {target}{RESET}\n")

    # Network Info if applicable
    if is_domain_or_ip(target):
        print(f"{CYAN}[*] Gathering Network Info for '{target}'...{RESET}")
        net_info = get_network_info(target)
        if "error" not in net_info:
            print(f"{GREEN}[+] Network Details:{RESET}")
            for k, v in net_info.items():
                print(f"    - {k}: {v}")
        else:
            print(f"    {RED}[!] {net_info['error']}{RESET}")
        print()

    # Social Media
    social_results = check_social_media(target)
    if social_results:
        print(f"\n{GREEN}[+] Found {len(social_results)} Social Media Profiles:{RESET}")
        for p, u in social_results.items():
            print(f"    - {CYAN}{p}{RESET}: {u}")
    else:
        print(f"\n{YELLOW}[!] No direct social media profiles found.{RESET}")

    # Web Results
    print(f"\n{CYAN}[*] Searching web results...{RESET}")
    web_results = search_web_free(target)
    if isinstance(web_results, list) and web_results:
        print(f"{GREEN}[+] Top Web Results:{RESET}")
        for r in web_results:
            print(f"    - {BOLD}{r.get('title', 'No Title')}{RESET}: {r.get('href', 'No URL')}")
    elif not web_results:
         print(f"{YELLOW}[!] No web results found.{RESET}")
    else:
        print(f"    {RED}[!] {web_results.get('error')}{RESET}")

    # Dorking Links
    print(f"\n{GREEN}[+] Deep Investigation Dorks:{RESET}")
    dorks = generate_dorking_links(target)
    for name, link in dorks.items():
        print(f"    - {CYAN}{name}{RESET}: {link}")

    print("\n" + "="*70)
    print(f"{GREEN}{BOLD}   Search complete. Happy hunting!{RESET}")
    print("="*70 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo - Ultimate Free OSINT Tool")
    parser.add_argument("target", help="Enter the target's name, username, domain, or IP")
    args = parser.parse_args()
    run_tool(args.target)
