# Étude préalable : protéger des routes Caddy avec Authelia

*13 octobre 2026. Étude seulement : rien n'est installé ni modifié.*

## Question

Peut-on mettre une authentification commune (identifiant, mot de passe, éventuellement un second facteur) devant certaines routes du proxy Caddy (`https://10.0.0.206/…`) grâce à **Authelia** ?

## Réponse courte

**Oui techniquement, mais pas tant que le site est consulté par son adresse IP.** Authelia repose sur un **cookie de session lié à un nom de domaine**, qui ne peut être ni une adresse IP, ni `localhost`. Il faut donc d'abord **un nom pour le head, résolu par les postes clients**. C'est **la décision préalable**, et elle ne relève pas seulement de la technique : il faut savoir si l'on peut obtenir un nom DNS auprès de l'informatique, ou ajouter une entrée `hosts` sur chaque poste.

Sans nom de domaine, l'alternative réaliste est le **`basic_auth` de Caddy** (voir plus bas).

## Faits vérifiés

### Côté Authelia
D'après la documentation officielle :
- **domaine du cookie** (`session.cookies[].domain`) : un vrai nom de domaine, « *must include at least one period* » ; **ni adresse IP, ni `localhost`** (« browsers do not allow sites to set the cookies Authelia requires ») ; pas un suffixe public ;
- **`authelia_url`** : obligatoirement en **`https://`**. Elle peut contenir un chemin, par exemple `https://nom/authelia/`, ce qui évite d'avoir à créer un sous-domaine ;
- **intégration Caddy** : directive `forward_auth` vers `/api/authz/forward-auth`, en recopiant les en-têtes `Remote-User`, `Remote-Groups`, `Remote-Email` et `Remote-Name`. Il faut **Caddy 2.5.1 ou plus** : nous avons la **2.11.4**.

### Côté réseau (le 13/10, depuis le head)
| Nom | Résolution |
|---|---|
| `10.0.0.206` | Adresse utilisée aujourd'hui : **incompatible avec Authelia** |
| `promaxgb10-host.example.com` | **Inconnu** du DNS du réseau (10.0.0.254) |
| `promaxgb10-host` | Sans point : **incompatible**. Résolu seulement par `/etc/hosts` sur le head |
| `promaxgb10-host.local` | mDNS uniquement. Il annonce **deux adresses** : 10.0.0.206 et **192.168.100.10** (lien 200G, injoignable depuis le réseau local). C'est **fragile** : un poste peut tomber sur la mauvaise, et Windows gère mal le mDNS |

Caddy délivre déjà des certificats (CA interne) pour `promaxgb10-host` et `promaxgb10-host.local`. Pour tout nouveau nom, il suffit de l'ajouter à l'adresse du site dans le Caddyfile.

### Côté routes
| Route | Authentification actuelle | Usage |
|---|---|---|
| `/` (OpenFox) | **Mot de passe propre** (API en 401 sans session) | Agent qui a accès au shell du head : **sensible** |
| `/code/` (code-server) | **Mot de passe propre** (`/code/login`) | Shell et fichiers : **sensible** |
| `/pilote/` | **Aucune** | Arrête ou change le modèle : **à protéger en priorité** |
| `/glance/` | **Aucune** | Lecture seule, mais révèle la topologie ; intègre le pilote |
| `/ajean/` | **Aucune** | Application personnelle |
| `/llama/` | — | Service arrêté (502) |
| `/vllm-cluster/`, `/vision/` | **Clé d'API** (vLLM, llama-server) | **API** appelées par des programmes : une page de connexion les casserait. **Ne pas les mettre derrière Authelia** |

## Architecture proposée (si un nom est disponible)

```
Navigateur ──https://NOM/…──> Caddy
   ├─ /authelia/*                        → Authelia 127.0.0.1:9091 (portail de connexion)
   ├─ /pilote/*, /glance/*, /ajean/*, …  → forward_auth Authelia, puis service
   ├─ /vllm-cluster/*, /vision/*         → service directement (clé d'API, pas d'Authelia)
   └─ /  (OpenFox)                       → forward_auth (au choix), puis OpenFox

Client API ──https://10.0.0.206/vllm-cluster|vision/…──> inchangé (bloc IP réservé aux API)
Navigateur ──https://10.0.0.206/pilote…──> redirection vers https://NOM/pilote…
```

- **Authelia** : conteneur Docker (`authelia/authelia`, version épinglée), réseau host, écoute sur `127.0.0.1:9091`, sous le chemin `/authelia`. Fichiers dans `caddy-proxy/authelia/` :
  - `configuration.yml` ;
  - `users_database.yml` : utilisateurs, mots de passe hachés en argon2id ;
  - base SQLite ;
  - **secrets** (JWT, session, chiffrement du stockage) dans des fichiers en droits 600, **hors de git**.
