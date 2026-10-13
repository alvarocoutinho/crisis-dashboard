"""Constants and CSV schemas for the frozen proof of concept."""
CEMADEN_ALERTS_URL = "https://painelalertas.cemaden.gov.br/wsAlertas2"
PED_BASE_URL = "https://sws.cemaden.gov.br/PED/rest"
SGAA_TOKEN_URL = "https://sgaa.cemaden.gov.br/SGAA/rest/controle-token/tokens"
PED_ACUM_URL = f"{PED_BASE_URL}/pcds-acum/acumulados-recentes"
YT_BASE = "https://www.googleapis.com/youtube/v3"

ARI_WEIGHTS = {"max_acc48hr": 0.30, "max_acc72hr": 0.25, "max_acc96hr": 0.20, "max_acc120hr": 0.25}
ARI_THRESHOLDS = {
    "alto": lambda r: r["max_acc120hr"] >= 150 or r["max_acc48hr"] >= 80,
    "moderado": lambda r: r["max_acc120hr"] >= 80 or r["max_acc48hr"] >= 30,
    "baixo": lambda r: r["max_acc120hr"] > 0,
}

BRAZIL_STATES = {
    "AC":"Acre","AL":"Alagoas","AP":"Amapá","AM":"Amazonas","BA":"Bahia","CE":"Ceará","DF":"Distrito Federal",
    "ES":"Espírito Santo","GO":"Goiás","MA":"Maranhão","MT":"Mato Grosso","MS":"Mato Grosso do Sul","MG":"Minas Gerais",
    "PA":"Pará","PB":"Paraíba","PR":"Paraná","PE":"Pernambuco","PI":"Piauí","RJ":"Rio de Janeiro","RN":"Rio Grande do Norte",
    "RS":"Rio Grande do Sul","RO":"Rondônia","RR":"Roraima","SC":"Santa Catarina","SP":"São Paulo","SE":"Sergipe","TO":"Tocantins",
}
REGIONAL_ALIASES = {
    "PE": ["pernambuco", "grande recife", "rmr", "recife"], "AL": ["alagoas", "maceio"],
    "AM": ["amazonas", "manaus"], "PA": ["para", "pará", "belem", "belém"],
    "MA": ["maranhao", "maranhão", "sao luis", "são luís"], "PB": ["paraiba", "paraíba", "joao pessoa", "joão pessoa"],
    "BA": ["bahia", "salvador"], "CE": ["ceara", "ceará", "fortaleza"],
    "RJ": ["rio de janeiro", "baixada fluminense"], "SP": ["sao paulo", "são paulo", "grande sao paulo"],
}
EVENT_TERMS = {
    "Movimentos de Massa": ["deslizamento", "deslizamentos", "desabamento", "desmoronamento", "queda de barreira", "barreira caiu", "encosta", "morro", "morros", "soterramento", "terra deslizou", "barranco"],
    "Risco Hidrológico": ["enchente", "enchentes", "alagamento", "alagamentos", "inundação", "inundacoes", "inundações", "cheia", "transbordamento", "enxurrada", "chuva forte", "chuvas fortes", "fortes chuvas", "temporal", "rio transbordou"],
    "default": ["chuva", "chuvas", "temporal", "desastre", "emergência", "emergencia", "defesa civil", "alerta", "risco"],
}
IMPACT_TERMS = ["mortes", "mortos", "vidas", "desabrigados", "feridos", "atingiu", "atingem", "estragos", "em alerta", "vitimas", "vítimas", "tragedia", "tragédia", "desaparecidos"]
NEGATIVE_TERMS = ["saudi arabia", "arabia saudita", "vietnam", "alps", "alaska", "ceo", "bilionária", "bilionaria", "anime", "short drama", "drama", "bíblia", "profeta", "wedding", "gameplay", "tutorial", "receita", "gospel", "oração"]
THEMES = {
    "culpa_governanca": r"prefeit|govern|president|lula|psb|joao campos|politic|corrupt|roub|gestao|orcamento|responsab",
    "politizacao_midia": r"globo|jornalism|reporter|imprensa|militant|pix|fazendo o l|vot|esquerd|candidato",
    "vulnerabilidade": r"menos favorecid|coitad|populacao|povo|sofr|area de risco|necessidade|desabrig|desaloj",
    "infraestrutura": r"drenagem|infraestrutura|escoamento|urbanizacao|obra|contencao|mudancas climaticas",
    "recorrencia": r"todo ano|sempre foi assim|nada muda|cronico|normal isso|mais de 10 anos",
    "risco_saude_alerta": r"risco|leptospirose|alerta|avisando|vai piorar|se cuidem|defesa civil|cemaden",
    "emocao_religiosidade": r"deus|senhor|misericord|traged|horrorizad|coracao|tribulacao",
    "conhecimento_local": r"sou de|moro em|conhecido|onde moro|nesta regiao|aqui em",
}
YT_SEARCH_TERMS = {
    "Movimentos de Massa": ["deslizamento", "desabamento", "morro", "encosta"],
    "Risco Hidrológico": ["enchente", "alagamento", "inundação", "chuva forte"],
    "default": ["desastre", "emergência", "defesa civil"],
}

