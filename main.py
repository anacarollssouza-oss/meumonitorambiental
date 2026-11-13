import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from google import genai

# 1. Configuração de Variáveis de Ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def buscar_publicacoes_mma_hoje():
    # Calcula a data de HOJE no fuso horário de Brasília (UTC-3)
    fuso_brasilia = timezone(timedelta(hours=-3))
    hoje = datetime.now(fuso_brasilia)
    data_url = hoje.strftime("%d-%m-%Y")      # Ex: 13-11-2026
    data_exibicao = hoje.strftime("%d/%m/%Y") # Ex: 13/11/2026

    # URL oficial de consulta do DOU filtrada por Seção 1 (do1), data exata de hoje e órgão (MMA)
    url = (
        f"https://www.in.gov.br/consulta/-/buscar/dou?"
        f"q=%22Minist%C3%A9rio+do+Meio+Ambiente+e+Mudan%C3%A7a+do+Clima%22"
        f"&s=do1&exactDate=personalizado&publishFrom={data_url}&publishTo={data_url}&sortType=0"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9"
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    publicacoes_mma = []

    resultados_html = soup.select("div.resultado")

    if resultados_html:
        for item in resultados_html:
            titulo_tag = item.select_one("h5.title-marker a") or item.select_one("a")
            resumo_tag = item.select_one("p.abstract-marker") or item.select_one("p")
            hierarquia_tag = item.select_one("ol.dou-hierarquia")

            titulo = titulo_tag.get_text(strip=True) if titulo_tag else "Sem título"
            link = titulo_tag["href"] if (titulo_tag and titulo_tag.has_attr("href")) else ""
            if link and not link.startswith("http"):
                link = f"https://www.in.gov.br{link}"

            resumo = resumo_tag.get_text(strip=True) if resumo_tag else ""
            orgao = hierarquia_tag.get_text(" > ", strip=True) if hierarquia_tag else ""

            if "MEIO AMBIENTE" in orgao.upper() or "MEIO AMBIENTE" in titulo.upper() or not orgao:
                publicacoes_mma.append(
                    f"Órgão/Hierarquia: {orgao}\nTítulo: {titulo}\nResumo: {resumo}\nLink: {link}\n---"
                )
    else:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                dados_json = json.loads(script.string)
                if isinstance(dados_json, dict) and "itemListElement" in dados_json:
                    for el in dados_json["itemListElement"]:
                        publicacoes_mma.append(str(el))
            except Exception:
                continue

    print(f"Total de publicações encontradas para {data_exibicao}: {len(publicacoes_mma)}")
    return "\n".join(publicacoes_mma), data_exibicao

def analisar_com_gemini(texto_publicacoes, data_str):
    if not texto_publicacoes.strip():
        return f"📅 *Síntese DOU - MMA ({data_str})*\n\nNão foram encontradas novas publicações do Ministério do Meio Ambiente e Mudança do Clima no DOU de hoje."
    
    if not GEMINI_API_KEY:
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada nas Secrets.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Você é um consultor técnico sênior em direito e licenciamento ambiental no Brasil.
    Analise as publicações abaixo extraídas da Seção 1 do Ministério do Meio Ambiente e Mudança do Clima (MMA) no Diário Oficial da União referentes ao dia {data_str}:

    {texto_publicacoes}

    Sintetize TODAS as portarias, resoluções, decretos, despachos ou instruções normativas encontradas em formato Markdown limpo para leitura no Telegram:

    🏛️ *Síntese DOU - MMA ({data_str})*

    Para cada ato normativo/publicação:
    - 📄 *Norma/Tipo:* [Identificação do ato e secretaria/órgão emissor]
    - 📌 *O que estabelece / Impacto:* [Resumo claro do conteúdo normativo, diretrizes, prazos ou impactos operacionais]
    - 🔗 *Link:* [Link direto da publicação]
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
        payload.pop("parse_mode", None)
        response = requests.post(url, json=payload)
        resultado = response.json()
        if not resultado.get("ok"):
            raise Exception(f"Erro na entrega do Telegram: {resultado.get('description')}")
        
    return response.status_code

if __name__ == "__main__":
    dados, data_formatada = buscar_publicacoes_mma_hoje()
    resumo = analisar_com_gemini(dados, data_formatada)
    enviar_telegram(resumo)
    print("Automação do MMA executada com sucesso!")
