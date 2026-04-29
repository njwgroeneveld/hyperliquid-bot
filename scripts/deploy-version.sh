#!/bin/bash
# Deployt de versie uit het VERSION bestand als eigen pod naast bestaande versies.
# Gebruik: bash scripts/deploy-version.sh

set -e

VERSION=$(cat "$(dirname "$0")/../VERSION" | tr -d '[:space:]')
VERSION_SLUG=$(echo "$VERSION" | tr '.' '-')
IMAGE="ghcr.io/njwgroeneveld/hyperliquid-bot:v${VERSION}"
NAMESPACE="trading"

echo "Deploying hyperliquid-bot v${VERSION}..."

kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolume
metadata:
  name: hyperliquid-bot-pv-v${VERSION_SLUG}
spec:
  capacity:
    storage: 1Gi
  accessModes:
    - ReadWriteOnce
  hostPath:
    path: /data/hyperliquid-bot-v${VERSION_SLUG}
  persistentVolumeReclaimPolicy: Retain
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: hyperliquid-bot-pvc-v${VERSION_SLUG}
  namespace: ${NAMESPACE}
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
  volumeName: hyperliquid-bot-pv-v${VERSION_SLUG}
  storageClassName: ""
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hyperliquid-bot-v${VERSION_SLUG}
  namespace: ${NAMESPACE}
  labels:
    app: hyperliquid-bot
    version: v${VERSION}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: hyperliquid-bot
      version: v${VERSION}
  template:
    metadata:
      labels:
        app: hyperliquid-bot
        version: v${VERSION}
    spec:
      nodeSelector:
        kubernetes.io/hostname: niels-desktop
      containers:
        - name: bot
          image: ${IMAGE}
          resources:
            requests:
              memory: "256Mi"
              cpu: "100m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          ports:
            - containerPort: 8080
              name: metrics
          env:
            - name: HYPERLIQUID_TESTNET
              value: "true"
            - name: LOG_DIR
              value: "/data/logs"
            - name: DATABASE_PATH
              value: "/data/bot.db"
            - name: METRICS_PORT
              value: "8080"
            - name: HYPERLIQUID_PRIVATE_KEY
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: private_key
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: anthropic_api_key
                  optional: true
            - name: TELEGRAM_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: telegram_bot_token
                  optional: true
            - name: TELEGRAM_CHAT_ID
              valueFrom:
                secretKeyRef:
                  name: hyperliquid-secrets
                  key: telegram_chat_id
                  optional: true
          volumeMounts:
            - name: data
              mountPath: /data
            - name: config
              mountPath: /app/config
          livenessProbe:
            httpGet:
              path: /metrics
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 60
            failureThreshold: 3
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: hyperliquid-bot-pvc-v${VERSION_SLUG}
        - name: config
          configMap:
            name: hyperliquid-bot-config
EOF

echo ""
echo "✅ Deployed hyperliquid-bot v${VERSION}"
echo "Status: kubectl get pods -n ${NAMESPACE} -l version=v${VERSION}"
echo "Alle versies: kubectl get deployments -n ${NAMESPACE} -l app=hyperliquid-bot"
