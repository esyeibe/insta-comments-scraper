# 🚀 insta-comments-scraper — Instagram Comment & Reply Scraper

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/esyeibe/insta-comments-scraper?style=social)](https://github.com/esyeibe/insta-comments-scraper/stargazers)

Tool Python asinkron untuk mengambil (scrape) **komentar utama dan seluruh balasan berantai (nested replies)** dari Instagram Reel, Postingan, maupun IGTV. Hasil scraping otomatis tersimpan rapi dalam format **CSV (bisa langsung dibuka di Excel), JSON, dan TXT**.

> [!NOTE]
> **Kredit & Acknowledgement**:
> Proyek ini merupakan pengembangan dan penyempurnaan (*improved version*) dari repository [kaifcodec/InstaScrape](https://github.com/kaifcodec/InstaScrape), dengan penambahan dukungan balasan komentar (*threaded replies*), perbaikan sesi otomatis (*self-healing auth*), rate limiter anti-ban, dan ekspor multi-format.

---

## ✨ Fitur Utama

- 💬 **Komentar & Balasan**: Mengambil komentar utama beserta seluruh balasan bersarang (*nested replies*).
- 📊 **Ekspor 3 Format**: Otomatis menyimpan ke file **CSV** (siap buka di Excel tanpa format berantakan), **JSON**, dan **TXT**.
- 🛡️ **Aman & Anti-Ban**: Menggunakan cookie browser (`sessionid`) dan pembatas kecepatan (rate limit) agar terhindar dari checkpoint/blokir.
- 💾 **Sesi Otomatis**: Cukup konfigurasi cookie sekali, sesi otomatis tersimpan untuk pemakaian seterusnya.

---

## 🔄 Alur Kerja Singkat

```text
[1. Input Link] ──► [2. Cek Sesi Cookie] ──► [3. Unduh Komentar & Balasan] ──► [4. Simpan CSV, JSON, TXT]
```

1. **Input Link**: Masukkan URL postingan atau Reel Instagram.
2. **Validasi Sesi**: Script otomatis menggunakan sesi cookie yang sudah tersimpan.
3. **Proses Unduh**: Komentar dan balasan diambil secara bertahap dan aman.
4. **Selesai**: Data langsung tersimpan rapi di dalam folder `download_comments/`.

---

## 🛠️ Panduan Instalasi (Mudah & Cepat)

Ikuti langkah-langkah mudah di bawah ini untuk menjalankan project:

### 1. Clone Repository
Buka terminal / CMD Anda, lalu jalankan:
```bash
git clone https://github.com/esyeibe/insta-comments-scraper.git
cd insta-comments-scraper
```

### 2. Buat & Aktifkan Virtual Environment (`venv`)
Sangat disarankan menggunakan `venv` agar package tidak tercampur dengan Python sistem:

- **Pengguna Linux / macOS:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

- **Pengguna Windows (PowerShell / Command Prompt):**
  ```powershell
  # Buat venv:
  python -m venv venv

  # Aktifkan di PowerShell:
  .\venv\Scripts\Activate.ps1

  # Atau jika menggunakan Command Prompt (CMD):
  .\venv\Scripts\activate.bat
  ```
*(Tanda `(venv)` akan muncul di awal baris terminal Anda jika sudah aktif).*

### 3. Install Dependensi
```bash
pip install -r requirements.txt
```

### 4. Siapkan File Konfigurasi (`.env`)
Salin file template `.env.example` menjadi `.env`:
```bash
cp .env.example .env
```
*(Di Windows jika perintah `cp` tidak bisa, gunakan: `copy .env.example .env`).*

---

## 🔑 Cara Mengambil Cookie (`sessionid`) Browser

Cara paling aman menggunakan script ini adalah dengan cookie `sessionid` dari browser Anda:

1. Buka [instagram.com](https://www.instagram.com) di browser dan pastikan sudah login ke akun Anda.
2. Tekan tombol **`F12`** (atau klik kanan ➔ pilih **Inspect** / Periksa).
3. Masuk ke tab **Application** (Chrome/Edge) atau **Storage** (Firefox).
4. Di panel kiri, klik **Cookies** ➔ klik `https://www.instagram.com`.
5. Cari baris bernama **`sessionid`**, lalu klik dua kali pada kolom **Value** dan **Salin (Copy)** nilainya.
6. Buka file `.env` di project Anda, lalu tempelkan nilainya:
   ```env
   IG_SESSIONID=tempel_sessionid_disini
   ```

*(Opsional: Anda juga bisa mengatur kecepatan `DEFAULT_RPS=1.0` di file `.env`).*

---

## ▶️ Cara Menjalankan

### Cara 1: Mode Interaktif (Paling Santai)
Cukup jalankan:
```bash
python main.py
```
1. Masukkan URL postingan atau Reel Instagram saat diminta (contoh: `https://www.instagram.com/reel/C-xyz123/`).
2. Tekan **Enter** untuk menggunakan kecepatan default (1.0 request/detik).
3. Script akan otomatis berjalan dan menampilkan progress bar scraping.

### Cara 2: Langsung dengan Argumen URL
Anda juga bisa langsung menyertakan link URL pada perintah:
```bash
python main.py https://www.instagram.com/reel/DctF_wKTvOm/
```

---

## 📁 Hasil Output

Setiap proses scraping akan membuat folder baru di dalam `download_comments/`:

```text
download_comments/{SHORTCODE}_{TANGGAL_WAKTU}/
  ├── {SHORTCODE}_comments.csv   # Tabel rapi, bisa langsung klik 2x dibuka di Excel
  ├── {SHORTCODE}_comments.json  # Format JSON lengkap untuk developer / data scientist
  └── {SHORTCODE}_comments.txt   # Teks baca rapi dengan simbol balasan (↳)
```

---

## 💡 Tips Aman
- Gunakan nilai **RPS 0.5 – 1.5** agar akun aman dari batasan limit Instagram (HTTP 429).
- Jika ingin scrape ribuan data, disarankan menggunakan akun sekunder (*second account*).
- Jika sesi habis di tengah jalan, script otomatis meminta Anda memasukkan cookie baru dan melanjutkan proses tanpa mengulang dari awal (*self-healing*).

---

## ⚠️ Lisensi & Penafian

Proyek ini dibuat untuk tujuan pembelajaran, analisis data, dan penelitian pribadi. Harap gunakan secara bijak dan patuhi ketentuan layanan Instagram.

Lisensi di bawah [MIT License](LICENSE).
