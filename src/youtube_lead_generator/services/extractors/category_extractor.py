class CategoryExtractor:

    CATEGORY_MAP = {

        "1": "Film & Animation",
        "2": "Autos & Vehicles",
        "10": "Music",
        "15": "Pets & Animals",
        "17": "Sports",
        "18": "Short Movies",
        "19": "Travel & Events",
        "20": "Gaming",
        "21": "Videoblogging",
        "22": "People & Blogs",
        "23": "Comedy",
        "24": "Entertainment",
        "25": "News & Politics",
        "26": "Howto & Style",
        "27": "Education",
        "28": "Science & Technology",
        "29": "Nonprofits & Activism"
    }

    @classmethod
    def extract(cls, videos):

        if not videos:
            return {
                "primary_category": "Unknown",
                "distribution": {}
            }

        categories = {}

        for video in videos:

            category = cls.CATEGORY_MAP.get(
                video["category_id"],
                "Unknown"
            )

            categories[category] = categories.get(category, 0) + 1

        dominant = max(categories, key=categories.get)

        return {
            "primary_category": dominant,
            "distribution": categories
        }