- **Pas d'e-mail** : `notifier: filesystem`. Les codes d'enregistrement d'un second facteur et de réinitialisation sont écrits dans un fichier sur le head.
- **Second facteur** (TOTP, ou clé WebAuthn) : facultatif. On peut l'exiger par route, par exemple `two_factor` pour `/pilote/` et `/code/`, et `one_factor` ailleurs.
- **Caddyfile** :
  - un bloc `NOM` (site principal, avec `forward_auth` sur les routes choisies) ;
  - un bloc `10.0.0.206` qui garde **seulement les API**, sans Authelia, et **redirige** tout le reste vers `https://NOM/…`. Les clients d'API configurés sur l'adresse IP continuent donc de fonctionner.

## Conséquences à prévoir

| Sujet | Effet | Remède |
|---|---|---|
| Accès par **IP** dans le navigateur | Plus possible pour les routes protégées | Redirection automatique vers `https://NOM/…` |
| Accès par **tunnel SSH** | Le tunnel actuel (`https://localhost:<port>`) **ne fonctionne plus** : Authelia refuse `localhost` | Changer de type de tunnel : voir « Tunnel SSH » ci-dessous |
| **Glance** : moniteur et tuile | La tuile lit `127.0.0.1:8095` directement : **inchangée**. Les `check-url` en `https://10.0.0.206/pilote` recevraient une redirection | Faire pointer les `check-url` sur les ports locaux (`http://127.0.0.1:8095/`…) |
| **Iframe du pilote dans Glance** | Fonctionne si Glance et le pilote sont sur le même `NOM` : même cookie, même origine | Rien |
| **Journaux en direct** (SSE) | L'authentification n'est vérifiée qu'à l'ouverture du flux | Rien |
| **OpenFox** et **code-server** | Double connexion (Authelia, puis leur propre mot de passe) | Accepter, ou ne pas les mettre derrière Authelia |
| **Certificat** | Un nouveau nom demande un certificat de la CA interne : automatique avec Caddy | Ajouter `NOM` à l'adresse du site ; les postes font déjà confiance à la CA |
| **Ressources** | Authelia est léger (quelques dizaines de Mo de mémoire) | Rien ; mais la mémoire du head est déjà serrée (≈6 Go libres) |
| **Téléchargement** | Image `authelia/authelia` à télécharger depuis Docker Hub, par le proxy | **Votre accord**, au moment de l'installation |
| **Maintenance** | Un service de plus : mises à jour, sauvegarde de `users_database.yml` et des secrets, et risque de **se bloquer dehors** | Garder un accès de secours (tunnel SSH vers les ports locaux, qui ne passe pas par Caddy) |

## Tunnel SSH

Un tunnel vers le port 443 du head **ne fonctionne pas tel quel** : le navigateur voit `localhost`, Authelia ne peut pas y poser son cookie, et le certificat présenté ne correspond pas. Le problème n'est pas le tunnel lui-même, mais **le nom et le port que voit le navigateur**. Trois façons d'y remédier, de la plus sûre à la moins sûre :

### Solution recommandée : pas d'Authelia pour les connexions arrivant par le tunnel

Une requête qui passe par un tunnel SSH arrive sur Caddy **depuis le head lui-même** : l'adresse source est 127.0.0.1, ou 10.0.0.206 si le tunnel vise l'adresse réseau du head. L'utilisateur est alors **déjà authentifié par SSH**, avec sa clé. Caddy peut donc n'appliquer `forward_auth` qu'aux connexions venant d'une **autre** machine :

```
@distant not remote_ip 127.0.0.0/8 ::1 10.0.0.206/32
handle /pilote/* {
	forward_auth @distant 127.0.0.1:9091 {
		uri /api/authz/forward-auth?authelia_url=https://NOM/authelia/
		copy_headers Remote-User Remote-Groups Remote-Email Remote-Name
	}
	uri strip_prefix /pilote
	reverse_proxy 127.0.0.1:8095
}
```

