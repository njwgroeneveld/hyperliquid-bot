#!/bin/bash
# Verwijdert een specifieke versie van de hyperliquid-bot.
# Gebruik: bash scripts/remove-version.sh 0.1.0

set -e

if [ -z "$1" ]; then
  echo "Gebruik: $0 <versie>"
  echo "Voorbeeld: $0 0.1.0"
  echo ""
  echo "Draaiende versies:"
  kubectl get deployments -n trading -l app=hyperliquid-bot
  exit 1
fi

VERSION="$1"
VERSION_SLUG=$(echo "$VERSION" | tr '.' '-')
NAMESPACE="trading"

echo "Verwijderen hyperliquid-bot v${VERSION}..."

kubectl delete deployment "hyperliquid-bot-v${VERSION_SLUG}" -n "${NAMESPACE}" --ignore-not-found
kubectl delete pvc "hyperliquid-bot-pvc-v${VERSION_SLUG}" -n "${NAMESPACE}" --ignore-not-found
kubectl delete pv "hyperliquid-bot-pv-v${VERSION_SLUG}" --ignore-not-found

echo "✅ Versie v${VERSION} verwijderd"
