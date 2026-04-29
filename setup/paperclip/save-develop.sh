#!/bin/bash
# Haalt de laatste Develop Agent comment op uit Paperclip en slaat hem op als bestand.
# Slaat over als het bestand al bestaat (idempotent).

API_URL="http://127.0.0.1:3100"
DEVELOP_AGENT_ID="1289b5cc-da57-4dba-8b93-139e121c475c"
COMPANY_ID="2799ab32-12fa-4d5e-8905-89fc9c81073d"
REPORTS_DIR="/home/niels/Projects/hyperliquid-bot/trading-company/reports/develop"

# Haal de meest recente afgeronde develop issue op
ISSUE_ID=$(curl -s "$API_URL/api/companies/$COMPANY_ID/issues?assigneeAgentId=$DEVELOP_AGENT_ID&status=done" \
  | python3 -c "import sys,json; issues=json.load(sys.stdin); print(issues[0]['id']) if issues else exit(1)" 2>/dev/null)

if [ -z "$ISSUE_ID" ]; then
  exit 0
fi

# Haal timestamp en comment in één API call op
RESULT=$(curl -s "$API_URL/api/issues/$ISSUE_ID/comments" \
  | python3 -c "
import sys, json
from datetime import datetime
comments = json.load(sys.stdin)
if not comments:
    exit(1)
longest = max(comments, key=lambda c: len(c.get('body', '')))
dt = datetime.fromisoformat(longest['createdAt'].replace('Z', '+00:00')).astimezone()
print(dt.strftime('%Y-%m-%d-%H%M'))
print(longest['body'])
" 2>/dev/null)

TIMESTAMP=$(echo "$RESULT" | head -1)
COMMENT=$(echo "$RESULT" | tail -n +2)

if [ -z "$TIMESTAMP" ] || [ -z "$COMMENT" ]; then
  exit 0
fi

FILENAME="$REPORTS_DIR/${TIMESTAMP}-develop.md"

# Sla over als bestand al bestaat
if [ -f "$FILENAME" ]; then
  exit 0
fi

echo "$COMMENT" > "$FILENAME"
echo "$(date '+%Y-%m-%d %H:%M') Opgeslagen: $FILENAME" >> /tmp/save-develop.log
