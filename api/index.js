const express = require('express');
const cors = require('cors');
const app = express();

app.use(cors({ origin: '*' }));
app.use(express.json());

const BOT_TOKEN = "8116280112:AAERR6AH23JavjshO073QZmcDH7_qDEwdro"; // Token Telegram của bạn
const ADMIN_ID = "8914123780";
const VERCEL_DOMAIN = "https://vuotlinkkiemtien.vercel.app";

// Database tạm lưu trên RAM
const db = {
    users: {
        "8914123780": { id: "8914123780", name: "DA ⚔ PRO", dcoin: 1000000000, isBanned: 0, isAdmin: true }
    },
    daily_tasks: {}
};

// Danh sách Nhiệm Vụ Mẫu
const DB_TASKS = [
    { id: "task1", title: "Vượt link Nhiệm vụ 1 (Link4M)", reward: 1000, limit: 3, link: "https://link4m.co/api-shorten/v2?api=6a69d21cd1f4b667a1055225&url=yourdestinationlink.com" },
    { id: "task2", title: "Vượt link Nhiệm vụ 2 (TrafficVN)", reward: 1200, limit: 2, link: "https://google.com" }
];

// Security Middleware
function checkUserSecurity(req, res, next) {
    const userId = req.headers['x-telegram-id'];
    const userName = req.headers['x-telegram-name'] || 'User_' + userId;
    
    if (!userId) return res.status(401).json({ error: 'Chưa có thông tin Telegram!' });

    const strUserId = String(userId);
    if (!db.users[strUserId]) {
        db.users[strUserId] = { 
            id: strUserId, 
            name: decodeURIComponent(userName), 
            dcoin: 0, 
            isBanned: 0, 
            isAdmin: (strUserId === ADMIN_ID) 
        };
    }
    
    req.user = db.users[strUserId];
    next();
}

// Trang chủ Check
app.get('/', (req, res) => {
    res.send("Server Bot Vercel đang chạy ngon lành!");
});

// Telegram Webhook API
app.post('/api/webhook', async (req, res) => {
    res.status(200).send('OK');
    try {
        const update = req.body;
        if (update && update.message && update.message.text === '/start') {
            const chatId = update.message.chat.id;
            await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: chatId,
                    text: "👋 Chào mừng bạn đến với Mini App!\nBấm nút bên dưới để mở ứng dụng:",
                    reply_markup: {
                        inline_keyboard: [[
                            { 
                                text: "🚀 Mở Mini App", 
                                web_app: { url: "https://ducanhbuiok-svg.github.io/vuotlinkkiemtien" } 
                            }
                        ]]
                    }
                })
            });
        }
    } catch (e) {
        console.error("Lỗi Webhook:", e);
    }
});

// User API
app.get('/api/user/info', checkUserSecurity, (req, res) => {
    res.json(req.user);
});

// Tasks API
app.get('/api/tasks', checkUserSecurity, (req, res) => {
    const tasksWithStatus = DB_TASKS.map(task => ({
        ...task,
        currentCount: 0
    }));
    res.json(tasksWithStatus);
});

module.exports = app;
