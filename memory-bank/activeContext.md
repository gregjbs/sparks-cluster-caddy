# Active Context

## Current focus
Dashboard Glance déployé sur `/glance` (07/10) : liens vers les routes Caddy, monitor des services, tuiles de santé des 2 Sparks et du cluster vLLM. En attente de nouvelles instructions.

## Recent changes
- 2026-10-12 — Route `/pilote/*` → 127.0.0.1:8095 (pilote.py, ~/work/ia/cluster-pilote ; strip_prefix ; redir /pilote → /pilote/). **Pas d'authentification** (décision utilisateur) ; pilote.py exige l'en-tête X-Pilote et contrôle Origin (Host transmis par Caddy, testé). basic_auth à ajouter plus tard si besoin (procédure dans cluster-pilote/README.md).
- 2026-10-12 — Route `/vision/*` → 192.168.100.11:8001 (llama-server Qwen3.5-2B sur le worker, lien 200G ; strip_prefix, `flush_interval -1`). Validée, rechargée, testée depuis une autre machine (302 /vision → /vision/, 401 sans clé / 200 avec, description d'image en 0,7 s ; autres routes inchangées). Non commitée.
- 2026-10-07 — **Dashboard Glance sur `/glance`** : conteneur `glanceapp/glance` (port 8082, réseau host, `base-url: /glance` + `proxied: true`), route Caddy `handle_path /glance/*` → 127.0.0.1:8082. Santé du cluster via `glance/cluster-health.py` (cron 30 s, `glance/install-cron.sh`) → `glance/assets/cluster-health.json` servi par Glance ; widgets custom-api « Sparks » et « Cluster vLLM », monitor des services, bookmarks des routes. Validé (rendu serveur OK, cron frais, aucune régression) ; commité dans `main`.
- 2026-10-06 — **OpenFox (10369) exposé en HTTPS sur le port 10443** (site Caddy dédié `https://10.0.0.206:10443` → forward vers `10.0.0.206:10369`, pas de strip, à la racine). La première tentative en sous-chemin `/openfox` sur :443 a été **abandonnée** : OpenFox est compilé pour la racine (assets `/assets/...`, API `/api/...`, WS `/ws/...`) → conflit avec Open WebUI qui occupe la racine de :443 (page blanche). La route `/openfox` a donc été retirée du Caddyfile. **Validé, rechargé et testé** : page 200, assets 200, API 401 (joignable, demande d'auth). **Ports Caddy : 443 + 10443**. **Non commité**.
- 2026-10-06 — Ajout d'Open WebUI (10.0.0.206:3000) **à la racine** via un `handle` sans matcher (route par défaut) et `redir /openwebui* /`. Raison : Open WebUI 0.11.3 ne fonctionne pas sous un sous-chemin. Validé, rechargé, testé ; commité sur la branche `ajout-openwebui`.
- 2026-10-05 — Ajout de la route `/vllm-cluster/*` → 10.0.0.206:8000 (strip_prefix, `flush_interval -1` pour le streaming). Validée et rechargée sur la cible ; non commitée.
- `58f776e` — Ajout de code-server au proxy (route `/code*` → 10.0.0.206:8081, avec headers de forwarding).
- `042cdde` — Commit initial et fonctionnel (routes /ajean et /llama + compose + ca-root.crt).
- `.clinerules/` (règles Memory Bank) est encore **non tracké** dans git.

## Next steps
- À décider avec l'utilisateur. Idées possibles : tracker `.clinerules/` dans git, ajouter une route, durcir le proxy (auth), documenter l'installation de la CA.

## Important patterns & preferences
- Toujours expliciter pourquoi une route fait `strip_prefix` ou pas (commentaire dans le Caddyfile).
- Garder les commentaires du Caddyfile en français.
- Selon l'outil utilisé : depuis Claude Code sur `promaxgb10-host`, Docker est disponible et le proxy peut être validé, rechargé et testé directement.

## Learnings
- Browsers ne pas envoyer de SNI pour une IP → d'où `network_mode: host` (Caddy doit matcher le certificat sur la vraie IP, pas sur l'IP du bridge).
- `redir /x /x/` obligatoire pour les apps qui servent leurs assets relatifs depuis la racine, sinon les assets ne matchent plus la route `/x*`.
- 2026-10-13 — **basic_auth sur toutes les routes** (matcher `@protege` en tête du bloc de site), sauf connexions du head (remote_ip 127.0.0.0/8, ::1, 10.0.0.206 : tunnels SSH, sondes Glance) et API `/vllm-cluster/*`, `/vision/*` (clé d'API, même en-tête Authorization). Identifiant/hash dans `.env` (600, ignoré par git, `env_file` du service caddy) → changement = `docker compose up -d caddy`. Testé depuis le worker : 401 partout, API 200 avec clé ; head : 200. Ne pas ajouter trusted_proxies. Authelia/caddy-security abandonnés (nom de domaine requis, notamment pour les YubiKey) : voir ETUDE-authelia.md.
