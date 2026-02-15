import os
import time
import json
import shutil
import subprocess
import socket
import struct
import threading
import base64
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, render_template, redirect, url_for, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit
import telebot


# ================== APP INIT ==================
app = Flask(__name__)
app.secret_key = "sampplay-secret-key-final-v3"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

login_manager = LoginManager(app)
login_manager.login_view = "login"


# ================== TELEGRAM ==================
TELEGRAM_BOT_TOKEN = "7421057972:AAHHGD-2J6SGN6CzttiNPg6JKTj5zLOmWsA"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)


# ================== PATH ==================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
CHAT_IMAGES_FOLDER = os.path.join(BASE_DIR, "static", "chat_images")
DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "downloads")

USERS_FILE = os.path.join(BASE_DIR, "users.json")
SERVERS_FILE = os.path.join(BASE_DIR, "servers.json")
CHAT_FILE = os.path.join(BASE_DIR, "chat_history.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

for p in [UPLOAD_FOLDER, CHAT_IMAGES_FOLDER, DOWNLOAD_FOLDER]:
    os.makedirs(p, exist_ok=True)


def init_json(path, default):
    if not os.path.exists(path):
        with open(path, "w") as f:
            json.dump(default, f)


init_json(USERS_FILE, {})
init_json(SERVERS_FILE, [])
init_json(CHAT_FILE, [])
init_json(CONFIG_FILE, {"maintenance": False, "announcement": "", "announcement_id": 0})


# ================== HELPERS ==================
def load_json(p):
    with open(p) as f:
        return json.load(f)


def save_json(p, d):
    with open(p, "w") as f:
        json.dump(d, f, indent=2)


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in {"png", "jpg", "jpeg", "gif", "webp"}


# ================== USER ==================
class User(UserMixin):
    def __init__(self, uid, data):
        self.id = uid
        self.username = data["username"]
        self.role = data.get("role", "member")
        self.profile_pic = data.get("profile_pic", "")
        self.points = data.get("points", 0)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_vip(self):
        return self.role in ["admin", "vip"]


@login_manager.user_loader
def load_user(uid):
    users = load_json(USERS_FILE)
    if uid in users:
        return User(uid, users[uid])
    return None


# ================== TELEGRAM BOT ==================
def run_telegram_bot():
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception:
            time.sleep(5)


@bot.message_handler(commands=["maintenance"])
def tg_maintenance(msg):
    cfg = load_json(CONFIG_FILE)
    if "on" in msg.text:
        cfg["maintenance"] = True
    elif "off" in msg.text:
        cfg["maintenance"] = False
    save_json(CONFIG_FILE, cfg)
    bot.reply_to(msg, "OK")


# ================== SOCKET CHAT ==================
@socketio.on("message")
def handle_message(data):
    if not current_user.is_authenticated:
        return

    msg = {
        "user": current_user.username,
        "role": current_user.role,
        "text": data.get("msg", ""),
        "time": datetime.now().strftime("%H:%M"),
    }

    hist = load_json(CHAT_FILE)
    hist.append(msg)
    hist = hist[-100:]
    save_json(CHAT_FILE, hist)

    emit("message_response", msg, broadcast=True)


# ================== ROUTES ==================
@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        users = load_json(USERS_FILE)
        for uid, d in users.items():
            if d["username"] == request.form["username"]:
                if check_password_hash(d["password_hash"], request.form["password"]):
                    login_user(User(uid, d))
                    return redirect("/")
        return render_template("login.html", error="Login gagal")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        users = load_json(USERS_FILE)
        uid = str(len(users) + 1)
        users[uid] = {
            "username": request.form["username"],
            "password_hash": generate_password_hash(request.form["password"]),
            "role": "admin" if not users else "member",
            "points": 0,
        }
        save_json(USERS_FILE, users)
        login_user(User(uid, users[uid]))
        return redirect("/")
    return render_template("register.html")


@app.route("/logout")
def logout():
    logout_user()
    return redirect("/login")


# ================== CONVERTER ==================
@app.route("/convert", methods=["POST"])
@login_required
def convert():
    data = request.get_json()
    url = data.get("url")

    if not url:
        return jsonify({"error": "URL kosong"}), 400

    user_dir = os.path.join(DOWNLOAD_FOLDER, f"user_{current_user.id}")
    os.makedirs(user_dir, exist_ok=True)

    filename = f"{int(time.time())}.mp3"
    filepath = os.path.join(user_dir, filename)

    cmd = [
        "yt-dlp",
        "--ffmpeg-location", "/usr/bin",
        "-x",
        "--audio-format", "mp3",
        "-o", filepath,
        url
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode != 0:
        return jsonify({"error": res.stderr}), 500

    users = load_json(USERS_FILE)
    users[current_user.id]["points"] += 1
    save_json(USERS_FILE, users)

    return jsonify({"success": True, "file": filename})


@app.route("/downloads/<folder>/<file>")
def download(folder, file):
    return send_from_directory(os.path.join(DOWNLOAD_FOLDER, folder), file)


# ================== MAIN ==================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))

    threading.Thread(
        target=run_telegram_bot,
        daemon=True
    ).start()

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
)
