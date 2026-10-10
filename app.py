import os
import re
import time
import uuid
import shutil
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, request, jsonify, send_file, after_this_request
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app)

# Keep requests bounded; video files are temporary on Render's ephemeral disk.
MAX_CONTENT_LENGTH = 2 * 1024 * 1024
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "video-downloader"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Only allow the social platforms this app is intended to support.
ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "instagram.com", "www.instagram.com", "m.instagram.com",
    "facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch",
    "twitter.com", "www.twitter.com", "x.com", "www.x.com",
}

# Limit simultaneous downloads so one instance cannot be overwhelmed.
download_semaphore = threading.BoundedSemaphore(value=2)


def validate_video_url(raw_url):
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("Vui lòng dán link video.")
    url = raw_url.strip()
    if len(url) > 2048:
        raise ValueError("Link quá dài.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Link không hợp lệ. Hãy dùng link bắt đầu bằng https://")
    host = parsed.hostname.lower().rstrip(".")
    if host not in ALLOWED_HOSTS:
        raise ValueError("Link này chưa được hỗ trợ. Hãy dùng YouTube, TikTok, Instagram, Facebook hoặc X.")
    return url


def clean_old_files(max_age_seconds=2 * 60 * 60):
    now = time.time()
    try:
        for item in DOWNLOAD_DIR.iterdir():
            try:
                if item.is_file() and now - item.stat().st_mtime > max_age_seconds:
                    item.unlink(missing_ok=True)
                elif item.is_dir() and now - item.stat().st_mtime > max_age_seconds:
                    shutil.rmtree(item, ignore_errors=True)
            except OSError:
                pass
    except OSError:
        pass


def safe_filename(name, default="video"):
    name = str(name or default)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    return (name[:120] or default)


@app.get("/")
def health():
    return jsonify({
        "ok": True,
        "service": "Video Downloader API",
        "supported_platforms": ["YouTube", "TikTok", "Instagram", "Facebook", "X"]
    })


@app.route("/get-download-link", methods=["POST", "OPTIONS"])
def get_download_link():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    try:
        url = validate_video_url(data.get("url"))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    if not download_semaphore.acquire(blocking=False):
        return jsonify({
            "success": False,
            "message": "Server đang xử lý video khác. Bạn thử lại sau ít phút nhé."
        }), 429

    job_dir = DOWNLOAD_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    clean_old_files()

    try:
        # Prefer a single-file MP4 when available to avoid requiring FFmpeg
        # for most videos. Fall back to the best single-file format available.
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(job_dir / "%(title).120B-%(id)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
            "fragment_retries": 2,
            "socket_timeout": 25,
            "restrictfilenames": True,
            "overwrites": True,
        }

        # Intentionally do not load cookies.txt from the repository.
        # Never commit account session cookies to source control.
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "video"
            requested_downloads = info.get("requested_downloads") or []
            filepath = None

            if requested_downloads:
                candidate = requested_downloads[0].get("filepath")
                if candidate and os.path.isfile(candidate):
                    filepath = candidate

            if not filepath:
                candidate = ydl.prepare_filename(info)
                if os.path.isfile(candidate):
                    filepath = candidate

            if not filepath:
                files = [p for p in job_dir.iterdir() if p.is_file()]
                if files:
                    filepath = str(max(files, key=lambda p: p.stat().st_size))

        if not filepath or not os.path.isfile(filepath):
            shutil.rmtree(job_dir, ignore_errors=True)
            return jsonify({
                "success": False,
                "message": "Không tìm thấy file sau khi tải. Video có thể bị giới hạn hoặc nền tảng không cung cấp định dạng phù hợp."
            }), 502

        ext = Path(filepath).suffix or ".mp4"
        download_name = safe_filename(title) + ext

        @after_this_request
        def remove_temp_file(response):
            # Give the response time to finish sending before removing the file.
            # A daemon cleanup is also performed for files left behind by disconnects.
            def delayed_cleanup():
                time.sleep(60)
                shutil.rmtree(job_dir, ignore_errors=True)
            threading.Thread(target=delayed_cleanup, daemon=True).start()
            return response

        return send_file(
            filepath,
            as_attachment=True,
            download_name=download_name,
            mimetype="application/octet-stream",
            conditional=True,
        )

    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        # Log the detailed exception in Render Logs; send a helpful but bounded
        # message to the browser.
        app.logger.exception("Video download failed")
        message = str(exc)
        if "page needs to be reloaded" in message.lower():
            message = (
                "YouTube yêu cầu tải lại trang hoặc xác minh thêm. "
                "Đây không phải lỗi giao diện; hãy thử video khác và kiểm tra log Render. "
                "Cookies hợp lệ cũng không đảm bảo giải quyết được hạn chế từ YouTube."
            )
        elif "requested format is not available" in message.lower():
            message = (
                "Không có định dạng phù hợp cho video này. "
                "Hãy thử video khác; backend đã thử chọn MP4 đơn tệp rồi dự phòng định dạng tốt nhất."
            )
        else:
            message = "Không tải được video. Kiểm tra Logs trên Render để xem chi tiết. Lỗi: " + message[:350]
        return jsonify({"success": False, "message": message}), 500
    finally:
        download_semaphore.release()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
