"""Frozen proof-of-concept orchestrator.

It proves auditable collection and linkage, not behavioral causality or
population-level alert receipt. Municipal media absence is logged as an
observation only when the API search completed in an alert-anchored window.
"""
from __future__ import annotations
from datetime import timedelta
from typing import Any
from . import cemaden, ped, storage, youtube
from .config import build_config
from .constants import *
from .evidence import is_municipal, municipal_evidence
from .geo import score_video
from .timeutils import parse_dt, utcnow

VALID={"FULL_PIPELINE","CEMADEN_ONLY","CEMADEN_PED_ONLY","YOUTUBE_ONLY","COMMENT_REFRESH_ONLY"}
def needs_ped(mode:str)->bool: return mode in {"FULL_PIPELINE","CEMADEN_PED_ONLY"}
def needs_yt(mode:str)->bool: return mode in {"FULL_PIPELINE","YOUTUBE_ONLY","COMMENT_REFRESH_ONLY"}

def _status_row(status:dict[str,dict], cod:str, now_iso:str)->dict:
    row=status.get(cod,{"cod_alerta":cod,"first_seen_at":now_iso,"last_seen_at":now_iso,"last_attempt_at":"","ped_status":"not_requested","youtube_status":"not_requested","comment_status":"not_requested","last_error":"","is_complete":False})
    row["last_seen_at"]=now_iso; row["last_attempt_at"]=now_iso; status[cod]=row; return row

def _register_alert(alert:dict, active:list[dict], ari_class:str)->None:
    code=str(alert["cod_alerta"])
    if any(str(row.get("cod_alerta"))==code for row in active): return
    now=storage.utcnow_iso()
    active.append({"cod_alerta":code,"municipio":alert.get("municipio",""),"uf":alert.get("uf",""),"evento":alert.get("evento",""),"nivel":alert.get("nivel",""),"alert_opened_at":alert.get("datahoracriacao",""),"first_collected_at":now,"last_refreshed_at":now,"tracking_day":0,"ari_class":ari_class,"status":"open"})

def _register_video_links(alert:dict, links:list[dict], active:list[dict])->None:
    now=storage.utcnow_iso(); existing={row["tracking_key"] for row in active}
    for link in links:
        key=f"{alert['cod_alerta']}::{link['video_id']}"
        if key in existing: continue
        active.append({"tracking_key":key,"cod_alerta":alert["cod_alerta"],"alert_municipio":alert.get("municipio",""),"alert_uf":alert.get("uf",""),"video_id":link["video_id"],"alert_opened_at":alert.get("datahoracriacao",""),"link_scope":link["link_scope"],"first_collected_at":now,"last_refreshed_at":now,"refresh_count":0,"status":"active"}); existing.add(key)

def _advance(active_alerts:list[dict], active_videos:list[dict], config:dict)->None:
    now=utcnow(); limit=config["ALERT_TRACKING_DAYS"]
    open_alerts=set()
    for row in active_alerts:
        if row.get("status")!="open": continue
        opened=parse_dt(row.get("alert_opened_at")) or parse_dt(row.get("first_collected_at"))
        if not opened: continue
        day=max(0,(now-opened).days); row["tracking_day"]=day; row["last_refreshed_at"]=now.isoformat()
        if day>=limit: row["status"]="closed"
        else: open_alerts.add(str(row["cod_alerta"]))
    for row in active_videos:
        if row.get("status")=="active" and str(row.get("cod_alerta")) not in open_alerts: row["status"]="closed"

def _visibility(alert:dict,*,ari_summary:dict|None,after:str,before:str,source:str,candidates:int,links:list[dict],rejected:list[dict],outcome:str,now_iso:str)->dict:
    direct=sum(bool(link.get("is_municipal_evidence")) for link in links); broader=len(links)-direct
    if outcome!="ok": status=outcome; substantive=False
    elif direct: status="municipal_video_found"; substantive=False
    elif broader: status="broader_video_found_no_municipal"; substantive=False
    elif rejected: status="no_relevant_videos"; substantive=source=="alert_anchored"
    else: status="no_results"; substantive=source=="alert_anchored"
    return {"cod_alerta":alert["cod_alerta"],"alert_municipio":alert.get("municipio",""),"alert_uf":alert.get("uf",""),"alert_codibge":alert.get("codibge",""),"alert_evento":alert.get("evento",""),"alert_nivel":alert.get("nivel",""),"ari_class":(ari_summary or {}).get("antecedent_rain_class",""),"ari_index":(ari_summary or {}).get("antecedent_rain_index",""),"search_published_after":after,"search_published_before":before,"search_window_source":source,"n_candidates":candidates,"n_relevant_videos":len(links),"n_direct_municipal_videos":direct,"n_broader_videos":broader,"status":status,"is_substantive_absence":substantive,"rejection_reasons_summary":";".join(r.get("rejection_reason","") for r in rejected)[:300],"collected_at":now_iso}

