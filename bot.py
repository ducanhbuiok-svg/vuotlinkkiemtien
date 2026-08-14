import os
import json
import hmac
import hashlib
from urllib.parse import parse_qs
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = 8914123780

# Đường dẫn file dữ liệu
DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "withdraws": []}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users": {}, "withdraws": []}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def verify_telegram_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=400, detail="Thiếu dữ liệu xác thực")
    try:
        parsed_data = parse_qs(init_data)
        user_json = parsed_data.get('user', ['{}'])[0]
        return json.loads(user_json)
    except Exception:
        raise HTTPException(status_code=401, detail="Dữ liệu không hợp lệ")

def mask_string(s: str, visible_start=2, visible_end=2) -> str:
    if not s or len(s) <= visible_start + visible_end:
        return "***"
    return s[:visible_start] + "***" + s[-visible_end:]

# Model dữ liệu API
class WithdrawRequest(BaseModel):
    amount: float
    wallet_info: str

class AdminActionRequest(BaseModel):
    withdraw_id: int
    action: str # approve, reject, hold
    note: str = ""

class AdminGrantRequest(BaseModel):
    target_user_id: str
    amount: float
    note: str = ""

@app.post("/api/user-info")
def get_user_info(x_tg_data: str = Header(None)):
    user = verify_telegram_data(x_tg_data)
    user_id = str(user.get("id"))
    
    db = load_db()
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "name": user.get("first_name", "User"),
            "username": user.get("username", ""),
            "avatar": user.get("photo_url", ""),
            "balance": 1000,
            "total_links": 0,
            "notifications": []
        }
        save_db(db)
    else:
        db["users"][user_id]["name"] = user.get("first_name", "User")
        db["users"][user_id]["username"] = user.get("username", "")
        if user.get("photo_url"):
            db["users"][user_id]["avatar"] = user.get("photo_url")
        save_db(db)

    user_data = db["users"][user_id]
    notifications = user_data.get("notifications", [])
    
    if notifications:
        user_data["notifications"] = []
        save_db(db)
        
    return {**user_data, "unread_notifications": notifications}

@app.post("/api/withdraw")
def create_withdraw(req: WithdrawRequest, x_tg_data: str = Header(None)):
    user = verify_telegram_data(x_tg_data)
    user_id = str(user.get("id"))
    
    db = load_db()
    user_data = db["users"].get(user_id, {"balance": 0})
    
    if req.amount < 10000:
        return {"success": False, "message": "Số tiền rút tối thiểu là 10,000 DCOIN!"}
        
    if user_data.get("balance", 0) < req.amount:
        return {"success": False, "message": "Số dư DCOIN không đủ!"}
        
    user_data["balance"] -= req.amount
    
    withdraw_id = len(db["withdraws"]) + 1
    new_item = {
        "id": withdraw_id,
        "user_id": user_id,
        "user_name": user.get("first_name", "User"),
        "username": user.get("username", ""),
        "avatar": user.get("photo_url", ""),
        "amount": req.amount,
        "wallet_info": req.wallet_info,
        "status": "pending",
        "note": "Đang chờ Admin kiểm tra",
        "created_at": "Gần đây"
    }
    
    db["withdraws"].append(new_item)
    save_db(db)
    
    return {"success": True, "message": f"Đã gửi yêu cầu rút {req.amount:,} DCOIN thành công!"}

@app.post("/api/user-history")
def get_user_history(x_tg_data: str = Header(None)):
    user = verify_telegram_data(x_tg_data)
    user_id = str(user.get("id"))
    
    db = load_db()
    user_withdraws = [w for w in db["withdraws"] if str(w["user_id"]) == user_id]
    user_withdraws.reverse()
    return {"success": True, "data": user_withdraws}

@app.post("/api/leaderboard")
def get_leaderboard(x_tg_data: str = Header(None)):
    current_user = verify_telegram_data(x_tg_data)
    is_admin = (current_user.get("id") == ADMIN_ID)
    
    db = load_db()
    all_users = []
    
    for uid, udata in db["users"].items():
        display_name = udata.get("name", "User") if is_admin else mask_string(udata.get("name", "User"), 2, 1)
        display_id = uid if is_admin else mask_string(uid, 3, 3)
        display_username = udata.get("username", "") if is_admin else mask_string(udata.get("username", ""), 1, 1)
        
        all_users.append({
            "user_id": display_id,
            "raw_id": uid,
            "name": display_name,
            "username": display_username,
            "avatar": udata.get("avatar", ""),
            "balance": udata.get("balance", 0),
            "total_links": udata.get("total_links", 0)
        })
        
    all_users.sort(key=lambda x: x["balance"], reverse=True)
    top_10 = all_users[:10]
    
    return {"success": True, "is_admin": is_admin, "data": top_10}

