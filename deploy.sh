#!/bin/bash

# Stop and remove existing container
docker stop token-bot 2>/dev/null || true
docker rm token-bot 2>/dev/null || true

# Build fresh image
echo "🔨 Building Docker image..."
docker build -t token-bot .

# Deploy with proper settings
echo "🚀 Deploying bot..."
docker run -d \
  --name token-bot \
  --restart=unless-stopped \
  --memory="256m" \
  --cpus="0.3" \
  -e TELEGRAM_BOT_TOKEN="8203230559:AAECPHooiEDW7N7TWn_ROuVLfhdo7o4i42Y" \
  -e ADMIN_CHAT_ID="6547839325" \
  token-bot

# Wait and show logs
echo "⏳ Waiting for startup..."
sleep 10

echo "📋 Container status:"
docker ps --filter name=token-bot --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "📜 Recent logs:"
docker logs token-bot --tail=20

echo ""
echo "✅ Bot deployed successfully!"
echo "🔗 Use these commands:"
echo "   docker logs token-bot -f     # View live logs"
echo "   docker stop token-bot        # Stop bot"
echo "   docker start token-bot       # Start bot"
