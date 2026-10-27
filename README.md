# FreeToken Suite

Toolkit untuk [freetoken.website](https://freetoken.website) — gateway LLM OpenAI-compatible
dengan klaim **$60 free credits** per akun.

> ⚠️ Gunakan untuk akun milik sendiri. Repo ini mendokumentasikan perilaku API publik
> apa adanya; penulis tidak bertanggung jawab atas penyalahgunaan.

## Profil lahan

| Item | Nilai |
|---|---|
| Base URL | `https://freetoken.website/v1` |
| Model | 23 model: `claude-5.5-opus/-sonnet/-haiku`, `claude-5-opus/-sonnet/-fable` (ctx 1M), `gpt-5.6-sol/terra/luna`, `DeepSeek-V4-Pro/Flash`, `glm-5.2`, `kimi-k3`, `MiniMax-M3`, `Qwen3.8-27B`, `kat-coder-pro-v2.5`, `auto` |
| Key | `sk-tf-` + 32 karakter |
| Backend | New API di belakang Cloudflare |
| Free tier | $60 saldo awal, tanpa kartu kredit |

## Cara kerja

SPA-nya membangun objek user **sepenuhnya di client** — saldo, API key (`sk-tf-` +
32 random), referral code — menyimpannya di `localStorage`, lalu
`POST /api/user/sync` dengan objek itu. Endpoint menerima apa adanya, dan key-nya
langsung hidup di gateway.

Konsekuensinya: provisioning tidak perlu email OTP (mailer mereka sering `500`)
dan tidak perlu OAuth. Suite ini memanfaatkan alur yang sama seperti frontend-nya.

## Struktur

```
freetoken-suite/
├── config.example.toml
├── main.py              # CLI
├── run.sh
├── src/
│   ├── client.py        # OpenAI-compatible client + endpoint akun
│   ├── provision.py     # /api/user/sync provisioning + chat probe
│   ├── daily.py         # klaim reward harian ($5 dari client + bonus server)
│   ├── topup.py         # set saldo akun
│   ├── mail.py          # Tempik-compatible disposable mail (jalur OTP)
│   └── router.py        # inject ke 9router
├── data/   (gitignored)
└── logs/   (gitignored)
```

## Instalasi

```bash
git clone https://github.com/<user>/freetoken-suite.git
cd freetoken-suite
cp config.example.toml config.toml   # isi domain mail + path DB 9router
chmod +x run.sh
```

Butuh Python 3.11+ (pakai `tomllib`). Tidak ada dependency eksternal — semuanya stdlib.

## Perintah

```bash
./run.sh models                     # katalog model + harga
./run.sh health                     # cek gateway (522 = origin down)
./run.sh provision -n 10            # bikin N akun + probe chat tiap key
./run.sh sync                       # inject semua key ke 9router (prefix ft/)
./run.sh claim                      # klaim reward harian semua akun
./run.sh topup --balance 300        # set saldo akun
./run.sh chat -m auto -p "hi"       # chat dengan key tersimpan
./run.sh add --key sk-tf-xxx        # inject key manual
./run.sh verify --limit 5           # chat-test semua key
./run.sh status                     # key lokal / koneksi 9router
```

## Otomasi harian

Reward harian dijalankan lewat systemd timer:

```ini
# /etc/systemd/system/freetoken-claim.timer
[Timer]
OnCalendar=*-*-* 00:10:00
Persistent=true
RandomizedDelaySec=600
```

## Endpoint yang dipakai

```
POST /api/user/sync    {email, username, balance, apiKeys:[{key}], ...}
GET  /api/user/me?email=<email>
POST /api/send-otp     {email}
POST /api/verify-otp   {email, code}
GET  /api/auth/github/login
GET  /v1/models
POST /v1/chat/completions
```

## Catatan

- Voucher promo di UI (`FREETOKEN100`, `DEEPSEEK` → "+$25") dicek **client-side saja**,
  hanya pesan kosmetik — tidak menambah saldo.
- Reward harian menaikkan saldo ~$10/akun/hari (client menambah $5, server menambah lagi).
- Origin mereka labil: `502`/`522` sesekali muncul. Key tetap disimpan begitu
  `/api/user/sync` sukses, karena key digenerate di client dan tidak bisa dipulihkan.