@app.post("/api/admin/pending-withdraws")
def get_admin_withdraws(x_tg_data: str = Header(None)):
    user = verify_telegram_data(x_tg_data)
    if user.get("id") != ADMIN_ID:
        raise HTTPException(status_code=403, detail="Không có quyền Admin")
        
    db = load_db()
    db["withdraws"].reverse()
    return {"success": True, "data": db["withdraws"]}

@app.post("/api/admin/action-withdraw")
def action_withdraw(req: AdminActionRequest, x_tg_data: str = Header(None)):
    user = verify_telegram_data(x_tg_data)
    if user.get("id") != ADMIN_ID:
        raise HTTPException(status_code=403, detail="Không có quyền Admin")
        
    db = load_db()
    target_item = None
    for item in db["withdraws"]:
        if item["id"] == req.withdraw_id:
            target_item = item
            break
            
    if not target_item:
        return {"success": False, "message": "Không tìm thấy đơn!"}
        
    if req.action == "approve":
        target_item["status"] = "approved"
        target_item["note"] = req.note or "Đã chuyển tiền thành công!"
        msg = f"✅ Đã DUYỆT đơn #{req.withdraw_id}!"
        
    elif req.action == "reject":
        target_item["status"] = "rejected"
        target_item["note"] = req.note or "Thông tin tài khoản không chính xác."
        u_id = str(target_item["user_id"])
        if u_id in db["users"]:
            db["users"][u_id]["balance"] += target_item["amount"]
        msg = f"❌ Đã TỪ CHỐI & hoàn xu đơn #{req.withdraw_id}!"
        
    elif req.action == "hold":
        target_item["status"] = "held"
        target_item["note"] = req.note or "Phát hiện gian lận. DCOIN bị tạm giữ vĩnh viễn."
        msg = f"🔒 Đã GIỮ DCOIN vi phạm cho đơn #{req.withdraw_id}!"
        
    save_db(db)
    return {"success": True, "message": msg}

@app.post("/api/admin/grant-dcoin")
def grant_dcoin(req: AdminGrantRequest, x_tg_data: str = Header(None)):
    user = verify_telegram_data(x_tg_data)
    if user.get("id") != ADMIN_ID:
        raise HTTPException(status_code=403, detail="Không có quyền Admin")
        
    db = load_db()
    target_id = str(req.target_user_id).strip()
    
    if target_id not in db["users"]:
        return {"success": False, "message": f"Tài khoản ID `{target_id}` chưa từng vào Mini App!"}
        
    db["users"][target_id]["balance"] += req.amount
    
    if "notifications" not in db["users"][target_id]:
        db["users"][target_id]["notifications"] = []
        
    db["users"][target_id]["notifications"].append({
        "amount": req.amount,
        "note": req.note or "Phần thưởng từ Admin dành cho bạn!"
    })
    
    save_db(db)
    return {"success": True, "message": f"🎉 Đã tặng +{req.amount:,} DCOIN cho tài khoản ID `{target_id}` thành công!"}

# Webhook Telegram Bot gửi câu chào & Nút Tham gia Nhóm
@app.post("/webhook")
def telegram_webhook(update: dict):
    if "message" in update and "text" in update["message"]:
        msg = update["message"]
        text = msg.get("text", "")
        chat_id = msg["chat"]["id"]
        first_name = msg["from"].get("first_name", "Bạn")
        
        if text.startswith("/start"):
            welcome_text = (
                f"👋 **Xin chào {first_name}!**\n\n"
                f"Chào mừng bạn đến với **DCOIN Mini App** - Nơi vượt link ngắn kiếm tiền uy tín và an toàn nhất!\n\n"
                f"📢 **ĐỂ BẮT ĐẦU KIẾM TIỀN, VUI LÒNG THAM GIA CÁC KÊNH CHÍNH THỨC:**\n"
                f"1. Tham gia Kênh Tin Tức để nhận Mã Giftcode mỗi ngày.\n"
                f"2. Tham gia Nhóm Hỗ Trợ để trao đổi và được Admin giúp đỡ.\n\n"
                f"👇 Bấm các nút bên dưới để tham gia và mở App nhé!"
            )
            
            payload = {
                "chat_id": chat_id,
                "text": welcome_text,
                "parse_mode": "Markdown",
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {"text": "📢 Kênh Thông Báo Telegram", "url": "https://t.me/your_channel_link"},
                        ],
                        [
                            {"text": "💬 Nhóm Hỗ Trợ Cộng Đồng", "url": "https://t.me/your_group_link"}
                        ],
                        [
                            {"text": "🚀 MỞ MINI APP KIẾM DCOIN", "web_app": {"url": "https://your-app.vercel.app"}}
                        ]
                    ]
                }
            }
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(url, json=payload)
            
    return {"status": "ok"}
