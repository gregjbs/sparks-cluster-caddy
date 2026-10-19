# System Patterns

## Architecture
```
Navigateur (LAN)
   │  https://10.0.0.206/{ajean,llama,code,vllm-cluster,vision,pilote}   +   https://10.0.0.206/ (openfox, racine)
   ▼
Caddy 2 (conteneur Docker, network_mode: host, port 443)
   │  tls internal (CA locale Caddy, persistée dans les volumes)
   ├── :443  site principal
   │   ├── /ajean*  → strip_prefix /ajean → 10.0.0.206:8090 (ajean)
   │   ├── /llama*  → préfixe conservé     → 10.0.0.206:8080 (llama-server)
   │   ├── /code*   → strip_prefix /code  → 10.0.0.206:8081 (code-server)
   │   ├── /vllm-cluster/* → strip_prefix → 10.0.0.206:8000 (vLLM)
   │   ├── /vision/* → strip_prefix → 192.168.100.11:8001 (Qwen3.5-2B sur le worker, lien 200G)
   │   ├── /pilote/* → strip_prefix → 127.0.0.1:8095 (pilote.py, sans authentification)
   │   ├── /glance*    → handle_path (strip) → 127.0.0.1:8082 (Glance, base-url /glance)
   │   ├── /sw.js      → 404 (neutralise le service worker d'OpenFox, voir décision 5)
   │   └── / (défaut) → 127.0.0.1:10369 (openfox, PAS de strip ; OpenFox n'écoute que sur localhost)
```

## Key technical decisions
1. **`network_mode: host`** — indispensable : les navigateurs n'envoient pas de SNI pour les adresses IP. Caddy doit matcher le certificat sur la vraie IP de destination ; en bridge il verrait l'IP du bridge et le TLS échouerait.
2. **`tls internal`** — pas de domaine public ; Caddy génère et renouvelle les certificats via sa CA locale. La CA racine est exportée dans `ca-root.crt` (valide 2026-09-24 → 2036-08-02) pour être ajoutée au store de confiance des clients.
3. **Strip-prefix vs keep-prefix** — dépend de comment l'upstream est monté :
   - ajean & code-server servent depuis la racine → `uri strip_prefix` + `redir /x /x/` (assets relatifs).
   - llama-server est déjà monté sous `/llama` → préfixe conservé, pas de redir.
   - openfox est compilé pour la RACINE (assets `/assets/...`, API `/api/...`, WS) : **impossible en sous-chemin** → depuis le 2026-10-07 il est servi **à la racine de :443** (route par défaut), Open WebUI ayant été retiré. Toute future application devra avoir son propre préfixe.
4. **Headers de forwarding sur /code** — `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto` remontés explicitement (code-server en a besoin).
5. **`/sw.js` → 404** — le service worker d'OpenFox (Workbox, portée `/`, `NavigationRoute` sans liste d'exclusion) renverrait son `index.html` pour TOUTE navigation du site (/ajean/, /code/…) dans un navigateur qui l'a installé. Le bloquer fait échouer l'enregistrement sans gêner OpenFox (perte du seul mode hors ligne / installable).
6. **Glance sous `/glance`** — Glance supporte nativement un sous-chemin via `server.base-url: /glance` (+ `proxied: true`). Caddy fait `redir /glance /glance/` + `handle_path /glance/*` (qui retire le préfixe) → `127.0.0.1:8082`. Glance tourne en réseau host (comme Caddy) sur le port 8082.
7. **Santé des Sparks via cron + JSON servi par Glance** — le worker (10.0.0.230) n'expose aucun HTTP et `/metrics` vLLM est en format Prometheus protégé par clé : Glance ne peut pas mesurer directement. Un script `glance/cluster-health.py` (cron toutes les 30 s, stdlib, lit la clé `~/.cache/ds4-0731/api-key`, `nvidia-smi` local + `ssh 10.0.0.230` + ping) écrit `glance/assets/cluster-health.json` (instantané écrasé, pas d'historique). Glance le sert via `assets-path: /app/assets` (dossier `./glance/assets` bind-monté) et les widgets `custom-api` le lisent en local (`http://127.0.0.1:8082/assets/cluster-health.json`, cache 30 s). Aucun volume Caddy supplémentaire.

## Critical implementation paths
- `./Caddyfile` → monté en **read-only** sur `/etc/caddy/Caddyfile`. **Pas de rechargement automatique** : `docker exec caddy-proxy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`. Fichier monté seul → l'éditer sur place (même inode) ; après un `git switch`/`checkout`, `docker restart caddy-proxy`.
- Volumes nommés `caddy-data` (certificats/CA) et `caddy-config` (admin API JSON) → la CA survit aux rebuilds de conteneur.
- `ca-root.crt` doit être re-exporté seulement si la CA est régénérée (ex. perte des volumes).
