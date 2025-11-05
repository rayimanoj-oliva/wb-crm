import os
import mimetypes
import requests
from typing import Optional

from config.constants import get_media_url


def upload_header_image(access_token: str, image_path_or_url: str, phone_id: str) -> Optional[str]:
    """
    Upload a local file or remote URL to WhatsApp media endpoint.
    Returns media_id on success, None on failure.
    """
    try:
        content = None
        filename = None
        content_type = None

        if os.path.isfile(image_path_or_url):
            filename = os.path.basename(image_path_or_url)
            content_type = mimetypes.guess_type(image_path_or_url)[0] or "image/jpeg"
            with open(image_path_or_url, "rb") as f:
                content = f.read()
        else:
            resp = requests.get(image_path_or_url, timeout=15)
            if resp.status_code != 200:
                return None
            content = resp.content
            filename = os.path.basename(image_path_or_url.split("?")[0]) or "welcome.jpg"
            content_type = resp.headers.get("Content-Type") or mimetypes.guess_type(image_path_or_url)[0] or "image/jpeg"

        files = {
            "file": (filename, content, content_type),
            "messaging_product": (None, "whatsapp")
        }
        up = requests.post(get_media_url(phone_id), headers={"Authorization": f"Bearer {access_token}"}, files=files, timeout=20)
        if up.status_code == 200:
            return up.json().get("id")
    except Exception:
        return None
    return None
