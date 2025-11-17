# 🚀 Bot Deployment Guide

## ✅ Hozirgi holat

Bot to'liq tekshirilgan va serverga joylashga tayyor!

### 📦 Asosiy fayllar (10 ta):
1. ✅ `main.py` - Asosiy bot (xatolarsiz)
2. ✅ `config.py` - Konfiguratsiya
3. ✅ `database.py` - Database boshqaruv (referrer_id tuzatilgan)
4. ✅ `admin_panel.py` - Admin panel
5. ✅ `contest_manager.py` - Konkurs bot logikasi
6. ✅ `bot_factory.py` - Bot yaratish
7. ✅ `excel_exporter.py` - Excel eksport (bot_users ishlatadi)
8. ✅ `subscription_manager.py` - Obuna boshqaruv
9. ✅ `broadcast_manager.py` - Xabar yuborish
10. ✅ `admin_welcome_handler.py` - Admin salomlash

### ✅ So'nggi tuzatishlar:
1. ✅ Database query - `referrer_user_id` → `referrer_id`
2. ✅ Excel export - contest_participants → bot_users
3. ✅ Phone collection - har doim so'raladi
4. ✅ Manual phone input - qo'lda kiritish qo'shildi
5. ✅ Subscription check - alert xabari yaxshilandi
6. ✅ Admin panel - Qo'llanma tugmasi tuzatildi
7. ✅ Referral settings - single toggle button
8. ✅ Callback query logging - debugging uchun
9. ✅ 21 ta keraksiz test/debug fayl o'chirildi

## 🔧 Serverga joylash

> **Yangi:** GitHub orqali Railway deploy qilish uchun quyidagi bo'limni bajaring.

### 🔄 GitHub'ga push qilish

1. GitHub’da bo‘sh repozitoriya yarating (masalan, `konkursbot`).
2. Lokal repozitoriyada remote qo‘shing va birinchi pushni qiling:

```bash
git remote add origin https://github.com/<username>/<repository>.git
git branch -M main
git push -u origin main
```

> `<username>` va `<repository>` o‘rniga o‘z hisobingizdagi qiymatlarni qo‘ying.

### ☁️ Railway’da deploy qilish

