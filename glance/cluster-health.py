#!/usr/bin/env python3
"""Collecte la santé du cluster 2 Sparks (DeepSeek-V4-Flash) et écrit un JSON
destiné au dashboard Glance (glance/assets/cluster-health.json).

Exécuté toutes les 30 s par cron (voir install-cron.sh). Ne conserve aucun
historique : le fichier est écrasé à chaque passage.

Données collectées :
  - cluster : /health, /v1/models et /metrics de vLLM (clé d'API lue sur le head)
  - head    : nvidia-smi local
  - worker  : ping + nvidia-smi via SSH (10.0.0.230)
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
HEAD_IP = "10.0.0.206"
WORKER_IP = "10.0.0.230"
VLLM_URL = "http://127.0.0.1:8000"
KEY_FILE = os.path.expanduser("~/.cache/ds4-0731/api-key")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, "assets", "cluster-health.json")
STATE_FILE = os.path.join(BASE_DIR, "assets", ".state.json")
TIMEOUT = 5

# --------------------------------------------------------------------------- #
# Petites fonctions utilitaires
# --------------------------------------------------------------------------- #
def run(cmd, timeout=TIMEOUT):
    """Exécute une commande et renvoie (retour, stdout). Ne lève jamais."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode, p.stdout.strip()
    except Exception:
        return -1, ""


def http_get(url, headers=None, timeout=TIMEOUT):
    """GET HTTP et renvoie (code, corps). Ne lève jamais."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return -1, ""


def warn(msg):
    """Trace de diagnostic sur stderr (le cron ne redirige nulle part par défaut)."""
    print(f"cluster-health: WARN [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}",
          file=sys.stderr)


def metric_value(text, name):
    """Extrait la première valeur d'une métrique Prometheus 'vllm:*'."""
    m = re.search(rf"^{re.escape(name)}\{{[^}}]*\}}\s+([\d.eE+-]+)", text, re.M)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Collecte
# --------------------------------------------------------------------------- #
def read_api_key():
    try:
        with open(KEY_FILE) as f:
            key = f.read().strip()
        if not key:
            warn(f"clé d'API vide : {KEY_FILE}")
        return key or None
    except Exception:
        warn(f"clé d'API illisible : {KEY_FILE}")
        return None


def collect_head():
    """État du head (cette machine) via nvidia-smi."""
    info = {
        "name": "spark1",
        "hostname": os.uname().nodename or "",
        "ip": HEAD_IP,
        "up": True,
        "gpu_temp_c": None,
        "gpu_util_pct": None,
        "power_w": None,
    }
    code, out = run(["nvidia-smi", "--query-gpu=temperature.gpu,utilization.gpu,power.draw",
                     "--format=csv,noheader,nounits"])
    if code == 0 and out:
        parts = [p.strip() for p in out.split(",")]
        try:
            info["gpu_temp_c"] = int(float(parts[0]))
            info["gpu_util_pct"] = int(float(parts[1]))
            info["power_w"] = round(float(parts[2]), 1)
        except (ValueError, IndexError):
            pass
    else:
        info["up"] = False
        warn("nvidia-smi head a échoué")
    return info


def collect_worker():
    """État du worker via ping + SSH (nvidia-smi)."""
    info = {
        "name": "spark2",
        "hostname": "",
        "ip": WORKER_IP,
        "up": False,
        "ping_ms": None,
        "gpu_temp_c": None,
        "gpu_util_pct": None,
    }
    code, out = run(["ping", "-c", "1", "-W", "2", WORKER_IP])
    if code == 0:
        info["up"] = True
        m = re.search(r"time=([\d.]+)\s*ms", out)
        if m:
            info["ping_ms"] = round(float(m.group(1)), 1)
    else:
        warn(f"ping worker {WORKER_IP} a échoué (rc={code})")

    code, out = run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", WORKER_IP,
                     "hostname; nvidia-smi --query-gpu=temperature.gpu,utilization.gpu "
                     "--format=csv,noheader,nounits"])
    if code == 0 and out:
        lines = out.splitlines()
        info["hostname"] = lines[0].strip()
        if len(lines) > 1:
            parts = [p.strip() for p in lines[1].split(",")]
            try:
                info["gpu_temp_c"] = int(float(parts[0]))
                info["gpu_util_pct"] = int(float(parts[1]))
            except (ValueError, IndexError):
                pass
    elif code != 0:
        warn(f"ssh worker {WORKER_IP} a échoué (rc={code})")
    return info


