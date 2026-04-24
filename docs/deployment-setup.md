# Deployment Setup — Eenmalig

## Stap 1: GitHub repo aanmaken

1. Ga naar github.com → "New repository"
2. Naam: `hyperliquid-bot`, Private
3. Geen README of .gitignore aanmaken (die hebben we al)

## Stap 2: Code pushen

```bash
cd hyperliquid-bot
git init
git add .
git commit -m "feat: initial bot implementation"
git remote add origin https://github.com/njwgroeneveld/hyperliquid-bot.git
git push -u origin main
```

## Stap 3: GitHub Secrets instellen

Ga naar: github.com/njwgroeneveld/hyperliquid-bot → Settings → Secrets → Actions

Voeg toe:
| Secret | Waarde |
|---|---|
| `KUBECONFIG_DATA` | zie Stap 4 |
| `TELEGRAM_BOT_TOKEN` | je Telegram bot token |
| `TELEGRAM_CHAT_ID` | je Telegram chat ID |

(TELEGRAM is optioneel — deployment werkt ook zonder, alleen geen notificatie)

## Stap 4: KUBECONFIG_DATA aanmaken

Op Pi A (of via SSH):
```bash
cat ~/.kube/config | base64 -w 0
```
Kopieer de output en sla op als `KUBECONFIG_DATA` secret.

Zorg dat de kubeconfig werkt van buitenaf: het server adres moet het externe IP of hostname zijn van je Pi, niet `127.0.0.1`.

## Stap 5: NFS opzetten op Pi A

Op **Pi A** (NFS server):
```bash
sudo apt install nfs-kernel-server -y
sudo mkdir -p /data/hyperliquid-bot
sudo chown nobody:nogroup /data/hyperliquid-bot

# Exporteer de share — vervang 192.168.1.0/24 met je subnet
echo "/data/hyperliquid-bot  192.168.1.0/24(rw,sync,no_subtree_check)" | \
  sudo tee -a /etc/exports
sudo exportfs -a
sudo systemctl restart nfs-kernel-server
```

Op **Pi B** (NFS client):
```bash
sudo apt install nfs-common -y
# Test of de mount werkt:
sudo mount -t nfs PI_A_IP:/data/hyperliquid-bot /mnt/test
ls /mnt/test
sudo umount /mnt/test
```

## Stap 6: K8s namespace + secrets aanmaken (eenmalig op cluster)

```bash
# Namespace
kubectl create namespace trading

# Secret met je keys (vervang de waarden)
kubectl create secret generic hyperliquid-secrets \
  -n trading \
  --from-literal=private_key=0x... \
  --from-literal=anthropic_api_key=sk-ant-... \
  --from-literal=telegram_bot_token=... \
  --from-literal=telegram_chat_id=...
```

## Stap 7: PV aanmaken + manifests toepassen

Update eerst het IP in `k8s/pv-nfs.yaml` (vervang `192.168.1.100` met Pi A IP).
Update `k8s/deployment.yaml` (vervang `njwgroeneveld`).

Dan:
```bash
kubectl apply -f k8s/pv-nfs.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/servicemonitor.yaml   # alleen als je Prometheus Operator hebt
```

## Stap 8: Eerste deployment starten

Push een commit naar `main`:
```bash
git add .
git commit -m "chore: trigger first deployment"
git push
```

GitHub Actions bouwt nu automatisch de ARM64 Docker image en deployt naar je cluster.

## Daarna: automatisch

Elke `git push` naar `main` triggert:
1. Docker build (ARM64) → ghcr.io
2. `kubectl set image` → cluster rolt update uit
3. Telegram notificatie ✅ of ❌
