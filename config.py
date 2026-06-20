# -*- coding: utf-8 -*-
"""Cấu hình LICENSE cho Auto Edit Video.

Dùng CHUNG server ký số Ed25519 với các tool khác của chủ (mỗi tool 1 PRODUCT_ID riêng).
`license_client.py` import file này. CHỈ chứa thông tin CÔNG KHAI — an toàn lên GitHub.
⚠️ KHÔNG bao giờ để private_key.pem / ADMIN_TOKEN ở đây (chúng chỉ nằm ở server).
"""
import os

APP_NAME = "Auto Edit Video"
APP_VERSION = "1.0.0"                 # cho tính năng tự báo bản mới qua /version

# ---- License (hybrid: kích hoạt online 1 lần + chạy offline ~10 ngày grace) ----
LICENSE_ENABLED = False               # False = chạy TỰ DO khi dev; True = bản BÁN (đòi key)
LICENSE_SERVER_URL = "https://yt-license-server.onrender.com"

# ---- Thư mục lưu license trên máy khách (AppData) ----
APPDATA_ROOT = os.environ.get("APPDATA") or os.path.expanduser("~")
DATA_DIR = os.path.join(APPDATA_ROOT, "AutoEditVideo")
LICENSE_FILE = os.path.join(DATA_DIR, "license.json")
