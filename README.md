# Price Tracker Bot

A Telegram bot that tracks prices on Russian marketplaces and sends notifications when prices drop into a user-defined range.

## Supported Marketplaces

- Wildberries (wb.ru)
- Ozon (ozon.ru)
- Yandex Market (market.yandex.ru)
- AliExpress (aliexpress.ru/com)
- DNS (dns-shop.ru)
- M.Video (mvideo.ru)

## Features

- 📦 Track unlimited products across multiple marketplaces
- 💰 Set target price thresholds
- 🔔 Get notified when prices drop below your target
- ⏰ Automatic price checks every 30 minutes
- 📊 Price history tracking
- 🚀 Deployed on Render.com with keep-alive

## Tech Stack

- **Python 3.11+** - Core language
- **aiogram 3.x** - Async Telegram bot framework
- **FastAPI + Uvicorn** - Health check endpoint
- **APScheduler** - Scheduled price checking
- **Supabase PostgreSQL** - Database
- **httpx + playwright** - Web scraping
- **Docker** - Containerization

## Setup Instructions

### Prerequisites

- Python 3.11 or higher
- Docker (for deployment)
- Telegram account
- Supabase account (free tier available)

### Local Development

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd price-tracker-bot
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**
   ```bash
   playwright install chromium
   ```

5. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

6. **Run the bot**
   ```bash
   python -m app.main
   ```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token from @BotFather | Yes |
| `TELEGRAM_ADMIN_ID` | Your Telegram user ID for admin notifications | Yes |
| `SUPABASE_URL` | Your Supabase project URL | Yes |
| `SUPABASE_KEY` | Your Supabase anon/public key | Yes |
| `PORT` | Port for health check server (default: 8000) | No |
| `LOG_LEVEL` | Logging level (INFO, DEBUG, WARNING, ERROR) | No |

## Getting Credentials

### Telegram Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command
3. Follow the instructions to name your bot
4. Copy the token provided by BotFather

### Telegram User ID

1. Search for [@userinfobot](https://t.me/userinfobot) in Telegram
2. Start the bot and it will show your user ID
3. Copy the numeric ID

### Supabase Credentials

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project
3. Go to Settings → API
4. Copy the **Project URL** (SUPABASE_URL)
5. Copy the **anon public** key (SUPABASE_KEY)

### Database Schema

Create the following tables in Supabase SQL Editor:

```sql
-- Products table
CREATE TABLE products (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id BIGINT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    target_price NUMERIC NOT NULL,
    current_price NUMERIC,
    image_url TEXT,
    marketplace TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Price history table
CREATE TABLE price_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    price NUMERIC NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_products_user_id ON products(user_id);
CREATE INDEX idx_products_is_active ON products(is_active);
CREATE INDEX idx_price_history_product_id ON price_history(product_id);
```

## Deployment on Render

1. **Push code to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin <your-github-repo>
   git push -u origin main
   ```

2. **Connect to Render**
   - Go to [render.com](https://render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure:
     - **Name**: price-tracker-bot
     - **Region**: Choose closest to you
     - **Branch**: main
     - **Root Directory**: (leave blank)
     - **Runtime**: Docker
     - **Plan**: Free

3. **Add Environment Variables**
   Add all variables from `.env.example` in Render's dashboard

4. **Deploy**
   - Click "Create Web Service"
   - Wait for deployment to complete

5. **Set up UptimeRobot**
   - Go to [uptimerobot.com](https://uptimerobot.com)
   - Create new monitor → HTTP(s)
   - URL: `https://your-app.onrender.com/health`
   - Interval: 10 minutes (or less)

## Bot Commands

- `/start` - Welcome message and instructions
- `/add` - Add a new product to track
- `/list` - View all tracked products
- `/delete` - Remove a product from tracking
- `/help` - Show help message

## Project Structure

```
price-tracker-bot/
├── app/
│   ├── bot/              # Telegram bot handlers
│   ├── parsers/          # Marketplace scrapers
│   ├── scheduler/        # APScheduler jobs
│   ├── db/               # Database models & client
│   ├── notifications/    # Notification sender
│   ├── config.py         # Configuration
│   ├── health_server.py  # FastAPI health endpoint
│   └── main.py           # Application entry point
├── tests/                # Test files
├── Dockerfile            # Docker configuration
├── render.yaml           # Render deployment config
└── requirements.txt      # Python dependencies
```

## Troubleshooting

### Parser not working for a marketplace
Marketplace websites frequently change their HTML structure. Check logs for specific errors and update the parser selectors accordingly.

### Bot not responding
- Verify TELEGRAM_BOT_TOKEN is correct
- Check if the bot is running (`/health` endpoint should return `{"status": "ok"}`)
- Review logs for errors

### Render service going to sleep
- Ensure health server is running on the correct PORT
- Set up UptimeRobot to ping `/health` every 10 minutes

## License

MIT License

## Support

For issues or questions, please open an issue on GitHub.
