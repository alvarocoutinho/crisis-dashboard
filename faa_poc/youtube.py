"""YouTube retrieval with alert-anchored search windows and relational outputs."""
from __future__ import annotations
import getpass, os
from dataclasses import dataclass, field
from datetime import datetime
import requests
from .constants import YT_BASE, YT_SEARCH_TERMS
from .text import clean_text, classify_themes, comment_quality
from .timeutils import alert_search_window, hours_from_alert, in_event_window, parse_dt

@dataclass
class ApiResult:
    items: list[dict] = field(default_factory=list)
    status: str = "ok"  # ok | quota_exhausted | api_error
    error: str = ""

@dataclass
class QuotaTracker:
    """Per-run quota budget, following the YouTube Data API cost table
    (page updated 2026-10-08): every call costs 1 unit against the daily
    10,000, and ``search.list`` additionally has its OWN limit of 100
    calls/day. Units and searches are therefore budgeted separately.

    v0.3: every request is charged where it is made (including reply lookups
    that were previously uncounted). ``exhausted`` / ``search_exhausted``
    latch once the API itself answers quotaExceeded, so the rest of the run
    stops calling it.
    """
    used: int=0; ceiling: int=2400; high_reserve: int=400; exhausted: bool=False
    searches: int=0; search_ceiling: int=40; search_high_reserve: int=4; search_exhausted: bool=False
    def can_search(self, high: bool) -> bool:
        limit = self.search_ceiling if high else self.search_ceiling - self.search_high_reserve
        return not (self.exhausted or self.search_exhausted) and self.searches + 1 <= limit and self.can_spend(1)
    def charge_search(self) -> None: self.searches += 1; self.used += 1
    def can_spend(self, units:int=1) -> bool: return not self.exhausted and self.used + units <= self.ceiling
    def charge(self, units:int) -> None: self.used += units

def resolve_key(config:dict) -> str|None:
    key=config.get("YOUTUBE_API_KEY") or os.environ.get("YOUTUBE_API_KEY")
    if key: return key
    if not config.get("INTERACTIVE_CREDENTIALS",True): return None
    key=getpass.getpass("YouTube API Key (Enter to skip): ").strip()
    return key or None

def build_queries(alert:dict) -> list[str]:
    event=alert.get("evento",""); terms=next((terms for family,terms in YT_SEARCH_TERMS.items() if family!="default" and family in event),YT_SEARCH_TERMS["default"])
    municipality=(alert.get("municipio") or "").title(); uf=alert.get("uf","")
    return [f"{terms[0]} {municipality} {uf}".strip(),f"{terms[1]} {municipality} {uf}".strip()]

def _request(endpoint:str, params:dict) -> ApiResult:
    response=requests.get(f"{YT_BASE}/{endpoint}",params=params,timeout=20)
    if response.status_code==200: return ApiResult(items=response.json().get("items",[]))
    body=response.text.lower()
    status="quota_exhausted" if response.status_code==403 and "quota" in body else "api_error"
    return ApiResult(status=status,error=f"{response.status_code}:{response.text[:180]}")

def search(query:str, after:str, before:str, key:str, n:int) -> ApiResult:
    result=_request("search",{"part":"snippet","q":query,"type":"video","relevanceLanguage":"pt","regionCode":"BR","publishedAfter":after,"publishedBefore":before,"maxResults":n,"key":key})
    if result.status!="ok": return result
    out=[]
    for item in result.items:
        snippet=item.get("snippet",{}); video_id=item.get("id",{}).get("videoId")
        if video_id: out.append({"video_id":video_id,"title":snippet.get("title", ""),"channel_title":snippet.get("channelTitle", ""),"channel_id":snippet.get("channelId", ""),"published_at":snippet.get("publishedAt", ""),"description_snippet":snippet.get("description", "")[:500]})
    result.items=out; return result

def stats(video_ids:list[str],key:str) -> ApiResult:
    """Estatísticas + descrição completa e tags (v0.3.1).

    ``search.list`` devolve só um trecho curto da descrição; ``videos.list``
    com ``part=snippet`` traz a descrição inteira na MESMA chamada (custo
    de 1 unidade por chamada, até 50 vídeos), usada como evidência municipal.
    """
    if not video_ids: return ApiResult(items=[])
    result=_request("videos",{"part":"snippet,statistics","id":",".join(video_ids[:50]),"key":key})
    if result.status!="ok": return result
    out=[]
    for item in result.items:
        data=item.get("statistics",{}); snip=item.get("snippet",{})
        out.append({"video_id":item.get("id"),"view_count":data.get("viewCount",0),"like_count":data.get("likeCount",0),"comment_count":data.get("commentCount",0),
                    "description":snip.get("description",""),"tags":"|".join(snip.get("tags",[]) or [])})
    result.items=out; return result

