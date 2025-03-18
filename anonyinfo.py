import argparse
import requests
from bs4 import BeautifulSoup
import tweepy
import facebook

# APIs ke liye keys (Inko .env ya config file me store karna best hoga)
TWITTER_API_KEY = "your_api_key_here"
TWITTER_API_SECRET = "your_api_secret_here"
TWITTER_ACCESS_TOKEN = "your_access_token_here"
TWITTER_ACCESS_SECRET = "your_access_token_secret_here"
FACEBOOK_ACCESS_TOKEN = "your_facebook_app_access_token_here"

# Twitter API Setup
auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET)
twitter_api = tweepy.API(auth)

# Facebook API Setup
facebook_api = facebook.GraphAPI(FACEBOOK_ACCESS_TOKEN)

def search_web(target_name):
    """Google par search karega"""
    url = f"https://www.google.com/search?q={target_name}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    links = [link.get("href") for link in soup.find_all("a") if "http" in str(link.get("href"))]
    return links[:5]

def search_twitter(target_name):
    """Twitter profile & tweets dhoondhega"""
    try:
        users = twitter_api.search_users(target_name, count=1)
        if users:
            user = users[0]
            return {
                "username": user.screen_name,
                "bio": user.description,
                "tweets": [tweet.text for tweet in twitter_api.user_timeline(screen_name=user.screen_name, count=3)]
            }
        return {"error": "No Twitter user found"}
    except Exception as e:
        return {"error": f"Twitter search failed: {e}"}

def search_facebook(target_name):
    """Facebook pages check karega"""
    try:
        data = facebook_api.request(f"search?q={target_name}&type=page")
        if data["data"]:
            page = data["data"][0]
            return {"name": page.get("name", "Unknown"), "about": page.get("about", "No about info")}
        return {"error": "No public Facebook page found"}
    except Exception as e:
        return {"error": f"Facebook search failed: {e}"}

def run_tool(target):
    """Tool ka main function"""
    print(f"Searching for: {target}")

    web_results = search_web(target)
    twitter_results = search_twitter(target)
    facebook_results = search_facebook(target)

    print("\n🔍 Web Results:")
    for link in web_results:
        print(f"- {link}")

    print("\n🐦 Twitter Data:")
    print(twitter_results)

    print("\n📘 Facebook Data:")
    print(facebook_results)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo - OSINT Tool")
    parser.add_argument("target", help="Enter the target's name or username")
    args = parser.parse_args()
    run_tool(args.target)