def _collect_for_alert(alert:dict,key:str,quota:youtube.QuotaTracker,config:dict,video_index:set[str],comment_index:set[str],comment_link_index:set[tuple[str,str]]):
    """Search once per alert, then persist canonical entities and explicit links.

    Search failure and comment failure are tracked separately: a video can remain
    valid evidence of media visibility even when comments are disabled or unavailable.
    """
    after,before,source=youtube.search_window(alert,config)
    high=cemaden.is_high_priority(alert.get("nivel")); now_iso=storage.utcnow_iso()
    result={"canonical":[],"links":[],"comments":[],"comment_links":[],"rejected":[],"candidate_rows":[],"candidates":0,"skipped":0,"outcome":"ok","comment_outcome":"ok","after":after,"before":before,"source":source}
    seen_videos={}
    for query in youtube.build_queries(alert):
        if not quota.can_search(high):
            result["outcome"]="quota_exhausted"; break
        response=youtube.search(query,after,before,key,config["MAX_VIDEOS_PER_ALERT"])
        quota.charge_search()
        if response.status != "ok":
            # search.list tem limite diário próprio: recusa aqui bloqueia só buscas
            if response.status=="quota_exhausted": quota.search_exhausted=True
            result["outcome"] = response.status; break
        for video in response.items:
            seen_videos.setdefault(video["video_id"], {**video, "search_query": query})
    candidates=list(seen_videos.values())
    result["candidates"]=len(candidates)
    if result["outcome"] != "ok": return result

    if candidates and not quota.can_spend(1):
        result["outcome"]="quota_exhausted"; return result
    stats_response=youtube.stats([video["video_id"] for video in candidates],key)
    quota.charge(1 if candidates else 0)
    if stats_response.status != "ok":
        if stats_response.status=="quota_exhausted": quota.exhausted=True
        result["outcome"]=stats_response.status
        return result
    stats={row["video_id"]:row for row in stats_response.items}

    accepted=[]; scores={}
    for video in candidates:
        score=score_video(video,alert,config); vid=video["video_id"]; scores[vid]=score
        base={"video_id":vid,"cod_alerta":alert["cod_alerta"],"alert_municipio":alert.get("municipio",""),"alert_uf":alert.get("uf",""),"alert_codibge":alert.get("codibge",""),"alert_evento":alert.get("evento",""),"alert_nivel":alert.get("nivel",""),"alert_opened_at":alert.get("datahoracriacao",""),"search_query":video["search_query"],"search_published_after":after,"search_published_before":before,"search_window_source":source,"relevance_score":score["relevance_score"],"geo_score":score["geo_score"],"event_score":score["event_score"],"geo_match_type":score["geo_match_type"],"link_scope":score["link_scope"],"is_municipal_evidence":score["is_municipal_evidence"],"relevance_reasons":score["relevance_reasons"],"collected_at":now_iso}
        if not score["is_relevant"]:
            result["rejected"].append({**base,"title":video.get("title",""),"channel_title":video.get("channel_title",""),"rejection_reason":score["rejection_reason"]})
            continue
        accepted.append((base,video))
    opened_dt=parse_dt(alert.get("datahoracriacao"))
    window_end=opened_dt+timedelta(hours=config["EVENT_WINDOW_HOURS"]) if opened_dt else None
    for base,video in accepted:
        vid=base["video_id"]
        # v0.3.1: o vídeo nomeia o município? (título + descrição completa)
        base["municipal_evidence"]=municipal_evidence(alert.get("municipio",""),alert.get("uf",""),
            title=video.get("title",""),description=stats.get(vid,{}).get("description","") or video.get("description_snippet",""))
    # v0.3.2: vídeos que nomeiam o município entram antes dos de escopo
    # estadual/regional. Ordenar só pelo score deixava cobertura estadual
    # ocupar as vagas de MAX_VIDEOS_PER_ALERT (auditoria de 13/10/2026).
    accepted.sort(key=lambda pair:(is_municipal(pair[0]["municipal_evidence"]),pair[0]["geo_match_type"]=="municipality_direct",float(pair[0]["relevance_score"]),int(stats.get(pair[0]["video_id"],{}).get("comment_count",0) or 0),int(stats.get(pair[0]["video_id"],{}).get("view_count",0) or 0)),reverse=True)

    # v0.3.3: todos os candidatos (aceitos, excedentes e rejeitados) com os
    # atributos usados na decisão, para recalibrar os filtros depois sem
    # refazer buscas (separa recuperação de decisão).
    rank={pair[0]["video_id"]:i for i,pair in enumerate(accepted,1)}
    for video in candidates:
        vid=video["video_id"]; sc=scores[vid]; st=stats.get(vid,{})
        pos=rank.get(vid)
        result["candidate_rows"].append({
            "video_id":vid,"cod_alerta":alert["cod_alerta"],"alert_municipio":alert.get("municipio",""),"alert_uf":alert.get("uf",""),
            "alert_codibge":alert.get("codibge",""),"alert_evento":alert.get("evento",""),"alert_opened_at":alert.get("datahoracriacao",""),
            "search_query":video.get("search_query",""),"search_published_after":after,"search_published_before":before,
            "published_at":video.get("published_at",""),"channel_id":video.get("channel_id",""),"channel_title":video.get("channel_title",""),
            "title":video.get("title",""),"description_snippet":video.get("description_snippet",""),"description":st.get("description",""),
            "tags":st.get("tags",""),"view_count":st.get("view_count",""),"comment_count":st.get("comment_count",""),
            **{k:sc[k] for k in ("relevance_score","geo_score","event_score","geo_match_type","relevance_reasons","rejection_reason")},
            "municipal_evidence":municipal_evidence(alert.get("municipio",""),alert.get("uf",""),title=video.get("title",""),
                                                     description=st.get("description","") or video.get("description_snippet","")),
            "decision":("rejeitado" if pos is None else "selecionado" if pos<=config["MAX_VIDEOS_PER_ALERT"] else "aceito_excedente"),
            "rank":pos or "","filter_version":FILTER_VERSION,"collected_at":now_iso})

    for base,video in accepted[:config["MAX_VIDEOS_PER_ALERT"]]:
        vid=base["video_id"]
        result["links"].append(base)
        if vid not in video_index:
            result["canonical"].append({**{k:v for k,v in video.items() if k != "search_query"},**stats.get(vid,{}),"first_seen_at":now_iso})
            video_index.add(vid)
        comment_response=youtube.comments(vid,key,max_pages=config["MAX_COMMENT_PAGES"],order=config["YT_COMMENT_ORDER"],quota=quota,window_end=window_end)
        if comment_response.status != "ok":
            # v0.3: keep whatever was collected before the failure (partial
            # pages are still valid observations) but report the outcome so
            # the orchestrator retries the alert instead of marking it done.
            result["comment_outcome"]=comment_response.status
        canonical,links,skipped=youtube.comment_links(comment_response.items,alert=alert,link_scope=base["link_scope"],window_hours=config["EVENT_WINDOW_HOURS"])
        result["skipped"] += skipped
        for row in canonical:
            if row["comment_id"] not in comment_index:
                row["first_seen_at"]=now_iso; result["comments"].append(row); comment_index.add(row["comment_id"])
        for link in links:
            link["collected_at"]=now_iso; pair=(link["comment_id"],str(link["cod_alerta"]))
            if pair not in comment_link_index:
                result["comment_links"].append(link); comment_link_index.add(pair)
    return result

