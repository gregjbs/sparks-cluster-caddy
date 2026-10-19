# Tech Context

## Stack
- **Caddy 2** (image Docker `caddy:2`)
- **Docker Compose** (`docker-compose.yml`)
- **Glance** (dashboard homelab, image `glanceapp/glance`, port 8082, réseau host) — config `glance/glance.yml`, servira aussi `glance/assets/` (dont `cluster-health.json` produit par cron)
- Réseau : `network_mode: host` (pas de bridge, pas de mapping de ports)
- TLS : CA locale Caddy (`tls internal`), certificat racine exporté dans `ca-root.crt` (ECDSA P-256, "Caddy Local Authority - 2026 ECC Root")

## Services proxifiés (sur 10.0.0.206)
| Port | Service | Monté sous |
|------|---------|-----------|
| 8080 | llama-server | /llama (conservé) |
| 8081 | code-server  | /code (strip) |
| 8090 | ajean        | /ajean (strip) |
| 8001 (worker 192.168.100.11) | llama-server Qwen3.5-2B (vision de secours) | /vision (strip, `flush_interval -1`) ; joint par le lien 200G, couvert par NO_PROXY=192.168.100.0/24 |
| 8095 (127.0.0.1) | pilote.py (pilote web du cluster, ~/work/ia/cluster-pilote) | /pilote (strip) ; sans authentification ; lance les scripts start/stop des installations DeepSeek et de Qwen |
| 10369 (127.0.0.1) | openfox | **racine `/` de :443** (route par défaut, amont `127.0.0.1:10369`, pas de strip, `flush_interval -1`) ; `/sw.js` → 404 |
| 8000 | vLLM (cluster 2 Sparks) | /vllm-cluster (strip, `flush_interval -1`) |
| 8082 (0.0.0.0) | glance (dashboard Glance) | /glance (base-url `/glance` + `handle_path`, serveur dédié sur la machine) |

## Dev / ops workflow
1. Éditer `Caddyfile` dans ce repo.
2. **Rechargement** (l'image `caddy:2` ne surveille pas le fichier) : `docker exec caddy-proxy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`.
   ⚠️ Le Caddyfile est monté **en fichier seul** : l'éditer **sur place** (même inode). Un éditeur qui écrit un nouveau fichier puis le renomme casse le lien, et le conteneur continue de voir l'ancienne version (vérifier avec `stat -c %i Caddyfile` côté hôte et `docker exec caddy-proxy stat -c %i /etc/caddy/Caddyfile`).
3. Validation config sans redémarrer : `docker exec caddy-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`.

## Constraints
- **Docker est disponible** dans cet environnement d'IA : c'est la machine cible elle-même (`promaxgb10-host`). On peut donc lancer/valider/recharger/tester le proxy directement ici.
- Pas de CI.
- La CA est liée aux volumes `caddy-data`/`caddy-config` : les supprimer régénère la CA et rend `ca-root.crt` obsolète.

**Authentification** : `basic_auth @protege` (Caddyfile, en tête du site) ; `{$PROXY_USER}` `{$PROXY_HASH}` depuis `.env` (env_file, lu au démarrage). Changer le mot de passe : `docker exec -it caddy-proxy caddy hash-password`, mettre le hash entre apostrophes dans `.env`, puis `docker compose up -d caddy`. Dispensés : 127.0.0.0/8, ::1, 10.0.0.206 ; `/vllm-cluster/*`, `/vision/*`.
