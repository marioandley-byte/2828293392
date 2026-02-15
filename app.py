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

app = Flask(__name__)
app.secret_key = 'sampplay-secret-key-final-v3'

# ============ 1. KONFIGURASI ============
TELEGRAM_BOT_TOKEN = '7421057972:AAHHGD-2J6SGN6CzttiNPg6JKTj5zLOmWsA'
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False) 

# ============ 2. INISIALISASI PLUGIN ============
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ============ 3. CONFIG FOLDER & FILE ============
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
CHAT_IMAGES_FOLDER = os.path.join(BASE_DIR, 'static', 'chat_images')
MAIN_DOWNLOAD_FOLDER = os.path.join(BASE_DIR, 'downloads')
USERS_FILE = os.path.join(BASE_DIR, 'users.json')
SERVERS_FILE = os.path.join(BASE_DIR, 'servers.json')
CHAT_FILE = os.path.join(BASE_DIR, 'chat_history.json')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CHAT_IMAGES_FOLDER'] = CHAT_IMAGES_FOLDER

for folder in [UPLOAD_FOLDER, CHAT_IMAGES_FOLDER, MAIN_DOWNLOAD_FOLDER]:
    if not os.path.exists(folder): os.makedirs(folder)

def init_json(file, default_data):
    if not os.path.exists(file):
        with open(file, 'w') as f: json.dump(default_data, f)

init_json(USERS_FILE, {})
init_json(SERVERS_FILE, [])
init_json(CHAT_FILE, [])
init_json(CONFIG_FILE, {'maintenance': False, 'announcement': '', 'announcement_id': 0})

# ============ 4. LOGIC BOT TELEGRAM ============
def get_config():
    with open(CONFIG_FILE, 'r') as f: return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, 'w') as f: json.dump(data, f)

@bot.message_handler(commands=['maintenance'])
def toggle_maintenance(message):
    args = message.text.split()
    if len(args) < 2: return bot.reply_to(message, "Format: /maintenance on atau /maintenance off")
    
    status = args[1].lower()
    cfg = get_config()
    if status == 'on':
        cfg['maintenance'] = True
        save_config(cfg)
        bot.reply_to(message, "🚨 WEBSITE DIKUNCI (Maintenance Mode).")
    elif status == 'off':
        cfg['maintenance'] = False
        save_config(cfg)
        bot.reply_to(message, "✅ WEBSITE DIBUKA KEMBALI.")

@bot.message_handler(commands=['announce'])
def set_announcement(message):
    text = message.text.replace('/announce', '').strip()
    if not text:
        return bot.reply_to(message, "Format: /announce [pesan pengumuman]")
    
    cfg = get_config()
    cfg['announcement'] = text
    cfg['announcement_id'] = int(time.time()) 
    save_config(cfg)
    
    bot.reply_to(message, f"📢 Pengumuman berhasil disiarkan ke semua layar user:\n\n{text}")

@bot.message_handler(commands=['clear_announce'])
def clear_announcement(message):
    cfg = get_config()
    cfg['announcement'] = ""
    save_config(cfg)
    bot.reply_to(message, "✅ Pengumuman berhasil dihapus dari layar.")

def run_telegram_bot():
    print("🤖 Telegram Bot Started...")
    while True:
        try: bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e: time.sleep(5)

# ============ 5. HELPERS & UTILS ============
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'heic'}

def load_users():
    with open(USERS_FILE, 'r') as f: return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f: json.dump(users, f, indent=4)

def load_servers():
    with open(SERVERS_FILE, 'r') as f: return json.load(f)

def save_servers(srv):
    with open(SERVERS_FILE, 'w') as f: json.dump(srv, f, indent=4)

def load_chat():
    with open(CHAT_FILE, 'r') as f: return json.load(f)

def save_chat_msg(msg_data):
    history = load_chat()
    history.append(msg_data)
    if len(history) > 100: history.pop(0)
    with open(CHAT_FILE, 'w') as f: json.dump(history, f)

