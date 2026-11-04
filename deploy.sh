#!/usr/bin/env bash
# VoiceClaw VPS Quick Deploy / Update Script
set -e

echo "🚀 Starting VoiceClaw Deployment on VPS..."

# 1. Pull latest changes from GitHub
echo "📥 Pulling latest code..."
git pull origin main

# 2. Setup / activate virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

# 3. Install / upgrade dependencies
echo "📚 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Restart Bot & Web Server
if command -v pm2 &> /dev/null; then
    echo "🔄 Managing processes with PM2..."
    # Discord Bot
    if pm2 describe voiceclaw > /dev/null 2>&1; then
        pm2 restart voiceclaw
    else
        pm2 start voicecreate.py --interpreter python3 --name voiceclaw
    fi
    # Web Dashboard Server
    if pm2 describe voiceclaw-server > /dev/null 2>&1; then
        pm2 restart voiceclaw-server
    else
        pm2 start server.py --interpreter python3 --name voiceclaw-server
    fi
    pm2 save
    echo "✅ Successfully deployed bot & server with PM2! (Run 'pm2 status' or 'pm2 logs')"
elif systemctl is-active --quiet voiceclaw.service 2>/dev/null; then
    echo "🔄 Restarting systemd service voiceclaw..."
    sudo systemctl restart voiceclaw
    echo "✅ Successfully restarted voiceclaw systemd service!"
else
    echo "⚠️ Neither PM2 nor active systemd service detected."
    echo "Starting in background with nohup..."
    pkill -f "voicecreate.py" || true
    pkill -f "server.py" || true
    nohup python3 voicecreate.py > bot.log 2>&1 &
    nohup python3 server.py > server.log 2>&1 &
    echo "✅ Started bot & server in background! Logs: bot.log, server.log"
fi
