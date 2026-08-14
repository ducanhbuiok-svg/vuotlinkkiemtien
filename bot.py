import os
import json
import hmac
import hashlib
import sqlite3
import urllib.parse
import asyncio
import threading
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ==================== CẤU HÌNH QUAN TRỌNG (ĐIỀN ĐÚNG 2 MỤC NÀY) ====================
BOT_TOKEN = "8116280112:AAERR6AH23JavjshO073QZmcDH7_qDEwdro"  # ⚠️ Lấy từ @BotFather (ví dụ: "7123456789:AAFg...")
ADMIN_ID = 8914123780                          # ⚠️ Thay ID Telegram dạng số của bạn (dùng @userinfobot để lấy)
WEBAPP_URL = "https://vuotlinkkiemtien.vercel.app"

# ==================== CƠ SỞ DỮ LIỆU SQLITE ====================
DB_NAME = "database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Bảng lưu thông tin user & số dư
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 0,
            total_links INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    # Bảng lịch sử yêu cầu rút tiền
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            wallet_info TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ==================== ANTI-CHEAT: XÁC THỰC HMAC TELEGRAM ====================
def verify_telegram_init_data(init_data: str) -> dict:
    """Xác thực chữ ký bảo mật từ Telegram WebApp SDK."""
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed_data:
            return None
        
        received_hash = parsed_data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode('utf-8'), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(calculated_hash, received_hash):
            return json.loads(parsed_data.get("user", "{}"))
        return None
    except Exception:
        return None

# ==================== FASTAPI WEB SERVER (CHO RENDER & MINI APP) ====================
app = FastAPI(title="DCOIN Backend System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WithdrawRequest(BaseModel):
    amount: float
    wallet_info: str

@app.get("/")
def health_check():
    return {"status": "online", "message": "DCOIN Backend Server Running"}

@app.post("/api/user-info")
def get_user_info(x_tg_data: str = Header(None)):
    if not x_tg_data:
        raise HTTPException(status_code=401, detail="Missing Telegram Data")
    
    tg_user = verify_telegram_init_data(x_tg_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Anti-Cheat Triggered: Invalid Token")
    
    user_id = tg_user['id']
    username = tg_user.get('username', '')
    first_name = tg_user.get('first_name', 'User')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, total_links FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, balance, total_links, created_at) VALUES (?, ?, ?, 0, 0, ?)",
            (user_id, username, first_name, datetime.now().isoformat())
        )
        conn.commit()
        balance, total_links = 0.0, 0
    else:
        balance, total_links = row[0], row[1]
        
    conn.close()
    
    return {
        "user_id": user_id,
        "first_name": first_name,
        "username": username,
        "balance": balance,
        "total_links": total_links
    }

@app.post("/api/withdraw")
def request_withdraw(req: WithdrawRequest, x_tg_data: str = Header(None)):
    if not x_tg_data:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    tg_user = verify_telegram_init_data(x_tg_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Anti-Cheat Auth Failed")
    
    user_id = tg_user['id']
    amount = req.amount
    
    if amount < 10000:
        return {"success": False, "message": "Số dư rút tối thiểu là 10,000 DCOIN!"}
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row or row[0] < amount:
        conn.close()
        return {"success": False, "message": "Số dư không đủ!"}
    
    # Trừ tiền & tạo đơn rút
    new_balance = row[0] - amount
    cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
    cursor.execute(
        "INSERT INTO withdrawals (user_id, amount, wallet_info, created_at) VALUES (?, ?, ?, ?)",
        (user_id, amount, req.wallet_info, datetime.now().isoformat())
    )
    withdraw_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Bắn thông báo về Telegram cho Admin
    asyncio.run_coroutine_threadsafe(
        send_admin_withdraw_notification(withdraw_id, user_id, tg_user.get('first_name', ''), amount, req.wallet_info),
        bot_loop
    )
    
    return {"success": True, "message": "Yêu cầu rút tiền thành công!", "new_balance": new_balance}

# ==================== BOT TELEGRAM ====================
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
bot_loop = None

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Mở DCOIN App VIP", web_app={"url": WEBAPP_URL})
    ]])
    await update.message.reply_text(
        f"👋 Chào mừng **{user.first_name}** đến với DCOIN System!\n\nBấm nút bên dưới để mở Mini App nhé.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

async def send_admin_withdraw_notification(w_id, user_id, name, amount, wallet):
    text = (
        f"🚨 **YÊU CẦU RÚT TIỀN MỚI #{w_id}**\n\n"
        f"👤 **Khách hàng:** {name} (`{user_id}`)\n"
        f"💰 **Số tiền:** {amount:,.0f} DCOIN\n"
        f"💳 **Ví/Ngân hàng:** `{wallet}`"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt", callback_data=f"app_{w_id}_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Từ Chối", callback_data=f"rej_{w_id}_{user_id}_{amount}")
        ]
    ])
    try:
        await bot_app.bot.send_message(chat_id=ADMIN_ID, text=text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        print(f"Lỗi gửi tin nhắn cho Admin: {e}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action, w_id, user_id, amount = data[0], data[1], data[2], float(data[3])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if action == "app":
        cursor.execute("UPDATE withdrawals SET status = 'APPROVED' WHERE id = ?", (w_id,))
        conn.commit()
        await query.edit_message_text(f"{query.message.text}\n\nTRẠNG THÁI: **ĐÃ DUYỆT ✅**", parse_mode="Markdown")
        await bot_app.bot.send_message(chat_id=int(user_id), text=f"🎉 Lệnh rút {amount:,.0f} DCOIN của bạn đã được duyệt thành công!")
    elif action == "rej":
        # Hoàn tiền lại cho user
        cursor.execute("UPDATE withdrawals SET status = 'REJECTED' WHERE id = ?", (w_id,))
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        await query.edit_message_text(f"{query.message.text}\n\nTRẠNG THÁI: **ĐÃ TỪ CHỐI ❌ (Đã hoàn xu)**", parse_mode="Markdown")
        await bot_app.bot.send_message(chat_id=int(user_id), text=f"❌ Lệnh rút {amount:,.0f} DCOIN bị từ chối. Xu đã được hoàn lại.")
        
    conn.close()

bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(CallbackQueryHandler(handle_callback))

# ==================== KHỞI CHẠY (RENDER SAFE) ====================
def run_fastapi():
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    init_db()
    
    # Chạy Web Server FastAPI ở Thread riêng để Render nhận diện Web Service Free
    threading.Thread(target=run_fastapi, daemon=True).start()
    
    # Chạy Telegram Bot ở Main Thread
    bot_loop = asyncio.get_event_loop()
    print("🚀 DCOIN Engine VIP System Online!")
    bot_app.run_polling()
    
