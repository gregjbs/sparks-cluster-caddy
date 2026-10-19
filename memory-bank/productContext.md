# Product Context

## Why this project exists
La machine `promaxgb10-host` (IP LAN `10.0.0.206`) fait tourner plusieurs services sur des ports différents :
- `8080` — llama-server (API + UI Ollama-like, servie sous `/llama`)
- `8081` — code-server (VS Code dans le navigateur)
- `8090` — ajean (app perso, sert sa racine)
- `8000` — vLLM du cluster 2 DGX Spark (DeepSeek-V4-Flash, API compatible OpenAI, protégée par clé)
- `10369` — openfox (app compilée pour la racine, **servie à la racine du site**)

Accéder directement à chaque port est fragile (pas de HTTPS, ports à retenir, pas de TLS pour les assets). Ce projet met un unique point d'entrée `https://10.0.0.206/...` devant ces services.

## Problems it solves
- Un seul port à ouvrir/retourner (443) et une URL de base unique.
- HTTPS sur toutes les routes via la CA locale de Caddy (certificats auto-signés, sans domaine).
- Sémantique de chemins cohérente : rediriger vers le slash final pour les apps qui servent des assets relatifs depuis leur racine.

## How it should work (user experience)
- `https://10.0.0.206/ajean/` → l'app ajean, comme si on y était en racine.
- `https://10.0.0.206/llama/...` → llama-server, préfixe conservé côté upstream.
- `https://10.0.0.206/code/` → code-server, avec Host / X-Forwarded-* correctement propagés.
- `https://10.0.0.206/vllm-cluster/v1` → API vLLM (base URL OpenAI), réponses en streaming transmises au fil de l'eau.
- `https://10.0.0.206/vision/v1` → Qwen3.5-2B (description d'images), API compatible OpenAI, modèle `qwen3.5-2b`, même clé que DeepSeek.
- `https://10.0.0.206/pilote/` → pilote du cluster (arrêt/relance/variantes de DeepSeek, démarrage/arrêt de Qwen). **Sans mot de passe** (décision du 12/10).
- `https://10.0.0.206/` → OpenFox (à la racine ; authentification propre à OpenFox ; OpenFox n'est joignable que par Caddy).
- Côté client : installer une seule fois `ca-root.crt` dans le store de confiance du OS/navigateur pour avoir un cadenas vert.

## User
Utilisateur unique (user), accès depuis le LAN.
