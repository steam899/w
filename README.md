# 🐺🎲 Wolf Dice Bot

Bot automasi untuk **WolfBet Dice** dengan strategi **Martingale**.  
Dibina menggunakan **Python** + **Rich UI** untuk paparan yang interaktif.

---

## ⚡ Fitur Utama
- 🎨 Paparan konsol dengan **Rich (UI cantik)**
- 📊 Ringkasan sesi (baki awal, baki semasa, profit/loss, runtime)
- 🔁 Strategi **Martingale** automatik
- 🛑 **Stop-loss** & ✅ **Take-profit**
- 🔄 **Auto-restart session** (jika diaktifkan dalam config)

---

## 📂 Struktur Projek
```
WolfDiceBot/
├── bot.py             # Script utama bot
├── config.json        # Fail konfigurasi
├── requirements.txt   # Senarai dependency
└── README.md          # Dokumentasi
```

---

## ⚙️ Configurasi (`config.json`)
Contoh konfigurasi asas:

```json
{
  "access_token": "TOKEN_ANDA",
  "currency": "btc",
  "base_bet": 0.00000001,
  "multiplier": 2.0,
  "max_bet": 0.0001,
  "chance": 49.5,
  "rule_mode": "auto",
  "take_profit": 0.0005,
  "stop_loss": -0.0005,
  "cooldown_sec": 1,
  "debug": true,
  "auto_start": false,
  "auto_start_delay": 5
}
```

---

## 🚀 Cara Menjalankan
1. **Clone repo**
   ```bash
   git clone https://github.com/steam899/w.git
   cd w
   ```

2. **Install dependency**
   ```bash
   pip install -r requirements.txt
   ```

3. **Edit config.json** → letak `access_token` WolfBet anda  

4. **Jalankan bot**
   ```bash
   python bot.py
   ```

---

## 📌 Nota
⚠️ Gunakan bot ini dengan **tanggungjawab**.  
🎯 Sesuai untuk eksperimen, bukan jaminan keuntungan.  

---

✌️ Selamat mencuba & semoga profit!  
