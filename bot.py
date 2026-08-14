import os, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

threading.Thread(target=lambda: HTTPServer(('0.0.0.0', int(os.environ.get('PORT', 8080))), Health).serve_forever(), daemon=True).start()
import sqlite3
import json
import logging
import random
import string
import time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== CẤU HÌNH BOT ====================
TOKEN = "8116280112:AAERR6AH23JavjshO073QZmcDH7_qDEwdro"
ADMIN_ID = 8914123780                         # Thay Telegram ID của bạn vào đây
WEBAPP_URL = "https://vuotlinkkiemtien.vercel.app" # Thay Link Vercel/GitHub Pages của bạn

# API KEY CÁC TRANG RÚT GỌN LINK
LINK4M_API = "YOUR_LINK4M_API_KEY"
TRAFFICVN_API = "YOUR_TRAFFICVN_API_KEY"
YEUTIEPTHI_API = "YOUR_YEUTIEPTHI_API_KEY"

# CẤU HÌNH ANTI-CHEAT VIP
MIN_TASK_TIME_SECONDS = 25  # Thời gian tối thiểu vượt link (Dưới 25s = Auto Tool Bypass)
TOKEN_EXPIRE_SECONDS = 900  # Mã Token hết hạn sau 15 phút (900 giây)
# =======================================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# KHỞI TẠO CƠ SỞ DỮ LIỆU SQLITE
def init_db():
    conn = sqlite3.connect("dcoin_app.db")
    cursor = conn.cursor()
    
    # Bảng User
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0,
        week_dcoin REAL DEFAULT 0,
        month_dcoin REAL DEFAULT 0,
        total_links INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        cheat_warnings INTEGER DEFAULT 0,
        saved_holder TEXT DEFAULT '',
        saved_stk TEXT DEFAULT ''
    )''')
    
    # Bảng Token Anti-Cheat
    cursor.execute('''CREATE TABLE IF NOT EXISTS task_tokens (
        token_code TEXT PRIMARY KEY,
        user_id INTEGER,
        platform TEXT,
        reward_amount INTEGER,
        created_at REAL,
        status TEXT DEFAULT 'PENDING'
    )''')
    
    conn.commit()
    conn.close()

def get_user_data(user_id):
    conn = sqlite3.connect("dcoin_app.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, week_dcoin, month_dcoin, total_links, is_banned, cheat_warnings FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        data = (0, 0, 0, 0, 0, 0)
    else:
        data = row
    conn.close()
    return data

def generate_random_token():
    return "DC-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

# LỆNH /START
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    
    if data[4] == 1:
        await update.message.reply_text("🚫 **TÀI KHOẢN CỦA BẠN ĐÃ BỊ KHÓA VĨNH VIỄN DO DÙNG TOOL GIAN LẬN!**", parse_mode="Markdown")
        return

    keyboard = [[KeyboardButton("🚀 MỞ DCOIN MINI APP", web_app=WebAppInfo(url=WEBAPP_URL))]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"👋 **Chào mừng bạn đến với DCOIN System!**\n\n"
        f"🛡️ *Hệ thống Anti-Cheat VIP đang bật để đảm bảo sự công bằng.*\n"
        f"Nhấn nút bên dưới để bắt đầu làm nhiệm vụ kiếm DCOIN.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# XỬ LÝ SỰ KIỆN TỪ WEBAPP (SEND DATA)
async def web_app_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    data_user = get_user_data(user_id)

    if data_user[4] == 1:
        await update.message.reply_text("🚫 Tài khoản đã bị khóa vĩnh viễn!")
        return

    raw_data = update.effective_message.web_app_data.data
    data = json.loads(raw_data)
    req_type = data.get("type")

    # 1. YÊU CẦU TẠO LINK NHIỆM VỤ CÓ MÃ TOKEN ANTI-CHEAT
    if req_type == "request_task_link":
        platform = data.get("platform", "link4m")
        reward_map = {"link4m": 350, "trafficvn": 300, "layma": 400, "yeutiepthi": 500}
        reward = reward_map.get(platform, 300)
        
        token_code = generate_random_token()
        now = time.time()

        conn = sqlite3.connect("dcoin_app.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO task_tokens (token_code, user_id, platform, reward_amount, created_at) VALUES (?, ?, ?, ?, ?)",
                       (token_code, user_id, platform, reward, now))
        conn.commit()
        conn.close()

        # Tạo URL đích kèm Token
        destination_url = f"https://yourdomain.com/landing?token={token_code}"
        
        if platform == "trafficvn":
            short_link = f"https://trafficvn.net/st?api={TRAFFICVN_API}&url={destination_url}"
        elif platform == "yeutiepthi":
            short_link = f"https://yeutiepthi.org/st?api={YEUTIEPTHI_API}&url={destination_url}"
        else:
            short_link = f"https://link4m.co/st?api={LINK4M_API}&url={destination_url}"

        await update.message.reply_text(
            f"🔗 **LINK NHIỆM VỤ ({platform.upper()}):**\n\n"
            f"👉 **Truy cập link:** {short_link}\n\n"
            f"🔑 **MÃ XÁC NHẬN CỦA BẠN:** `{token_code}`\n"
            f"Sau khi vượt link xong, lấy mã `{token_code}` dán vào Mini App hoặc gõ `/xacnhan {token_code}` để nhận **+{reward} DCOIN**.\n\n"
            f"⏳ *Mã có thời hạn 15 phút. Cấm sử dụng Tool Auto Bypass!*",
            parse_mode="Markdown"
        )

    # 2. XÁC NHẬN MÃ TOKEN (ANTI-CHEAT VIP CHECK)
    elif req_type == "verify_task_code":
        code = data.get("code", "").strip().upper()
        now = time.time()

        conn = sqlite3.connect("dcoin_app.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, platform, reward_amount, created_at, status FROM task_tokens WHERE token_code = ?", (code,))
        token_data = cursor.fetchone()

        if not token_data:
            await update.message.reply_text("❌ **Mã xác nhận Không Hợp Lệ!**", parse_mode="Markdown")
            conn.close()
            return

        t_user_id, platform, reward, created_at, status = token_data

        if t_user_id != user_id:
            await update.message.reply_text("⚠️ **CẢNH BÁO:** Mã Token này không thuộc về bạn!", parse_mode="Markdown")
            conn.close()
            return

        if status == 'COMPLETED':
            await update.message.reply_text("❌ **Mã Token này ĐÃ SỬ DỤNG rồi!**", parse_mode="Markdown")
            conn.close()
            return

        time_taken = now - created_at

        # KIỂM TRA TOOL BYPASS (Dưới 25s)
        if time_taken < MIN_TASK_TIME_SECONDS:
            cursor.execute("UPDATE users SET cheat_warnings = cheat_warnings + 1 WHERE user_id = ?", (user_id,))
            cursor.execute("SELECT cheat_warnings FROM users WHERE user_id = ?", (user_id,))
            warnings = cursor.fetchone()[0]

            if warnings >= 3:
                cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
                conn.commit()
                await update.message.reply_text("🚫 **TÀI KHOẢN ĐÃ BỊ KHÓA VĨNH VIỄN DO SỬ DỤNG TOOL BYPASS!**")
            else:
                conn.commit()
                await update.message.reply_text(
                    f"🚨 **PHÁT HIỆN GIAN LẬN!**\n\n"
                    f"⏱️ Bạn hoàn thành trong **{int(time_taken)}s** (Yêu cầu tối thiểu {MIN_TASK_TIME_SECONDS}s).\n"
                    f"⚠️ Cảnh báo: **{warnings}/3 lần**. Đạt 3 lần sẽ bị KHOÁ TK!",
                    parse_mode="Markdown"
                )
            conn.close()
            return

        if time_taken > TOKEN_EXPIRE_SECONDS:
            await update.message.reply_text("⏰ **Mã Token đã QUÁ HẠN 15 PHÚT!** Vui lòng lấy link mới.", parse_mode="Markdown")
            conn.close()
            return

        # CỘNG DCOIN & CẬP NHẬT TRẠNG THÁI
        cursor.execute("UPDATE task_tokens SET status = 'COMPLETED' WHERE token_code = ?", (code,))
        cursor.execute("UPDATE users SET balance = balance + ?, week_dcoin = week_dcoin + ?, month_dcoin = month_dcoin + ?, total_links = total_links + 1 WHERE user_id = ?",
                       (reward, reward, reward, user_id))
        
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        new_balance = cursor.fetchone()[0]
        
        conn.commit()
        conn.close()

        # Báo tin nhắn Telegram
        await update.message.reply_text(
            f"🎉 **XÁC NHẬN THÀNH CÔNG!**\n\n"
            f"🔑 Mã Token: `{code}`\n"
            f"⏱️ Thời gian vượt: **{int(time_taken)}s** (Hợp lệ)\n"
            f"💰 Tiền thưởng: **+{reward} DCOIN**\n"
            f"💳 Số dư hiện tại: **{new_balance:,.0f} DCOIN**",
            parse_mode="Markdown"
        )

    # 3. RÚT TIỀN NGÂN HÀNG
    elif req_type == "withdraw_bank":
        bank, holder, stk, amount = data.get("bank"), data.get("holder").upper(), data.get("stk"), int(data.get("amount"))
        await update.message.reply_text(
            f"✅ **ĐÃ GỬI LỆNH RÚT NGÂN HÀNG!**\n\n"
            f"🏦 Ngân hàng: **{bank}**\n"
            f"👤 Chủ TK: **{holder}**\n"
            f"💳 Số TK: `{stk}`\n"
            f"💵 Số tiền: **{amount:,} DCOIN**",
            parse_mode="Markdown"
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 **RÚT NGÂN HÀNG:** {user_name} (`{user_id}`)\n🏦 {bank} | `{stk}` | `{holder}`\n💰 Số tiền: `{amount:,} VNĐ`",
            parse_mode="Markdown"
        )

    # 4. ĐỔI THẺ CÀO
    elif req_type == "withdraw_card":
        prov, amount = data.get("provider"), int(data.get("amount"))
        await update.message.reply_text(f"✅ Đã gửi yêu cầu đổi thẻ **{prov}** mệnh giá **{amount:,} DCOIN**.")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 **ĐỔI THẺ CÀO:** {user_name} (`{user_id}`)\n💳 Loại thẻ: `{prov}`\n💰 Mệnh giá: `{amount:,} VNĐ`",
            parse_mode="Markdown"
        )

    # 5. NẠP GAME (TỰ ĐỘNG CHUYỂN ROBLOX SANG USERNAME)
    elif req_type == "withdraw_game":
        game_type = data.get("game_type", "game")
        game_user_id = data.get("game_user_id")
        pkg_name = data.get("pkg_name")
        price = int(data.get("price"))

        if game_type == "roblox":
            label_name = "Username Roblox"
            game_display = "Roblox"
        else:
            label_name = "ID Game"
            game_display = game_type.upper()

        await update.message.reply_text(
            f"✅ **ĐÃ GỬI YÊU CẦU NẠP {game_display}!**\n\n"
            f"🎮 Gói: **{pkg_name}**\n"
            f"👤 {label_name}: `{game_user_id}`\n"
            f"💵 Trừ số dư: **{price:,} DCOIN**",
            parse_mode="Markdown"
        )

        admin_alert = (
            f"🎮 **YÊU CẦU NẠP GAME MỚI!**\n\n"
            f"👤 **Khách:** {user_name} (`{user_id}`)\n"
            f"🎯 **Game:** `{game_display}`\n"
            f"🔑 **{label_name}:** `{game_user_id}`\n"
            f"🎁 **Gói Nạp:** `{pkg_name}`\n"
            f"💵 **Trị giá:** `{price:,} DCOIN`\n\n"
            f"👉 Nạp gói **{pkg_name}** cho {label_name}: `{game_user_id}`!"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, parse_mode="Markdown")

    # 6. LƯU CẤU HÌNH NGÂN HÀNG
    elif req_type == "save_bank":
        holder, stk = data.get("holder").upper(), data.get("stk")
        conn = sqlite3.connect("dcoin_app.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET saved_holder = ?, saved_stk = ? WHERE user_id = ?", (holder, stk, user_id))
        conn.commit()
        conn.close()

# LỆNH XÁC NHẬN DỰ PHÒNG QUA CHAT
async def xacnhan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: `/xacnhan [MÃ_TOKEN]` (Ví dụ: `/xacnhan DC-X8921A`)", parse_mode="Markdown")
        return
    code = context.args[0].strip().upper()
    update.effective_message.web_app_data = type('obj', (object,), {'data': json.dumps({'type': 'verify_task_code', 'code': code})})
    await web_app_handler(update, context)

if __name__ == "__main__":
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("xacnhan", xacnhan_command))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_handler))
    print("🚀 DCOIN Engine Complete System Running!")
    app.run_polling()
