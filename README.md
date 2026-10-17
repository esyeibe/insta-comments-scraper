# 🚀 InstaScrape — Async Instagram Comment & Threaded Reply Scraper

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/esyeibe/insta-comments-scraper?style=social)](https://github.com/esyeibe/insta-comments-scraper/stargazers)
[![HTTP/2](https://img.shields.io/badge/Network-HTTP%2F2-success.svg)](https://http2.github.io/)
[![Async](https://img.shields.io/badge/AsyncIO-httpx-blueviolet.svg)](https://www.python-httpx.org/)

**InstaScrape** adalah scraper komentar Instagram berbasis Python asinkron (`httpx` + HTTP/2) yang cepat, tangguh, dan kaya fitur. Dirancang untuk mengekstrak seluruh komentar utama (*parent comments*) sekaligus balasan percakapan bersarang (*threaded/nested replies*) dari berbagai jenis konten Instagram (**Reels, Posts, IGTV, Share Links**), dilengkapi sistem autentikasi mandiri (*self-healing session*), manajemen rate limit adaptif, serta ekspor data simultan ke format **CSV (Excel-Ready UTF-8 BOM), JSON bersarang, dan TXT rapi**.

---

## 📑 Daftar Isi

- [✨ Fitur Utama](#-fitur-utama)
- [🏗️ Alur Kerja Sistem (Pipeline)](#️-alur-kerja-sistem-pipeline)
- [📦 Persyaratan Sistem](#-persyaratan-sistem)
- [🛠️ Panduan Instalasi](#️-panduan-instalasi)
- [⚙️ Konfigurasi (`.env`)](#️-konfigurasi-env)
- [🔐 Panduan Autentikasi & Pengambilan Cookie](#-panduan-autentikasi--pengambilan-cookie)
- [▶️ Cara Penggunaan](#️-cara-penggunaan)
  - [1. Mode Interaktif](#1-mode-interaktif)
  - [2. Mode Argumen CLI Langsung](#2-mode-argumen-cli-langsung)
  - [3. Tool Autentikasi Standalone (`login.py`)](#3-tool-autentikasi-standalone-loginpy)
- [📁 Struktur & Contoh Output](#-struktur--contoh-output)
  - [1. File CSV (`.csv`)](#1-file-csv-csv)
  - [2. File JSON (`.json`)](#2-file-json-json)
  - [3. File TXT (`.txt`)](#3-file-txt-txt)
- [🛡️ Anti-Ban & Best Practices Rate Limiting](#️-anti-ban--best-practices-rate-limiting)
- [❓ Solusi Masalah & FAQ](#-solusi-masalah--faq)
- [📂 Struktur File Proyek](#-struktur-file-proyek)
- [⚠️ Penafian (Disclaimer) & Lisensi](#️-penafian-disclaimer--lisensi)

---

## ✨ Fitur Utama

- 🧵 **Threaded Replies Scraping**: Mengekstrak komentar induk (*parent*) beserta seluruh percakapan di dalamnya (*nested replies*) menggunakan GraphQL Child Query Hash (`51fdd02b67508306ad4484ff574a0b62`). Opsi ini dapat diaktifkan atau dinonaktifkan sesuai kebutuhan (`INCLUDE_REPLIES`).
- 🔐 **Metode Autentikasi Fleksibel & Bebas Checkpoint**:
  - **Browser Cookie / `sessionid` (Direkomendasikan)**: Menghindari blokir checkpoint, verifikasi SMS/Email, dan proteksi 2FA Instagram.
  - **Full Cookie Header**: Dukungan langsung menempelkan seluruh header string `Cookie` dari DevTools.
  - **Login Username & Password**: Opsi login otomatis berbasis mobile API (eksperimental).
- 💾 **Session Persistence**: Menyimpan sesi secara aman di `cookie.json` (lengkap dengan timestamp `iat` dan masa kedaluwarsa `overall_expiry`) serta sinkronisasi otomatis ke file [`.env`](file:///.env). Cukup login satu kali untuk penggunaan berkali-kali.
- 🔄 **Self-Healing Authentication (In-Flight Recovery)**: Apabila sesi kedaluwarsa di tengah proses pengambilan komentar (HTTP 301/302 redirect, 401 Unauthorized, atau permintaan checkpoint), scraper tidak akan crash atau kehilangan data. Anda akan dipandu untuk memperbarui cookie secara interaktif dan proses scraping akan **langsung dilanjutkan dari titik terakhir**.
- ⚡ **Asynchronous Engine & HTTP/2**: Dibangun di atas `httpx.AsyncClient` dengan dukungan HTTP/2 multiplexing, keep-alive connection pooling (`max_keepalive_connections=10`, `max_connections=20`), dan timeout adaptif.
- ⏱️ **Rate Limiter Cerdas & Auto-Backoff**: Mengatur ritme request-per-second (RPS) menggunakan token rate limiter. Saat mendeteksi batas Instagram (HTTP 429 *Too Many Requests*), scraper otomatis melakukan jeda bertahap (*exponential backoff retry*) hingga 3 kali percobaan.
- 📊 **Real-time Progress Bar (`tqdm`)**: Menampilkan indikator persentase, kecepatan halaman per detik, estimasi waktu (ETA), dan total komentar yang telah berhasil dihimpun secara dinamis.
- 📁 **Triple Export Terstruktur & Atomik**: Setiap proses menghasilkan folder unik berbasis timestamp (`download_comments/{SHORTCODE}_{YYYYMMDD_HHMMSS}/`) berisi:
  - **CSV**: Berisi 9 kolom data lengkap, berformat **UTF-8 with BOM (`utf-8-sig`)** sehingga dapat langsung dibuka rapi di Microsoft Excel tanpa teks rusak/berantakan.
  - **JSON**: Struktur bersarang (*hierarchical*) lengkap dengan metadata ringkasan dan relasi induk-balasan.
  - **TXT**: Format teks bersih dengan simbol indentasi balasan (`  ↳ `).
  - **Atomic File Writing**: File ditulis ke format `.tmp` terlebih dahulu sebelum diganti secara atomik (`os.replace`) untuk mencegah file korup jika proses dihentikan mendadak.
- 🔗 **Dukungan Format URL Luas**:
  - `https://www.instagram.com/reel/<shortcode>/`
  - `https://www.instagram.com/reels/<shortcode>/`
  - `https://www.instagram.com/p/<shortcode>/` (Feed Post)
  - `https://www.instagram.com/tv/<shortcode>/` (IGTV)
  - `https://www.instagram.com/share/reel/<shortcode>/`
  - Raw shortcode langsung (contoh: `DctF_wKTvOm`).

---

## 🏗️ Alur Kerja Sistem (Pipeline)

```mermaid
flowchart TD
    A[Mulai: Input URL / Shortcode] --> B{Cek Autentikasi}
    B -->|cookie.json Valid| D[Gunakan Sesi Tersimpan]
    B -->|Ada di .env / Config| E[Buat Sesi dari .env]
    B -->|Belum Ada| F[Prompt Interaktif Cookie / Kredensial]
    F -->|Simpan| G[Tulis cookie.json & update .env]
    G --> D
    E --> D

    D --> H[Inisialisasi HTTP/2 AsyncClient & RateLimiter]
    H --> I[GraphQL Query: Ambil Halaman Komentar Parent]
    
    I -->|Error 401 / Sesi Habis| J[Self-Healing: Prompt Update Cookie]
    J -->|Sesi Baru Valid| I
    
    I -->|HTTP 429: Rate Limit| K[Backoff Sleep: 5s x Tries]
    K --> I

    I --> L{INCLUDE_REPLIES == True?}
    L -->|Ya| M[GraphQL Child Query: Fetch edge_threaded_comments]
    L -->|Tidak| N[Lewati Balasan]
    M --> O[Susun Struktur Hierarkis Komentar]
    N --> O

    O --> P{Ada Next Page & Cursor?}
    P -->|Ya| Q[Update tqdm Progress Bar] --> I
    P -->|Tidak| R[Tulis Output Atomik .tmp -> Rename]

    R --> S[📁 Hasil Tersimpan di download_comments/{SHORTCODE}_{TIMESTAMP}/]
    S --> T[Selesai]
```

---

## 📦 Persyaratan Sistem

- **Python**: Versi `3.9` ke atas.
- **Sistem Operasi**: Windows, macOS, atau Linux.
- **Dependensi Python**:
  - [`httpx`](https://www.python-httpx.org/) (Asynchronous HTTP client dengan HTTP/2)
  - [`tqdm`](https://tqdm.github.io/) (Visualisasi progress bar interaktif)
  - [`requests`](https://requests.readthedocs.io/) (Manajemen autentikasi dan handshake cookie)

---

## 🛠️ Panduan Instalasi

1. **Clone repository ini:**
   ```bash
   git clone https://github.com/esyeibe/insta-comments-scraper.git
   cd insta-comments-scraper
   ```

2. **Buat dan aktifkan Virtual Environment (Disarankan):**
   ```bash
   # Di Linux / macOS:
   python3 -m venv venv
   source venv/bin/activate

   # Di Windows (PowerShell):
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install seluruh dependensi:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Siapkan file konfigurasi lingkungan [`.env`](file:///.env):**
   ```bash
   cp .env.example .env
   ```

---

## ⚙️ Konfigurasi (`.env`)

Konfigurasi disimpan di file [`.env`](file:///.env). Edit file tersebut untuk mengatur kredensial dan preferensi scraping Anda:

```env
# ============================================================
# InstaScrape Configuration
# ============================================================

# [PILIHAN 1 - SANGAT DIREKOMENDASIKAN]
# Masukkan sessionid dari browser (Buka instagram.com -> F12 -> Application -> Cookies -> sessionid)
IG_SESSIONID=your_sessionid_here

# Atau Anda bisa menempelkan seluruh string header Cookie di sini:
IG_COOKIE=

# [PILIHAN 2 - Kredensial Username & Password]
# Jika ingin mencoba login otomatis via mobile API:
IG_USERNAME=
IG_PASSWORD=

# [PENGATURAN SCRAPING]
# Batas request per detik (disarankan 0.5 sampai 2.0 agar tidak memicu rate limit 429)
DEFAULT_RPS=1.0

# Ambil juga balasan komentar (replies)? (True/False)
INCLUDE_REPLIES=True
```

### Penjelasan Variabel Konfigurasi:

| Variabel | Tipe | Default | Keterangan |
| :--- | :---: | :---: | :--- |
| `IG_SESSIONID` | *String* | *(Kosong)* | Nilai cookie `sessionid` akun Instagram Anda dari browser. **Paling aman dari verifikasi bot/checkpoint.** |
| `IG_COOKIE` | *String* | *(Kosong)* | Raw string header `Cookie` lengkap dari browser. Alternatif jika ingin menyertakan seluruh cookie. |
| `IG_USERNAME` | *String* | *(Kosong)* | Username Instagram untuk login otomatis via mobile API. |
| `IG_PASSWORD` | *String* | *(Kosong)* | Password Instagram untuk login otomatis. |
| `DEFAULT_RPS` | *Float* | `1.0` | Batas maksimum request per detik (*Requests Per Second*). Disarankan `0.5` – `2.0`. |
| `INCLUDE_REPLIES` | *Boolean* | `True` | Jika `True`, scraper mengambil komentar utama dan seluruh balasannya. Jika `False`, hanya komentar induk. |

> [!NOTE]
> **Prioritas Pembacaan Sesi**:
> 1. `cookie.json` lokal (jika ada dan belum kedaluwarsa).
> 2. Variabel Lingkungan OS (*System Environment Variables*).
> 3. File [`.env`](file:///.env) (`IG_COOKIE` > `IG_SESSIONID` > `IG_USERNAME` & `IG_PASSWORD`).
> 4. File `config.json` (jika ada).
> 5. Prompt terminal interaktif pada saat eksekusi.

---

## 🔐 Panduan Autentikasi & Pengambilan Cookie

Instagram memiliki perlindungan bot yang sangat ketat terhadap login otomatis username/password (sering kali memicu `challenge_required`, `two_factor_required`, atau `needs_upgrade`). Menggunakan **Cookie Browser (`sessionid`)** adalah cara paling stabil dan 100% aman.

### Langkah Mudah Mendapatkan `sessionid` dari Browser:

1. Buka [https://www.instagram.com](https://www.instagram.com) di browser (Google Chrome, Edge, Brave, atau Firefox) dan pastikan Anda sudah login.
2. Buka jendela **Developer Tools**:
   - Tekan tombol **`F12`** pada keyboard, atau klik kanan di mana saja lalu pilih **Inspect (Periksa)**.
3. Buka tab penyimpanan cookies:
   - **Chrome / Edge / Brave**: Klik tab **Application** (Aplikasi) ➔ di panel kiri buka **Cookies** ➔ klik `https://www.instagram.com`.
   - **Firefox**: Klik tab **Storage** (Penyimpanan) ➔ buka **Cookies** ➔ klik `https://www.instagram.com`.
4. Temukan baris bernama **`sessionid`**.
5. Klik dua kali pada kolom **Value**, lalu salin (*Copy*) seluruh isinya (formatnya biasanya diawali ID akun, contoh: `6812345678%3AabCdEf...`).
6. Tempelkan (*Paste*) ke file [`.env`](file:///.env) pada bagian `IG_SESSIONID=`, atau masukkan saat skrip memintanya di terminal.

> [!TIP]
> **Alternatif (Full Cookie Header):**
> Pada tab **Network** di DevTools, refresh halaman Instagram, klik salah satu request ke `instagram.com`, buka sub-tab **Headers**, lalu salin seluruh isi dari **Request Headers -> Cookie**. Anda bisa langsung menempelkannya ke `IG_COOKIE=` di `.env`. Skrip otomatis mengekstrak `sessionid`, `csrftoken`, `mid`, dan `ds_user_id`!

---

## ▶️ Cara Penggunaan

### 1. Mode Interaktif
Cukup jalankan file [`main.py`](file:///home/esyeibe/project/InstaScrape/main.py):
```bash
python3 main.py
```
1. Masukkan URL postingan atau shortcode saat diminta.
2. Atur kecepatan RPS (tekan `Enter` untuk menggunakan nilai default dari `.env`).
3. Jika sesi belum tersimpan, Anda akan diminta memilih metode autentikasi dan diberi pilihan untuk menyimpannya ke `.env` secara permanen.

### 2. Mode Argumen CLI Langsung
Anda dapat langsung menyertakan URL postingan atau shortcode sebagai argumen perintah:
```bash
# Menggunakan URL Instagram Reel:
python3 main.py https://www.instagram.com/reel/DctF_wKTvOm/

# Menggunakan URL Feed Post biasa (/p/):
python3 main.py https://www.instagram.com/p/C-xyz123/

# Menggunakan URL Share Link:
python3 main.py https://www.instagram.com/share/reel/DctF_wKTvOm/

# Menggunakan Shortcode langsung:
python3 main.py DctF_wKTvOm
```

### 3. Tool Autentikasi Standalone (`login.py`)
File [`login.py`](file:///home/esyeibe/project/InstaScrape/login.py) dapat dijalankan secara independen untuk mengelola, menguji, atau mengekspor cookie akun Anda:

```bash
# Login atau validasi cookie manual dan langsung simpan ke .env:
python3 login.py -c "6812345678%3Aabc123xyz..." --save

# Login via Username & Password dan simpan ke .env:
python3 login.py -u akun_saya -p password_saya --save

# Tampilkan data cookie aktif dalam format JSON:
python3 login.py --json

# Buka wizard interaktif login:
python3 login.py
```

---

## 📁 Struktur & Contoh Output

Setiap proses scraping secara otomatis membuat sub-folder unik berdasarkan shortcode dan timestamp di dalam folder `download_comments/`:

```text
download_comments/
└── DctF_wKTvOm_20261017_161315/
    ├── DctF_wKTvOm_comments.csv   # Data tabular lengkap (Excel-Ready UTF-8 BOM)
    ├── DctF_wKTvOm_comments.json  # Data hierarki bersarang + metadata
    └── DctF_wKTvOm_comments.txt   # Teks baca rapi berindentasi balasan
```

---

### 1. File CSV (`.csv`)
File CSV disimpan dengan encoding **UTF-8 with BOM (`utf-8-sig`)**, sehingga dapat langsung dibuka menggunakan **Microsoft Excel, Google Sheets, LibreOffice Calc, atau Pandas** tanpa masalah encoding karakter atau emoji yang rusak.

#### Spesifikasi Kolom CSV:
| Nama Kolom | Tipe Data | Keterangan |
| :--- | :--- | :--- |
| `comment_id` | String | ID unik komentar dari Instagram. |
| `comment_type` | String | Nilai `parent` (komentar utama) atau `reply` (balasan). |
| `parent_id` | String | ID komentar induk. Bernilai kosong jika baris adalah komentar `parent`. |
| `username` | String | Username pengirim komentar/balasan. |
| `text` | String | Teks isi komentar (dibersihkan dari newline acak). |
| `reply_to_username`| String | Username yang dibalas (hanya terisi pada baris `reply`). |
| `created_at` | Integer | Waktu pembuatan dalam format Unix Timestamp (detik). |
| `created_time` | String | Waktu pembuatan dalam format lokal terbaca (`YYYY-MM-DD HH:MM:SS`). |
| `reply_count` | Integer | Jumlah balasan yang dimiliki (terisi pada komentar `parent`). |

#### Contoh Data CSV:
```csv
comment_id,comment_type,parent_id,username,text,reply_to_username,created_at,created_time,reply_count
18066119471756048,parent,,teuku_zachlul,Kekayaan alam aceh hanya untuk rakyat aceh,,1788193529,2026-08-31 23:25:29,20
18034134122657201,reply,18066119471756048,aprilmaret43,"@teuku_zachlul buat gam lebih detail nya , Untuk rakyat sisa sisanya atau ampasnya...",teuku_zachlul,1789271581,2026-09-13 10:53:01,0
18051733055799643,reply,18066119471756048,tm_puteh_attari,@g_el_community Batak sebenarnya orang gayo 😂,teuku_zachlul,1790072214,2026-09-22 17:16:54,0
```

---

### 2. File JSON (`.json`)
Menyimpan struktur pohon komentar (*nested hierarchy*) yang sangat ideal untuk analisis NLP, data science, atau integrasi aplikasi web.

#### Contoh Struktur JSON:
```json
{
  "generated_at": 1792228395,
  "shortcode": "DctF_wKTvOm",
  "parent_comment_count": 442,
  "reply_comment_count": 259,
  "total_comments": 701,
  "comments": [
    {
      "id": "18066119471756048",
      "username": "teuku_zachlul",
      "text": "Kekayaan alam aceh hanya untuk rakyat aceh",
      "created_at": 1788193529,
      "reply_count": 20,
      "replies": [
        {
          "id": "18034134122657201",
          "username": "aprilmaret43",
          "text": "@teuku_zachlul buat gam lebih detail nya , Untuk rakyat sisa sisanya atau ampasnya...",
          "created_at": 1789271581
        },
        {
          "id": "18051733055799643",
          "username": "tm_puteh_attari",
          "text": "@g_el_community Batak sebenarnya orang gayo 😂",
          "created_at": 1790072214
        }
      ]
    }
  ]
}
```

---

### 3. File TXT (`.txt`)
Format teks bersih dan intuitif dengan indentasi panah (`  ↳ `) untuk membaca alur percakapan secara langsung:

```text
teuku_zachlul: Kekayaan alam aceh hanya untuk rakyat aceh
  ↳ aprilmaret43: @teuku_zachlul buat gam lebih detail nya , Untuk rakyat sisa sisanya atau ampasnya...
  ↳ tm_puteh_attari: @g_el_community Batak sebenarnya orang gayo 😂
  ↳ g_el_community: @teuku_zachlul Tolol.. Kumpulan imigran Rohingya numpang hidup...
user_lain: Konten yang sangat menarik!
  ↳ creator: Terima kasih banyak sudah menonton!
```

---

## 🛡️ Anti-Ban & Best Practices Rate Limiting

1. **Rekomendasi RPS (`DEFAULT_RPS`)**:
   - Gunakan nilai **`0.5` sampai `1.5`** untuk operasi yang aman dan stabil.
   - Nilai **`1.0`** berarti 1 request per detik (~50 komentar per detik).
   - Nilai di atas **`3.0`** sangat berisiko memicu respons HTTP 429 (*Too Many Requests*) dari firewall Instagram.
2. **Gunakan Akun Sekunder (Burner Account)**:
   - Selalu disarankan menggunakan akun sekunder / pengujian saat melakukan scraping dalam skala besar untuk menghindari risiko penalti pada akun personal utama Anda.
3. **Mekanisme Exponential Backoff**:
   - Jika Instagram mengembalikan status HTTP 429 atau pesan *"Please wait a few minutes"*, scraper akan otomatis berhenti sejenak (`5 detik x jumlah percobaan`) dan mencoba kembali secara bertahap hingga 3 kali.
4. **Masa Berlaku Cookie**:
   - Cookie `sessionid` dari browser umumnya bertahan antara **30 hingga 90 hari** selama Anda tidak menekan tombol *"Log Out"* di browser tempat cookie tersebut disalin.

---

## ❓ Solusi Masalah & FAQ

<details>
<summary><b>1. Muncul pesan "Instagram API menolak versi aplikasi ini ('needs_upgrade')"?</b></summary>
<br>
Instagram secara berkala memperbarui protokol enkripsi password pada mobile API v1. Jika Anda mencoba login dengan Username & Password dan menemui pesan ini, <b>jangan panik</b>. Gunakan metode <b>Browser Cookie (Opsi 1)</b> dengan menyalin <code>sessionid</code> dari browser Anda. Metode ini 100% bekerja dan aman dari penolakan versi API.
</details>

<details>
<summary><b>2. Muncul error "HTTP 429: Too Many Requests"?</b></summary>
<br>
Instagram mendeteksi frekuensi request yang terlalu tinggi dari alamat IP Anda.
<ul>
  <li>Turunkan nilai <code>DEFAULT_RPS</code> di file <code>.env</code> menjadi <code>0.5</code> atau <code>0.3</code>.</li>
  <li>Beri jeda istirahat 5–15 menit sebelum menjalankan scraper kembali, atau gunakan koneksi VPN / proxy.</li>
</ul>
</details>

<details>
<summary><b>3. Muncul error "Media tidak ditemukan"?</b></summary>
<br>
Kemungkinan penyebab:
<ul>
  <li>Postingan/Reel telah dihapus oleh pemiliknya.</li>
  <li>Shortcode yang dimasukkan salah atau tidak lengkap.</li>
  <li>Postingan berasal dari <b>akun private</b> dan akun yang digunakan pada sessionid Anda belum mem-follow akun tersebut.</li>
</ul>
</details>

<details>
<summary><b>4. Bagaimana cara hanya mengambil komentar utama tanpa balasannya?</b></summary>
<br>
Buka file <code>.env</code> dan ubah pengaturan balasan menjadi:
<pre><code>INCLUDE_REPLIES=False</code></pre>
Scraping akan berjalan jauh lebih cepat karena tidak memanggil GraphQL child query.
</details>

<details>
<summary><b>5. Bagaimana jika sesi login kedaluwarsa di tengah proses scraping?</b></summary>
<br>
InstaScrape memiliki fitur <b>Self-Healing Auth</b>. Program tidak akan keluar atau menghapus data yang sudah terdownload. Terminal akan memunculkan prompt untuk memasukkan cookie baru, dan scraper akan langsung melanjutkan pengambilan data dari cursor pagination terakhir.
</details>

---

## 📂 Struktur File Proyek

```text
InstaScrape/
├── .env                  # Kredensial & pengaturan lokal (tidak di-track git)
├── .env.example          # Template konfigurasi environment
├── .gitignore            # Daftar file yang diabaikan oleh git
├── LICENSE               # Lisensi proyek (MIT)
├── README.md             # Dokumentasi lengkap proyek
├── requirements.txt      # Daftar dependensi modul Python
├── cookie.json           # File cache sesi aktif (dibuat otomatis)
├── login.py              # Modul autentikasi, parser cookie, & standalone CLI
├── main.py               # Mesin utama scraper asinkron & eksportir data
└── download_comments/    # Direktori penyimpanan hasil scraping
    └── {SHORTCODE}_{TIMESTAMP}/
        ├── {SHORTCODE}_comments.csv
        ├── {SHORTCODE}_comments.json
        └── {SHORTCODE}_comments.txt
```

---

## ⚠️ Penafian (Disclaimer) & Lisensi

Proyek ini dibuat semata-mata untuk tujuan **edukasi, riset, dan analisis data pribadi**. Penggunaan alat ini harus senantiasa mematuhi [Ketentuan Layanan Instagram (Terms of Service)](https://help.instagram.com/581066165581870). Pengembang tidak bertanggung jawab atas segala bentuk penyalahgunaan, pembatasan akun, atau pemblokiran yang timbul akibat aktivitas scraping yang melanggar ketentuan pihak ketiga.

Didistribusikan di bawah lisensi **MIT License**. Lihat file [LICENSE](LICENSE) untuk informasi lisensi selengkapnya.
