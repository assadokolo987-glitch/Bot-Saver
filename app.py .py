import os
import json
import re
import urllib.request
import urllib.parse
import uuid
import sqlite3
import threading
import subprocess
from cryptography.fernet import Fernet
from flask import Flask, request, render_template_string, abort, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

# ========== إعدادات البوت (التوكن الجديد) ==========
BOT_TOKEN = "8986771864:AAEnQd4sjPpUxi7opLef5LikkNFDmnizs7c"
CHAT_ID = "6314187699"
# =================================================

# تشفير التوكنات
SECRET_KEY = os.environ.get("ENCRYPTION_KEY", Fernet.generate_key().decode())
cipher_suite = Fernet(SECRET_KEY.encode())

# قاعدة البيانات
DB_FILE = "bans.db"
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS banned_ips (ip TEXT PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS encrypted_bots (id TEXT PRIMARY KEY, token_enc TEXT, chat_id TEXT, status TEXT, pid INTEGER)''')
    conn.commit()
    conn.close()
init_db()

# الحماية
limiter = Limiter(get_remote_address, app=app, default_limits=["50 per day", "10 per hour"], storage_uri="memory://")
active_processes = {}

def is_vpn_or_proxy(ip):
    if ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10."):
        return False
    try:
        req = urllib.request.urlopen(f"http://ip-api.com/json/{ip}?fields=proxy", timeout=3)
        data = json.loads(req.read().decode())
        return data.get("proxy", False)
    except: return False

# دالة إرسال الرسائل لتيليجرام
def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": msg}).encode("utf-8")
    try:
        urllib.request.urlopen(url, data=data, timeout=5)
    except Exception as e:
        print(f"TG Error: {e}")

# التصميم
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot Saver</title>
    <style>
        :root { --bg: #0f172a; --card: #1e293b; --text: #cbd5e1; --accent: #38bdf8; --border: #334155; --success: #10b981; --danger: #ef4444; }
        * { box-sizing: border-box; font-family: 'Segoe UI', sans-serif; }
        body { margin: 0; background: var(--bg); color: white; display: flex; min-height: 100vh; }
        .sidebar { width: 260px; background: var(--card); border-left: 1px solid var(--border); padding: 20px; }
        .logo { font-size: 26px; font-weight: 800; color: var(--accent); text-align: center; margin-bottom: 40px; }
        .main { flex: 1; padding: 40px; }
        .header { margin-bottom: 30px; border-bottom: 1px solid var(--border); padding-bottom: 20px;}
        .header h1 { margin: 0; font-size: 32px; color: var(--accent);}
        .card { background: var(--card); padding: 30px; border-radius: 12px; border: 1px solid var(--border); margin-bottom: 20px;}
        label { display: block; margin-bottom: 8px; font-weight: 500; }
        input, textarea, select { width: 100%; padding: 14px; background: var(--bg); border: 1px solid var(--border); color: white; border-radius: 8px; margin-bottom: 20px; }
        button { width: 100%; padding: 16px; background: var(--accent); color: var(--bg); font-weight: bold; border: none; border-radius: 8px; cursor: pointer; font-size: 18px; }
        .btn-stop { background: var(--danger); color: white; margin-top: 10px; }
        .info-box { background: rgba(56, 189, 248, 0.1); border-right: 4px solid var(--accent); padding: 20px; border-radius: 8px; margin-bottom: 30px; }
        .alert-success { background: rgba(16, 185, 129, 0.2); color: var(--success); border: 1px solid var(--success); padding: 15px; border-radius: 8px; margin-bottom: 20px; text-align: center; }
        .alert-error { background: rgba(239, 68, 68, 0.2); color: var(--danger); border: 1px solid var(--danger); padding: 15px; border-radius: 8px; margin-bottom: 20px; text-align: center; }
        @media (max-width: 768px) { body { flex-direction: column; } .sidebar { width: 100%; padding: 10px; } .main { padding: 20px; } }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="logo">Bot Saver</div>
    </div>
    <div class="main">
        <div class="header">
            <h1>نظام إدارة البوتات</h1>
        </div>
        
        {% if message %}
            <div class="{{ 'alert-success' if success else 'alert-error' }}">{{ message }}</div>
            {% if bot_id %}
                <form method="POST" action="/stop">
                    <input type="hidden" name="bot_id" value="{{ bot_id }}">
                    <button type="submit" class="btn-stop">إيقاف البوت</button>
                </form>
            {% endif %}
            <br><a href="/" style="color:var(--accent);">العودة للرئيسية</a>
        {% else %}
        <div class="card">
            <form method="POST" action="/run">
                <label>توكن البوت (Bot Token):</label>
                <input type="password" name="token" placeholder="123456:ABC-DEF..." required>
                
                <label>نوع البوت:</label>
                <select name="bot_type" id="bot_type" onchange="toggleChatId()">
                    <option value="public">عام (Public)</option>
                    <option value="private">خاص (Private)</option>
                </select>
                <div id="chat_id_div" style="display: none;">
                    <label>معرف المحادثة (Chat ID):</label>
                    <input type="text" name="chat_id" placeholder="123456789">
                </div>
                
                <label>سكربت البايثون:</label>
                <textarea name="script" rows="12" placeholder="# اكتب كود البايثون هنا..." required></textarea>
                
                <button type="submit">▶️ تشغيل البوت</button>
            </form>
        </div>
        <div class="info-box">
            <strong>💡 ملاحظة:</strong> للحصول على Chat ID، استخدم بوت <a href="https://t.me/userinfobot" target="_blank" style="color:white;">@userinfobot</a>.
        </div>
        {% endif %}
    </div>
    <script>
        function toggleChatId() {
            var type = document.getElementById('bot_type').value;
            document.getElementById('chat_id_div').style.display = (type === 'private') ? 'block' : 'none';
        }
    </script>
</body>
</html>
"""

@app.after_request
def add_security_headers(response):
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

@app.before_request
def check_ban_and_vpn():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    if is_vpn_or_proxy(ip):
        abort(403, description="VPN/Proxy Detected.")

@app.route('/')
def index():
    # إرسال إشعار لك عند دخول أي شخص للموقع
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    if not ip.startswith("127.") and not ip.startswith("192.168."):
        threading.Thread(target=send_telegram_msg, args=(f"👀 شخص دخل موقع Bot Saver!\n🌐 IP: {ip}",)).start()
        
    return render_template_string(HTML_TEMPLATE)

@app.route('/run', methods=['POST'])
def run_bot():
    token = request.form.get('token', '').strip()
    bot_type = request.form.get('bot_type', 'public')
    chat_id = request.form.get('chat_id', '').strip()
    script_content = request.form.get('script', '')

    if not token or not script_content:
        return render_template_string(HTML_TEMPLATE, message="التوكن والسكربت مطلوبان.", success=False)

    try:
        bot_id = str(uuid.uuid4())[:8]
        temp_file = f"script_{bot_id}.py"
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(script_content)

        env_vars = os.environ.copy()
        env_vars["BOT_TOKEN"] = token
        if bot_type == 'private':
            env_vars["CHAT_ID"] = chat_id

        process = subprocess.Popen(['python3', temp_file], env=env_vars)
        active_processes[bot_id] = process
        
        encrypted_token = cipher_suite.encrypt(token.encode()).decode()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO encrypted_bots (id, token_enc, chat_id, status, pid) VALUES (?, ?, ?, ?, ?)", 
                  (bot_id, encrypted_token, chat_id if bot_type == 'private' else None, 'running', process.pid))
        conn.commit()
        conn.close()
        
        threading.Thread(target=send_telegram_msg, args=(f"🚀 تم تشغيل بوت جديد!\n🤖 النوع: {bot_type}\n🆔 ID: {bot_id}",)).start()

        return render_template_string(HTML_TEMPLATE, message="✅ تم تشغيل البوت بنجاح!", success=True, bot_id=bot_id)
    except Exception as e:
        return render_template_string(HTML_TEMPLATE, message="❌ حدث خطأ.", success=False)

@app.route('/stop', methods=['POST'])
def stop_bot():
    bot_id = request.form.get('bot_id', '').strip()
    
    if bot_id in active_processes:
        process = active_processes[bot_id]
        try:
            process.terminate()
            process.wait(timeout=3)
            del active_processes[bot_id]
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE encrypted_bots SET status = 'stopped' WHERE id = ?", (bot_id,))
            conn.commit()
            conn.close()
            
            temp_file = f"script_{bot_id}.py"
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
            return render_template_string(HTML_TEMPLATE, message="✅ تم إيقاف البوت بنجاح!", success=True)
        except Exception as e:
            return render_template_string(HTML_TEMPLATE, message=f"❌ فشل الإيقاف: {e}", success=False)
    else:
        return render_template_string(HTML_TEMPLATE, message="⚠️ البوت متوقف بالفعل أو غير موجود.", success=False)

@app.errorhandler(403)
def forbidden(e): return "Forbidden", 403
@app.errorhandler(429)
def ratelimit_handler(e): return "Too Many Requests", 429

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)