def _refresh(key:str,active:list[dict],config:dict,comment_index:set[str],comment_link_index:set[tuple[str,str]]):
    new=skipped=0; now_iso=storage.utcnow_iso()
    for record in active:
        if record.get("status")!="active": continue
        response=youtube.comments(record["video_id"],key,max_pages=config["MAX_COMMENT_PAGES"],order=config["YT_COMMENT_ORDER"])
        if response.status!="ok": continue
        alert={"cod_alerta":record["cod_alerta"],"datahoracriacao":record.get("alert_opened_at","")}
        canonical,links,dropped=youtube.comment_links(response.items,alert=alert,link_scope=record.get("link_scope",""),window_hours=config["EVENT_WINDOW_HOURS"]); skipped+=dropped
        for row in canonical:
            if row["comment_id"] not in comment_index: row["first_seen_at"]=now_iso; storage.append_csv(config,"youtube_comments_canonical.csv",[row],COMMENT_CANONICAL_FIELDS); comment_index.add(row["comment_id"]); new+=1
        fresh_links=[]
        for link in links:
            pair=(link["comment_id"],str(link["cod_alerta"])); link["collected_at"]=now_iso
            if pair not in comment_link_index: fresh_links.append(link); comment_link_index.add(pair)
        storage.append_csv(config,"youtube_alert_comment_links.csv",fresh_links,COMMENT_LINK_FIELDS)
        record["last_refreshed_at"]=now_iso; record["refresh_count"]=int(record.get("refresh_count",0))+1
    return new,skipped

