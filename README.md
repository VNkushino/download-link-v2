# Video Downloader — bản sửa backend

## File
- `app.py`: Flask API; giữ endpoint `/get-download-link` để tương thích giao diện.
- `index.html`: giao diện điện thoại; backend trả file tải xuống trực tiếp.
- `requirements.txt`: các thư viện Python.
- `Procfile`: lệnh chạy Gunicorn trên Render.

## Deploy Render
1. Thay các file tương ứng trong repository GitHub.
2. Không upload/commit `cookies.txt`; xóa file này khỏi repository nếu đã từng commit.
3. Trong Render, đặt Root Directory đúng thư mục chứa `app.py`.
4. Build Command: `pip install -r requirements.txt`
5. Start Command có thể để Render đọc `Procfile`, hoặc dùng: `gunicorn --workers 1 --threads 4 --timeout 300 app:app`
6. Deploy lại và kiểm tra Logs.

## Hành vi
- Hỗ trợ URL từ YouTube, TikTok, Instagram, Facebook và X, tùy khả năng extractor hiện tại của yt-dlp và quyền truy cập của video.
- Backend tải file tạm trước khi trả file về điện thoại; đây là cách tránh trả một direct stream URL không còn hợp lệ hoặc chỉ chứa video/âm thanh riêng lẻ.
- Bản này ưu tiên `best[ext=mp4]/best` để chọn luồng đơn tệp và tránh phụ thuộc FFmpeg trong đa số trường hợp.
- Không tự động sử dụng cookies. Video riêng tư, yêu cầu đăng nhập, CAPTCHA hoặc bị giới hạn bởi nền tảng có thể vẫn thất bại.
- Render free có thể ngủ, giới hạn tài nguyên và dung lượng tạm; không đảm bảo dịch vụ 24/7 hoặc video dài không giới hạn.

## Lưu ý bảo mật
File cookies người dùng đã gửi chứa thông tin phiên nhạy cảm. Hãy đăng xuất/thu hồi phiên liên quan và không commit cookie vào GitHub. Nếu cần cookies cho nội dung bạn có quyền truy cập, hãy dùng secret/private storage và không đưa cookie vào frontend hoặc log.

Chỉ tải video mà bạn sở hữu hoặc có quyền tải xuống; hãy tuân thủ điều khoản của nền tảng và luật áp dụng.
