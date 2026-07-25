import os

API_KEY = os.environ.get("YOUTUBE_API_KEY", "AIzaSyASuTHIOCox2OXbQG32BrPZE4mzsZ-OlCc")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAYjakNvh838TP32R6YGx53dNAPfvYg5DM")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite")