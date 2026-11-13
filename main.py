import os
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from google import genai

# 1. Configuração de Variáveis de Ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def buscar_publicacoes_mma_hoje():
    fuso_brasilia = timezone(timedelta(hours=-3))
    hoje = datetime.now(fuso_brasilia)
    data_url = hoje.strftime("%d-%m-%Y")      # Ex: 13-11-2026
    data_exibicao = hoje.strftime("%d/%m/%Y") # Ex: 13/11/2026

    url = f"https://www.in.gov.br/leiturajornal?secao=do1&data={data_url}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9"
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    script_params = soup.find("script", id="params")

    if not script_params or not script_params.string:
        print("Tag JSON 'params' não encontrada no HTML da edição.")
        return [], data_exibicao

    dados_edicao = json.loads(script_params.string)
    itens_json = dados_edicao.get("jsonArray", [])
    print(f"Total de atos carregados na Seção 1 ({data_exibicao}): {len(itens_json)}")

    publicacoes_mma = []

    for item in itens_json:
        hierarquia = item.get("hierarchyStr", "")
        if "MINISTÉRIO DO MEIO AMBIENTE" in hierarquia.upper():
            titulo = item.get("title", "Sem título")
            resumo = item.get("content", "")
            url_title = item.get("urlTitle", "")
            pagina = item.get("numberPage", "")
            edicao = item.get("editionNumber", "")
            link = f"https://www.in.gov.br/web/dou/-/{url_title}" if url_title else ""

            publicacoes_mma.append({
                "hierarquia": hierarquia,
                "edicao": f"Edição nº {edicao} - Pág. {pagina}",
                "titulo": titulo,
                "resumo": resumo,
                "link": link
            })

    print(f"Publicações do MMA filtradas: {len(publicacoes_mma)}")
    return publicacoes_mma, data_exibicao

def formatar_fallback_direto(publicacoes, data_str):
    linhas = [f"🏛️ *Boletim DOU - MMA ({data_str})*\n_(Resumo direto do DOU — servidor de IA em alta demanda)_\n"]
    for pub in publicacoes:
        linhas.append(
            f"📄 *{pub['titulo']}*\n"
            f"🏢 _{pub['hierarquia']}_\n"
            f"📌 {pub['resumo']}\n"
            f"🔗 {pub['link']}\n"
        )
    return "\n".join(linhas)

def analisar_com_gemini(publicacoes, data_str):
    if not publicacoes:
        return f"📅 *Síntese DOU - MMA ({data_str})*\n\nNão foram encontradas novas publicações do Ministério do Meio Ambiente e Mudança do Clima no DOU de hoje."
    
    if not GEMINI_API_KEY:
        raise ValueError("A chave GEMINI_API_KEY não foi encontrada nas Secrets.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    texto_publicacoes = "\n".join([
        f"Hierarquia: {p['hierarquia']}\nEdição/Página: {p['edicao']}\nTítulo: {p['titulo']}\nTexto/Resumo: {p['resumo']}\nLink: {p['link']}\n---"
        for p in publicacoes
    ])

    prompt = f"""
    Você é um consultor técnico sênior em direito e licenciamento ambiental no Brasil.
    Analise TODAS as publicações abaixo extraídas da Seção 1 do Ministério do Meio Ambiente e Mudança do Clima (MMA) no Diário Oficial da União referentes ao dia {data_str}:

    {texto_publicacoes}

    Sintetize cada publicação encontrada em formato Markdown limpo para leitura no Telegram:

    🏛️ *Síntese DOU - MMA ({data_str})*

    Para cada ato normativo/publicação:
    - 📄 *Ato / Órgão:* [Título da Norma e Órgão/Unidade vinculada]
    - 📌 *Síntese:* [Resumo objetivo do conteúdo e impacto prático/administrativo]
    - 🔗 *Link:* [Link direto da publicação]
    """

    # Descobre dinamicamente os modelos Gemini ativos disponíveis na conta
    modelos_candidatos = ["gemini-3.8-flash"]
    try:
        for m in client.models.list():
            nome_limpo = m.name.replace("models/", "")
            if "gemini" in nome_limpo and "flash" in nome_limpo and nome_limpo not in modelos_candidatos:
                modelos_candidatos.append(nome_limpo)
    except Exception as e:
        print(f"Aviso ao listar modelos: {e}")

    print(f"Modelos válidos identificados para tentativa: {modelos_candidatos}")

    for modelo in modelos_candidatos[:3]:
        for tentativa in range(1, 3):
            try:
                print(f"Gerando síntese com {modelo} (tentativa {tentativa})...")
                response = client.models.generate_content(
                    model=modelo,
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                print(f"Aviso ({modelo} - tentativa {tentativa}): {e}")
                time.sleep(20)

    # Plano B: se toda a API de IA estiver congestionada (503), envia os dados estruturados do DOU sem falhar
    print("Acionando envio direto estruturado (fallback sem IA)...")
    return formatar_fallback_direto(publicacoes, data_str)

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
    publicacoes, data_formatada = buscar_publicacoes_mma_hoje()
    resumo = analisar_com_gemini(publicacoes, data_formatada)
    enviar_telegram(resumo)
    print("Automação do MMA executada com sucesso!")
