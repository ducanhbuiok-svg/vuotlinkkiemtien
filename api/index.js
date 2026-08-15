const express = require('express');
const cors = require('cors');
const TelegramBot = require('node-telegram-bot-api');

const app = express();
app.use(cors());
app.use(express.json());

// ⚠️ THAY CÁC THÔNG TIN CỦA BẠN VÀO ĐÂY
const BOT_TOKEN = process.env.BOT_TOKEN || "8116280112:AAERR6AH23JavjshO073QZmcDH7_qDEwdro";
const ADMIN_ID = "8914123780"; // ID Telegram Admin duy nhất của bạn
const VERCEL_DOMAIN = "https://vuotlinkkiemtien.vercel.app"; // Link domain Vercel của bạn

const bot = new TelegramBot(BOT_TOKEN);

// Dữ liệu bộ nhớ tạm
let db = {
    users: {
        "8914123780": { id: "8914123780", name: "Admin", dcoin: 100000, isBanned: 0, isAdmin: true }
    },
    daily_tasks: {},
    pending_txs: {},
    withdrawals: []
};

// Cấu hình các nhà cung cấp Vượt Link
const LINK_TOKENS = { 
    link4m: '6a69d21cd1f4b667a1055225', 
    trafficvn: 'tf123456789' 
};

const DB_TASKS = [
    { id: 'link4m', name: 'Vượt Link Link4M', limit: 3, reward: 1000, apiToken: LINK_TOKENS.link4m, shortDomain: 'https://link4m.co/st' },
    { id: 'trafficvn', name: 'Nhiệm Vụ Traffic VN', limit: 2, reward: 1200, apiToken: LINK_TOKENS.trafficvn, shortDomain: 'https://trafficvn.com/st' }
];

function getTodayStr() { return new Date().toISOString().split('T')[0]; }
function getWeekStr() {
    const d = new Date();
    const onejan = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil((((d - onejan) / 86400000) + onejan.getDay() + 1) / 7);
    return `${d.getFullYear()}-W${week}`;
}

// Middleware xác thực User Telegram
function checkUserSecurity(req, res, next) {
    const userId = req.headers['x-telegram-id'];
    const userName = req.headers['x-telegram-name'] || 'User_' + userId;
    if (!userId) return res.status(401).json({ error: 'Vui lòng mở ứng dụng từ Telegram Mini App!' });

    if (!db.users[userId]) {
        db.users[userId] = { 
            id: userId, 
            name: userName, 
            dcoin: 0, 
            isBanned: 0, 
            isAdmin: (userId.toString() === ADMIN_ID.toString()) 
        };
    }
    if (db.users[userId].isBanned === 1) return res.status(403).json({ error: 'Tài khoản của bạn đã bị KHÓA!' });
    req.user = db.users[userId];
    next();
}

// Middleware bảo mật Admin (Chỉ duy nhất ADMIN_ID mới qua được)
function checkAdmin(req, res, next) {
    const userId = req.headers['x-telegram-id'];
    if (!userId || userId.toString() !== ADMIN_ID.toString()) {
        return res.status(403).json({ error: 'Quyền truy cập bị từ chối! Bạn không phải Admin.' });
    }
    next();
}

// Webhook nhận lệnh /start
app.post('/api/webhook', (req, res) => {
    const update = req.body;
    if (update && update.message && update.message.text === '/start') {
        const chatId = update.message.chat.id;
        bot.sendMessage(chatId, "👋 Chào mừng bạn đến với Mini App!\nBấm nút bên dưới để bắt đầu:", {
            reply_markup: {
                inline_keyboard: [
                    [{ text: "🚀 Mở Mini App", web_app: { url: "https://ducanhbuiok-svg.github.io/vuotlinkkiemtien" } }]
                ]
            }
        });
    }
    res.status(200).send('OK');
});

// --- API USER ---
app.get('/api/user/info', checkUserSecurity, (req, res) => {
    res.json({ 
        id: req.user.id, 
        name: req.user.name, 
        dcoin: req.user.dcoin, 
        isAdmin: (req.user.id.toString() === ADMIN_ID.toString()) 
    });
});

