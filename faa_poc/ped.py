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
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, config: dict):
        self.config=config
        self.token=None
        self.cooldown_until=0.0
        self.last_error=""

    def _cooldown_seconds(self) -> float:
        return float(self.config.get("PED_FAILURE_COOLDOWN_SECONDS",
                                     self.config.get("PED_REFRESH_COOLDOWN_SECONDS", 60)))

    def _get_with_retries(self, url: str, params: dict):
        attempts=max(1, int(self.config.get("PED_MAX_ATTEMPTS", 3)))
        connect_timeout=float(self.config.get("PED_CONNECT_TIMEOUT_SECONDS", 10))
        read_timeout=float(self.config.get("PED_READ_TIMEOUT_SECONDS", 45))
        backoff=float(self.config.get("PED_RETRY_BACKOFF_SECONDS", 2))
        codibge=params.get("codibge", "desconhecido")

        for attempt in range(1, attempts + 1):
            try:
                response=requests.get(
                    url,
                    params=params,
                    headers={"token":self.token},
                    timeout=(connect_timeout, read_timeout),
                )
                if response.status_code not in self.RETRYABLE_STATUS_CODES:
                    self.last_error=""
                    return response

                self.last_error=f"http_{response.status_code}"
                if attempt == attempts:
                    self.cooldown_until=time.time()+self._cooldown_seconds()
                    return response
                print(
                    f"[ped] codibge={codibge} respondeu HTTP {response.status_code}; "
                    f"tentativa {attempt}/{attempts}, repetindo",
                    flush=True,
                )
            except requests.RequestException as exc:
                self.last_error=f"{type(exc).__name__}:{exc}"
                if attempt == attempts:
                    self.cooldown_until=time.time()+self._cooldown_seconds()
                    print(
                        f"[ped] codibge={codibge} indisponível após {attempts} "
                        f"tentativas: {type(exc).__name__}",
                        flush=True,
                    )
                    return None
                print(
                    f"[ped] codibge={codibge} falhou com {type(exc).__name__}; "
                    f"tentativa {attempt}/{attempts}, repetindo",
                    flush=True,
                )

            time.sleep(backoff * (2 ** (attempt - 1)))

        return None

    def login(self) -> None:
        email,password = credentials(self.config)
        response = requests.post(SGAA_TOKEN_URL, json={"email":email,"password":password}, timeout=30)
        if response.status_code != 200: raise RuntimeError(f"PED login failed {response.status_code}")
        self.token = response.json()["token"]; self.cooldown_until=0.0; self.last_error=""
    def get(self, url: str, params: dict):
        if time.time() < self.cooldown_until:
            self.last_error="cooldown_active"
            return None
        response = self._get_with_retries(url, params)
        if response is None:
            return None
        if response.status_code != 401: return response
        try:
            self.login(); response = self._get_with_retries(url, params)
            if response is None:
                return None
            if response.status_code == 401:
                self.last_error="unauthorized_after_refresh"
                self.cooldown_until=time.time()+self._cooldown_seconds()
                return None
            return response
        except Exception as exc:
            self.last_error=f"auth_refresh:{type(exc).__name__}:{exc}"
            self.cooldown_until=time.time()+self._cooldown_seconds()
            return None

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
