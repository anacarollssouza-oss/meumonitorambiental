import os
import requests
import feedparser
from google import genai

# 1. Configuração de Variáveis de Ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def buscar_publicacoes_dou():
    rss_url = "https://www.in.gov.br/leituraguidada?p_p_id=leituraguidada_WAR_inoutportlet&p_p_lifecycle=0&p_p_state=pop_up&p_p_mode=view&_leituraguidada_WAR_inoutportlet_secao=do1&_leituraguidada_WAR_inoutportlet_rss=true"
    
    feed = feedparser.parse(rss_url)
    
    palavras_chave = [
        "MEIO AMBIENTE", "IBAMA", "ICMBIO", "CONAMA", "LICENCIAMENTO", 
        "RESOLUÇÃO", "PORTARIA", "INSTRUÇÃO NORMATIVA", "OUTORGA", "EFLUENTE"
    ]
    
    artigos_relevantes = []
    
    for entry in feed.entries[:30]:
        titulo = entry.get("title", "")
        descricao = entry.get("summary", "")
        link = entry.get("link", "")
        
        texto_completo = f"{titulo} {descricao}".upper()
        if any(kw in texto_completo for kw in palavras_chave):
            artigos_relevantes.append(f"Título: {titulo}\nResumo/Excerto: {descricao}\nLink: {link}\n---")
            
    return "\n".join(artigos_relevantes)

def analisar_com_gemini(texto_publicacoes):
    if not texto_publicacoes.strip():
        return "Nenhuma publicação relevante encontrada no DOU para os temas ambientais hoje."
    
    if not GEMINI_API_KEY:
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada nas Secrets.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Você é um consultor técnico sênior em direito e licenciamento ambiental no Brasil.
    Analise as publicações abaixo extraídas do Diário Oficial da União hoje:

    {texto_publicacoes}

    Se houver portarias, resoluções, decretos ou instruções normativas relevantes sobre meio ambiente, recursos hídricos, efluentes ou licenciamento ambiental:
    Sintetize em formato limpo para leitura rápida:
    - Norma/Órgão: [Número da Norma e Órgão Emissor]
    - O que muda na prática: [Breve explicação do impacto operacional/legal]
    - Link: [Link da publicação]

    Caso nenhuma norma tenha impacto relevante para licenciamento/gestão ambiental, responda exatamente: "Sem atualizações normativas críticas publicadas no DOU hoje."
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
        "disable_web_page_preview": True
    }
    response = requests.post(url, json=payload)
    resultado = response.json()
    
    print(f"Status do envio ao Telegram: {response.status_code}")
    print(f"Resposta do Telegram: {resultado}")
    
    if not resultado.get("ok"):
        raise Exception(f"Erro na entrega do Telegram: {resultado.get('description')}")
        
    return response.status_code

if __name__ == "__main__":
    dados = buscar_publicacoes_dou()
    resumo = analisar_com_gemini(dados)
    enviar_telegram(resumo)
    print("Automação executada com sucesso!")
