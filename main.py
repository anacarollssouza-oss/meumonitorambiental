import os
import requests
import feedparser
from datetime import datetime, timedelta, timezone
from google import genai

# 1. Configuração de Variáveis de Ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def buscar_publicacoes_mma_ontem():
    # RSS oficial do Diário Oficial da União (Seção 1)
    rss_url = "https://www.in.gov.br/leituraguidada?p_p_id=leituraguidada_WAR_inoutportlet&p_p_lifecycle=0&p_p_state=pop_up&p_p_mode=view&_leituraguidada_WAR_inoutportlet_secao=do1&_leituraguidada_WAR_inoutportlet_rss=true"
    
    feed = feedparser.parse(rss_url)
    
    # Data de ontem (no fuso horário de Brasília - UTC-3)
    fuso_brasilia = timezone(timedelta(hours=-3))
    ontem = (datetime.now(fuso_brasilia) - timedelta(days=1)).date()
    
    publicacoes_mma = []
    
    # Termos para identificar o Ministério do Meio Ambiente e Mudança do Clima
    termos_mma = [
        "MINISTÉRIO DO MEIO AMBIENTE E MUDANÇA DO CLIMA",
        "GABINETE DA MINISTRA",
        "SECRETARIA EXECUTIVA",
        "MMA"
    ]
    
    for entry in feed.entries:
        titulo = entry.get("title", "")
        descricao = entry.get("summary", "")
        link = entry.get("link", "")
        
        # Obter data da publicação no RSS
        published_parsed = entry.get("published_parsed")
        if published_parsed:
            data_pub = datetime(*published_parsed[:6], tzinfo=timezone.utc).astimezone(fuso_brasilia).date()
        else:
            data_pub = ontem  # Fallback caso o feed não informe a data estruturada
            
        texto_completo = f"{titulo} {descricao}".upper()
        
        # Filtra publicações do MMA veiculadas no dia anterior
        if data_pub == ontem and any(termo in texto_completo for termo in termos_mma):
            publicacoes_mma.append(f"Título: {titulo}\nDetalhes: {descricao}\nLink: {link}\n---")
            
    return "\n".join(publicacoes_mma), ontem.strftime("%d/%m/%Y")

def analisar_com_gemini(texto_publicacoes, data_str):
    if not texto_publicacoes.strip():
        return f"📅 *Síntese DOU - MMA ({data_str})*\n\nNão foram encontradas novas publicações do Ministério do Meio Ambiente e Mudança do Clima no DOU nesta data."
    
    if not GEMINI_API_KEY:
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada nas Secrets.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Você é um consultor técnico sênior em direito e licenciamento ambiental no Brasil.
    Analise todas as publicações abaixo extraídas da Seção do Ministério do Meio Ambiente e Mudança do Clima (MMA) no Diário Oficial da União referentes ao dia {data_str}:

    {texto_publicacoes}

    Sintetize todas as portarias, resoluções, decretos, despachos ou instruções normativas em formato Markdown limpo para leitura no Telegram:

    🏛️ **Síntese DOU - MMA ({data_str})**

    Para cada ato normativo/publicação:
    - 📄 **Norma/Tipo:** [Identificação do ato e órgão/secretaria emissora]
    - 📌 **O que estabelece / Impacto:** [Resumo claro do conteúdo normativo, diretrizes, prazos ou impactos operacionais]
    - 🔗 **Link:** [Link direto da publicação]
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text

def enviar_telegram(mensagem):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise ValueError("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não definidos nas Secrets.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    response = requests.post(url, json=payload)
    resultado = response.json()
    
    if not resultado.get("ok"):
        raise Exception(f"Erro na entrega do Telegram: {resultado.get('description')}")
        
    return response.status_code

if __name__ == "__main__":
    dados, data_formatada = buscar_publicacoes_mma_ontem()
    resumo = analisar_com_gemini(dados, data_formatada)
    enviar_telegram(resumo)
    print("Automação do MMA executada com sucesso!")
