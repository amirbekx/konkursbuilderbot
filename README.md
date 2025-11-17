# Telegram Bot Builder

Telegram orqali konkurs botlari yaratish va boshqarish tizimi.

## Xususiyatlari

### 🚀 **Asosiy funksiyalar:**
- 🤖 **Bot yaratish**: Foydalanuvchilar o'z konkurs botlarini yarata oladi
- 🏆 **Konkurs boshqaruvi**: Foto/video konkurslar o'tkazish
- 👥 **Ishtirokchilar boshqaruvi**: Konkurs ishtirokchilarini kuzatish
- 📊 **Admin panel**: To'liq tizim boshqaruvi
- 📈 **Statistika**: Botlar va konkurslar statistikasi
- 📥 **Excel export**: Ishtirokchilar ro'yxatini Excel formatda yuklab olish
- 📢 **Majburiy obuna**: Botdan foydalanish uchun kanallarga obuna bo'lish majburiyati
- 🔊 **Xabar yuborish**: Barcha foydalanuvchilarga xabar yuborish
- 🏅 **G'oliblarni aniqlash**: Konkurs g'oliblarini tanlash va e'lon qilish
- ⚙️ **Bot boshqaruvi**: Botlarni to'liq tahrirlash va sozlash
- 📱 **Telefon raqami**: Foydalanuvchilardan avtomatik telefon raqami so'rash

### 🚀 **Advanced Admin Panel:**
- 📊 **Analytics Dashboard**: Batafsil statistika va trends
- 👥 **User Management**: Foydalanuvchilarni boshqarish (ban/unban, admin qo'shish)
- 💾 **Backup & Restore**: Ma'lumotlarni saqlash va tiklash
- 📋 **System Logs**: Tizim loglari va monitoring
- 🎯 **Performance Monitor**: Real-time performance ko'rsatkichlari
- 🔧 **Bot Configuration**: Ilg'or bot sozlamalari
- ⚡ **Quick Actions**: Tezkor amallar va ta'mirlash
- 🛡️ **Security Center**: Xavfsizlik va himoya sozlamalari

## O'rnatish

1. **Repository ni klonlash**:
```bash
git clone <repository-url>
cd konkursbot
```

2. **Virtual environment yaratish**:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# yoki
venv\Scripts\activate  # Windows
```

3. **Kutubxonalarni o'rnatish**:
```bash
pip install -r requirements.txt
```

4. **Environment sozlamalari**:
- `.env.example` faylini `.env` ga nusxalang
- Kerakli qiymatlarni kiriting:

```bash
cp .env.example .env
```

`.env` faylida quyidagilarni to'ldiring:
```
MAIN_BOT_TOKEN=your_bot_token_here
ADMIN_USER_IDS=your_telegram_id_here
```

## Ishga tushirish

```bash
python main.py
```

## Foydalanish

### Asosiy bot buyruqlari:
- `/start` - Botni boshlash
- `/help` - Yordam
- `/create_bot` - Yangi konkurs boti yaratish
- `/my_bots` - Mening botlarim
- `/admin` - Admin panel (faqat adminlar uchun)

### Konkurs boti yaratish:
1. `/create_bot` buyrug'ini bosing
2. @BotFather dan bot yarating
3. Bot tokenini yuboring
4. Bot nomi va tavsifini kiriting
5. Botingiz tayyor!

### Konkurs boti yaratish:
1. Yaratgan botingizga o'ting
2. `/admin` buyrug'ini bosing
3. "➕ Yangi konkurs" tugmasini bosing
4. Konkurs ma'lumotlarini kiriting

### Advanced Admin Panel ishlatish:
1. Konkurs botingizda `/admin` buyrug'ini bosing
2. "🚀 Advanced Panel" tugmasini tanlang
3. Kerakli bo'limni tanlang:
   - **📊 Analytics** - Batafsil hisobotlar va trendlar
   - **👥 User Management** - Foydalanuvchilar boshqaruvi
   - **💾 Backup & Restore** - Ma'lumotlar zahirasi
   - **📋 System Logs** - Tizim monitoring
   - **🎯 Performance** - Ishlash ko'rsatkichlari
   - **🔧 Configuration** - Bot sozlamalari
   - **⚡ Quick Actions** - Tezkor amallar
   - **🛡️ Security Center** - Xavfsizlik markazi

## Loyiha tuzilishi

```
konkursbot/
├── main.py                  # Asosiy bot
├── config.py                # Konfiguratsiya
├── database.py              # Ma'lumotlar bazasi
├── bot_factory.py           # Bot yaratish moduli
├── admin_panel.py           # Admin panel
├── contest_manager.py       # Konkurs boshqaruvi
├── excel_exporter.py        # Excel export funksiyalari
├── subscription_manager.py  # Majburiy obuna boshqaruvi
├── broadcast_manager.py     # Xabar yuborish tizimi
├── requirements.txt         # Python kutubxonalar
├── .env.example            # Environment o'zgaruvchilar namunasi
└── README.md               # Bu fayl
```

## Xususiyatlar

### Bot Builder
- Foydalanuvchi uchun maksimal 3 ta bot
- Bot tokenini tekshirish
- Avtomatik bot ishga tushirish
- Bot sozlamalarini tahrirlash

### Konkurs tizimi
- Foto/video konkurslar
- Ishtirokchilar ro'yxati
- Avtomatik vaqt boshqaruvi
- G'oliblarni aniqlash va e'lon qilish
- Natijalarni Excel formatda export qilish

### Majburiy obuna tizimi
- Kanallarga obuna bo'lishni majburiy qilish
- Obunani avtomatik tekshirish
- Obuna talab qilish interfeysi

### Telefon raqami tizimi
- Botdan foydalanish uchun telefon raqami so'rash
- Xavfsiz telefon raqami saqlash
- Excel export da telefon raqamlarini ko'rsatish
- Admin tomonidan yoqish/o'chirish imkoni

### Xabar yuborish tizimi
- Barcha foydalanuvchilarga xabar yuborish
- Foto, video, matn xabarlar
- Xabar yuborish statistikasi
- Konkurs e'lonlari avtomatik yuborish

### Admin panel
- Tizim statistikasi
- Barcha botlar va konkurslar
- Foydalanuvchilar boshqaruvi
- Tizim sozlamalari
- Excel ma'lumotlar export

## Texnik talablar

- Python 3.8+
- python-telegram-bot 20.7
- SQLite (ma'lumotlar bazasi)

## Xavfsizlik

- Bot tokenlar xavfsiz saqlanadi
- Admin huquqlari tekshiriladi
- Ma'lumotlar bazasi strukturasi himoyalangan

## Rivojlantirish

Yangi xususiyatlar qo'shish uchun:

1. `database.py` da kerakli jadvallar yarating
2. `contest_manager.py` da yangi konkurs turlari qo'shing
3. `admin_panel.py` da yangi admin funksiyalar qo'shing

## Yordam

Savollar yoki muammolar bo'lsa:
- Issue yarating
- Telegram orqali admin bilan bog'laning

## Litsenziya

MIT License