- **Réseau local** (`https://NOM/…`) : connexion par Authelia. **Tunnel** (`https://localhost:<port>/…`, comme aujourd'hui) : accès direct. **Rien à changer sur le poste** : ni proxy, ni entrée `hosts`. Cela fonctionne même si les **politiques d'entreprise verrouillent le proxy** du navigateur, ce qui rend les options A et ci-dessous inapplicables (à vérifier dans `about:policies` ou `chrome://policy`).
- **Sécurité** : aucune ouverture nouvelle. Seuls les processus du head peuvent émettre depuis ces adresses, et ils accèdent déjà directement aux services (par exemple `127.0.0.1:8095`). Une machine distante ne peut pas usurper une adresse source TCP. **Condition** : ne pas déclarer de `trusted_proxies` dans Caddy (aucun aujourd'hui), sinon `X-Forwarded-For` pourrait fausser l'adresse vue.
- La session Authelia n'est pas partagée entre les deux accès ; ce n'est pas gênant, le tunnel n'en a pas besoin.

### Autres tunnels (si l'on veut Authelia aussi par le tunnel)

| Tunnel | Commande (sur le poste) | Ce que voit le navigateur | Fiabilité |
|---|---|---|---|
| **A. Proxy SOCKS** | `ssh -D 1080 user@<accès SSH du head>`, puis le navigateur configuré en proxy SOCKS 5 `localhost:1080` **avec résolution DNS par le proxy** (Firefox : « Proxy DNS lors de l'utilisation de SOCKS v5 », ou un profil dédié) | `https://NOM/…` **exactement comme sur le réseau local** : le nom est résolu côté head, port 443 | **Sûre** : aucune différence pour Caddy ni pour Authelia. **Recommandée.** Ne demande pas d'entrée `hosts` sur le poste, si le head résout `NOM` (DNS, ou une ligne dans son `/etc/hosts`) |
| **B. Port local 443** | `ssh -L 443:127.0.0.1:443 …` (droits administrateur sur le poste pour ouvrir le port 443 ; sous Windows ce n'est pas nécessaire), plus une entrée `hosts` `127.0.0.1 NOM` sur le poste | `https://NOM/…`, port 443 | **Sûre**, mais l'entrée `hosts` empêche d'utiliser le même nom sur le réseau local en même temps |
| **C. Autre port local** | `ssh -L 8443:127.0.0.1:443 …`, plus une entrée `hosts` `127.0.0.1 NOM` | `https://NOM:8443/…` | **Incertaine.** Le cookie ne dépend pas du port, mais le portail doit être annoncé à `https://NOM:8443/authelia/`. Caddy peut le transmettre requête par requête (paramètre `authelia_url` de `forward_auth`, documenté comme une « surcharge », avec `{http.request.hostport}`). Que fait Authelia d'un port différent dans cette adresse et dans l'adresse de retour ? **La documentation ne le précise pas : à tester** |

Dans tous les cas, garder un **accès de secours** qui ne passe ni par Caddy ni par Authelia : tunnel direct vers un port local, par exemple `ssh -L 8095:127.0.0.1:8095` pour le pilote.

## Les options pour le nom

| Option | Mise en œuvre | Avis |
|---|---|---|
| **1. Nom DNS officiel** demandé à l'informatique (par ex. `sparks.example.com` → 10.0.0.206) | Une demande, puis rien à faire sur les postes | **La meilleure**, si elle est possible |
| **2. Entrée `hosts`** sur chaque poste client (par ex. `10.0.0.206  sparks.lan`) | Une ligne par poste (droits administrateur du poste) | Bien pour **quelques utilisateurs** |
| **3. `promaxgb10-host.local`** (mDNS) | Rien côté postes en théorie | **Déconseillée** : deux adresses annoncées, dont celle du lien 200G. La corriger demanderait de modifier Avahi sur le head (sudo, réseau) |

## Alternatives à Authelia

| Solution | Fonctionne avec l'IP ? | Pour | Contre |
|---|:---:|---|---|
| **`basic_auth` de Caddy** | **Oui** | Intégré à Caddy : rien à installer, quelques lignes par route, mot de passe haché | Fenêtre de connexion du navigateur ; pas de vraie déconnexion ; pas de second facteur ; un identifiant commun ou une liste par route |
| **Tinyauth**, **oauth2-proxy** | Non (cookie de domaine, comme Authelia) | Plus légers qu'Authelia | Même contrainte de nom ; oauth2-proxy demande un fournisseur d'identité |
| **caddy-security** (module Caddy) | Partiellement | Portail intégré à Caddy | Demande une **image Caddy recompilée** (xcaddy) : plus de maintenance |
| **Authentik**, **Keycloak** | Non | Très complets (SSO, OIDC) | Lourds (base PostgreSQL, plusieurs Go de mémoire) : excessif ici |

## Recommandation

1. **Si un nom (option 1 ou 2) est envisageable** : Authelia, avec un bloc IP réservé aux API. Les routes protégées seraient :
   - `/pilote/` et `/glance/`, en un facteur, ou deux pour `/pilote/` ;
   - `/ajean/` ;
   - éventuellement OpenFox et `/code/`, en plus de leur propre mot de passe.

   Effort : **environ 1 h à 1 h 30 de session pour Claude**, une journée pour un humain qui découvre Authelia. Il faut ajouter vos tests de connexion, et l'essai par tunnel si vous l'utilisez.
2. **Si aucun nom n'est possible à court terme** : `basic_auth` de Caddy sur `/pilote/` et `/glance/`, voire `/ajean/`. Environ 15 minutes de session. On pourra passer à Authelia plus tard sans rien perdre.

## Points à trancher

1. **Nom** : nom DNS officiel (à demander), entrée `hosts` sur les postes, ou pas de nom (alors `basic_auth`) ?
2. **Routes à protéger**, et lesquelles demandent un second facteur ?
3. **Utilisateurs** : vous seul, ou plusieurs personnes (avec des groupes et des droits différents) ?
4. **Accès par tunnel SSH** : d'accord pour que les connexions arrivant par le tunnel (adresse source locale au head) **ne passent pas par Authelia**, l'authentification SSH en tenant lieu ? C'est la solution recommandée, sans aucun changement sur le poste.

## Décision et relecture de caddy-security (13/10/2026)

**Choix retenu : caddy-security** (module Caddy AuthCrunch, `github.com/greenpau/caddy-security`). Il fonctionne avec l'accès par IP : son cookie est lié à l'hôte. Il n'y a pas d'image officielle : on la **compile nous-mêmes en arm64** (`caddy:2-builder` + `xcaddy build --with github.com/greenpau/caddy-security@<version>`), en épinglant les versions.

**Relecture ciblée des CVE** (Trail of Bits 2023, CVE-2024-214xx) sur **caddy-security v1.4.1 / go-authcrunch v1.3.11**, par grep, sans compilation :

| Faille | Verdict |
|---|---|
| Usurpation `X-Forwarded-For` (21494), injection `X-Forwarded-Proto/Host` (21499) | **Corrigées** : `request_metadata.go` (`normalizeSecurityMetadata`) supprime les en-têtes `X-Forwarded-*`, `Forwarded` et `X-Real-IP` sauf pour un proxy de confiance (vérifié) |
| XSS Referer (21496) | Sans objet : l'en-tête n'est plus lu |
| Redirection ouverte (21497) | Corrigée : liste blanche (`trusted login/logout redirect uri`) obligatoire |
| XSS réfléchie (52430) | Corrigée (`html/template`), confiance moyenne |
| SSRF (21498) | Sans objet sans OAuth, SAML ni authproxy, confiance moyenne |
| Aléas (21495) | Corrigée (`crypto/rand`) |
| Session non invalidée à la déconnexion (21492) | **Présente** : le jeton reste valable jusqu'à son expiration (900 s par défaut) |
| Limite de tentatives (21500) | **Partielle** : 5 échecs puis 5 min de blocage, **par IP** et non par compte (vérifié) ; verrouillage du second facteur existant |

Les bases d'avis qui marquent ces CVE « non corrigées » sont **périmées**. Revue ciblée, pas un audit complet.

**Réglages imposés pour la mise en place :**
- pas de `trusted_proxies` ;
- aucune redirection de confiance, ou seulement vers notre hôte ;
- utilisateurs locaux uniquement : pas d'OAuth, de SAML, d'authproxy ni d'inscription publique ;
- **TOTP activé** ;
- `token_lifetime` ≤ 900 s ;
- HTTPS uniquement, mots de passe forts.

API `/vllm-cluster` et `/vision` hors portail (clé d'API). Connexions arrivant par le tunnel SSH (adresse source locale au head) dispensées, selon la solution de la section « Tunnel SSH ». Garder un accès de secours qui ne passe pas par Caddy.

## Abandon (13/10/2026)

Configuration caddy-security testée avec succès sur une instance d'essai (~/work/ia/caddy-security-build/essai,
README). **Abandonnée** par décision de l'utilisateur : la YubiKey en WebAuthn/U2F exige un nom de domaine
(refusée par les navigateurs sur https://10.0.0.206), même limitation de fond qu'Authelia. Production inchangée
(caddy-proxy sur caddy:2, /pilote et /code sans portail).

## Décision finale (13/10/2026) : `basic_auth` de Caddy

caddy-security a été écarté après essai : l'usage des **YubiKey (WebAuthn) impose un nom de domaine**, comme Authelia. Mise en place à la place :
- `basic_auth` sur **toutes les routes**, sauf les connexions venant du head (127.0.0.0/8, ::1, 10.0.0.206 : tunnels SSH, sondes Glance) et les API `/vllm-cluster/*` et `/vision/*`, protégées par clé ;
- identifiant et hash dans `.env`, hors git. Voir `memory-bank/techContext.md`.

L'image `local/caddy-security:2.11.7-csec1.4.1` (`~/work/ia/caddy-security-build/`) est conservée mais n'est pas utilisée.
