import re


class SocialExtractor:

    PATTERNS = {
        "email": [
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
        ],

        "instagram": [
            r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9._-]+",
            r"instagram\.com/[A-Za-z0-9._-]+"
        ],

        "twitter": [
            r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+",
            r"(?:twitter\.com|x\.com)/[A-Za-z0-9_]+"
        ],

        "facebook": [
            r"https?://(?:www\.)?facebook\.com/[A-Za-z0-9._-]+",
            r"facebook\.com/[A-Za-z0-9._-]+"
        ],

        "linkedin": [
            r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9-]+",
            r"https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9-]+"
        ],

        "discord": [
            r"https?://discord\.gg/[A-Za-z0-9]+",
            r"https?://discord\.com/invite/[A-Za-z0-9]+",
            r"https?://discord\.io/[A-Za-z0-9]+"
        ],

        "tiktok": [
            r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9._]+"
        ],

        "github": [
            r"https?://github\.com/[A-Za-z0-9_-]+"
        ],

        "website": [
            r"https?://(?!.*(?:youtube|instagram|twitter|x\.com|facebook|discord|linkedin|tiktok|github))[^\s]+"
        ]
    }

    @classmethod
    def extract(cls, texts):

        if isinstance(texts, str):
            texts = [texts]

        result = {}

        for platform, patterns in cls.PATTERNS.items():

            found = set()

            for text in texts:

                if not text:
                    continue

                for pattern in patterns:

                    matches = re.findall(pattern, text, re.IGNORECASE)

                    for match in matches:
                        found.add(match)

            result[platform] = list(found)

        return result