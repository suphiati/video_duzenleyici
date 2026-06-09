import os
import json
import time
from pathlib import Path

from app.config import YOUTUBE_CLIENT_SECRETS, YOUTUBE_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
REDIRECT_URI = "http://localhost:8000/api/batch/youtube/callback"


def _load_credentials():
    """Load stored OAuth2 credentials from token file."""
    if not YOUTUBE_TOKEN_FILE.exists():
        return None

    from google.oauth2.credentials import Credentials
    try:
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_FILE), SCOPES)
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            # Save refreshed token
            with open(YOUTUBE_TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        return creds if creds and creds.valid else None
    except Exception:
        return None


def is_authenticated() -> bool:
    """Check if valid YouTube credentials exist."""
    return _load_credentials() is not None


def get_auth_url() -> str:
    """Generate OAuth2 authorization URL for YouTube."""
    if not YOUTUBE_CLIENT_SECRETS.exists():
        raise FileNotFoundError(
            "client_secrets.json bulunamadi. "
            "Google Cloud Console'dan OAuth2 credentials indirip "
            f"{YOUTUBE_CLIENT_SECRETS} konumuna yerlestiriniz."
        )

    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        str(YOUTUBE_CLIENT_SECRETS),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def handle_callback(auth_code: str) -> bool:
    """Exchange authorization code for tokens and save them."""
    if not YOUTUBE_CLIENT_SECRETS.exists():
        raise FileNotFoundError("client_secrets.json bulunamadi")

    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        str(YOUTUBE_CLIENT_SECRETS),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.fetch_token(code=auth_code)
    creds = flow.credentials

    # Save credentials
    with open(YOUTUBE_TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    return True


def upload_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: list[str] = None,
    privacy: str = "private",
    category_id: str = "22",
    progress_callback=None,
    thumbnail: str | None = None,
) -> str:
    """
    Upload a video to YouTube using resumable upload.

    If ``thumbnail`` points to an existing image, it is set as the video's
    custom thumbnail after the upload completes. This is best-effort: custom
    thumbnails require a verified channel, so a failure here never fails the
    upload itself.

    Returns: YouTube video URL
    """
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("YouTube hesabi bagli degil. Once giris yapin.")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    file_size = os.path.getsize(file_path)
    media = MediaFileUpload(
        file_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retries = 0
    max_retries = 3

    while response is None:
        try:
            status, response = request.next_chunk()
            if status and progress_callback:
                percent = status.progress() * 100
                progress_callback(percent)
        except Exception as e:
            retries += 1
            if retries > max_retries:
                raise RuntimeError(f"YouTube yukleme hatasi ({retries} deneme): {e}")
            wait = 2 ** retries * 5
            time.sleep(wait)

    video_id = response.get("id", "")

    # Best-effort custom thumbnail (requires a verified channel).
    if video_id and thumbnail and os.path.exists(thumbnail):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail, mimetype="image/jpeg"),
            ).execute()
        except Exception:
            pass

    if progress_callback:
        progress_callback(100)

    return f"https://www.youtube.com/watch?v={video_id}"
