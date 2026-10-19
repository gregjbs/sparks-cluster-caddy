# Progress

## What works
- Proxy fonctionnel : :443 avec ajean, llama, code-server, vllm-cluster, **Glance (/glance)** + **OpenFox à la racine** (amont `127.0.0.1:10369`) ; le port 10443 n'est plus utilisé — voir commits.
- Dashboard **Glance** sur `https://10.0.0.206/glance/` (conteneur `glance`, port 8082, réseau host) : liens vers toutes les routes Caddy, monitor vert/rouge des services, tuiles Sparks (HEAD/WORKER : temp/util GPU, ping, power) et cluster vLLM (API, requêtes en cours, tok/s, KV cache, acceptation DSpark) via `glance/assets/cluster-health.json` généré par cron 30 s.
- TLS auto-signé opérationnel, CA racine exportée (`ca-root.crt`).
- Persistance CA via volumes nommés.

## Current status
Stable / Glance déployé et fonctionnel sur `/glance` (07/10).

## What's left to build
Rien de connu. Possibles évolutions (non demandées) :
- Tracker `.clinerules/` (et `memory-bank/`) dans git.
- Route supplémentaire, ou bascule vers des Hostnames distincts (ex. `ajean.promaxgb10-host.local`) si un jour on a un domaine.
- Auth basique (Caddy `basicauth`) sur certaines routes.
- Script d'installation de `ca-root.crt` côté clients.

## Known issues
- OpenFox : première tentative en sous-chemin `/openfox` sur :443 **impossible** (app compilée pour la racine, conflit avec Open WebUI) → d'abord exposé sur le port 10443 (06/10), puis servi à la racine de :443 (07/10).
- **OpenFox occupe la racine du site** (depuis le 2026-10-07 ; avant : Open WebUI, retiré) : toute adresse non prise par une route préfixée lui est envoyée. Une future application devra avoir son propre préfixe et ne pas utiliser de chemins absolus (sinon un port/site dédié, cf. openfox sur 10443).
- Service worker d'OpenFox neutralisé (`/sw.js` → 404) : OpenFox n'est plus installable / hors ligne, choix délibéré pour protéger /ajean, /code, etc.
- OpenFox n'écoute plus que sur `127.0.0.1:10369` (`OPENFOX_HOST`, réglé par l'utilisateur le 2026-10-07) : seul accès possible depuis le réseau = Caddy en HTTPS (vérifié : accès direct refusé depuis le worker).
- `/llama/` renvoie 502 tant que llama-server n'est pas lancé (rien n'écoute sur 8080, constaté le 2026-10-05).
- `caddy reload` avertit « Caddyfile input is not formatted » (ligne 20) : le bloc code-server est indenté avec des espaces. Sans effet ; `caddy fmt` corrigerait.
- Avertissement de sécurité normal tant que `ca-root.crt` n'est pas installé dans le store de confiance du client.

## Evolution of decisions
1. `042cdde` — commit initial : /ajean + /llama, tls internal, host networking.
2. `58f776e` — ajout /code (code-server) avec headers de forwarding.
3. `fc34844` — création du Memory Bank et des règles Cline.
4. 2026-10-05 — ajout /vllm-cluster (vLLM du cluster 2 Sparks, port 8000), testé : redirection, /health, 401 sans clé, 200 avec, streaming SSE. (Commité : `daa50a1`, branche `ajout-vllm-cluster`.)
5. 2026-10-06 — réindentation du bloc code-server par l'utilisateur (tabulations).
6. 2026-10-06 — ajout d'Open WebUI (port 3000) à la racine, `/openwebui` redirigé vers `/` : la version 0.11.3 ne supporte pas de sous-chemin (base "" figé, assets /_app/..., API /api/..., WebSocket /ws/...). Testé : page, assets, /api/config, WebSocket 101, routes existantes inchangées. Branche `ajout-openwebui` (basée sur `ajout-vllm-cluster`).
7. 2026-10-06 — essai route `/openfox` en sous-chemin sur :443 (strip_prefix) : **abandonné** car OpenFox est compilé pour la racine (page blanche, conflit assets/API/WS avec Open WebUI).
8. 2026-10-06 — **correction Memory Bank** : Docker est en réalité disponible ici (c'est la machine cible `promaxgb10-host`), contrairement à ce qui était écrit en `techContext.md`.
9. 2026-10-06 — **OpenFox exposé sur son propre port HTTPS 10443** (`https://10.0.0.206:10443` → 10.0.0.206:10369, à la racine, pas de strip). Retrait de la route `/openfox` de :443. Validé/rechargé/testé (page 200, assets 200, API 401). Non commité.
10. 2026-10-07 — **Open WebUI retiré** (conteneur supprimé par l'utilisateur) ; **OpenFox servi à la racine de :443** (route par défaut → 10.0.0.206:10369, `flush_interval -1`) ; `/sw.js` → 404 pour neutraliser son service worker de portée `/` ; bloc `:10443` supprimé. Puis (utilisateur) OpenFox restreint à `127.0.0.1` et amont Caddy passé à `127.0.0.1:10369`, Caddy redémarré. Validé et testé depuis une autre machine du LAN : page, assets, WebSocket (101), `/api/*` (401 sans session), `/sw.js` 404, routes existantes inchangées ; accès direct à :10369 refusé.
11. 2026-10-07 — **Dashboard Glance sur `/glance`** (conteneur `glanceapp/glance`, port 8082, réseau host, config `glance/glance.yml` avec `base-url: /glance` + `proxied: true`). Caddy : `redir /glance /glance/` + `handle_path /glance/*` → `127.0.0.1:8082`. Santé des 2 Sparks et du cluster : `glance/cluster-health.py` (cron 30 s via `glance/install-cron.sh`, stdlib, clé `~/.cache/ds4-0731/api-key`, nvidia-smi + ssh 10.0.0.230 + ping) → `glance/assets/cluster-health.json` servi par Glance (`assets-path`), widgets custom-api « Sparks » et « Cluster vLLM ». Monitor + bookmarks pour toutes les routes. Validé : `/glance` 200, rendu serveur des widgets OK, cron frais (< 30 s), aucune régression des autres routes ; `caddy validate` OK (inode préservé). Commité et fusionné dans `main`.
- 2026-10-12 — Ajout de `/vision/` → 192.168.100.11:8001 (Qwen3.5-2B, vision de secours de DeepSeek, llama-server sur le worker). Testé depuis le LAN. Commité (98e12bd).
- 2026-10-12 — Ajout de `/pilote/` → 127.0.0.1:8095 (pilote web du cluster, sans authentification). Validé, rechargé (même inode), testé en HTTPS (302, page 200, état, 403 sur origine étrangère) ; autres routes inchangées.
- 2026-10-13 — basic_auth global (sauf head et API), secrets dans .env ; conteneur caddy-proxy recréé ; tests OK depuis le worker.
