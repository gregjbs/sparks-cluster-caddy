#!/usr/bin/env bash
# Installe (ou retire) le cron de collecte de la santé du cluster pour Glance.
# Le script cluster-health.py est lancé toutes les 30 s (2 lignes par minute).
#
# ⚠️  À lancer en tant que l'utilisateur qui possède la clé d'API vLLM
#     (~/.cache/ds4-0731/api-key) : sinon /metrics renvoie 401 et le widget
#     « Cluster vLLM » reste vide. Ne PAS utiliser sudo/root.
#
# Usage :
#   ./install-cron.sh          # installe
#   ./install-cron.sh --uninstall   # retire
set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cluster-health.py"
CRON="$(crontab -l 2>/dev/null | grep -vF "$SCRIPT" || true)"

KEY="${HOME}/.cache/ds4-0731/api-key"
if [[ ! -r "$KEY" ]]; then
    echo "⚠️  ATTENTION : clé d'API illisible pour l'utilisateur courant ($(whoami))."
    echo "   Chemin attendu : $KEY"
    echo "   /metrics renverra 401 (widget « Cluster vLLM » vide)."
    echo "   Lancez ce script en tant que l'utilisateur qui possède cette clé."
else
    echo "Clé d'API lisible : $KEY (utilisateur $(whoami))"
fi

if [[ "${1:-}" == "--uninstall" ]]; then
    printf '%s\n' "$CRON" | crontab -
    echo "Cron retiré : $SCRIPT"
    exit 0
fi

printf '%s\n' "$CRON" \
    "* * * * * sleep 0  && /usr/bin/python3 $SCRIPT" \
    "* * * * * sleep 30 && /usr/bin/python3 $SCRIPT" \
    | crontab -

echo "Cron installé : $SCRIPT toutes les 30 s."
crontab -l | grep -F "$SCRIPT"
