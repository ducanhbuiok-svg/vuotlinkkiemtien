import os
import hmac
import hashlib
import urllib.parse
import json
import secrets
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime

app = Flask(__name__)
CORS(app)

# =========================================================
# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG & DATABASE
# =========================================================
MONGO_URL = os.getenv("mongodb+srv://ducanhbuiok_db_user:ducanhbuiok_db_user@cluster0.a4zrytg.mongodb.net/?appName=Cluster0")
BOT_TOKEN = os.getenv("8116280112:AAERR6AH23JavjshO073QZmcDH7_qDEwdro")
LINK4M_TOKEN = os.getenv("LINK4M_TOKEN", "6a69d21cd1f4b667a1055225")
ADMIN_ID = str(os.getenv("ADMIN_ID", "8914123780")).strip()               # ID Telegram Admin
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").replace("@daxprovn", "")

URL_CHANNEL = os.getenv("URL_CHANNEL", "https://t.me/kenhthongbaodab_roblox")
URL_GROUP = os.getenv("URL_GROUP", "https://t.me/nhomchatdanmmo")

client = MongoClient(MONGO_URL)
db = client.dcoin_database

users_col = db.users          
history_col = db.history      
tasks_col = db.tasks          
withdrawals_col = db.withdrawals 
audit_logs_col = db.admin_audit_logs # Lưu lịch sử Admin bơm DCOIN

MAX_TASKS_PER_DAY = 2         # Chuẩn 2 lượt/ngày theo Link4m
MIN_TASK_TIME_SECONDS = 5     # Thời gian chờ tối thiểu 15s

# =========================================================
# 2. XÁC THỰC BẢO MẬT HMAC-SHA256 CỦA TELEGRAM
# =========================================================
def verify_telegram_data(init_data_str):
    """
    Xác thực chuỗi initData từ Telegram WebApp SDK gửi lên server.
    Chống giả mạo user_id 100%.
    """
    if not init_data_str or not BOT_TOKEN:
        return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data_str))
        if 'hash' not in parsed_data:
            return None
        
        received_hash = parsed_data.pop('hash')
        
        # Sắp xếp tham số theo alphabet
        data_check_arr = [f"{k}={v}" for k, v in sorted(parsed_data.items())]
        data_check_string = "\n".join(data_check_arr)

        # Tạo HMAC secret key từ Bot Token
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode('utf-8'), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()

        if calculated_hash == received_hash:
            user_info = json.loads(parsed_data.get('user', '{}'))
            return user_info
        return None
    except Exception as e:
        print("Lỗi xác thực HMAC Telegram:", e)
        return None

def send_telegram_msg(chat_id, text, keyboard=None):
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if keyboard: payload["reply_markup"] = keyboard
        import requests
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload, timeout=5)
    except Exception as e:
        print(f"Lỗi gửi tin nhắn Telegram:", e)

def make_short_link(original_url):
    if not LINK4M_TOKEN: return original_url
    try:
        import requests
        api_url = f"https://link4m.com/api?api={LINK4M_TOKEN}&url={original_url}"
        res = requests.get(api_url, timeout=10).json()
        return res.get('shortenedUrl', original_url)
    except Exception as e:
        return original_url