app.get('/api/tasks', checkUserSecurity, (req, res) => {
    const today = getTodayStr();
    const keyPrefix = `${req.user.id}_${today}_`;
    const tasksWithStatus = DB_TASKS.map(task => {
        const count = db.daily_tasks[`${keyPrefix}${task.id}`] || 0;
        return { ...task, currentCount: count, isCompleted: count >= task.limit };
    });
    res.json(tasksWithStatus);
});

// API TẠO LINK VƯỢT TỰ ĐỘNG (AUTO)
app.post('/api/tasks/start-auto', checkUserSecurity, (req, res) => {
    const { taskId } = req.body;
    const task = DB_TASKS.find(t => t.id === taskId);
    if (!task) return res.status(400).json({ error: 'Nhiệm vụ không tồn tại!' });

    const today = getTodayStr();
    const taskKey = `${req.user.id}_${today}_${taskId}`;
    const currentCount = db.daily_tasks[taskKey] || 0;

    if (currentCount >= task.limit) {
        return res.status(400).json({ error: 'Bạn đã đạt giới hạn hôm nay!' });
    }

    const txId = 'TX-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
    const targetCallbackUrl = `${VERCEL_DOMAIN}/api/tasks/callback?txId=${txId}`;
    
    db.pending_txs[txId] = {
        userId: req.user.id,
        taskId: task.id,
        reward: task.reward,
        createdAt: Date.now()
    };

    const finalShortLink = `${task.shortDomain}?api=${task.apiToken}&url=${encodeURIComponent(targetCallbackUrl)}`;
    res.json({ success: true, shortLink: finalShortLink });
});

// TRANG CALLBACK XÁC NHẬN TỰ ĐỘNG & CỘNG DCOIN
app.get('/api/tasks/callback', (req, res) => {
    const { txId } = req.query;

    if (!txId || !db.pending_txs[txId]) {
        return res.send(`
            <html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Lỗi</title></head>
            <body style="background:#0f172a; color:#ef4444; text-align:center; padding-top:50px; font-family:sans-serif;">
                <h2>❌ Mã xác minh không hợp lệ hoặc đã hết hạn!</h2>
                <p style="color:#94a3b8;">Vui lòng quay lại Mini App và thử lại.</p>
            </body></html>
        `);
    }

    const tx = db.pending_txs[txId];
    const today = getTodayStr();
    const taskKey = `${tx.userId}_${today}_${tx.taskId}`;
    const currentCount = db.daily_tasks[taskKey] || 0;

    db.daily_tasks[taskKey] = currentCount + 1;
    if (db.users[tx.userId]) {
        db.users[tx.userId].dcoin += tx.reward;
    }

    db.withdrawals.push({
        id: 'AUTO-' + Date.now(),
        userId: tx.userId,
        userName: db.users[tx.userId] ? db.users[tx.userId].name : 'User',
        category: 'Làm Nhiệm Vụ Auto',
        method: 'Tự Động Xác Nhận',
        details: `+${tx.reward} DCOIN (Vượt Link Auto)`,
        amountDcoin: `+${tx.reward}`,
        status: 'HOAN_THANH',
        createdAt: new Date().toLocaleString('vi-VN'),
        createdWeek: getWeekStr()
    });

    delete db.pending_txs[txId];

    res.send(`
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Xác Nhận Thành Công</title>
            <style>
                body { background-color: #0f172a; color: #f8fafc; font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
                .card { background: #1e293b; padding: 30px; border-radius: 16px; text-align: center; border: 1px solid #334155; max-width: 90%; width: 320px; }
                .icon { font-size: 48px; color: #22c55e; margin-bottom: 10px; }
                .btn { display: inline-block; margin-top: 20px; background: #38bdf8; color: #0f172a; text-decoration: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">🎉</div>
                <h2>Xác Nhận Thành Công!</h2>
                <p style="color: #38bdf8; font-size: 18px; font-weight: bold;">+${tx.reward} DCOIN</p>
                <p style="color: #94a3b8; font-size: 13px;">DCOIN đã được cộng tự động vào tài khoản của bạn.</p>
                <a class="btn" href="javascript:window.close();">Đóng Trang Này</a>
            </div>
        </body>
        </html>
    `);
});

