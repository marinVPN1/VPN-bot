#!/bin/bash

# VPN Bot Installer
# This script installs the VPN subscription service on Ubuntu 22.04 or 24.04

set -e

echo "🚀 Starting VPN Bot installation..."

# Check OS
if [[ ! -f /etc/os-release ]]; then
    echo "❌ Unsupported OS"
    exit 1
fi

source /etc/os-release
echo "🔍 Detected OS: $ID $VERSION_ID"

if [[ "$ID" != "ubuntu" ]]; then
    echo "❌ This script is designed for Ubuntu Linux only"
    echo "   Detected: $ID"
    exit 1
fi

if [[ "$VERSION_ID" != "22.04" && "$VERSION_ID" != "24.04" ]]; then
    echo "❌ This script is designed for Ubuntu 22.04 or 24.04"
    echo "   Detected version: $VERSION_ID"
    exit 1
fi

echo "✅ OS check passed (Ubuntu $VERSION_ID)"

# Install Docker and Docker Compose
echo "📦 Installing Docker and Docker Compose..."

# Remove any existing Docker installations
echo "🧹 Removing any existing Docker installations..."
sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
sudo apt purge -y docker-ce docker-ce-cli containerd.io 2>/dev/null || true
sudo rm -rf /var/lib/docker /etc/docker
sudo groupdel docker 2>/dev/null || true

# Install dependencies
sudo apt update
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release uidmap

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package index
sudo apt update

# Install Docker
echo "🐳 Installing Docker..."
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Start and enable Docker service
echo "🔄 Starting Docker service..."
sudo systemctl daemon-reload
sudo systemctl start docker
sudo systemctl enable docker

# Check if Docker started successfully
if ! sudo systemctl is-active --quiet docker; then
    echo "❌ Docker service failed to start. Trying to fix common issues..."

    # Try to fix cgroups issue
    if [ -f /etc/default/grub ]; then
        sudo sed -i 's/GRUB_CMDLINE_LINUX=""/GRUB_CMDLINE_LINUX="cgroup_enable=memory swapaccount=1"/' /etc/default/grub
        sudo update-grub
    fi

    # Try alternative start method
    sudo dockerd --iptables=false --bridge=none &

    # Wait a bit
    sleep 5

    if ! sudo systemctl is-active --quiet docker && ! pgrep -f dockerd > /dev/null; then
        echo "❌ Docker still not working. Please check system logs:"
        echo "   sudo systemctl status docker.service"
        echo "   journalctl -xeu docker.service"
        echo ""
        echo "🔧 You can try manual installation:"
        echo "   curl -fsSL https://get.docker.com -o get-docker.sh"
        echo "   sudo sh get-docker.sh"
        exit 1
    fi
fi

# Add current user to docker group (if not root)
if [ "$EUID" -ne 0 ]; then
    sudo usermod -aG docker $USER
    echo "👤 Added $USER to docker group"
    echo "   You may need to log out and back in for this to take effect"
fi

# Test Docker installation
echo "🧪 Testing Docker installation..."
if sudo docker run --rm hello-world > /dev/null 2>&1; then
    echo "✅ Docker installed and working"
else
    echo "⚠️ Docker installed but test failed. This might be normal if running as non-root user."
    echo "   Try: sudo docker run --rm hello-world"
fi

# Clone repository (assuming script is run in project directory)
# If not, uncomment and modify:
# git clone https://github.com/your-repo/vpn-bot.git
# cd vpn-bot

# Check if users.db exists
if [ ! -f "users.db" ]; then
    echo "❌ users.db not found! Please place your existing users.db file in the project root directory."
    exit 1
fi

echo "✅ Existing users.db found"

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