# caddy-proxy

Reverse proxy **Caddy 2** (Docker) qui expose les services du cluster IA sur un unique point d'entrée HTTPS (`https://10.0.0.206/…`, port 443) de la machine `promaxgb10-host`. Les certificats sont auto-signés via la CA locale de Caddy (`tls internal`) — pas de domaine public, pas de Let's Encrypt.

> La documentation du projet (Caddyfile, commits, docs) est en français.

---

## Routes servies

| Route | Amont (upstream) | Préfixe | Remarque |
|---|---|---|---|
| `/` (racine) | `127.0.0.1:10369` | — | **OpenFox** (route par défaut). `/sw.js` → 404 (service worker neutralisé). |
| `/ajean/` | `10.0.0.206:8090` | retiré | App ajean. Redir `/ajean` → `/ajean/`. |
| `/llama/` | `10.0.0.206:8080` | conservé | llama-server (déjà monté sous `/llama`). |
| `/code/` | `10.0.0.206:8081` | retiré | code-server, headers `Host` / `X-Forwarded-*` transmis. |
| `/vllm-cluster/` | `10.0.0.206:8000` | retiré | API vLLM (base URL `…/vllm-cluster/v1`, compatible OpenAI). Streaming SSE sans tampon (`flush_interval -1`). |
| `/vision/` | `192.168.100.11:8001` | retiré | Qwen3.5-2B (vision de secours de DeepSeek) sur le worker, lien 200G. Streaming SSE. |
| `/pilote/` | `127.0.0.1:8095` | retiré | Pilote web du cluster (**sans mot de passe**). |
| `/glance/` | `127.0.0.1:8082` | retiré (`handle_path`) | Dashboard Glance (`base-url: /glance`). |

---

## Authentification

La quasi-totalité des routes est protégée par un **`basic_auth` Caddy** :
- Identifiant et hash bcrypt dans `.env` (hors git, droits 600) : `PROXY_USER`, `PROXY_HASH`, lus au démarrage du conteneur (`env_file`).
- **Exemptés** : les connexions venant du head lui-même (`127.0.0.0/8`, `::1`, `10.0.0.206`) et les API `/vllm-cluster/*` et `/vision/*` (déjà protégées par clé d'API — même en-tête `Authorization`).

**Changer le mot de passe** :
```bash
docker exec -it caddy-proxy caddy hash-password          # génère le hash bcrypt
# coller le hash dans PROXY_HASH dans .env (entre apostrophes), puis :
docker compose up -d caddy
```

---

## Certificats TLS côté client

- Caddy génère et renouvelle ses certificats via sa CA locale, **persistée dans les volumes** `caddy-data` / `caddy-config` (survit aux rebuilds).
- Le certificat racine est exporté dans **`ca-root.crt`** à la racine du dépôt.
- Pour une navigation sans avertissement (cadenas vert), installer `ca-root.crt` une seule fois dans le store de confiance du OS / navigateur de chaque client.

> ⚠️ Supprimer les volumes `caddy-data` / `caddy-config` **régénère la CA** et rend `ca-root.crt` obsolète.

---

## Démarrage / arrêt

```bash
# Lancer les services (Caddy + Glance)
docker compose up -d

# Lancer seulement Glance (si Caddy est déjà actif)
docker compose up -d glance

# Voir les logs
docker compose logs -f caddy glance

# Arrêter
docker compose down

# Redémarrer uniquement le proxy (ex. après édition du Caddyfile hors inode)
docker restart caddy-proxy
```

---

## Maintenance du proxy (édition du Caddyfile)

> Le `Caddyfile` est monté **en fichier seul** (read-only) : l'éditer **sur place** (même inode). Un éditeur qui écrit un nouveau fichier puis le renomme casse le lien (`stat -c %i Caddyfile` côté hôte ↔ `docker exec caddy-proxy stat -c %i /etc/caddy/Caddyfile`).

```bash
# Éditer le Caddyfile, puis :
docker exec caddy-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile   # valider
docker exec caddy-proxy caddy reload  --config /etc/caddy/Caddyfile --adapter caddyfile   # recharger
```

Après un `git switch` / `git checkout`, il faut `docker restart caddy-proxy`.

---

## Dashboard Glance (`/glance`)

Conteneur `glanceapp/glance` (port 8082, réseau host) qui affiche :
- des **liens** vers toutes les routes Caddy ;
- un **monitor** de disponibilité (vert/rouge) et temps de réponse des services ;
- la **santé des 2 Spark** (HEAD / WORKER : GPU, temp, power, ping) et du **cluster vLLM** (API, requêtes, tok/s, KV cache…).

Les données de santé sont produites par `glance/cluster-health.py` (cron 30 s, `glance/install-cron.sh`) → `glance/assets/cluster-health.json`, servi par Glance.

> Détails : voir [`glance/README.md`](glance/README.md).

---

## Structure du dépôt

```
Caddyfile           Configuration Caddy (routes, basic_auth, TLS interne)
docker-compose.yml  Services caddy + glance (network_mode: host)
.env                Secrets basic_auth (hors git, droits 600)
ca-root.crt         Certificat racine de la CA Caddy (à truster côté client)
glance/             Dashboard homelab (config, script de santé, README)
memory-bank/        Mémoire projet (brief, contexte, patterns, historique)
ETUDE-authelia.md   Étude abandonnée : auth Authelia (nom de domaine requis)
```

---

## Pièges & limites connues

- **OpenFox occupe la racine du site** : toute adresse non prise par une route préfixée lui est envoyée. Une future application devra avoir son propre préfixe (et éviter les chemins absolus).
- **`/sw.js` → 404** : le service worker d'OpenFox (portée `/`) est neutralisé pour ne pas capter les navigations vers `/ajean/`, `/code/`, etc. Coût : plus d'app installable / hors ligne pour OpenFox.
- `/llama/` renvoie **502** tant que llama-server n'écoute pas sur 8080.
- Le reload affiche un avertissement `Caddyfile input is not formatted` (bloc code-server indenté avec des espaces). Sans effet ; `caddy fmt` corrigerait.

---

## Documentation complémentaire

- Mémoire projet : [`memory-bank/`](memory-bank/)
- Dashboard : [`glance/README.md`](glance/README.md)
- Étude authentification : [`ETUDE-authelia.md`](ETUDE-authelia.md)
