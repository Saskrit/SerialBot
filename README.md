# Serial Hub

Telegram bot and web app for browsing and delivering daily TV serial episodes. Users search and watch in Telegram; admins manage the catalog, users, and settings from a web panel.

## Features

### Telegram bot
- Browse serials and episodes by date
- Search by name, slug, or alias
- Free daily watch limit (configurable in admin)
- **Membership tiers** — Episode Pass (₹10), Daily Unlimited Pass (₹19), Weekly/Monthly/Quarterly/Annual VIP
- Upgrade screen when daily limit is reached (all plans compared; Monthly VIP highlighted)
- **My Membership** page — plan, usage, referrals, unlocks, VIP expiry
- **Refer & Watch** — referrer and new user each get 5 bonus watches via `ref_TELEGRAM_ID` link (one referral per user)
- Episode requests and support tickets
- Trial episode timer for free users (optional, set in admin)
- Episode uploads from private storage channels

### Public website (`/`)
- Browse serials, search, and view episode dates
- Full membership catalog at `/plan` (matches bot pricing)
- Links into the Telegram bot to watch episodes

### Admin panel (`/admin`)
- Dashboard overview
- Serials CRUD (name, slug, aliases)
- Episode management and stats (top viewed, browse by serial)
- User management (ban, VIP, unlock)
- **Referrals** — see who invited whom (name, username, Telegram ID)
- Settings (free daily limit, trial timer)
- Payment review (legacy pending screenshots)
- Episode requests, support replies, broadcast messages

## Tech stack

- **Python 3.12** · [aiogram](https://docs.aiogram.dev/) 3.x
- **MongoDB** (Motor async driver)
- **aiohttp** — health check, admin panel, public site
- **Jinja2** — HTML templates

## Prerequisites

- Python 3.12+
- MongoDB Atlas (or local MongoDB)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- One or more private Telegram channels for episode storage (bot must be admin)

## Local setup

1. **Clone and install dependencies**

   ```bash
   git clone <your-repo-url>
   cd serialbot
   pip install -r requirements.txt
   ```

2. **Configure environment**

   Copy `.env.example` to `.env` and fill in values:

   ```bash
   cp .env.example .env
   ```

3. **Run the bot**

   ```bash
   python bot.py
   ```

   On Windows you can use `run_forever.bat` to auto-restart on crash.

4. **Open in browser**

   | URL | Purpose |
   |-----|---------|
   | `http://localhost:10000/` | Public site |
   | `http://localhost:10000/admin` | Admin panel |
   | `http://localhost:10000/health` | Health check |

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Telegram bot token |
| `MONGODB_URI` | Yes | MongoDB connection string |
| `MONGODB_DB` | No | Database name (default: `serialhub`) |
| `ADMIN_IDS` | Recommended | Comma-separated Telegram user IDs with bot admin access |
| `ADMIN_SECRET` | Recommended | Password for `/admin` web login |
| `STORAGE_CHANNEL_IDS` | Yes* | Comma-separated private channel IDs where episodes are stored |
| `STORAGE_CHANNEL_ID` | Yes* | Single channel ID (legacy; use `STORAGE_CHANNEL_IDS` for multiple) |
| `PAYMENT_CONTACT_USERNAME` | No | Telegram username for VIP / payment contact (default: `godthough`) |
| `NOTIFY_ON_NEW_EPISODE` | No | Notify users when new episodes are added (`true` / `false`) |
| `TELEGRAM_PROXY` | No | HTTP proxy for Telegram API (if needed) |
| `PORT` | No | HTTP port (default: `10000`) |
| `RESTART_ON_CRASH` | No | Restart polling after errors (default: `true`) |

\* At least one storage channel must be configured.

## Deploy on Railway

The repo includes `railway.toml` for Railway:

- **Build:** `pip install -r requirements.txt`
- **Start:** `python bot.py`
- **Health check:** `/health`

Set all required variables in **Service → Variables**. For MongoDB Atlas, allow `0.0.0.0/0` in Network Access so Railway can connect.

## Storage channels

Episodes are uploaded to private Telegram channels. The bot copies files from the correct channel into the user's DM when they watch.

1. Create one or more private channels.
2. Add the bot as an admin with permission to post/read messages.
3. Set channel IDs in `STORAGE_CHANNEL_IDS` (format: `-1001234567890`).
4. Upload episodes via the bot's admin flow or by forwarding videos into a storage channel (the bot parses serial name and date from the caption).

Multiple channels are supported; each episode stores which channel it came from for reliable delivery.

## Membership plans

| Plan | Price | Validity |
|------|-------|----------|
| Episode Pass | ₹10 | Permanent unlock for one episode |
| Daily Unlimited Pass | ₹19 | 24 hours unlimited |
| Weekly VIP | ₹39 | 7 days |
| Monthly VIP | ₹99 | 30 days (recommended) |
| Quarterly VIP | ₹249 | 90 days |
| Annual VIP | ₹799 | 12 months |

Payments are completed via Telegram contact (`PAYMENT_CONTACT_USERNAME`). Plan definitions live in `services/membership.py`.

## Payments

VIP upgrades and episode unlocks are handled by contacting the configured Telegram user (`PAYMENT_CONTACT_USERNAME`). Users message that account from the bot; admins grant VIP or unlocks from `/admin`.

## Project structure

```
serialbot/
├── bot.py                 # Entry point (polling + HTTP server)
├── config.py              # Environment and constants
├── handlers/              # Telegram command and callback handlers
├── keyboards/             # Inline keyboards
├── middlewares/           # User registration, logging
├── database/              # MongoDB connection and repository
├── services/              # Business logic (delivery, referrals, settings, …)
└── web/
    ├── routes.py          # Admin panel routes
    ├── user_routes.py     # Public site routes
    ├── templates/         # Jinja2 HTML (admin + site)
    └── static/            # CSS and assets
```

## Admin access

- **Telegram:** users listed in `ADMIN_IDS` get admin commands in the bot.
- **Web:** visit `/admin`, log in with a Telegram ID from `ADMIN_IDS` and the `ADMIN_SECRET` password.

## License

Private project — add a license here if you plan to open-source it.