# ============ 6. USER CLASS ============
class User(UserMixin):
    def __init__(self, id, username, password_hash, role='member', bio='', profile_pic='', points=0, theme='default'):
        self.id = str(id)
        self.username = username
        self.password_hash = password_hash
        self.role = role
        self.bio = bio
        self.profile_pic = profile_pic
        self.points = points
        self.theme = theme

    @property
    def is_admin(self): return self.role == 'admin'
    @property
    def is_vip(self): return self.role in ['admin', 'vip']

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    data = users.get(str(user_id))
    if data: return User(user_id, data['username'], data['password_hash'], data.get('role', 'member'), data.get('bio', ''), data.get('profile_pic', ''), data.get('points', 0), data.get('theme', 'default'))
    return None

@app.before_request
def check_maintenance():
    if request.endpoint in ['static', 'login', 'maintenance_page', 'admin_login_bypass', 'api_announcement']: return
    cfg = get_config()
    if cfg.get('maintenance'):
        if current_user.is_authenticated and current_user.is_admin: return
        return render_template('maintenance.html')

# ============ 8. LOGIKA QUERY SA-MP ============
def query_samp(ip, port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.5)
        ip_parts = ip.split('.')
        packet = b'SAMP' + bytearray([int(x) for x in ip_parts]) + struct.pack('<H', int(port)) + b'i'
        
        sock.sendto(packet, (ip, int(port)))
        data, _ = sock.recvfrom(4096)
        sock.close()
        
        if data.startswith(b'SAMP') and data[10:11] == b'i':
            offset = 12 
            players = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            max_players = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
            hostname_len = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
            try: hostname = data[offset:offset+hostname_len].decode('latin-1', errors='replace')
            except: hostname = "SAMP Server"
            return {'online': True, 'hostname': hostname, 'players': players, 'max_players': max_players}
    except Exception as e: pass
    return {'online': False}

# ============ 9. SOCKET.IO CHAT ============
@socketio.on('message')
def handle_message(data):
    if not current_user.is_authenticated: return
    msg_content = data.get('msg', '')
    img_data = data.get('image', None)
    image_filename = None
    
    if img_data:
        try:
            header, encoded = img_data.split(",", 1)
            ext = header.split('/')[1].split(';')[0]
            if ext not in ['png', 'jpg', 'jpeg', 'gif']: ext = 'jpg'
            file_data = base64.b64decode(encoded)
            filename = f"chat_{int(time.time())}_{current_user.id}.{ext}"
            with open(os.path.join(app.config['CHAT_IMAGES_FOLDER'], filename), "wb") as f:
                f.write(file_data)
            image_filename = filename
        except: pass

    msg_obj = {
        'user': current_user.username,
        'role': current_user.role,
        'pic': current_user.profile_pic,
        'text': msg_content,
        'image': image_filename,
        'time': datetime.now().strftime("%H:%M")
    }
    save_chat_msg(msg_obj)
    emit('message_response', msg_obj, broadcast=True)

# ============ 10. ROUTES ============
@app.route('/')
@login_required
def index(): return render_template('index.html')