# =========================================================
# 3. TELEGRAM WEBHOOK & LỆNH /START
# =========================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json or {}
    if "message" in data and "text" in data["message"]:
        msg = data["message"]
        chat_id = str(msg["chat"]["id"])
        text = msg["text"].strip()
        first_name = msg["from"].get("first_name", "")
        last_name = msg["from"].get("last_name", "")
        username = msg["from"].get("username", "")

        display_name = f"{first_name} {last_name}".strip() or "Người dùng Telegram"

        if text.startswith("/start"):
            ref_by = None
            parts = text.split()
            if len(parts) > 1 and parts[1].startswith("ref_"):
                potential_ref = parts[1].replace("ref_", "")
                if potential_ref != chat_id: ref_by = potential_ref

            user = users_col.find_one({"uid": chat_id})
            if not user:
                users_col.insert_one({
                    "uid": chat_id,
                    "display_name": display_name,
                    "username": username,
                    "balance": 0,
                    "last_checkin": "",
                    "ref_by": ref_by,
                    "ref_count": 0
                })
                if ref_by:
                    users_col.update_one({"uid": ref_by}, {"$inc": {"balance": 500, "ref_count": 1}})
                    history_col.insert_one({
                        "uid": ref_by,
                        "type": "Thưởng giới thiệu bạn bè",
                        "amount": "+500 DCOIN",
                        "date": datetime.now().strftime("%d/%m/%Y %H:%M")
                    })
            else:
                users_col.update_one({"uid": chat_id}, {"$set": {"display_name": display_name, "username": username}})

            msg_text = (
                f"🎉 **CHÀO MỪNG {display_name.upper()} ĐẾN VỚI DCOIN MINI APP!**\n\n"
                "💎 Tích lũy DCOIN dễ dàng qua các nhiệm vụ:\n"
                "• Điểm danh nhận thưởng mỗi ngày\n"
                "• Vượt link rút gọn hỗ trợ cộng điểm\n"
                "• Giới thiệu bạn bè nhận 500 DCOIN/lượt\n\n"
                "📌 Tham gia Kênh & Nhóm chính thức bên dưới để cập nhật tin tức:"
            )
            
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "📢 Kênh Thông Báo", "url": URL_CHANNEL},
                        {"text": "💬 Nhóm Trao Đổi", "url": URL_GROUP}
                    ],
                    [
                        {"text": "🆘 Liên hệ Admin Support", "url": f"https://t.me/{ADMIN_USERNAME}"}
                    ],
                    [
                        {"text": "🚀 MỞ MINI APP KIẾM DCOIN", "web_app": {"url": "https://dcoin-app.vercel.app"}}
                    ]
                ]
            }
            send_telegram_msg(chat_id, msg_text, keyboard)

    return "ok", 200

