const express = require('express');
const TelegramBot = require('node-telegram-bot-api');
const cors = require('cors');

const app = express();
app.use(express.json());
app.use(cors());

// --- CẤU HÌNH BIẾN MÔI TRƯỜNG ---
const BOT_TOKEN = '8116280112:AAERR6AH23JavjshO073QZmcDH7_qDEwdro';
const ADMIN_PASSWORD = '03603656556571867186'; // Mật khẩu truy cập Admin
const ADMIN_TELEGRAM_ID = '8914123780'; // ID Telegram của bạn
const MINI_APP_URL = 'https://vuotlinkkiemtien.vercel.app/'; // URL Webview Mini App
const ADMIN_TELEGRAM_USERNAME = 'daxprovn'; // Telegram Username để hỗ trợ

const bot = new TelegramBot(BOT_TOKEN, { polling: true });

// --- CƠ SỞ DỮ LIỆU GIẢ LẬP (Lưu vào Memory / Có thể nối MongoDB/SQLite) ---
let DB = {
    users: {}, // { id: { name, avatar, username, dcoin: 0, isBanned: false, banReason: '', dailyTasks: { task_id: { count: 0, lastDate: 'YYYY-MM-DD' } } } }
    tasks: [
        { id: 'link4m', name: 'Link4M Vượt Mã', image: 'https://cdn-icons-png.flaticon.com/512/1006/1006771.png', limit: 2, reward: 1000, link: 'https://link4m.co/example' },
        { id: 'trafficvn', name: 'Traffic VN', image: 'https://cdn-icons-png.flaticon.com/512/2082/2082800.png', limit: 3, reward: 1500, link: 'https://trafficvn.com/example' },
        { id: 'site2s', name: 'Site2S lấy mã', image: 'https://cdn-icons-png.flaticon.com/512/1384/1384060.png', limit: 2, reward: 1200, link: 'https://site2s.com/example' }
    ],
    withdrawals: [], // Danh sách đơn rút tiền / nạp game
    weeklyStats: {}, // Thống kê số link đã vượt trong tuần { userId: count }
    notifications: {} // Thông báo thưởng Admin { userId: { amount, note, unread: true } }
};

// --- TELEGRAM BOT LOGIC ---
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    const opts = {
        reply_markup: {
            inline_keyboard: [
                [
                    { text: '💬 Tham gia Nhóm Chat', url: 'https://t.me/nhomchatdanmmo' },
                    { text: '📢 Kênh Thông Báo', url: 'https://t.me/kenhthongbaodab_roblox' }
                ],
                [
                    { text: '🚀 Mở Mini App', web_app: { url: MINI_APP_URL } }
                ]
            ]
        }
    };
    bot.sendMessage(chatId, `👋 Chào mừng ${msg.from.first_name} đến với Hệ thống Làm Nhiệm Vụ Kiếm DCOIN! Click nút bên dưới để bắt đầu:`, opts);
});

// --- HELPER ANTI-FRAUD & DATE ---
function getTodayStr() {
    return new Date().toISOString().split('T')[0];
}

function checkUserSecurity(req, res, next) {
    const userId = req.headers['x-telegram-id'];
    if (!userId) return res.status(401).json({ error: 'Thiếu ID người dùng!' });
    
    // Tạo user nếu chưa tồn tại
    if (!DB.users[userId]) {
        DB.users[userId] = {
            id: userId,
            name: req.headers['x-telegram-name'] || 'User',
            avatar: req.headers['x-telegram-avatar'] || 'https://i.imgur.com/6VBx3io.png',
            username: req.headers['x-telegram-username'] || 'N/A',
            dcoin: 0,
            isBanned: false,
            banReason: '',
            dailyTasks: {}
        };
    }

    if (DB.users[userId].isBanned) {
        return res.status(403).json({ 
            isBanned: true, 
            banReason: DB.users[userId].banReason || 'Tài khoản vi phạm quy định gian lận.' 
        });
    }
    req.user = DB.users[userId];
    next();
}

// --- API ENDPOINTS ---

// 1. Lấy thông tin user + Dashboard
app.get('/api/user/info', checkUserSecurity, (req, res) => {
    const today = getTodayStr();
    const notification = DB.notifications[req.user.id];
    let pendingNotif = null;
    
    if (notification && notification.unread) {
        pendingNotif = notification;
        DB.notifications[req.user.id].unread = false; // Chỉ hiển thị 1 lần
    }

    res.json({
        user: req.user,
        notification: pendingNotif,
        adminSupportUrl: `https://t.me/${ADMIN_TELEGRAM_USERNAME}`
    });
});

// 2. Lấy danh sách nhiệm vụ + Cập nhật lượt làm trong ngày
app.get('/api/tasks', checkUserSecurity, (req, res) => {
    const today = getTodayStr();
    const tasksData = DB.tasks.map(t => {
        const userTaskData = req.user.dailyTasks[t.id] || { count: 0, lastDate: today };
        let count = userTaskData.count;
        if (userTaskData.lastDate !== today) {
            count = 0; // Tự động reset sang ngày mới
        }
        return {
            ...t,
            completedToday: count,
            isLocked: count >= t.limit
        };
    });
    res.json(tasksData);
});

// 3. Hoàn tất vượt link (Chống Hack: Yêu cầu mã xác thực / Token từ Server)
app.post('/api/tasks/complete', checkUserSecurity, (req, res) => {
    const { taskId } = req.body;
    const task = DB.tasks.find(t => t.id === taskId);
    if (!task) return res.status(400).json({ error: 'Nhiệm vụ không tồn tại!' });

    const today = getTodayStr();
    if (!req.user.dailyTasks[taskId] || req.user.dailyTasks[taskId].lastDate !== today) {
        req.user.dailyTasks[taskId] = { count: 0, lastDate: today };
    }

    if (req.user.dailyTasks[taskId].count >= task.limit) {
        return res.status(400).json({ error: 'Bạn đã vượt quá giới hạn nhiệm vụ này hôm nay!' });
    }

    // Cộng thưởng & Cập nhật số liệu
    req.user.dailyTasks[taskId].count += 1;
    req.user.dcoin += task.reward;
    DB.weeklyStats[req.user.id] = (DB.weeklyStats[req.user.id] || 0) + 1;

    // Lưu Lịch sử
    DB.withdrawals.push({
        id: 'TASK-' + Date.now(),
        userId: req.user.id,
        userName: req.user.name,
        type: 'Làm Nhiệm Vụ',
        details: `Vượt link thành công: ${task.name}`,
        amount: `+${task.reward} DCOIN`,
        status: 'HOAN_THANH',
        createdAt: new Date().toLocaleString('vi-VN')
    });

    res.json({ 
        success: true, 
        dcoin: req.user.dcoin, 
        count: req.user.dailyTasks[taskId].count,
        limit: task.limit 
    });
});

// 4. Bảng Xếp Hạng Tuần (Thống kê thực tế)
app.get('/api/leaderboard', checkUserSecurity, (req, res) => {
    const list = Object.keys(DB.weeklyStats).map(uid => ({
        id: uid,
        name: DB.users[uid]?.name || 'N/A',
        avatar: DB.users[uid]?.avatar || '',
        count: DB.weeklyStats[uid]
    })).sort((a, b) => b.count - a.count).slice(0, 50);

    res.json(list);
});

// 5. Yêu cầu Rút tiền / Nạp Game
app.post('/api/withdraw', checkUserSecurity, (req, res) => {
    const { category, method, details, amountDcoin } = req.body;

    // Kiểm tra đầu vào cực kỳ chặt chẽ
    if (!method || !details || !amountDcoin || amountDcoin <= 0) {
        return res.status(400).json({ error: 'Thông tin không chính xác hoặc thiếu! Vui lòng điền lại đầy đủ.' });
    }

    if (req.user.dcoin < amountDcoin) {
        return res.status(400).json({ error: 'Số DCOIN của bạn không đủ để thực hiện giao dịch này!' });
    }

    // Trừ tiền tạm thời
    req.user.dcoin -= amountDcoin;

    const newOrder = {
        id: 'WD-' + Date.now(),
        userId: req.user.id,
        userName: req.user.name,
        userAvatar: req.user.avatar,
        telegramUsername: req.user.username,
        category: category, // 'Rút Tiền' hoặc 'Nạp Game'
        method: method,
        details: details, // Chuỗi thông tin nhập chi tiết
        amountDcoin: amountDcoin,
        status: 'CHO_DUYET', // CHO_DUYET, HOAN_THANH, DA_DUYET, TU_CHUOI, THU_HOI
        createdAt: new Date().toLocaleString('vi-VN')
    };

    DB.withdrawals.unshift(newOrder);
    res.json({ success: true, message: 'Đơn của bạn đã gửi thành công và đang chờ Admin duyệt!' });
});

// 6. Lịch sử giao dịch cá nhân
app.get('/api/history', checkUserSecurity, (req, res) => {
    const myHistory = DB.withdrawals.filter(w => w.userId === req.user.id);
    res.json(myHistory);
});

// --- ADMIN API (BẢO MẬT 2 LỚP) ---

// Xác thực password Admin
app.post('/api/admin/auth', (req, res) => {
    const { password } = req.body;
    if (password === ADMIN_PASSWORD) {
        return res.json({ success: true, token: 'ADMIN_SECRET_TOKEN_VALID' });
    }
    res.status(401).json({ error: 'Mật khẩu Admin không chính xác!' });
});

// Lấy toàn bộ đơn rút tiền / nạp game
app.get('/api/admin/orders', (req, res) => {
    if (req.headers['x-admin-token'] !== 'ADMIN_SECRET_TOKEN_VALID') {
        return res.status(403).json({ error: 'Từ chối truy cập!' });
    }
    res.json(DB.withdrawals);
});

// Xử lý đơn (Hoàn thành / Phê duyệt / Trả DCOIN / Thu DCOIN Gian lận)
app.post('/api/admin/process-order', (req, res) => {
    if (req.headers['x-admin-token'] !== 'ADMIN_SECRET_TOKEN_VALID') return res.status(403).end();
    const { orderId, action } = req.body; // action: 'APPROVE', 'COMPLETE', 'REFUND', 'PENALTY'

    const order = DB.withdrawals.find(o => o.id === orderId);
    if (!order) return res.status(404).json({ error: 'Đơn không tồn tại' });

    const targetUser = DB.users[order.userId];

    if (action === 'APPROVE') {
        order.status = 'DA_DUYET';
    } else if (action === 'COMPLETE') {
        order.status = 'HOAN_THANH';
    } else if (action === 'REFUND') {
        order.status = 'HOAN_TRA';
        if (targetUser) targetUser.dcoin += order.amountDcoin; // Hoàn lại DCOIN
    } else if (action === 'PENALTY') {
        order.status = 'GIAN_LAN_THU_HOI';
        if (targetUser) {
            targetUser.dcoin = 0; // Thu hồi sạch DCOIN
            targetUser.isBanned = true; // Khóa luôn tài khoản
            targetUser.banReason = 'Phát hiện hành vi gian lận đơn nạp/rút!';
        }
    }
    res.json({ success: true });
});

// Tặng DCOIN vô hạn cho Admin
app.post('/api/admin/gift-dcoin', (req, res) => {
    if (req.headers['x-admin-token'] !== 'ADMIN_SECRET_TOKEN_VALID') return res.status(403).end();
    const { targetUserId, amount, note } = req.body;

    if (!DB.users[targetUserId]) return res.status(404).json({ error: 'Không tìm thấy ID người dùng!' });

    DB.users[targetUserId].dcoin += parseInt(amount);
    
    // Tạo thông báo hiển thị 1 lần duy nhất cho User
    DB.notifications[targetUserId] = {
        amount: amount,
        note: note,
        unread: true
    };

    res.json({ success: true, message: `Đã tặng ${amount} DCOIN cho Telegram ID: ${targetUserId}` });
});

// Khóa / Mở khóa tài khoản
app.post('/api/admin/toggle-ban', (req, res) => {
    if (req.headers['x-admin-token'] !== 'ADMIN_SECRET_TOKEN_VALID') return res.status(403).end();
    const { targetUserId, isBanned, note } = req.body;

    if (!DB.users[targetUserId]) return res.status(404).json({ error: 'Không tìm thấy người dùng này!' });

    DB.users[targetUserId].isBanned = isBanned;
    DB.users[targetUserId].banReason = note || 'Vi phạm điều khoản dịch vụ.';

    res.json({ success: true, message: isBanned ? 'Đã khóa tài khoản!' : 'Đã mở khóa tài khoản!' });
});

app.listen(3000, () => console.log('Server Telegram Mini App đang chạy tại port 3000'));
                                        
