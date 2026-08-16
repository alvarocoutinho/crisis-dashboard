"""PED accumulations-only client and exploratory ARI calculation."""
from __future__ import annotations
import getpass, os, time, requests
from .constants import ARI_THRESHOLDS, ARI_WEIGHTS, PED_ACUM_URL, SGAA_TOKEN_URL

ACC_COLS = ("acc1hr","acc3hr","acc6hr","acc12hr","acc24hr","acc48hr","acc72hr","acc96hr","acc120hr")
def credentials(config: dict) -> tuple[str,str]:
    email = config.get("PED_EMAIL") or os.environ.get("PED_EMAIL")
    password = config.get("PED_PASSWORD") or os.environ.get("PED_PASSWORD")
    if not email or not password:
        if not config.get("INTERACTIVE_CREDENTIALS", True): raise RuntimeError("PED credentials missing")
        email = email or input("PED e-mail: "); password = password or getpass.getpass("PED senha: ")
    return email, password

class PedClient:
    def __init__(self, config: dict): self.config=config; self.token=None; self.cooldown_until=0.0
    def login(self) -> None:
        email,password = credentials(self.config)
        response = requests.post(SGAA_TOKEN_URL, json={"email":email,"password":password}, timeout=30)
        if response.status_code != 200: raise RuntimeError(f"PED login failed {response.status_code}")
        self.token = response.json()["token"]; self.cooldown_until=0.0
    def get(self, url: str, params: dict):
        if time.time() < self.cooldown_until: return None
        response = requests.get(url, params=params, headers={"token":self.token}, timeout=30)
        if response.status_code != 401: return response
        try:
            self.login(); response = requests.get(url, params=params, headers={"token":self.token}, timeout=30)
            if response.status_code == 401: self.cooldown_until=time.time()+self.config["PED_REFRESH_COOLDOWN_SECONDS"]; return None
            return response
        except Exception:
            self.cooldown_until=time.time()+self.config["PED_REFRESH_COOLDOWN_SECONDS"]; return None

def summarize(rows: list[dict], alert: dict) -> dict:
    if not rows: return {}
    parsed=[]
    for row in rows:
        parsed.append({col: float(row.get(col) or 0) if str(row.get(col) or "").strip() else 0.0 for col in ACC_COLS})
    def max_of(col): return max(item[col] for item in parsed)
    def mean_of(col): return sum(item[col] for item in parsed)/len(parsed)
    summary={"cod_alerta":alert.get("cod_alerta"),"alert_municipio":alert.get("municipio"),"alert_uf":alert.get("uf"),"alert_evento":alert.get("evento"),"alert_nivel":alert.get("nivel"),"n_stations":len({row.get("codestacao") for row in rows}),"max_acc24hr":round(max_of("acc24hr"),2),"max_acc48hr":round(max_of("acc48hr"),2),"max_acc72hr":round(max_of("acc72hr"),2),"max_acc96hr":round(max_of("acc96hr"),2),"max_acc120hr":round(max_of("acc120hr"),2),"mean_acc24hr":round(mean_of("acc24hr"),2),"mean_acc48hr":round(mean_of("acc48hr"),2),"mean_acc72hr":round(mean_of("acc72hr"),2),"mean_acc120hr":round(mean_of("acc120hr"),2)}
    summary["antecedent_rain_index"] = round(sum(summary[key]*weight for key,weight in ARI_WEIGHTS.items()),2)
    summary["antecedent_rain_class"] = "sem_sinal"
    for label, condition in ARI_THRESHOLDS.items():
        if condition(summary): summary["antecedent_rain_class"] = label; break
    return summary

def fetch_accumulations(alert: dict, client: PedClient) -> tuple[list[dict],dict]:
    codibge=alert.get("codibge")
    if not codibge: return [],{}
    response=client.get(PED_ACUM_URL,{"codibge":int(codibge),"formato":"JSON"})
    if response is None or response.status_code != 200: return [],{}
    rows=[{**item,"cod_alerta":alert.get("cod_alerta"),"alert_municipio":alert.get("municipio"),"alert_uf":alert.get("uf"),"alert_evento":alert.get("evento"),"alert_nivel":alert.get("nivel")} for item in (response.json() or [])]
    return rows,summarize(rows,alert)