1. [Railway.app](https://railway.app/) ga kiring va "New Project" → "Deploy from GitHub repo" ni tanlang.
2. Yangi GitHub repozitoriyani ulab, Python uchun "Service" yarating.
3. Railway avtomatik ravishda `Procfile` (`worker: python main.py`) ni o‘qiydi. Agar kerak bo‘lsa, service Settings > Start Command bo‘limida `python main.py` ni qo‘lda yozing.
4. "Variables" bo‘limida `MAIN_BOT_TOKEN`, `ADMIN_USER_IDS`, `DATABASE_URL=sqlite:///bot_builder.db`, `LOG_LEVEL` va boshqa kerakli muhit o‘zgaruvchilarini kiriting.
5. `PYTHON_VERSION` environment o‘zgaruvchisini `3.11` ga sozlang (agar Railway avtomatik aniqlamasa).
6. Deploy tugaganidan so‘ng service loglarini tekshirib, bot muvaffaqiyatli ishga tushganini tasdiqlang.

> Railway'da SQLite fayli persistent storage talab etsa, "Add Volume" orqali `bot_builder.db` saqlash uchun katalogni (`/app/data` kabi) ulang va `DATABASE_URL` ni mos ravishda yangilang (`sqlite:////app/data/bot_builder.db`).

### 1. VPS/Server tayyorlash

```bash
# Server yangilash
sudo apt update && sudo apt upgrade -y

# Python o'rnatish
sudo apt install python3.11 python3.11-venv python3-pip -y

# Git o'rnatish
sudo apt install git -y
```

### 2. Proyektni yuklash

```bash
# Ish papkasiga o'tish
cd /home/your_user/

# Proyektni klonlash yoki yuklash
mkdir eskikonkurs
cd eskikonkurs

# Fayllarni yuklash (FTP/SCP orqali)
```

### 3. Virtual environment yaratish

```bash
# Virtual environment
python3.11 -m venv .venv

# Aktivlashtirish
source .venv/bin/activate

# Kutubxonalarni o'rnatish
pip install -r requirements.txt
```

### 4. Environment sozlamalari

```bash
# .env faylini yaratish
nano .env
```

Quyidagilarni kiriting:
```env
MAIN_BOT_TOKEN=8342648099:AAEo40wf7e5R8DIWwPolR-3MfhHWDg22Wyg
ADMIN_USER_IDS=5425876649,8377725356
```

### 5. Systemd service yaratish

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

Quyidagi konfiguratsiyani kiriting:
```ini
[Unit]
Description=Telegram Bot Builder
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/home/your_user/eskikonkurs
Environment="PATH=/home/your_user/eskikonkurs/.venv/bin"
ExecStart=/home/your_user/eskikonkurs/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 6. Service ni ishga tushirish

```bash
# Service ni yoqish
sudo systemctl enable telegram-bot.service

# Service ni boshlash
sudo systemctl start telegram-bot.service

# Statusni tekshirish
sudo systemctl status telegram-bot.service

# Loglarni ko'rish
sudo journalctl -u telegram-bot.service -f
```

## 📊 Monitoring

### Loglarni kuzatish
```bash
# Real-time logs
sudo journalctl -u telegram-bot.service -f

# Oxirgi 100 ta log
sudo journalctl -u telegram-bot.service -n 100

# Bugun loqlari
sudo journalctl -u telegram-bot.service --since today
```

### Bot statusini tekshirish
```bash
# Service holati
sudo systemctl status telegram-bot.service

# Service ni qayta ishga tushirish
sudo systemctl restart telegram-bot.service

# Service ni to'xtatish
sudo systemctl stop telegram-bot.service
```

## 🔒 Xavfsizlik

### 1. Firewall sozlash
```bash
# UFW o'rnatish
sudo apt install ufw -y

# SSH ruxsat berish
sudo ufw allow 22/tcp

# UFW yoqish
sudo ufw enable

# Statusni tekshirish
sudo ufw status
```

### 2. Fayllar ruxsatini o'rnatish
```bash
# .env faylini himoyalash
chmod 600 .env

# Database faylini himoyalash
chmod 600 bot_builder.db
```

### 3. Backup sozlash
```bash
# Backup skripti yaratish
nano backup.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/your_user/backups"
SOURCE_DIR="/home/your_user/eskikonkurs"

mkdir -p $BACKUP_DIR

# Database backup
cp $SOURCE_DIR/bot_builder.db $BACKUP_DIR/bot_builder_$DATE.db

# Excel exports backup
tar -czf $BACKUP_DIR/exports_$DATE.tar.gz -C $SOURCE_DIR exports/

# 7 kundan eski backuplarni o'chirish
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

```bash
# Skriptga ruxsat berish
chmod +x backup.sh

# Cron job qo'shish (har kuni soat 3 da)
crontab -e

# Quyidagini qo'shing:
0 3 * * * /home/your_user/eskikonkurs/backup.sh >> /home/your_user/backup.log 2>&1
```

## 🐛 Troubleshooting

### Bot ishlamayapti
```bash
# Loglarni tekshirish
sudo journalctl -u telegram-bot.service -n 50

# Python processlarni tekshirish
ps aux | grep python

# Service ni qayta ishga tushirish
sudo systemctl restart telegram-bot.service
```

### Database xatoliklari
```bash
# Database integrity tekshirish
sqlite3 bot_builder.db "PRAGMA integrity_check;"

# Database backup dan tiklash
cp backups/bot_builder_YYYYMMDD_HHMMSS.db bot_builder.db
sudo systemctl restart telegram-bot.service
```

### Disk bo'sh joyini tekshirish
```bash
# Disk holati
df -h

# Eng katta fayllarni topish
du -sh * | sort -rh | head -10

# Eski loglarni tozalash
sudo journalctl --vacuum-time=7d
```

## 📈 Performance

### Resource monitoring
```bash
# CPU va RAM
htop

# Disk I/O
iotop

# Bot process statistikasi
ps aux | grep python
```

## 🔄 Yangilash

```bash
# Botni to'xtatish
sudo systemctl stop telegram-bot.service

# Yangi kodlarni yuklash
# (FTP/SCP orqali)

# Database backup
cp bot_builder.db bot_builder_backup_$(date +%Y%m%d).db

# Virtual environment yangilash (agar kerak bo'lsa)
source .venv/bin/activate
pip install -r requirements.txt --upgrade

# Botni qayta ishga tushirish
sudo systemctl start telegram-bot.service

# Loglarni kuzatish
sudo journalctl -u telegram-bot.service -f
```

## ✅ Test checklist

Serverda test qilish:
- [ ] Bot ishga tushdi
- [ ] Main bot /start ishlaydi
- [ ] Yangi bot yaratish ishlaydi
- [ ] Contest bot /start ishlaydi
- [ ] Admin panel ochiladi
- [ ] Excel eksport ishlaydi
- [ ] Telefon raqam so'raydi
- [ ] Obuna check ishlaydi
- [ ] Referral link ishlaydi
- [ ] Broadcast yuborish ishlaydi

## 📞 Support

Muammolar yoki savollar uchun:
- Telegram: Admin
- Logs: `/var/log/syslog` yoki `journalctl`

---

**Bot versiyasi:** 2.0
**Oxirgi yangilanish:** 2025-11-11
**Status:** ✅ Serverga joylashga tayyor
