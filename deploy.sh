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

# 4. Restart Bot Process
if command -v pm2 &> /dev/null; then
    echo "🔄 Restarting with PM2..."
    if pm2 describe voiceclaw > /dev/null 2>&1; then
        pm2 restart voiceclaw
    else
        pm2 start voicecreate.py --interpreter python3 --name voiceclaw
        pm2 save
    fi
    echo "✅ Successfully deployed with PM2! (Run 'pm2 logs voiceclaw' to view logs)"
elif systemctl is-active --quiet voiceclaw.service 2>/dev/null; then
    echo "🔄 Restarting systemd service voiceclaw..."
    sudo systemctl restart voiceclaw
    echo "✅ Successfully restarted voiceclaw systemd service!"
else
    echo "⚠️ Neither PM2 nor active systemd service detected."
    echo "Starting in background with nohup..."
    pkill -f "voicecreate.py" || true
    nohup python3 voicecreate.py > bot.log 2>&1 &
    echo "✅ Started in background! Log: bot.log"
fi
