import re

def analyze_relationships(target, data):
    """
    Builds a relationship map based on gathered data.
    Links: Email -> Domain, User -> Platforms, IP -> Infrastructure
    """
    relations = []

    # 1. Email to Domain link
    if "@" in target:
        domain = target.split("@")[-1]
        relations.append({"from": target, "to": domain, "type": "hosted_on"})

    # 2. Username to Social Presence patterns
    if "social" in data:
        for platform in data["social"].keys():
            relations.append({"from": target, "to": platform, "type": "alias_present"})

    # 3. Infrastructure links
    if "net" in data:
        if "IP Address" in data["net"]:
            ip = data["net"]["IP Address"]
            relations.append({"from": target, "to": ip, "type": "resolves_to"})
        if "ISP" in data["net"]:
            relations.append({"from": target, "to": data["net"]["ISP"], "type": "provider"})

    # 4. Pattern Recognition (Heuristic)
    # If same username is found on dev sites and gaming sites
    dev_count = sum(1 for p in data.get("social", {}).keys() if p in ["GitHub", "GitLab", "Bitbucket", "StackOverflow"])
    game_count = sum(1 for p in data.get("social", {}).keys() if p in ["Steam", "Roblox", "Chess.com", "EpicGames"])

    if dev_count > 0 and game_count > 0:
        relations.append({"from": target, "to": "Dev-Gamer Profile", "type": "persona_detected"})

    return relations
