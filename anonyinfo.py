import argparse
import requests
from bs4 import BeautifulSoup
import tweepy
import facebook
import os
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Get API keys from environment variables
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_SECRET = os.getenv("TWITTER_ACCESS_SECRET")
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")

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

def search_instagram(target_name):
    """
    Instagram profile dhoondhega.
    WARNING: This function uses an unofficial, unauthenticated API endpoint that is subject to change and may break without notice.
    """
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={target_name}"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "x-ig-app-id": "936619743392459",
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()['data']['user']
            return {
                "biography": data['biography'],
                "followers": data['edge_followed_by']['count'],
                "following": data['edge_follow']['count'],
                "num_posts": data['edge_owner_to_timeline_media']['count'],
                "profile_pic_url": data['profile_pic_url_hd'],
                "verified": data['is_verified'],
            }
        return {"error": "No Instagram user found"}
    except Exception as e:
        return {"error": f"Instagram search failed: {e}"}

def run_tool(target):
    """Tool ka main function"""
    print(f"Searching for: {target}")

    results = {
        "web": search_web(target),
        "twitter": search_twitter(target),
        "facebook": search_facebook(target),
        "instagram": search_instagram(target),
    }

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnonyInfo - OSINT Tool")
    parser.add_argument("target", help="Enter the target's name or username")
    args = parser.parse_args()
    run_tool(args.target)
