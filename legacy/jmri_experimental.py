# server.py - JMRI MCP Server complet
from mcp.server.fastmcp import FastMCP
import logging
import httpx
import json
from typing import Optional

logger = logging.getLogger("jmri_mcp")

mcp = FastMCP("JMRI DCC Controller")

# =========================
# CONFIGURATION
# =========================
JMRI_WEB_BASE = "http://10.0.20.20:12080"      # Web Server (roster, power, etc.)
JMRI_JSON_PORT = "http://10.0.20.20:12021"    # JSON Server (throttle) ← IMPORTANT

SYSTEMS = {
    "zou": "Z",
    "ohara": "O",
    "raijin": "R"
}

# =========================
# HELPERS
# =========================
def jmri_web_post(endpoint: str, payload: dict) -> dict:
    """POST sur le Web Server (power, lights simples, etc.)"""
    try:
        r = httpx.post(f"{JMRI_WEB_BASE}{endpoint}", json=payload, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Web Server error {endpoint}: {e}")
        return {"error": str(e)}


def jmri_json_command(command: dict) -> dict:
    """Envoie une commande au JSON Server (nécessaire pour throttle)"""
    try:
        data = json.dumps(command) + "\n"
        r = httpx.post(JMRI_JSON_PORT, content=data, timeout=10,
                       headers={"Content-Type": "application/json"})
        if r.content:
            return r.json()
        return {"status": "sent"}
    except Exception as e:
        logger.error(f"JSON Server error: {e}")
        return {"error": str(e)}


# =========================
# POWER
# =========================
@mcp.tool()
def power_on(system: str) -> dict:
    """Allume l'alimentation d'un système ferroviaire."""
    if system not in SYSTEMS:
        return {"success": False, "error": f"Système inconnu. Disponibles: {list(SYSTEMS.keys())}"}

    prefix = SYSTEMS[system]
    payload = {"method": "post", "data": {"state": 2, "prefix": prefix}}
    result = jmri_web_post("/json/power", payload)
    return {"success": True, "system": system, "state": "ON", "jmri": result}


@mcp.tool()
def power_off(system: str) -> dict:
    """Éteint l'alimentation d'un système ferroviaire."""
    if system not in SYSTEMS:
        return {"success": False, "error": f"Système inconnu. Disponibles: {list(SYSTEMS.keys())}"}

    prefix = SYSTEMS[system]
    payload = {"method": "post", "data": {"state": 4, "prefix": prefix}}
    result = jmri_web_post("/json/power", payload)
    return {"success": True, "system": system, "state": "OFF", "jmri": result}


# =========================
# ROSTER
# =========================
@mcp.tool()
def list_roster() -> dict:
    """Liste toutes les locomotives du roster JMRI."""
    try:
        r = httpx.get(f"{JMRI_WEB_BASE}/json/roster", timeout=8)
        data = r.json()
        return {"success": True, "roster": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
def search_roster(query: str) -> dict:
    """Recherche une locomotive dans le roster."""
    try:
        r = httpx.get(f"{JMRI_WEB_BASE}/json/roster", timeout=8)
        entries = r.json() if isinstance(r.json(), list) else []
        q = query.lower()
        results = [e for e in entries if isinstance(e, dict) and
                  (q in str(e.get("userName", "")).lower() or
                   q in str(e.get("name", "")).lower() or
                   q in str(e.get("address", "")))]
        return {"success": True, "query": query, "results": results[:15]}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================
# THROTTLE & LUMIÈRES
# =========================
@mcp.tool()
def set_function(loco_name: str, function: int, state: bool) -> dict:
    """
    Active/désactive une fonction sur une locomotive.
    function=0 → Lumières principales (très souvent avant + arrière)
    """
    command = {
        "type": "throttle",
        "data": {
            "name": loco_name,
            f"F{function}": state
        }
    }
    result = jmri_json_command(command)
    return {
        "success": "error" not in result,
        "loco": loco_name,
        "function": f"F{function}",
        "state": "ON" if state else "OFF",
        "result": result
    }


@mcp.tool()
def lights_on(loco_name: str) -> dict:
    """Allume les lumières de l'autorail/locomotive (F0)"""
    return set_function(loco_name, 0, True)


@mcp.tool()
def lights_off(loco_name: str) -> dict:
    """Éteint les lumières de l'autorail/locomotive (F0)"""
    return set_function(loco_name, 0, False)


@mcp.tool()
def release_loco(loco_name: str) -> dict:
    """Libère le throttle d'une locomotive (bonne pratique)."""
    command = {
        "type": "throttle",
        "data": {
            "name": loco_name,
            "release": None
        }
    }
    result = jmri_json_command(command)
    return {"success": True, "loco": loco_name, "action": "released", "result": result}


# =========================
# DÉMARRAGE
# =========================
if __name__ == "__main__":
    print("🚂 Serveur MCP JMRI démarré - Prêt pour Kira")
    mcp.run(transport="stdio")