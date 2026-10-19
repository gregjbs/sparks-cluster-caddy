# Project Brief — caddy-proxy

## One-liner
Reverse proxy Caddy 2 (Docker) exposant 5 services locaux en HTTPS sur un seul port (443), avec certificats auto-signés (CA interne de Caddy).

## Requirements (source of truth)
- Un seul point d'entrée HTTPS sur la machine `promaxgb10-host` (10.0.0.206).
- Routes :
  - `/ajean/`  → `10.0.0.206:8090` (préfixe retiré, l'app sert sa racine)
  - `/llama/`  → `10.0.0.206:8080` (préfixe conservé, llama-server est déjà monté sous /llama)
  - `/code/`   → `10.0.0.206:8081` (préfixe retiré, code-server ; headers de forwarding explicites)
  - `/vllm-cluster/` → `10.0.0.206:8000` (préfixe retiré, vLLM du cluster 2 Sparks ; streaming SSE sans tampon ; clé d'API vérifiée par vLLM)
  - `/glance/` → `127.0.0.1:8082` (préfixe retiré via `handle_path`, dashboard Glance en `base-url: /glance`)
  - `/vision/` → `192.168.100.11:8001` (préfixe retiré ; Qwen3.5-2B, vision de secours de DeepSeek, sur le worker par le lien 200G ; clé d'API vérifiée par llama-server)
  - `/pilote/` → `127.0.0.1:8095` (préfixe retiré ; pilote web du cluster, ~/work/ia/cluster-pilote ; sans authentification)
  - **racine `/`** (route par défaut) → `127.0.0.1:10369` (OpenFox, qui ne supporte pas de sous-chemin et n'écoute que sur localhost) ; `/sw.js` → 404
- TLS auto-signé (`tls internal`) — pas de domaine public.
- Le certificat racine CA est exporté dans `ca-root.crt` pour être trusté côté client.

## Out of scope
- Pas de domaine public / pas de Let's Encrypt.
- Pas d'authN/authZ au niveau du proxy (à faire côté services si besoin ; vLLM exige sa propre clé d'API).
- Pas de gestion de déploiement automatisée : le compose est lancé à la main sur la machine cible.

## Language
La documentation projet (Caddyfile, commits) est en français.
