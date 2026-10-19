# Glance — dashboard homelab sur `/glance`

Dashboard de page d'accueil [Glance](https://github.com/glanceapp/glance),
servi par Caddy sur `https://10.0.0.206/glance/`.

Contenu :
- **Liens** vers toutes les routes référencées dans le `Caddyfile`
  (OpenFox à la racine, `/ajean/`, `/llama/`, `/code/`, `/vllm-cluster/`, `/glance/`).
- **Monitor** : disponibilité (vert/rouge) + temps de réponse de chaque service.
- **Sparks** : tuiles HEAD / WORKER (état, hostname, IP, température GPU, utilisation, puissance / ping).
- **Cluster vLLM** : état de l'API, requêtes en cours / en attente, débit (tok/s), KV cache, taux d'acceptation DSpark.

## Fichiers

| Fichier | Rôle |
|---|---|
| `glance.yml` | Configuration Glance (thème, pages, widgets) |
| `cluster-health.py` | Collecte la santé des 2 Sparks + du cluster (stdlib Python 3) |
| `install-cron.sh` | Installe / retire le cron 30 s qui alimente le JSON |
| `assets/cluster-health.json` | Sortie du script (dernier état connu, écrasé à chaque passage) |

## Déploiement

1. **Lancer Glance** (avec Caddy) :
   ```bash
   docker compose up -d glance
   ```
   Glance écoute sur `0.0.0.0:8082` (réseau host), config `base-url: /glance`.

2. **Alimenter les données de santé** (cron toutes les 30 s) :
   ```bash
   glance/install-cron.sh
   ```
   Le script `cluster-health.py` lit :
   - la clé d'API vLLM dans `~/.cache/ds4-0731/api-key` (métriques protégées) ;
   - `nvidia-smi` local (head) ;
   - `ping` + `ssh 10.0.0.230` (worker, SSH sans mot de passe déjà en place).

3. **Caddy** : la route `/glance` du `Caddyfile` pointe sur `127.0.0.1:8082`.
   Après édition du Caddyfile : `docker exec caddy-proxy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile`,
   puis `docker exec caddy-proxy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile`.

4. **CA racine** : pour que le lien « CA racine » du dashboard fonctionne, copier
   le certificat de la CA Caddy dans `assets/` :
   ```bash
   cp ca-root.crt glance/assets/
   ```
   (à rafraîchir si la CA est régénérée, cf. memory-bank).

## Vérification

```bash
curl -sk https://10.0.0.206/glance/ | head                      # 200, HTML Glance
curl -s  http://127.0.0.1:8082/assets/cluster-health.json | jq .  # JSON de santé
curl -sk https://10.0.0.206/glance/assets/cluster-health.json   # via Caddy
```

## Notes

- **Liens cliquables relatifs, sondes absolues** : les `url` (liens cliquables)
  sont **relatifs** (`/ajean/`, `/code/`, …) pour suivre l'origine de la page
  (accès direct `https://10.0.0.206/…` **ou** via tunnel SSH `https://localhost:<port>/…`).
  Les `check-url` des widgets `monitor` restent **absolus** (`https://10.0.0.206/…`)
  car la sonde de statut est exécutée côté serveur Glance (sur le head).
- **URLs dupliquées** : les mêmes routes sont maintenues dans les widgets
  `monitor` **et** `bookmarks` de `glance.yml`. Toute modification de route Caddy
  doit être reportée aux deux endroits (elles sont volontairement indépendantes).
- **CA racine** : `assets/ca-root.crt` est une copie instantanée de la CA Caddy,
  servie par le dashboard. Si la CA est régénérée (volume `caddy-data` recréé),
  la recopier : `cp ca-root.crt glance/assets/`.
- **Pas d'historique** : `cluster-health.json` est un instantané régénéré toutes les 30 s,
  écrasé à chaque passage. Pas de base de données.
- **Authentification** : aucune (LAN, cohérent avec le reste du proxy).
  Une éventuelle protection Caddy `basicauth` sur `/glance` est possible.
- Port Glance : **8082** (libre ; 8080 est réservé à llama-server).
