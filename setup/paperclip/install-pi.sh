#!/bin/bash
# =============================================================================
# AI Trading Bedrijf — Pi Installatie Script
# =============================================================================
# Gebruik:
#   git clone https://github.com/njwgroeneveld/hyperliquid-bot.git
#   cd hyperliquid-bot/setup/paperclip
#   chmod +x install-pi.sh
#   bash install-pi.sh
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

echo ""
echo "============================================="
echo "  AI Trading Bedrijf — Pi Setup"
echo "============================================="
echo ""

# -----------------------------------------------------------------------------
# Stap 1: Node.js v20+
# -----------------------------------------------------------------------------
echo "📦 Stap 1: Node.js controleren..."
if command -v node &> /dev/null; then
  NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
  if [ "$NODE_VERSION" -ge 18 ]; then
    log "Node.js $(node --version) al geinstalleerd"
  else
    warn "Versie te oud, upgraden naar v20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
    log "Node.js geupgraded naar $(node --version)"
  fi
else
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
  log "Node.js $(node --version) geinstalleerd"
fi

# -----------------------------------------------------------------------------
# Stap 2: pm2
# -----------------------------------------------------------------------------
echo ""
echo "📦 Stap 2: pm2 installeren..."
if command -v pm2 &> /dev/null; then
  log "pm2 al geinstalleerd"
else
  sudo npm install -g pm2
  log "pm2 geinstalleerd"
fi

# -----------------------------------------------------------------------------
# Stap 3: Paperclip installeren
# -----------------------------------------------------------------------------
echo ""
echo "📦 Stap 3: Paperclip installeren..."
CONFIG_FILE="$HOME/.paperclip/instances/default/config.json"

if [ -f "$CONFIG_FILE" ]; then
  log "Paperclip al geconfigureerd"
else
  echo "Paperclip onboarding uitvoeren (achtergrond)..."
  # onboard --yes start ook de server, dus we draaien het in achtergrond
  # en stoppen zodra de config aangemaakt is
  npx paperclipai onboard --yes &
  ONBOARD_PID=$!

  echo "Wachten tot config aangemaakt is..."
  for i in {1..30}; do
    if [ -f "$CONFIG_FILE" ]; then
      sleep 3  # even wachten zodat config volledig geschreven is
      kill $ONBOARD_PID 2>/dev/null || true
      wait $ONBOARD_PID 2>/dev/null || true
      log "Paperclip geconfigureerd"
      break
    fi
    if [ $i -eq 30 ]; then
      err "Paperclip configuratie niet gevonden na 60 seconden"
    fi
    sleep 2
  done
fi

# -----------------------------------------------------------------------------
# Stap 4: Anthropic API key configureren
# -----------------------------------------------------------------------------
echo ""
echo "🔑 Stap 4: Anthropic API key configureren..."

if grep -q '"llm"' "$CONFIG_FILE"; then
  log "LLM provider al geconfigureerd"
else
  echo "Voer je Anthropic API key in (begint met sk-ant-):"
  read -r -s ANTHROPIC_KEY
  echo ""
  if [[ ! "$ANTHROPIC_KEY" == sk-ant-* ]]; then
    err "Ongeldige API key — moet beginnen met sk-ant-"
  fi

  TEMP_FILE=$(mktemp)
  head -n -1 "$CONFIG_FILE" > "$TEMP_FILE"
  cat >> "$TEMP_FILE" << EOF
  ,
  "llm": {
    "provider": "claude",
    "apiKey": "$ANTHROPIC_KEY"
  }
}
EOF
  mv "$TEMP_FILE" "$CONFIG_FILE"
  log "API key geconfigureerd"
fi

# Stap 4b: bind blijft op loopback (vereist door local_trusted mode)
# Toegang vanuit Windows via SSH tunnel: ssh -L 3100:localhost:3100 pi@<pi-ip>

# -----------------------------------------------------------------------------
# Stap 5: risk-thresholds.json neerzetten
# -----------------------------------------------------------------------------
echo ""
echo "📄 Stap 5: risk-thresholds.json aanmaken..."

# Ga naar de hyperliquid-bot root (twee niveaus omhoog vanuit setup/paperclip)
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$REPO_ROOT/trading-company"

if [ -f "$REPO_ROOT/trading-company/risk-thresholds.json" ]; then
  log "risk-thresholds.json al aanwezig"
else
  cp "$(dirname "$0")/risk-thresholds.json" "$REPO_ROOT/trading-company/risk-thresholds.json"
  log "risk-thresholds.json aangemaakt"
fi

# Maak reports mappen aan
mkdir -p "$REPO_ROOT/trading-company/reports/review"
mkdir -p "$REPO_ROOT/trading-company/reports/tactiek"
mkdir -p "$REPO_ROOT/trading-company/reports/develop"
mkdir -p "$REPO_ROOT/trading-company/reports/test"
mkdir -p "$REPO_ROOT/trading-company/reports/board"
mkdir -p "$REPO_ROOT/trading-company/reports/risk"
mkdir -p "$REPO_ROOT/trading-company/reports/process"
log "Reports directories aangemaakt"

# -----------------------------------------------------------------------------
# Stap 6: Paperclip starten (tijdelijk voor setup)
# -----------------------------------------------------------------------------
echo ""
echo "🚀 Stap 6: Paperclip starten..."
pm2 stop paperclip 2>/dev/null || true

npx paperclipai run &
PAPERCLIP_PID=$!

echo "Wachten tot Paperclip klaar is..."
for i in {1..30}; do
  if curl -s http://127.0.0.1:3100/api/health > /dev/null 2>&1; then
    log "Paperclip bereikbaar"
    break
  fi
  if [ $i -eq 30 ]; then
    err "Paperclip start niet op tijd"
  fi
  sleep 2
done

# -----------------------------------------------------------------------------
# Stap 7: Bedrijf + agents + routine aanmaken
# -----------------------------------------------------------------------------
echo ""
echo "🏢 Stap 7: AI Trading Bedrijf aanmaken..."
node "$(dirname "$0")/pi-setup.js"

# -----------------------------------------------------------------------------
# Stap 8: Paperclip als pm2 service
# -----------------------------------------------------------------------------
echo ""
echo "⚙️  Stap 8: Paperclip als service instellen..."
kill $PAPERCLIP_PID 2>/dev/null || true
sleep 2

pm2 start "npx paperclipai run" --name paperclip
pm2 save
pm2 startup | grep "sudo" | bash 2>/dev/null || warn "Voer handmatig uit: pm2 startup && pm2 save"

log "Paperclip draait als pm2 service"

# -----------------------------------------------------------------------------
# Klaar
# -----------------------------------------------------------------------------
PI_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "============================================="
echo -e "${GREEN}🎉 Installatie voltooid!${NC}"
echo "============================================="
echo ""
echo "Paperclip UI : http://${PI_IP}:3100"
echo "Bedrijf      : AI Trading Bedrijf (AIT)"
echo "Agents       : 6 aangemaakt"
echo "Routine      : elke donderdag 20:00"
echo ""
echo "Volgende stap: zorg dat hyperliquid-bot/"
echo "en trading-company/ in dezelfde map staan."
echo "============================================="