@app.route('/maintenance')
def maintenance_page(): return render_template('maintenance.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = True if request.form.get('remember') == 'on' else False

        users = load_users()
        for uid, d in users.items():
            if d['username'] == username:
                if check_password_hash(d['password_hash'], password):
                    user = User(uid, d['username'], d['password_hash'], d.get('role'), d.get('bio'), d.get('profile_pic'), d.get('points'), d.get('theme'))
                    login_user(user, remember=remember)
                    return redirect(url_for('index'))
        return render_template('login.html', error='Login Gagal')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        users = load_users()
        for d in users.values():
            if d['username'] == username: return render_template('register.html', error='Username sudah ada')
        
        nid = str(len(users) + 1)
        role = 'admin' if len(users) == 0 else 'member'
        users[nid] = {'username': username, 'password_hash': generate_password_hash(password), 'role': role, 'bio': 'New User', 'profile_pic': '', 'points': 0, 'theme': 'default'}
        save_users(users)
        
        user = User(nid, username, users[nid]['password_hash'], role, points=0, theme='default')
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/monitor')
@login_required
def monitor_page(): return render_template('monitor.html')

@app.route('/chat')
@login_required
def chat_page(): return render_template('chat.html')

@app.route('/converter')
@login_required
def converter(): return render_template('converter.html')

@app.route('/profile')
@login_required
def profile_page(): return render_template("profile.html")

# --- API MONITOR & SYSTEM ---
@app.route('/api/announcement')
def api_announcement():
    cfg = get_config()
    return jsonify({
        'text': cfg.get('announcement', ''),
        'id': cfg.get('announcement_id', 0)
    })

@app.route('/api/servers', methods=['GET'])
def get_servers():
    servers = load_servers()
    results = []
    for s in servers:
        status = query_samp(s['ip'], s['port'])
        results.append({
            'ip': s['ip'], 'port': s['port'], 'added_by': s['added_by'],
            'online': status['online'],
            'hostname': status.get('hostname', f"{s['ip']}:{s['port']}"),
            'players': status.get('players', 0),
            'max_players': status.get('max_players', 0)
        })
    return jsonify(results)

@app.route('/api/servers', methods=['POST'])
@login_required
def add_server():
    data = request.get_json()
    servers = load_servers()
    for s in servers:
        if s['ip'] == data['ip'] and str(s['port']) == str(data['port']): return jsonify({'error': 'Server sudah ada'}), 400
    servers.append({'ip': data['ip'], 'port': int(data['port']), 'added_by': current_user.username})
    save_servers(servers)
    return jsonify({'success': True})

@app.route('/api/servers', methods=['DELETE'])
@login_required
def delete_server():
    if not current_user.is_admin: return jsonify({'error': 'Akses Ditolak'}), 403
    data = request.get_json()
    servers = load_servers()
    new_servers = [s for s in servers if not (s['ip'] == data['ip'] and str(s['port']) == str(data['port']))]
    save_servers(new_servers)
    return jsonify({'success': True})

@app.route('/api/chat_history')
@login_required
def get_chat_history(): return jsonify(load_chat())

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    try:
        users = load_users()
        uid = str(current_user.id)
        if request.form.get('username'): users[uid]['username'] = request.form.get('username')
        if request.form.get('bio'): users[uid]['bio'] = request.form.get('bio')
        if request.form.get('theme'): users[uid]['theme'] = request.form.get('theme')
        
        if 'avatar' in request.files:
            f = request.files['avatar']
            if f and f.filename != '':
                if allowed_file(f.filename):
                    ext = f.filename.rsplit('.', 1)[-1].lower()
                    fn = secure_filename(f"u_{uid}_{int(time.time())}.{ext}")
                    f.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
                    users[uid]['profile_pic'] = fn
                else: return jsonify({'success': False, 'error': 'Format foto tidak didukung.'}), 400
        save_users(users)
        return jsonify({'success': True})
    except Exception as e: return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/list')
def list_files():
    users = load_users()
    files = []
    if os.path.exists(MAIN_DOWNLOAD_FOLDER):
        for folder_name in os.listdir(MAIN_DOWNLOAD_FOLDER):
            folder_path = os.path.join(MAIN_DOWNLOAD_FOLDER, folder_name)
            if os.path.isdir(folder_path) and folder_name.startswith('user_'):
                user_id = folder_name.split('_')[1]
                user_name = users.get(user_id, {}).get('username', f'User #{user_id}')
                for f in os.listdir(folder_path):
                    if f.endswith('.mp3'):
                        filepath = os.path.join(folder_path, f)
                        try:
                            stat = os.stat(filepath)
                            files.append({'filename': f, 'user_id': user_id, 'username': user_name, 'url': f"/downloads/{folder_name}/{f}", 'modified': stat.st_mtime, 'size': stat.st_size})
                        except: continue
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify(files)

@app.route('/leaderboard')
def get_leaderboard():
    users = load_users()
    leaderboard = []
    for uid, d in users.items(): leaderboard.append({'id': uid, 'username': d['username'], 'points': d.get('points', 0), 'pic': d.get('profile_pic', '')})
    leaderboard.sort(key=lambda x: x['points'], reverse=True)
    return jsonify(leaderboard[:10])

@app.route('/user/<user_id>')
@login_required
def public_profile(user_id):
    users = load_users()
    user_data = users.get(str(user_id))
    if not user_data: return "User tidak ditemukan", 404
    if str(user_id) == str(current_user.id): return redirect(url_for('profile_page'))
    target_user = {'id': user_id, 'username': user_data['username'], 'bio': user_data.get('bio', ''), 'profile_pic': user_data.get('profile_pic', ''), 'role': user_data.get('role', 'member'), 'points': user_data.get('points', 0)}
    return render_template('public_profile.html', user=target_user)

@app.route('/convert', methods=['POST'])
@login_required
def convert():
    data = request.get_json()
    video_url = data.get('url')
    if not video_url: return jsonify({'error': 'URL kosong'}), 400
    limit_mb = '100M' if current_user.is_vip else '20M'
    try:
        t_cmd = ['yt-dlp', '--print', '%(title)s', '--no-warnings', '--quiet', video_url]
        res = subprocess.run(t_cmd, capture_output=True, text=True, check=True)
        title = "".join([c for c in res.stdout.strip() if c.isalnum() or c in " ._-"]).strip() or 'Untitled'
        
        filename = f"{title}_{int(time.time())}.mp3"
        user_folder = os.path.join(MAIN_DOWNLOAD_FOLDER, f"user_{current_user.id}")
        if not os.path.exists(user_folder): os.makedirs(user_folder)
        
        filepath = os.path.join(user_folder, filename)
        dl_cmd = ['yt-dlp', '-x', '--audio-format', 'mp3', '--audio-quality', '0', '-o', filepath, '--no-warnings', '--quiet', '--max-filesize', limit_mb, video_url]
        subprocess.run(dl_cmd, check=True)

        users = load_users()
        users[str(current_user.id)]['points'] += 1
        save_users(users)
        return jsonify({'success': True})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/downloads/<folder>/<filename>')
def download_file_route(folder, filename): return send_from_directory(os.path.join(MAIN_DOWNLOAD_FOLDER, folder), filename)

# ============ ADMIN ROUTES ============
@app.route('/admin')
@login_required
def admin_page():
    if not current_user.is_admin: abort(403)
    return render_template('admin.html')

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin: abort(403)
    users = load_users()
    res = []
    def cf(uid):
        p = os.path.join(MAIN_DOWNLOAD_FOLDER, f"user_{uid}")
        return len(os.listdir(p)) if os.path.exists(p) else 0
    for uid, d in users.items(): res.append({'id':uid, 'username': d['username'], 'role':d['role'], 'download_count': cf(uid)})
    return jsonify(res)

@app.route('/admin/users/<uid>', methods=['DELETE'])
@login_required
def admin_del_user(uid):
    if not current_user.is_admin: abort(403)
    users = load_users()
    if uid in users and uid != str(current_user.id):
        p = os.path.join(MAIN_DOWNLOAD_FOLDER, f"user_{uid}")
        if os.path.exists(p): shutil.rmtree(p)
        del users[uid]
        save_users(users)
        return jsonify({'success':True})
    return jsonify({'error':'Gagal'}), 400

@app.route('/admin/files', methods=['DELETE'])
@login_required
def admin_del_file():
    if not current_user.is_admin: abort(403)
    data = request.get_json()
    p = os.path.join(MAIN_DOWNLOAD_FOLDER, f"user_{data['user_id']}", data['filename'])
    if os.path.exists(p):
        os.remove(p)
        return jsonify({'success':True})
    return jsonify({'error':'File not found'}), 404

if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 8080))

    # Jalankan bot Telegram di thread terpisah
    try:
        threading.Thread(
            target=run_telegram_bot,
            daemon=True
        ).start()
    except Exception as e:
        print("Telegram bot gagal start:", e)

    # Jalankan Flask + SocketIO dengan aman di Railway
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )
