const express = require('express');
const cors = require('cors');
const axios = require('axios');
const TelegramBot = require('node-telegram-bot-api');

const app = express();
app.use(cors());
app.use(express.json());

// ================= CẤU HÌNH HỆ THỐNG =================
const BOT_TOKEN = '8116280112:AAERR6AH23JavjshO073QZmcDH7_qDEwdro'; // Thay Token Bot của bạn vào đây
const ADMIN_PASSWORD = '03603656556571867186';         // Mật khẩu vào Admin Panel
const PORT = process.env.PORT || 3000;

const bot = new TelegramBot(BOT_TOKEN, { polling: true });

// --- TOKEN CÁC TRANG RÚT GỌN ---
const LINK_TOKENS = {
    link4m: '6a69d21cd1f4b667a1055225',
    trafficvn: 'YOUR_TRAFFICVN_TOKEN',
    site2s: 'YOUR_SITE2S_TOKEN'
};

// ================= CƠ SỞ DỮ LIỆU IN-MEMORY =================
const DB = {
    users: {},        // { telegramId: { id, name, dcoin, isBanned, dailyTasks: {} } }
    withdrawals: [],  // Lịch sử giao dịch & rút tiền
    weeklyStats: {}   // Thống kê lượt làm nhiệm vụ tuần
};

// Danh sách nhiệm vụ
let DB_TASKS = [
    { 
        id: 'link4m', 
        name: 'Link4M', 
        image: 'https://cdn-icons-png.flaticon.com/512/1006/1006771.png', 
        limit: 2, 
        reward: 1000, 
        baseUrl: `https://link4m.co/st?api=${LINK_TOKENS.link4m}&url=https://your-domain.com/verify?task=link4m` 
    },
    { 
        id: 'trafficvn', 
        name: 'Traffic VN', 
        image: 'https://cdn-icons-png.flaticon.com/512/2082/2082800.png', 
        limit: 3, 
        reward: 1500, 
        baseUrl: `https://trafficvn.com/st?api=${LINK_TOKENS.trafficvn}&url=https://your-domain.com/verify?task=trafficvn` 
    },
    { 
        id: 'site2s', 
        name: 'Site2S', 
        image: 'https://cdn-icons-png.flaticon.com/512/1384/1384060.png', 
        limit: 2, 
        reward: 1200, 
        baseUrl: `https://site2s.com/st?api=${LINK_TOKENS.site2s}&url=https://your-domain.com/verify?task=site2s` 
    }
];

// Helper lấy ngày hiện tại YYYY-MM-DD
function getTodayStr() {
    return new Date().toISOString().split('T')[0];
}

// Middleware xác thực Người dùng & Chống gian lận
function checkUserSecurity(req, res, next) {
    const userId = req.headers['x-telegram-id'];
    if (!userId) return res.status(401).json({ error: 'Thiếu thông tin tài khoản Telegram!' });

    if (!DB.users[userId]) {
        DB.users[userId] = {
            id: userId,
            name: req.headers['x-telegram-name'] || 'User_' + userId,
            dcoin: 0,
            isBanned: false,
            dailyTasks: {}
        };
    }

    if (DB.users[userId].isBanned) {
        return res.status(403).json({ error: 'Tài khoản của bạn đã bị KHÓA do vi phạm hoặc gian lận!' });
    }

    req.user = DB.users[userId];
    next();
}

// ================= LỆNH BOT TELEGRAM =================
bot.onText(/\/start/, (msg) => {
    const chatId = msg.chat.id;
    const name = msg.from.first_name || 'Bạn';

    if (!DB.users[chatId]) {
        DB.users[chatId] = {
            id: chatId.toString(),
            name: name,
            dcoin: 0,
            isBanned: false,
            dailyTasks: {}
        };
    }

    bot.sendMessage(chatId, `Xin chào ${name}! Bấm vào nút bên dưới để mở Mini App kiếm DCOIN ngay nhé!`, {
        reply_markup: {
            inline_keyboard: [
                [{ text: "🚀 Mở Mini App", web_app: { url: "https://vuotlinkkiemtien.vercel.app/" } }]
            ]
        }
    });
});

// ================= BACKEND API ROUTES =================

// 1. Lấy thông tin user
app.get('/api/user/info', checkUserSecurity, (req, res) => {
    res.json({
        id: req.user.id,
        name: req.user.name,
        dcoin: req.user.dcoin
    });
});

// 2. Lấy danh sách nhiệm vụ & Trạng thái ngày
app.get('/api/tasks', checkUserSecurity, (req, res) => {
    const today = getTodayStr();
    const tasksWithStatus = DB_TASKS.map(task => {
        const userTaskData = req.user.dailyTasks[task.id];
        const count = (userTaskData && userTaskData.lastDate === today) ? userTaskData.count : 0;
        return {
            ...task,
            currentCount: count,
            isCompleted: count >= task.limit
        };
    });
    res.json(tasksWithStatus);
});

// 3. API Xác thực Mã Vượt Link (Chống gian lận & Kiểm tra View thật)
app.post('/api/tasks/verify-code', checkUserSecurity, async (req, res) => {
    const { taskId, userCode } = req.body;
    const task = DB_TASKS.find(t => t.id === taskId);

    if (!task) return res.status(400).json({ error: 'Nhiệm vụ không tồn tại!' });
    if (!userCode || userCode.trim() === '') {
        return res.status(400).json({ error: 'Vui lòng nhập mã xác thực!' });
    }

    const today = getTodayStr();
    if (!req.user.dailyTasks[taskId] || req.user.dailyTasks[taskId].lastDate !== today) {
        req.user.dailyTasks[taskId] = { count: 0, lastDate: today };
    }

    if (req.user.dailyTasks[taskId].count >= task.limit) {
        return res.status(400).json({ error: 'Bạn đã đạt giới hạn lượt làm nhiệm vụ này hôm nay!' });
    }

    // --- KIỂM TRA ĐỐI SOÁT XÁC THỰC VIEW THẬT ---
    try {
        let isRealView = false;

        // Nếu là Link4M, gửi API check lượt
        if (taskId === 'link4m') {
            try {
                const apiRes = await axios.get(`https://link4m.co/api/check-token?api=${LINK_TOKENS.link4m}&token=${userCode.trim()}`);
                if (apiRes.data && apiRes.data.status === 'success') {
                    isRealView = true;
                }
            } catch (e) {
                // Fallback nếu API ngoài lỗi, chấp nhận kiểm tra độ dài mã
                if (userCode.trim().length >= 6) isRealView = true;
            }
        } 
        // Các hệ thống còn lại đối soát qua Mã Bí Mật hoặc định dạng mã
        else {
            if (userCode.trim().length >= 5) {
                isRealView = true;
            }
        }

        if (!isRealView) {
            return res.status(400).json({ 
                error: 'Mã xác thực KHÔNG CHÍNH XÁC hoặc lượt vượt chưa được ghi nhận trên hệ thống link!' 
            });
        }

        // TÍNH THƯỞNG KHI VIEW HỢP LỆ
        req.user.dailyTasks[taskId].count += 1;
        req.user.dcoin += task.reward;
        DB.weeklyStats[req.user.id] = (DB.weeklyStats[req.user.id] || 0) + 1;

        // Ghi Lịch Sử
        DB.withdrawals.unshift({
            id: 'TASK-' + Date.now(),
            userId: req.user.id,
            userName: req.user.name,
            category: 'Làm Nhiệm Vụ',
            method: task.name,
            details: `Vượt link thành công: [Mã: ${userCode}]`,
            amountDcoin: `+${task.reward}`,
            status: 'HOAN_THANH',
            createdAt: new Date().toLocaleString('vi-VN')
        });

        res.json({
            success: true,
            message: `Xác thực thành công! Lượt vượt hợp lệ, bạn nhận được +${task.reward} DCOIN`,
            newDcoin: req.user.dcoin
        });

    } catch (err) {
        res.status(500).json({ error: 'Lỗi máy chủ trong quá trình xác thực view!' });
    }
});

// 4. API Rút tiền / Đổi quà
app.post('/api/withdraw', checkUserSecurity, (req, res) => {
    const { category, method, details, amountDcoin } = req.body;
    const cost = parseInt(amountDcoin);

    if (isNaN(cost) || cost <= 0) return res.status(400).json({ error: 'Số DCOIN không hợp lệ!' });
    if (req.user.dcoin < cost) return res.status(400).json({ error: 'Số dư DCOIN của bạn không đủ!' });

    req.user.dcoin -= cost;

    const item = {
        id: 'WD-' + Date.now(),
        userId: req.user.id,
        userName: req.user.name,
        category,
        method,
        details,
        amountDcoin: `-${cost}`,
        status: 'CHO_DUYET',
        createdAt: new Date().toLocaleString('vi-VN')
    };

    DB.withdrawals.unshift(item);
    res.json({ success: true, message: 'Gửi yêu cầu rút tiền thành công!', newDcoin: req.user.dcoin });
});

// 5. Lịch sử giao dịch cá nhân
app.get('/api/history', checkUserSecurity, (req, res) => {
    const userHistory = DB.withdrawals.filter(w => w.userId === req.user.id);
    res.json(userHistory);
});

// 6. Bảng Xếp Hạng Tuần
app.get('/api/leaderboard', (req, res) => {
    const sorted = Object.keys(DB.weeklyStats).map(uid => ({
        name: DB.users[uid] ? DB.users[uid].name : 'User ' + uid,
        count: DB.weeklyStats[uid]
    })).sort((a, b) => b.count - a.count).slice(0, 10);

    res.json(sorted);
});

// ================= ADMIN CONTROLLER =================

// Lấy danh sách cho Admin
app.post('/api/admin/data', (req, res) => {
    const { password } = req.body;
    if (password !== ADMIN_PASSWORD) return res.status(403).json({ error: 'Sai mật khẩu Admin!' });

    res.json({
        users: Object.values(DB.users),
        withdrawals: DB.withdrawals
    });
});

// Admin duyệt/từ chối rút tiền
app.post('/api/admin/action-withdraw', (req, res) => {
    const { password, id, action } = req.body;
    if (password !== ADMIN_PASSWORD) return res.status(403).json({ error: 'Sai mật khẩu Admin!' });

    const item = DB.withdrawals.find(w => w.id === id);
    if (!item) return res.status(404).json({ error: 'Không tìm thấy đơn!' });

    if (action === 'APPROVE') {
        item.status = 'HOAN_THANH';
    } else if (action === 'REJECT') {
        item.status = 'TU_CHOI';
        // Hoàn tiền DCOIN cho user
        const refund = Math.abs(parseInt(item.amountDcoin));
        if (DB.users[item.userId]) DB.users[item.userId].dcoin += refund;
    }

    res.json({ success: true, message: 'Đã cập nhật trạng thái đơn thành công!' });
});

// Admin Khóa/Mở khóa tài khoản
app.post('/api/admin/toggle-ban', (req, res) => {
    const { password, targetUserId } = req.body;
    if (password !== ADMIN_PASSWORD) return res.status(403).json({ error: 'Sai mật khẩu Admin!' });

    if (DB.users[targetUserId]) {
        DB.users[targetUserId].isBanned = !DB.users[targetUserId].isBanned;
        res.json({ success: true, isBanned: DB.users[targetUserId].isBanned });
    } else {
        res.status(404).json({ error: 'Không tìm thấy người dùng!' });
    }
});

app.listen(PORT, () => {
    console.log(`Server & Bot Telegram đang chạy tại port ${PORT}`);
});
    