app.post('/api/withdraw', checkUserSecurity, (req, res) => {
    const { category, method, details, amountDcoin } = req.body;
    const cost = parseInt(amountDcoin);

    if (isNaN(cost) || cost <= 0) return res.status(400).json({ error: 'Số DCOIN không hợp lệ!' });
    if (db.users[req.user.id].dcoin < cost) return res.status(400).json({ error: 'Số dư DCOIN không đủ!' });

    db.users[req.user.id].dcoin -= cost;
    db.withdrawals.push({
        id: 'WD-' + Date.now(),
        userId: req.user.id,
        userName: req.user.name,
        category, method, details, amountDcoin: cost,
        status: 'CHO_DUYET',
        createdAt: new Date().toLocaleString('vi-VN'),
        createdWeek: getWeekStr()
    });

    res.json({ success: true, message: 'Đã gửi yêu cầu rút tiền thành công!' });
});

app.get('/api/history', checkUserSecurity, (req, res) => {
    const userHistory = db.withdrawals.filter(w => w.userId === req.user.id).reverse();
    res.json(userHistory);
});

app.get('/api/leaderboard', (req, res) => {
    const currentWeek = getWeekStr();
    const counts = {};
    db.withdrawals.filter(w => w.category === 'Làm Nhiệm Vụ Auto' && w.createdWeek === currentWeek).forEach(w => {
        counts[w.userName] = (counts[w.userName] || 0) + 1;
    });
    const leaderboard = Object.keys(counts).map(name => ({ name, count: counts[name] })).sort((a, b) => b.count - a.count).slice(0, 10);
    res.json(leaderboard);
});

// --- API DÀNH RIÊNG CHO ADMIN BẢO MẬT ---
app.get('/api/admin/data', checkAdmin, (req, res) => {
    res.json({
        users: Object.values(db.users),
        withdrawals: db.withdrawals.filter(w => w.category !== 'Làm Nhiệm Vụ Auto').reverse()
    });
});

app.post('/api/admin/adjust-dcoin', checkAdmin, (req, res) => {
    const { targetUserId, amount } = req.body;
    const numAmount = parseInt(amount);

    if (!db.users[targetUserId]) return res.status(404).json({ error: 'Không tìm thấy User!' });
    if (isNaN(numAmount)) return res.status(400).json({ error: 'Số DCOIN nhập vào không hợp lệ!' });

    db.users[targetUserId].dcoin += numAmount;
    res.json({ success: true, message: `Thành công! Số dư mới của User: ${db.users[targetUserId].dcoin} DCOIN` });
});

app.post('/api/admin/process-withdraw', checkAdmin, (req, res) => {
    const { withdrawId, action } = req.body;
    const item = db.withdrawals.find(w => w.id === withdrawId);

    if (!item) return res.status(404).json({ error: 'Đơn rút tiền không tồn tại!' });
    if (item.status !== 'CHO_DUYET') return res.status(400).json({ error: 'Đơn này đã được xử lý!' });

    if (action === 'APPROVE') {
        item.status = 'THANH_TOAN';
        res.json({ success: true, message: 'Đã duyệt đơn thành công!' });
    } else if (action === 'REJECT') {
        item.status = 'TU_CHOI';
        if (db.users[item.userId]) {
            db.users[item.userId].dcoin += parseInt(item.amountDcoin);
        }
        res.json({ success: true, message: 'Đã từ chối đơn và hoàn tiền DCOIN cho người dùng!' });
    } else {
        res.status(400).json({ error: 'Hành động không hợp lệ!' });
    }
});

app.post('/api/admin/toggle-ban', checkAdmin, (req, res) => {
    const { targetUserId } = req.body;
    if (!db.users[targetUserId]) return res.status(404).json({ error: 'Không tìm thấy User!' });

    db.users[targetUserId].isBanned = db.users[targetUserId].isBanned === 1 ? 0 : 1;
    const statusText = db.users[targetUserId].isBanned === 1 ? 'Khóa' : 'Mở khóa';
    res.json({ success: true, message: `Đã ${statusText} tài khoản ${targetUserId}!` });
});
// Thêm đoạn này để trang chủ hiện thông báo Server sống
app.get('/', (req, res) => {
    res.send("Server Bot Vercel đang chạy ngon lành!");
});
module.exports = app;