def collect_cluster():
    """État de l'API vLLM (health, modèle, métriques)."""
    key = read_api_key()
    info = {
        "api_up": False,
        "health": None,
        "model": "",
        "version": "",
        "requests_running": 0,
        "requests_waiting": 0,
        "kv_cache_usage_pct": 0.0,
        "prefix_cache_hit_rate": None,
        "generation_tokens_total": 0,
        "prompt_tokens_total": 0,
        "tokens_per_sec": 0.0,
        "spec_acceptance_pct": None,
        "spec_tokens_per_step": None,
    }

    health_code, _ = http_get(f"{VLLM_URL}/health")
    info["health"] = health_code
    if health_code != 200:
        return info
    info["api_up"] = True

    headers = {"Authorization": f"Bearer {key}"} if key else {}
    _, models_body = http_get(f"{VLLM_URL}/v1/models", headers=headers)
    m = re.search(r'"id"\s*:\s*"([^"]+)"', models_body)
    if m:
        info["model"] = m.group(1)

    _, version_body = http_get(f"{VLLM_URL}/version")
    m = re.search(r'"version"\s*:\s*"([^"]+)"', version_body)
    if m:
        info["version"] = m.group(1)

    code, metrics_body = http_get(f"{VLLM_URL}/metrics", headers=headers)
    if code != 200 or not metrics_body:
        if code == 401:
            warn(f"/metrics renvoie 401 (clé d'API absente ou invalide) : {KEY_FILE}")
        else:
            warn(f"/metrics a échoué (http={code})")
        return info

    info["requests_running"] = int(metric_value(metrics_body, "vllm:num_requests_running") or 0)
    info["requests_waiting"] = int(metric_value(metrics_body, "vllm:num_requests_waiting") or 0)
    info["kv_cache_usage_pct"] = round(metric_value(metrics_body, "vllm:kv_cache_usage_perc") or 0.0, 1)
    pc_hits = metric_value(metrics_body, "vllm:prefix_cache_hits_total")
    pc_queries = metric_value(metrics_body, "vllm:prefix_cache_queries_total")
    if pc_queries and pc_queries > 0:
        info["prefix_cache_hit_rate"] = round((pc_hits or 0.0) / pc_queries * 100, 1)
    info["generation_tokens_total"] = int(metric_value(metrics_body, "vllm:generation_tokens_total") or 0)
    info["prompt_tokens_total"] = int(metric_value(metrics_body, "vllm:prompt_tokens_total") or 0)

    drafts = metric_value(metrics_body, "vllm:spec_decode_num_drafts_total")
    draft_tokens = metric_value(metrics_body, "vllm:spec_decode_num_draft_tokens_total")
    accepted = metric_value(metrics_body, "vllm:spec_decode_num_accepted_tokens_total")
    if draft_tokens and draft_tokens > 0:
        info["spec_acceptance_pct"] = round(accepted / draft_tokens * 100, 1)
    if drafts and drafts > 0 and accepted is not None:
        info["spec_tokens_per_step"] = round(1 + accepted / drafts, 2)

    now = time.time()
    prev = {}
    try:
        with open(STATE_FILE) as f:
            prev = json.load(f)
    except Exception:
        pass
    pgen = prev.get("generation_tokens_total")
    ptime = prev.get("time")
    if pgen is not None and ptime and now > ptime:
        dt = now - ptime
        if dt > 0:
            info["tokens_per_sec"] = round((info["generation_tokens_total"] - pgen) / dt, 1)

    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"time": now, "generation_tokens_total": info["generation_tokens_total"]}, f)
    except Exception:
        pass

    return info


def main():
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cluster": collect_cluster(),
        "head": collect_head(),
        "worker": collect_worker(),
    }
    try:
        os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
        tmp = OUT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, OUT_FILE)  # écriture atomique : Glance ne lit jamais un fichier à moitié écrit
    except Exception as e:
        print(f"cluster-health: échec écriture {OUT_FILE}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
