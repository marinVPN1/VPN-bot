#!/bin/bash

# VPN Bot Installer
# This script installs the VPN subscription service on Ubuntu 22.04

set -e

echo "🚀 Starting VPN Bot installation..."

# Check OS
if [[ ! -f /etc/os-release ]]; then
    echo "❌ Unsupported OS"
    exit 1
fi

source /etc/os-release
if [[ "$ID" != "ubuntu" || "$VERSION_ID" != "22.04" ]]; then
    echo "❌ This script is designed for Ubuntu 22.04"
    exit 1
fi

echo "✅ OS check passed"

# Install Docker and Docker Compose
echo "📦 Installing Docker and Docker Compose..."
sudo apt update
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker

echo "✅ Docker installed"

# Clone repository (assuming script is run in project directory)
# If not, uncomment and modify:
# git clone https://github.com/your-repo/vpn-bot.git
# cd vpn-bot

# Check if database.db exists
if [ ! -f "database.db" ]; then
    echo "❌ database.db not found! Please place your existing database.db file in the project root directory."
    exit 1
fi

echo "✅ Existing database.db found"

# Create .env file
echo "🔧 Configuring environment variables..."

read -p "Enter Yookassa Shop ID: " YOOKASSA_SHOP_ID
read -p "Enter Yookassa Secret Key: " YOOKASSA_SECRET_KEY
read -p "Enter 3X-UI URL: " XUI_URL
read -p "Enter 3X-UI Token: " XUI_TOKEN
read -p "Enter Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Enter Admin Telegram ID: " ADMIN_TELEGRAM_ID
read -p "Enter Domain (e.g., vpn.example.com): " DOMAIN
read -p "Enter SSL Email: " SSL_EMAIL

# Generate JWT secret
JWT_SECRET=$(openssl rand -hex 32)

cp .env.template .env
sed -i "s/YOOKASSA_SHOP_ID=.*/YOOKASSA_SHOP_ID=$YOOKASSA_SHOP_ID/" .env
sed -i "s/YOOKASSA_SECRET_KEY=.*/YOOKASSA_SECRET_KEY=$YOOKASSA_SECRET_KEY/" .env
sed -i "s/XUI_URL=.*/XUI_URL=$XUI_URL/" .env
sed -i "s/XUI_TOKEN=.*/XUI_TOKEN=$XUI_TOKEN/" .env
sed -i "s/TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN/" .env
sed -i "s/ADMIN_TELEGRAM_ID=.*/ADMIN_TELEGRAM_ID=$ADMIN_TELEGRAM_ID/" .env
sed -i "s/DOMAIN=.*/DOMAIN=$DOMAIN/" .env
sed -i "s/SSL_EMAIL=.*/SSL_EMAIL=$SSL_EMAIL/" .env
sed -i "s/JWT_SECRET=.*/JWT_SECRET=$JWT_SECRET/" .env
sed -i "s|WEBHOOK_URL=.*|WEBHOOK_URL=https://$DOMAIN/api/payments/yookassa/webhook|" .env
sed -i "s|BOT_WEBHOOK_URL=.*|BOT_WEBHOOK_URL=https://$DOMAIN/api/bot/webhook|" .env

echo "✅ Environment configured"

# Create nginx config directory
mkdir -p nginx/ssl

# Start services
echo "🐳 Starting Docker services..."
sudo docker-compose up -d

# Setup SSL
echo "🔒 Setting up SSL certificates..."
sudo docker-compose run --rm certbot
sudo docker-compose exec nginx nginx -s reload

# Get server IP
SERVER_IP=$(curl -s ifconfig.me)

echo ""
echo "🎉 Installation completed successfully!"
echo ""
echo "🌐 Admin Panel: https://$DOMAIN/admin"
echo "🔑 Login: admin"
echo "🔑 Password: 123456"
echo ""
echo "📩 Yookassa Webhook URL: https://$DOMAIN/api/payments/yookassa/webhook"
echo "🤖 Bot Webhook URL: https://$DOMAIN/api/bot/webhook"
echo ""
echo "📋 Add this webhook URL to your Yookassa dashboard:"
echo "https://$DOMAIN/api/payments/yookassa/webhook"
echo ""
echo "📋 Set this webhook URL in BotFather for your bot:"
echo "https://$DOMAIN/api/bot/webhook"
echo ""
echo "🔧 If you need to access via IP instead of domain, use: https://$SERVER_IP"
echo ""
echo "📚 Check logs with: docker-compose logs -f"
echo "🔄 Restart services: docker-compose restart"