# =========================================================
# 4. API DÀNH CHO USER (AUTHENTICATED)
# =========================================================
@app.route('/api/user', methods=['POST'])
def get_user():
    try:
        data = request.json or {}
        init_data = data.get('init_data', '')
        
        # Xác thực với Telegram
        tg_user = verify_telegram_data(init_data)
        if not tg_user:
            # Fallback nếu test local (dev mode)
            uid = str(data.get('user_id', '')).strip()
            display_name = data.get('display_name', 'Người dùng')
            username = data.get('username', '')
        else:
            uid = str(tg_user.get('id'))
            display_name = f"{tg_user.get('first_name', '')} {tg_user.get('last_name', '')}".strip()
            username = tg_user.get('username', '')

        if not uid:
            return jsonify({"error": "Xác thực tài khoản Telegram thất bại!"}), 401

        user = users_col.find_one({"uid": uid})
        if not user:
            new_user = {"uid": uid, "display_name": display_name, "username": username, "balance": 0, "last_checkin": "", "ref_count": 0}
            users_col.insert_one(new_user)
            user = new_user
        else:
            users_col.update_one({"uid": uid}, {"$set": {"display_name": display_name, "username": username}})

        is_admin = (uid == ADMIN_ID) and bool(ADMIN_ID)

        return jsonify({
            "uid": user.get("uid"),
            "display_name": display_name,
            "username": username,
            "balance": user.get("balance", 0),
            "ref_count": user.get("ref_count", 0),
            "is_admin": is_admin,
            "admin_username": ADMIN_USERNAME
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/checkin', methods=['POST'])
def checkin():
    try:
        data = request.json or {}
        uid = str(data.get('user_id', '')).strip()
        if not uid: return jsonify({"success": False, "msg": "Thiếu user_id"}), 400

        today = datetime.now().strftime("%Y-%m-%d")
        user = users_col.find_one({"uid": uid})
        
        if user and user.get("last_checkin") == today:
            return jsonify({"success": False, "msg": "Hôm nay bạn đã điểm danh rồi!"})

        users_col.update_one({"uid": uid}, {"$inc": {"balance": 100}, "$set": {"last_checkin": today}}, upsert=True)
        history_col.insert_one({"uid": uid, "type": "Điểm danh hàng ngày", "amount": "+100 DCOIN", "date": datetime.now().strftime("%d/%m/%Y %H:%M")})

        updated_user = users_col.find_one({"uid": uid})
        return jsonify({"success": True, "msg": "Điểm danh thành công! +100 DCOIN", "new_balance": updated_user["balance"]})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/get-task-link', methods=['POST'])
def get_task_link():
    try:
        data = request.json or {}
        uid = str(data.get('user_id', '')).strip()
        task_id = str(data.get('task_id', 'task_1'))
        target_url = data.get('target_url', 'https://google.com')

        if not uid: return jsonify({"success": False, "msg": "Thiếu user_id"}), 400

        today = datetime.now().strftime("%Y-%m-%d")
        completed_today = tasks_col.count_documents({"uid": uid, "status": "completed", "date": today})
        
        if completed_today >= MAX_TASKS_PER_DAY:
            return jsonify({"success": False, "msg": f"Bạn đã đạt giới hạn tối đa {MAX_TASKS_PER_DAY} nhiệm vụ/ngày!"})

        task_token = secrets.token_hex(16)
        short_link = make_short_link(target_url)

        tasks_col.update_one(
            {"uid": uid, "task_id": task_id, "date": today},
            {"$set": {"uid": uid, "task_id": task_id, "task_token": task_token, "status": "pending", "created_at": time.time(), "date": today}},
            upsert=True
        )

        return jsonify({"success": True, "short_link": short_link, "task_token": task_token})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/complete-task', methods=['POST'])
def complete_task():
    try:
        data = request.json or {}
        uid = str(data.get('user_id', '')).strip()
        task_id = str(data.get('task_id', 'task_1'))
        task_token = data.get('task_token', '')
        reward = int(data.get('reward', 300))

        if not uid or not task_token: return jsonify({"success": False, "msg": "Thiếu Token xác thực."}), 400

        today = datetime.now().strftime("%Y-%m-%d")
        task_record = tasks_col.find_one({"uid": uid, "task_id": task_id, "date": today})

        if not task_record or task_record.get("task_token") != task_token:
            return jsonify({"success": False, "msg": "Mã xác thực không đúng hoặc đã hết hạn!"})

        if task_record.get("status") == "completed":
            return jsonify({"success": False, "msg": "Nhiệm vụ này đã nhận thưởng rồi!"})

        elapsed_time = time.time() - task_record.get("created_at", 0)
        if elapsed_time < MIN_TASK_TIME_SECONDS:
            return jsonify({"success": False, "msg": f"Thao tác quá nhanh! Vui lòng chờ ít nhất {MIN_TASK_TIME_SECONDS}s."})

        tasks_col.update_one({"_id": task_record["_id"]}, {"$set": {"status": "completed", "completed_at": time.time()}})
        users_col.update_one({"uid": uid}, {"$inc": {"balance": reward}})

        history_col.insert_one({"uid": uid, "type": f"Hoàn thành Vượt link #{task_id}", "amount": f"+{reward} DCOIN", "date": datetime.now().strftime("%d/%m/%Y %H:%M")})

        updated_user = users_col.find_one({"uid": uid})
        return jsonify({"success": True, "msg": f"Thành công! +{reward} DCOIN", "new_balance": updated_user["balance"]})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    try:
        data = request.json or {}
        uid = str(data.get('user_id', '')).strip()
        amount = int(data.get('amount', 0))
        method = data.get('method', 'MOMO')
        account_number = data.get('account_number', '').strip()
        account_name = data.get('account_name', '').strip()
        bank_name = data.get('bank_name', '').strip()

        if amount < 10000:
            return jsonify({"success": False, "msg": "Số DCOIN rút tối thiểu là 10,000 DCOIN!"})

        if not account_number or not account_name:
            return jsonify({"success": False, "msg": "Vui lòng nhập đầy đủ Số tài khoản & Tên người nhận!"})

        user = users_col.find_one({"uid": uid})
        if not user or user.get("balance", 0) < amount:
            return jsonify({"success": False, "msg": "Số dư DCOIN của bạn không đủ!"})

        # Trừ tiền tạm khóa
        users_col.update_one({"uid": uid}, {"$inc": {"balance": -amount}})
        req_id = secrets.token_hex(4)

        withdrawals_col.insert_one({
            "req_id": req_id,
            "uid": uid,
            "display_name": user.get("display_name", "N/A"),
            "username": user.get("username", ""),
            "amount": amount,
            "method": method,
            "account_number": account_number,
            "account_name": account_name,
            "bank_name": bank_name,
            "status": "pending",           # pending, approved, completed, rejected_refund, rejected_penalty
            "reason": "",
            "date": datetime.now().strftime("%d/%m/%Y %H:%M")
        })

        if ADMIN_ID:
            send_telegram_msg(ADMIN_ID, f"🚨 **CÓ ĐƠN RÚT TIỀN MỚI!**\n\n👤 User: **{user.get('display_name')}** (@{user.get('username')})\n🆔 ID: `{uid}`\n💵 Rút: **{amount:,} DCOIN**\n💳 {method} ({bank_name}): `{account_number}` ({account_name})\n🆔 Mã đơn: `{req_id}`")

        return jsonify({"success": True, "msg": "Đã gửi yêu cầu rút tiền! Vui lòng chờ Admin xử lý."})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/user/withdrawals', methods=['POST'])
def get_user_withdrawals():
    """Lấy lịch sử rút tiền của người dùng kèm chi tiết trạng thái & lý do"""
    try:
        data = request.json or {}
        uid = str(data.get('user_id', '')).strip()
        if not uid: return jsonify({"success": False, "data": []})

        items = list(withdrawals_col.find({"uid": uid}, {"_id": 0}).sort("_id", -1).limit(20))
        return jsonify({"success": True, "data": items})
    except Exception as e:
        return jsonify({"success": False, "data": []}), 500

@app.route('/api/leaderboard', methods=['POST'])
def get_leaderboard():
    """Bảng xếp hạng Top 20 tài khoản nhiều DCOIN nhất"""
    try:
        top_users = list(users_col.find({}, {"_id": 0, "uid": 1, "display_name": 1, "username": 1, "balance": 1}).sort("balance", -1).limit(20))
        return jsonify({"success": True, "data": top_users})
    except Exception as e:
        return jsonify({"success": False, "data": []}), 500

# =========================================================
# 5. CÁC API CẢI TIẾN CHUYÊN DỤNG CHO ADMIN
# =========================================================
@app.route('/api/admin/withdrawals', methods=['POST'])
def admin_get_withdrawals():
    try:
        data = request.json or {}
        admin_id = str(data.get('admin_id', '')).strip()
        if admin_id != ADMIN_ID or not ADMIN_ID:
            return jsonify({"success": False, "msg": "Bạn không có quyền Admin!"}), 403

        items = list(withdrawals_col.find({}, {"_id": 0}).sort("_id", -1).limit(50))
        return jsonify({"success": True, "data": items})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/admin/action-withdraw', methods=['POST'])
def admin_action_withdraw():
    """
    Xử lý đơn rút tiền chuẩn 5 nút bấm từ Admin Panel:
    - approve: Duyệt đơn (Đang chuyển tiền)
    - complete: Hoàn thành (Tiền đã gửi thành công)
    - reject_refund: Hoàn lại (Từ chối + Hoàn tiền lại ví user)
    - reject_penalty: Hủy do vi phạm (Từ chối + Không hoàn tiền)
    - undo_approve: Hủy duyệt (Đưa về trạng thái Chờ duyệt)
    """
    try:
        data = request.json or {}
        admin_id = str(data.get('admin_id', '')).strip()
        req_id = data.get('req_id', '')
        action = data.get('action', '')
        reason = data.get('reason', '').strip()

        if admin_id != ADMIN_ID or not ADMIN_ID:
            return jsonify({"success": False, "msg": "Bạn không có quyền Admin!"}), 403

        item = withdrawals_col.find_one({"req_id": req_id})
        if not item: return jsonify({"success": False, "msg": "Đơn không tồn tại!"})

        uid = item["uid"]
        amount = item["amount"]

        if action == "approve":
            withdrawals_col.update_one({"req_id": req_id}, {"$set": {"status": "approved"}})
            send_telegram_msg(uid, f"🔵 **ĐƠN RÚT TIỀN ĐÃ ĐƯỢC DUYỆT!**\n\nĐơn rút **{amount:,} DCOIN** của bạn đã được duyệt và đang trong quá trình chuyển tiền.")
            return jsonify({"success": True, "msg": "Đã chuyển trạng thái sang [ĐÃ DUYỆT / ĐANG CHUYỂN TIỀN]"})

        elif action == "complete":
            withdrawals_col.update_one({"req_id": req_id}, {"$set": {"status": "completed"}})
            send_telegram_msg(uid, f"🟢 **RÚT TIỀN HOÀN THÀNH!**\n\nTiền cho đơn rút **{amount:,} DCOIN** đã được chuyển thành công tới tài khoản của bạn!")
            return jsonify({"success": True, "msg": "Đã chuyển trạng thái sang [HOÀN THÀNH]"})

        elif action == "reject_refund":
            withdrawals_col.update_one({"req_id": req_id}, {"$set": {"status": "rejected_refund", "reason": reason}})
            users_col.update_one({"uid": uid}, {"$inc": {"balance": amount}})
            send_telegram_msg(uid, f"🟣 **ĐƠN RÚT TIỀN BỊ TỪ CHỐI (ĐÃ HOÀN TIỀN)**\n\nLý do: `{reason or 'Không có'}`\nSố DCOIN **{amount:,}** đã được hoàn lại về ví của bạn.")
            return jsonify({"success": True, "msg": "Đã HOÀN TIỀN lại ví và chuyển đơn sang [ĐÃ HỦY - HOÀN TIỀN]"})

        elif action == "reject_penalty":
            withdrawals_col.update_one({"req_id": req_id}, {"$set": {"status": "rejected_penalty", "reason": reason}})
            send_telegram_msg(uid, f"🔴 **ĐƠN RÚT TIỀN BỊ HỦY DO VI PHẠM!**\n\nLý do: `{reason or 'Vi phạm quy định hệ thống'}`\nSố DCOIN cho đơn rút này bị tịch thu.")
            return jsonify({"success": True, "msg": "Đã HỦY ĐƠN (Phạt không hoàn tiền) thành công!"})

        elif action == "undo_approve":
            withdrawals_col.update_one({"req_id": req_id}, {"$set": {"status": "pending"}})
            send_telegram_msg(uid, f"🟡 **CẬP NHẬT TRẠNG THÁI RÚT TIỀN**\n\nĐơn rút **{amount:,} DCOIN** của bạn đã được trả về trạng thái [Đang chờ duyệt].")
            return jsonify({"success": True, "msg": "Đã khôi phục đơn về trạng thái [CHỜ DUYỆT]"})

        return jsonify({"success": False, "msg": "Hành động không hợp lệ!"})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route('/api/admin/inject-dcoin', methods=['POST'])
def admin_inject_dcoin():
    """Admin bơm/chuyển DCOIN trực tiếp cho tài khoản qua ID Telegram kèm Ghi chú"""
    try:
        data = request.json or {}
        admin_id = str(data.get('admin_id', '')).strip()
        target_uid = str(data.get('target_uid', '')).strip()
        amount = int(data.get('amount', 0))
        note = data.get('note', 'Nạp tiền từ Admin').strip()
        
        if admin_id != ADMIN_ID or not ADMIN_ID:
            return jsonify({"success": False, "msg": "Bạn không có quyền Admin!"}), 403

        if not target_uid or amount <= 0:
            return jsonify({"success": False, "msg": "Thiếu Telegram ID người nhận hoặc số DCOIN không hợp lệ!"})

        target_user = users_col.find_one({"uid": target_uid})
        if not target_user:
            return jsonify({"success": False, "msg": "Tài khoản Telegram ID này chưa từng mở Mini App!"})

        # Cộng DCOIN
        users_col.update_one({"uid": target_uid}, {"$inc": {"balance": amount}})

        # Lưu Log Audit Kiểm toán
        audit_logs_col.insert_one({
            "admin_id": admin_id,
            "target_uid": target_uid,
            "target_name": target_user.get("display_name", ""),
            "amount": amount,
            "note": note,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        })

        # Báo cho User
        send_telegram_msg(target_uid, f"🎁 **BẠN VỪA NHẬN ĐƯỢC DCOIN TỪ ADMIN!**\n\n💰 Số lượng: **+{amount:,} DCOIN**\n📌 Nội dung: `{note}`")

        return jsonify({"success": True, "msg": f"Đã chuyển thành công +{amount:,} DCOIN cho User {target_uid}!"})
    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