def _comment_row(snippet:dict,*,video_id:str,comment_id:str,parent_id:str|None,is_reply:bool) -> dict:
    text=snippet.get("textDisplay",""); clean=clean_text(text)
    return {"comment_id":comment_id,"video_id":video_id,"parent_id":parent_id,"text":text,"text_clean":clean,"author":snippet.get("authorDisplayName", ""),"published_at":snippet.get("publishedAt", ""),"like_count":snippet.get("likeCount",0),"is_reply":is_reply,**classify_themes(clean),**comment_quality(clean)}

def _status_from_response(response) -> tuple[str, str]:
    if response.status_code == 200:
        return "ok", ""
    body = response.text.lower()
    status = "quota_exhausted" if response.status_code == 403 and "quota" in body else "api_error"
    return status, f"{response.status_code}:{response.text[:180]}"

COMMENT_PAGE_SIZE = 100  # API maximum; 1 unit per page regardless of size

def comments(video_id:str,key:str,*,max_pages:int,order:str,quota:QuotaTracker|None=None,window_end:datetime|None=None) -> ApiResult:
    """Retrieve up to ``max_pages`` comment-thread pages plus available replies.

    v0.3 (quota): pages of 100 threads instead of 20 (same 1-unit cost);
    replies come embedded via ``part=snippet,replies`` and ``comments.list``
    is called only when a thread has more replies than the embedded ones;
    threads whose top-level comment is after ``window_end`` skip that extra
    call, because their replies are necessarily later and would be dropped
    by ``comment_links`` anyway. Every request is charged to ``quota``.
    A partial result (budget or API quota ran out) keeps the items collected
    so far and reports ``quota_exhausted`` so the alert is retried later.
    """
    collected=[]; token=None; pages=0; incomplete=""
    def _spend() -> bool:
        if quota is None: return True
        if not quota.can_spend(1): return False
        quota.charge(1); return True
    while pages < max_pages:
        if not _spend(): return ApiResult(items=collected,status="quota_exhausted",error="run_budget_exhausted")
        params={"part":"snippet,replies","videoId":video_id,"maxResults":COMMENT_PAGE_SIZE,"order":order,"key":key}
        if token: params["pageToken"]=token
        response=requests.get(f"{YT_BASE}/commentThreads",params=params,timeout=20)
        status,error=_status_from_response(response)
        if status != "ok":
            if status=="quota_exhausted" and quota is not None: quota.exhausted=True
            return ApiResult(items=collected,status=status,error=error)
        data=response.json(); pages += 1
        for item in data.get("items",[]):
            thread=item.get("snippet",{}); top=thread.get("topLevelComment",{}); snippet=top.get("snippet",{}); cid=top.get("id","")
            if not cid: continue
            collected.append(_comment_row(snippet,video_id=video_id,comment_id=cid,parent_id=None,is_reply=False))
            n_replies=int(thread.get("totalReplyCount",0) or 0)
            if n_replies<=0: continue
            replies=(item.get("replies") or {}).get("comments",[]) or []
            top_published=parse_dt(snippet.get("publishedAt"))
            after_window=window_end is not None and top_published is not None and top_published>window_end
            if len(replies)<n_replies and not after_window:
                if not _spend():
                    incomplete="run_budget_exhausted"
                else:
                    reply_response=requests.get(f"{YT_BASE}/comments",params={"part":"snippet","parentId":cid,"maxResults":100,"key":key},timeout=20)
                    reply_status,reply_error=_status_from_response(reply_response)
                    if reply_status=="ok": replies=reply_response.json().get("items",[])
                    elif reply_status=="quota_exhausted":
                        incomplete=reply_error
                        if quota is not None: quota.exhausted=True
            for reply in replies:
                rs=reply.get("snippet",{}); rid=reply.get("id","")
                if rid: collected.append(_comment_row(rs,video_id=video_id,comment_id=rid,parent_id=cid,is_reply=True))
        token=data.get("nextPageToken")
        if not token: break
    if incomplete: return ApiResult(items=collected,status="quota_exhausted",error=incomplete)
    return ApiResult(items=collected)

def comment_links(comment_rows:list[dict],*,alert:dict,link_scope:str,window_hours:int) -> tuple[list[dict],list[dict],int]:
    canonical, links, skipped=[],[],0
    opened=alert.get("datahoracriacao","")
    for row in comment_rows:
        in_window=in_event_window(row.get("published_at"),opened,window_hours)
        if in_window is False:
            skipped+=1; continue
        canonical.append(row)
        links.append({"comment_id":row["comment_id"],"video_id":row["video_id"],"cod_alerta":alert["cod_alerta"],"alert_opened_at":opened,"hours_from_alert_open":hours_from_alert(row.get("published_at"),opened),"in_event_window":in_window,"link_scope":link_scope,"collected_at":""})
    return canonical,links,skipped

def search_window(alert:dict, config:dict) -> tuple[str,str,str]:
    return alert_search_window(alert.get("datahoracriacao"),pre_hours=config["SEARCH_PRE_ALERT_HOURS"],post_hours=config["SEARCH_POST_ALERT_HOURS"])
