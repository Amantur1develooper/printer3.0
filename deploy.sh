#!/bin/bash
# Run this on the VPS after uploading files
set -e

echo "=== Online Printer Deploy ==="

# 1. Install Docker if missing
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
fi

# 2. Install docker compose plugin if missing
if ! docker compose version &> /dev/null 2>&1; then
    echo "Installing docker compose plugin..."
    apt-get update -qq
    apt-get install -y docker-compose-plugin
fi

# 3. Check .env exists
if [ ! -f .env ]; then
    echo ""
    echo "ERROR: .env file not found!"
    echo "Create it first:  cp .env.example .env  then edit it."
    exit 1
fi

# 4. Build and start
echo "Building images..."
docker compose build

echo "Starting services..."
docker compose up -d

# 5. Create superuser if first deploy
echo ""
echo "Waiting for web to start..."
sleep 5

echo ""
echo "=== Done! ==="
echo ""
echo "Site is running at http://$(curl -s ifconfig.me 2>/dev/null || echo YOUR_IP)"
echo ""
echo "Next steps:"
echo "  1. Create admin user:  docker compose exec web python manage.py createsuperuser"
echo "  2. Check logs:         docker compose logs -f web"
echo "  3. Admin panel:        http://YOUR_IP/admin/"
echo "  4. Dashboard:          http://YOUR_IP/dashboard/"
