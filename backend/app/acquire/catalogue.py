"""Starter catalogue of popular platforms and the public URLs of their privacy policies and terms.

`ota` names the service and document in Open Terms Archive (contrib collection), used as a fallback when a
site refuses or times out. URLs were checked by hand on 2026-10-26; sites move them, so a failed fetch falls
back rather than failing silently.
"""

def _doc(kind, url, ota=None):
    return {"kind": kind, "url": url, "ota": ota}


PRIVACY, TERMS = "privacy", "terms"

SERVICES = [
    {"id": "google", "name": "Google", "domain": "google.com", "aliases": ["google.co.in", "gmail.com"], "region": "global", "docs": [
        _doc(PRIVACY, "https://policies.google.com/privacy?hl=en", ("Google", "Privacy Policy")),
        _doc(TERMS, "https://policies.google.com/terms?hl=en", ("Google", "Terms of Service"))]},
    {"id": "youtube", "name": "YouTube", "domain": "youtube.com", "region": "global", "docs": [
        _doc(TERMS, "https://www.youtube.com/t/terms", ("YouTube", "Terms of Service"))]},
    {"id": "whatsapp", "name": "WhatsApp", "domain": "whatsapp.com", "region": "global", "docs": [
        _doc(PRIVACY, "https://www.whatsapp.com/legal/privacy-policy", ("WhatsApp", "Privacy Policy")),
        _doc(TERMS, "https://www.whatsapp.com/legal/terms-of-service", ("WhatsApp", "Terms of Service"))]},
    {"id": "instagram", "name": "Instagram", "domain": "instagram.com", "region": "global", "docs": [
        _doc(PRIVACY, "https://privacycenter.instagram.com/policy", ("Instagram", "Privacy Policy")),
        _doc(TERMS, "https://help.instagram.com/581066165581870", ("Instagram", "Terms of Service"))]},
    {"id": "facebook", "name": "Facebook", "domain": "facebook.com", "aliases": ["facebookmail.com", "meta.com"], "region": "global", "docs": [
        _doc(PRIVACY, "https://www.facebook.com/privacy/policy/", ("Facebook", "Privacy Policy")),
        _doc(TERMS, "https://www.facebook.com/legal/terms", ("Facebook", "Terms of Service"))]},
    {"id": "x", "name": "X (Twitter)", "domain": "x.com", "aliases": ["twitter.com"], "region": "global", "docs": [
        _doc(PRIVACY, "https://x.com/en/privacy", ("Twitter", "Privacy Policy")),
        _doc(TERMS, "https://x.com/en/tos", ("Twitter", "Terms of Service"))]},
    {"id": "linkedin", "name": "LinkedIn", "domain": "linkedin.com", "region": "global", "docs": [
        _doc(PRIVACY, "https://www.linkedin.com/legal/privacy-policy", ("LinkedIn", "Privacy Policy")),
        _doc(TERMS, "https://www.linkedin.com/legal/user-agreement", ("LinkedIn", "Terms of Service"))]},
    {"id": "spotify", "name": "Spotify", "domain": "spotify.com", "region": "global", "docs": [
        _doc(PRIVACY, "https://www.spotify.com/us/legal/privacy-policy/", ("Spotify", "Privacy Policy")),
        _doc(TERMS, "https://www.spotify.com/us/legal/end-user-agreement/", ("Spotify", "Terms of Service"))]},
    {"id": "netflix", "name": "Netflix", "domain": "netflix.com", "region": "global", "docs": [
        _doc(PRIVACY, "https://help.netflix.com/legal/privacy", ("Netflix", "Privacy Policy")),
        _doc(TERMS, "https://help.netflix.com/legal/termsofuse", ("Netflix", "Terms of Service"))]},
    {"id": "amazon", "name": "Amazon India", "domain": "amazon.in", "region": "india", "docs": [
        _doc(PRIVACY, "https://www.amazon.in/gp/help/customer/display.html?nodeId=200534380"),
        _doc(TERMS, "https://www.amazon.in/gp/help/customer/display.html?nodeId=200545940")]},
    {"id": "uber", "name": "Uber", "domain": "uber.com", "region": "global", "docs": [
        _doc(PRIVACY, "https://www.uber.com/global/en/privacy-notice-riders-order-recipients/"),
        _doc(TERMS, "https://www.uber.com/in/en/legal/general-terms-of-use/")]},
    {"id": "openai", "name": "OpenAI / ChatGPT", "domain": "openai.com", "aliases": ["chatgpt.com"], "region": "global", "docs": [
        _doc(PRIVACY, "https://openai.com/policies/privacy-policy/"),
        _doc(TERMS, "https://openai.com/policies/terms-of-use/")]},
    {"id": "microsoft", "name": "Microsoft", "domain": "microsoft.com", "aliases": ["live.com", "outlook.com", "bing.com"], "region": "global", "docs": [
        _doc(PRIVACY, "https://www.microsoft.com/en-us/privacy/privacystatement", ("Microsoft", "Privacy Policy")),
        _doc(TERMS, "https://www.microsoft.com/en-us/servicesagreement", ("Microsoft", "Terms of Service"))]},
    {"id": "zoom", "name": "Zoom", "domain": "zoom.com", "aliases": ["zoom.us"], "region": "global", "docs": [
        _doc(PRIVACY, "https://www.zoom.com/en/trust/privacy/privacy-statement/", ("Zoom", "Privacy Policy")),
        _doc(TERMS, "https://www.zoom.com/en/trust/terms/", ("Zoom", "Terms of Service"))]},
    {"id": "reddit", "name": "Reddit", "domain": "reddit.com", "aliases": ["redditmail.com", "redditinc.com"], "region": "global", "docs": [
        _doc(PRIVACY, "https://www.reddit.com/policies/privacy-policy", ("Reddit", "Privacy Policy")),
        _doc(TERMS, "https://redditinc.com/policies/user-agreement", ("Reddit", "Terms of Service"))]},
    {"id": "zomato", "name": "Zomato", "domain": "zomato.com", "region": "india", "docs": [
        _doc(PRIVACY, "https://www.zomato.com/policies/privacy/"),
        _doc(TERMS, "https://www.zomato.com/policies/terms-of-service/")]},
    {"id": "swiggy", "name": "Swiggy", "domain": "swiggy.com", "aliases": ["swiggy.in"], "region": "india", "docs": [
        _doc(PRIVACY, "https://www.swiggy.com/privacy-policy"),
        _doc(TERMS, "https://www.swiggy.com/terms-and-conditions")]},
    {"id": "flipkart", "name": "Flipkart", "domain": "flipkart.com", "region": "india", "docs": [
        _doc(PRIVACY, "https://www.flipkart.com/pages/privacypolicy"),
        _doc(TERMS, "https://www.flipkart.com/pages/terms")]},
    {"id": "phonepe", "name": "PhonePe", "domain": "phonepe.com", "region": "india", "docs": [
        _doc(PRIVACY, "https://www.phonepe.com/privacy-policy/"),
        _doc(TERMS, "https://www.phonepe.com/terms-conditions/")]},
]

BY_ID = {s["id"]: s for s in SERVICES}


def ota_for(url: str) -> tuple[str, str] | None:
    for s in SERVICES:
        for d in s["docs"]:
            if d["url"] == url:
                return d["ota"]
    return None


def service_for_domain(domain: str) -> dict | None:
    """The catalogue service whose site this is (www.spotify.com and open.spotify.com both map to Spotify)."""
    domain = domain.lower().rstrip(".")
    for s in SERVICES:
        for d in [s["domain"], *s.get("aliases", [])]:
            if domain == d or domain.endswith("." + d):
                return s
    return None