def run(overrides:dict[str,Any]|None=None)->dict:
    runtime_overrides=dict(overrides or {})
    alerts_override=runtime_overrides.pop("ALERTS_OVERRIDE",None)
    config=build_config(runtime_overrides); mode=config["MODE"].upper()
    if mode not in VALID: raise ValueError(f"Invalid MODE: {mode}")
    started=storage.utcnow(); errors=[]; totals={"fetched":0,"processed":0,"videos":0,"comments":0,"skipped":0,"visibility":0,"substantive_absence":0,"ari_mismatches":0}
    storage.out_dir(config); ped_required=needs_ped(mode); yt_required=needs_yt(mode); ped_ok=yt_ok=False; client=None; key=None
    if ped_required:
        try: client=ped.PedClient(config); client.login(); ped_ok=True
        except Exception as exc: errors.append(f"ped_login:{exc}"); client=None
    if yt_required:
        key=youtube.resolve_key(config); yt_ok=bool(key)
        if not key: errors.append("youtube_key:missing")
    status=storage.load_status(config); active_alerts=storage.load_active_alerts(config); active_videos=storage.load_active_videos(config)
    video_index=storage.build_set_index(config,"youtube_videos_canonical.csv","video_id"); comment_index=storage.build_set_index(config,"youtube_comments_canonical.csv","comment_id"); comment_link_index=storage.build_pair_index(config,"youtube_alert_comment_links.csv","comment_id","cod_alerta")
    quota=youtube.QuotaTracker(ceiling=config["YT_QUOTA_CEILING"],high_reserve=config["YT_QUOTA_HIGH_RESERVE"],search_ceiling=config.get("YT_SEARCH_CEILING",40),search_high_reserve=config.get("YT_SEARCH_HIGH_RESERVE",4))
    if mode=="COMMENT_REFRESH_ONLY":
        if key: totals["comments"],totals["skipped"]=_refresh(key,active_videos,config,comment_index,comment_link_index)
        _advance(active_alerts,active_videos,config); storage.save_active_alerts(config,active_alerts); storage.save_active_videos(config,active_videos)
        return _finish(config,started,mode,totals,quota,ped_required,ped_ok,yt_required,yt_ok,errors)
    if alerts_override is not None:
        # O orquestrador principal já consultou/reconciliou o CEMADEN e envia
        # somente os alertas devidos. Isso garante seleção por ID e também
        # permite acompanhar alertas que já migraram para extended_window.
        alerts=[dict(alert) for alert in alerts_override]
    else:
        try: alerts=cemaden.fetch_alerts(config)
        except Exception as exc: alerts=[]; errors.append(f"cemaden_fetch:{exc}")
    totals["fetched"]=len(alerts); now_iso=storage.utcnow_iso(); storage.append_csv(config,"alerts_log.csv",[{**a,"collected_at":now_iso} for a in alerts],ALERT_FIELDS)
    for alert in alerts[:config["MAX_ALERTS"]] if config.get("MAX_ALERTS") else alerts:
        cod=str(alert["cod_alerta"])
        state=_status_row(status,cod,now_iso)
        totals["processed"]+=1
        summary={}; ari_class=""
        force=bool(config.get("FORCE_REPROCESS",False))
        run_ped=ped_required and (force or state.get("ped_status")!="success")
        run_yt=yt_required and (force or state.get("youtube_status")!="ok")

        if run_ped:
            if client:
                client.last_error=""
                ped_failure_detail=""
                print(f"[faa_poc] PED alert={cod} codibge={alert.get('codibge','')}", flush=True)
                try:
                    rows,summary=ped.fetch_accumulations(alert,client)
                except Exception as exc:
                    # Uma falha de payload/parse em um município não deve
                    # cancelar a coleta dos demais alertas.
                    rows,summary=[],{}
                    detail=f"{type(exc).__name__}:{exc}"
                    errors.append(f"ped:{cod}:{detail}"[:500])
                    ped_failure_detail=detail
                if summary:
                    storage.append_csv(config,"rainfall_accumulations.csv",rows,ACUM_FIELDS)
                    storage.append_csv(config,"rainfall_accumulation_summary.csv",[summary],ACUM_SUMMARY_FIELDS)
                    ari_class=summary["antecedent_rain_class"]
                    state["ped_status"]="success"
                    state["last_error"]=""
                    totals["ari_mismatches"]+=int(ari_class=="alto" and "alto" not in (alert.get("nivel") or "").lower())
                else:
                    state["ped_status"]="failed"
                    client_error=getattr(client,"last_error","") or ped_failure_detail
                    if client_error:
                        state["last_error"]=f"ped_error:{client_error}"[:500]
                        if not ped_failure_detail:
                            errors.append(f"ped:{cod}:{client_error}"[:500])
                    else:
                        state["last_error"]="ped_no_accumulations"
            else:
                state["ped_status"]="unavailable"; state["last_error"]="ped_credentials_or_login_unavailable"

        _register_alert(alert,active_alerts,ari_class)

        if run_yt and key and (quota.exhausted or quota.search_exhausted):
            # v0.3: the API already answered quotaExceeded in this run; further
            # calls would fail too. Defer explicitly — never record as silence.
            state["youtube_status"]="deferred_quota"; state["comment_status"]="deferred_quota"
            state["last_error"]="youtube_quota_exhausted_earlier_in_run"
        elif run_yt:
            if key:
                result=_collect_for_alert(alert,key,quota,config,video_index,comment_index,comment_link_index)
                storage.append_csv(config,"youtube_videos_canonical.csv",result["canonical"],VIDEO_CANONICAL_FIELDS)
                storage.append_csv(config,"youtube_alert_video_links.csv",result["links"],VIDEO_LINK_FIELDS)
                storage.append_csv(config,"youtube_comments_canonical.csv",result["comments"],COMMENT_CANONICAL_FIELDS)
                storage.append_csv(config,"youtube_alert_comment_links.csv",result["comment_links"],COMMENT_LINK_FIELDS)
                storage.append_csv(config,"rejected_videos.csv",result["rejected"],REJECTED_FIELDS)
                storage.append_csv(config,"youtube_candidates.csv",result["candidate_rows"],CANDIDATE_FIELDS)
                _register_video_links(alert,result["links"],active_videos)
                state["youtube_status"]=result["outcome"]
                state["comment_status"]=("not_applicable" if not result["links"] else ("success" if result["comment_outcome"]=="ok" else result["comment_outcome"]))
                obs=_visibility(alert,ari_summary=summary,after=result["after"],before=result["before"],source=result["source"],candidates=result["candidates"],links=result["links"],rejected=result["rejected"],outcome=result["outcome"],now_iso=now_iso)
                storage.append_csv(config,"visibility_observations.csv",[obs],VISIBILITY_FIELDS)
                totals["videos"]+=len(result["links"])
                totals["comments"]+=len(result["comments"])
                totals["skipped"]+=result["skipped"]
                totals["visibility"]+=1
                totals["substantive_absence"]+=int(bool(obs["is_substantive_absence"]))
            else:
                state["youtube_status"]="unavailable"
                state["comment_status"]="unavailable"
                state["last_error"]="youtube_key_missing"

        state["is_complete"]=(not ped_required or state["ped_status"]=="success") and (not yt_required or (state["youtube_status"]=="ok" and state["comment_status"] in {"success","not_applicable"}))
    _advance(active_alerts,active_videos,config); storage.save_status(config,status); storage.save_active_alerts(config,active_alerts); storage.save_active_videos(config,active_videos)
    return _finish(config,started,mode,totals,quota,ped_required,ped_ok,yt_required,yt_ok,errors)

def _finish(config,started,mode,totals,quota,ped_required,ped_ok,yt_required,yt_ok,errors):
    duration=round((storage.utcnow()-started).total_seconds(),2)
    storage.append_csv(config,"pipeline_runs.csv",[{"run_at":started.isoformat(),"mode":mode,"duration_s":duration,"n_alerts_fetched":totals["fetched"],"n_alerts_processed":totals["processed"],"n_videos":totals["videos"],"n_comments":totals["comments"],"n_comments_skipped_outside_event_window":totals["skipped"],"n_visibility_observations":totals["visibility"],"n_substantive_absence_observations":totals["substantive_absence"],"n_ari_mismatches":totals["ari_mismatches"],"quota_used":quota.used,"ped_required":ped_required,"ped_ok":ped_ok,"youtube_required":yt_required,"youtube_ok":yt_ok,"errors":";".join(errors)[:500]}],RUN_LOG_FIELDS)
    return {"mode":mode,"duration_s":duration,"totals":totals,"errors":errors,"quota_used":quota.used,"quota_exhausted":quota.exhausted,"searches_used":quota.searches,"search_exhausted":quota.search_exhausted}
