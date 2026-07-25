import requests
import tempfile
import os

class ThumbnailExtractor:

    @staticmethod
    def download_thumbnail(video_id):
        url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        response = requests.get(url)
        
        if response.status_code != 200:
            url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            response = requests.get(url)
            if response.status_code != 200:
                print(f"Could not download thumbnail for {video_id}")
                return None
                
        fd, path = tempfile.mkstemp(suffix=".jpg")
        with os.fdopen(fd, 'wb') as f:
            f.write(response.content)
            
        return path