ALERT_FIELDS = ["cod_alerta","datahoracriacao","ult_atualizacao","codibge","evento","nivel","status","uf","municipio","latitude","longitude","collected_at"]
ACUM_FIELDS = ["cod_alerta","alert_municipio","alert_uf","alert_evento","alert_nivel","codestacao","codibge","id_estacao","datahora","acc1hr","acc3hr","acc6hr","acc12hr","acc24hr","acc48hr","acc72hr","acc96hr","acc120hr"]
ACUM_SUMMARY_FIELDS = ["cod_alerta","alert_municipio","alert_uf","alert_evento","alert_nivel","n_stations","max_acc24hr","max_acc48hr","max_acc72hr","max_acc96hr","max_acc120hr","mean_acc24hr","mean_acc48hr","mean_acc72hr","mean_acc120hr","antecedent_rain_index","antecedent_rain_class"]
VIDEO_CANONICAL_FIELDS = ["video_id","title","channel_title","channel_id","published_at","view_count","like_count","comment_count","description_snippet","description","tags","first_seen_at"]
VIDEO_LINK_FIELDS = ["video_id","cod_alerta","alert_municipio","alert_uf","alert_codibge","alert_evento","alert_nivel","alert_opened_at","search_query","search_published_after","search_published_before","search_window_source","relevance_score","geo_score","event_score","geo_match_type","link_scope","is_municipal_evidence","relevance_reasons","municipal_evidence","collected_at"]
COMMENT_CANONICAL_FIELDS = ["comment_id","video_id","parent_id","text","text_clean","author","published_at","like_count","is_reply",*THEMES.keys(),"comment_length","contains_url","emoji_only","low_information","topic_id","first_seen_at"]
COMMENT_LINK_FIELDS = ["comment_id","video_id","cod_alerta","alert_opened_at","hours_from_alert_open","in_event_window","link_scope","collected_at"]
REJECTED_FIELDS = ["video_id","title","channel_title","cod_alerta","alert_municipio","alert_uf","alert_codibge","search_query","search_published_after","search_published_before","relevance_score","geo_score","event_score","geo_match_type","rejection_reason","collected_at"]
VISIBILITY_FIELDS = ["cod_alerta","alert_municipio","alert_uf","alert_codibge","alert_evento","alert_nivel","ari_class","ari_index","search_published_after","search_published_before","search_window_source","n_candidates","n_relevant_videos","n_direct_municipal_videos","n_broader_videos","status","is_substantive_absence","rejection_reasons_summary","collected_at"]
PROCESSING_STATUS_FIELDS = ["cod_alerta","first_seen_at","last_seen_at","last_attempt_at","ped_status","youtube_status","comment_status","last_error","is_complete"]
ACTIVE_ALERT_FIELDS = ["cod_alerta","municipio","uf","evento","nivel","alert_opened_at","first_collected_at","last_refreshed_at","tracking_day","ari_class","status"]
ACTIVE_VIDEO_FIELDS = ["tracking_key","cod_alerta","alert_municipio","alert_uf","video_id","alert_opened_at","link_scope","first_collected_at","last_refreshed_at","refresh_count","status"]
RUN_LOG_FIELDS = ["run_at","mode","duration_s","n_alerts_fetched","n_alerts_processed","n_videos","n_comments","n_comments_skipped_outside_event_window","n_visibility_observations","n_substantive_absence_observations","n_ari_mismatches","quota_used","ped_required","ped_ok","youtube_required","youtube_ok","errors"]
