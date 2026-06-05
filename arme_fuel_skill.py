# arme_fuel_skill.py (com variações baseadas em dados históricos do mês anterior)
import os
import re
import requests
import feedparser
from datetime import datetime
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost

# ============================================================
# Credenciais – lidas do ambiente
# ============================================================
WP_USER = os.environ.get("WP_USERNAME", "")
WP_PASS = os.environ.get("WP_PASSWORD", "")
if not WP_USER or not WP_PASS:
    print("❌ Credenciais em falta.")
    exit(1)

# ============================================================
# Base de dados históricos (preços já conhecidos)
# ============================================================
PRECOS_HISTORICOS = {
    2026: {
        5: {  # Maio 2026
            "Gasolina": "151.10",
            "Gasóleo Normal": "126.90",
            "Gasóleo Eletricidade": "96.90",
            "Gasóleo Marinha": "90.60",
            "Petróleo": "160.60",
            "Fuel 380": "69.30",
            "Fuel 180": "72.40",
            "Butano Granel": "144.30"
        },
        4: {  # Abril 2026
            "Gasolina": "139.89",
            "Gasóleo Normal": "117.52",
            "Gasóleo Eletricidade": "95.04",
            "Gasóleo Marinha": "86.32",
            "Petróleo": "148.66",
            "Fuel 380": "67.92",
            "Fuel 180": "70.99",
            "Butano Granel": "144.30"
        }
    }
}

# ============================================================
# Extração dos preços a partir do HTML do artigo
# ============================================================
def extrair_precos_do_html(url):
    print(f"📄 A extrair preços de {url}")
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        texto = re.sub(r'\s+', ' ', resp.text)
        precos = {}
        padroes = {
            "Gasolina": r"Gasolina passa a ser vendida a ([\d.,]+) ESC/L",
            "Gasóleo Normal": r"Gasóleo Normal, a ([\d.,]+) ESC/L",
            "Gasóleo Eletricidade": r"Gasóleo para Eletricidade, a ([\d.,]+) ESC/L",
            "Gasóleo Marinha": r"Gasóleo Marinha, a ([\d.,]+) ESC/L",
            "Petróleo": r"Petróleo, ([\d.,]+) ESC/L",
            "Fuel 380": r"Fuel\s+380[^0-9]*([\d.,]+)\s*ESC/Kg",
            "Fuel 180": r"Fuel\s+180[^0-9]*([\d.,]+)\s*ESC/Kg",
            "Butano Granel": r"Gás Butano (?:passa a custar|mantem-se) a granel ([\d.,]+) ESC/Kg"
        }
        for prod, regex in padroes.items():
            m = re.search(regex, texto, re.IGNORECASE)
            if m:
                precos[prod] = m.group(1).replace(',', '.')
                print(f"   ✓ {prod}: {precos[prod]}")
            else:
                print(f"   ✗ {prod}: não encontrado")
        if precos and len(precos) >= 5:
            return precos
    except Exception as e:
        print(f"⚠️ Erro ao extrair HTML: {e}")
    return None

# ============================================================
# Obter artigo do mês actual (web)
# ============================================================
def obter_precos_web(ano, mes):
    meses = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"]
    mes_nome = meses[mes-1]
    titulo_alvo = f"ARME atualiza preços máximos dos combustíveis para {mes_nome} {ano}"
    print(f"🔎 A procurar artigo: '{titulo_alvo}'")

    # Estratégia 1: Feed RSS
    feed_url = "https://www.arme.cv/feed"
    try:
        feed = feedparser.parse(feed_url, agent="Mozilla/5.0")
        print(f"📡 Feed RSS: {len(feed.entries)} entradas encontradas.")
        for entry in feed.entries:
            if titulo_alvo.lower() in entry.title.lower():
                print(f"✅ Artigo encontrado via RSS: {entry.link}")
                return extrair_precos_do_html(entry.link)
    except Exception as e:
        print(f"⚠️ Erro no feed RSS: {e}")

    # Estratégia 2: Pesquisa no site
    search_url = f"https://www.arme.cv/index.php?option=com_search&view=search&searchword=preços+máximos"
    try:
        resp = requests.get(search_url, timeout=20)
        resp.raise_for_status()
        padrao = r'<a href="(index\.php\?option=com_content&amp;view=article&amp;id=\d+:[^"]+)".*?>(.*?)</a>'
        candidatos = []
        for link, tit in re.findall(padrao, resp.text, re.IGNORECASE):
            if "preços" in tit.lower() and mes_nome in tit.lower():
                url_artigo = "https://www.arme.cv/" + link.replace('&amp;', '&')
                candidatos.append((tit, url_artigo))
        if candidatos:
            tit, url = candidatos[0]
            print(f"✅ Artigo encontrado via pesquisa: {url}")
            return extrair_precos_do_html(url)
    except Exception as e:
        print(f"⚠️ Erro na pesquisa: {e}")

    # Estratégia 3: URL construída com ID (para meses recentes)
    if ano == 2026:
        if mes == 6:
            url_construida = f"https://www.arme.cv/index.php?option=com_content&view=article&id=1360:arme-atualiza-precos-maximos-dos-combustiveis-para-junho-2026&catid=79&Itemid=878"
            print(f"🔎 Tentando URL construída (ID=1360): {url_construida}")
            try:
                resp = requests.get(url_construida, timeout=20)
                if resp.status_code == 200 and "preços" in resp.text.lower():
                    print(f"✅ Artigo encontrado via URL construída!")
                    return extrair_precos_do_html(url_construida)
            except:
                pass
        else:
            # Tenta IDs sequenciais a partir do último conhecido
            id_base = 1360
            for tentativa in range(id_base, id_base + 10):
                url_tentativa = f"https://www.arme.cv/index.php?option=com_content&view=article&id={tentativa}:arme-atualiza-precos-maximos-dos-combustiveis-para-{mes_nome}-{ano}&catid=79&Itemid=878"
                print(f"🔎 Tentando ID {tentativa}...")
                try:
                    resp = requests.get(url_tentativa, timeout=10)
                    if resp.status_code == 200 and mes_nome in resp.text.lower():
                        print(f"✅ Artigo encontrado com ID {tentativa}")
                        return extrair_precos_do_html(url_tentativa)
                except:
                    continue

    print(f"❌ Não foi possível encontrar artigo para {mes_nome} {ano}")
    return None

# ============================================================
# Obter preços (com controlo de uso de web vs histórico)
# ============================================================
def obter_precos(ano, mes, usar_web=True):
    # Se for o mês anterior ao actual, usamos sempre os dados históricos (para garantir variação)
    hoje = datetime.now()
    mes_atual = hoje.month
    ano_atual = hoje.year
    if (ano == ano_atual and mes == mes_atual - 1) or (ano == ano_atual - 1 and mes == 12 and mes_atual == 1):
        # É o mês anterior – pegar do histórico se disponível
        if ano in PRECOS_HISTORICOS and mes in PRECOS_HISTORICOS[ano]:
            print(f"📦 Usando dados históricos para {mes}/{ano} (mês anterior).")
            return PRECOS_HISTORICOS[ano][mes].copy()
        else:
            print(f"⚠️ Dados históricos não disponíveis para {mes}/{ano}. Variações ficarão vazias.")
            return None

    # Para o mês actual, tenta web primeiro
    if usar_web:
        precos = obter_precos_web(ano, mes)
        if precos:
            print(f"✅ Preços de {mes}/{ano} obtidos da web.")
            return precos

    # Fallback para histórico (qualquer mês)
    if ano in PRECOS_HISTORICOS and mes in PRECOS_HISTORICOS[ano]:
        print(f"📦 Usando dados históricos para {mes}/{ano} (fallback).")
        return PRECOS_HISTORICOS[ano][mes].copy()
    return None

# ============================================================
# Cálculo das variações
# ============================================================
def calcular_variacoes(atual, anterior):
    variacoes = {}
    for prod in atual:
        if prod in anterior:
            try:
                a = float(atual[prod])
                ant = float(anterior[prod])
                diff = a - ant
                perc = (diff / ant) * 100 if ant != 0 else 0
                variacoes[prod] = {
                    'perc': f"{perc:+.2f}%".replace('.', ','),
                    'diff': f"{diff:+.2f}".replace('.', ',')
                }
            except:
                variacoes[prod] = {'perc': '—', 'diff': '—'}
        else:
            variacoes[prod] = {'perc': '—', 'diff': '—'}
    return variacoes

# ============================================================
# Geração do HTML do post (template completo)
# ============================================================
def gerar_html(atual, variacoes, mes, ano):
    meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    mes_nome = meses[mes-1]
    data_vigor = f"1 a 31 de {mes_nome} {ano}"
    ordem = ["Gasolina", "Gasóleo Normal", "Petróleo", "Butano Granel",
             "Gasóleo Eletricidade", "Gasóleo Marinha", "Fuel 380", "Fuel 180"]
    tabela = '<table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">\n'
    tabela += '<thead><tr><th>Produto</th><th>Preço ECV</th><th>Variação (%)</th><th>Diferença (ECV)</th></tr></thead><tbody>\n'
    for prod in ordem:
        if prod in atual:
            preco = atual[prod].replace('.', ',')
            var = variacoes.get(prod, {'perc': '—', 'diff': '—'})
            tabela += f'<tr>\n'
            tabela += f'<td>{prod}</td>\n'
            tabela += f'<td>{preco}</td>\n'
            tabela += f'<td>{var["perc"]}</td>\n'
            tabela += f'<td>{var["diff"]}</td>\n'
            tabela += '</tr>\n'
        else:
            tabela += '<tr>\n'
            tabela += f'<td>{prod}</td>\n'
            tabela += '<td>—</td>\n'
            tabela += '<td>—</td>\n'
            tabela += '<td>—</td>\n'
            tabela += '</tr>\n'
    tabela += '</tbody>\n</table>\n'
    butano_granel = atual.get('Butano Granel', '0').replace('.', ',')
    garrafas = f"""
<ul>
    <li>Garrafa de 3 Kg: 411,00 ECV</li>
    <li>Garrafa de 6 Kg: 866,00 ECV</li>
    <li>Garrafa de 12,5 Kg: 1.804,00 ECV</li>
    <li>Garrafa de 55 Kg: 7.937,00 ECV</li>
    <li>Gás a Granel (Kg): {butano_granel} ECV</li>
</ul>
"""
    html = f"""
<p>A Agência Reguladora Multissetorial da Economia (ARME) atualizou os preços máximos de venda dos combustíveis que vigoram entre {data_vigor}.</p>

<p>De acordo com a nova tabela, regista-se uma tendência de aumento nos preços da maioria dos produtos petrolíferos em comparação com o mês passado, com exceção do Gás Butano, que mantém o seu valor inalterado.</p>

<h3>Tabela de Preços ao Consumidor</h3>
<p>Abaixo apresentamos os valores fixados para a venda a retalho, bem como a variação percentual e nominal em relação ao período anterior:</p>

{tabela}

<h3>Preços do Gás Butano por Embalagem</h3>
<p>Para as famílias e empresas que utilizam gás butano, os preços das garrafas (já com IVA incluído) permanecem os mesmos que vigoraram em abril:</p>
{garrafas}

<h3>Estrutura de Custos</h3>
<p>O preço final de venda ao público é composto por diversos fatores regulados pela ARME, incluindo os Custos de Importação (CP), Custos de Logística (CU GSL), Custos de Distribuição (MMUD), além do IVA e outras taxas específicas aplicáveis ao setor.</p>

<p><em>Fonte: Agência Reguladora Multissetorial da Economia (ARME) – Tabela de Novos Preços Máximos de {data_vigor}</em></p>
"""
    return html

def publicar_rascunho(titulo, conteudo):
    client = Client("https://fiscocaboverde.com/xmlrpc.php", WP_USER, WP_PASS)
    post = WordPressPost()
    post.title = titulo
    post.content = conteudo
    post.post_status = 'publish'
    post.terms_names = {
        'category': ['NOTÍCIAS & ATUALIZAÇÕES'],
        'post_tag': ['combustíveis', 'ARME']
    }
    return client.call(NewPost(post))

# ============================================================
# Execução principal
# ============================================================
def main():
    hoje = datetime.now()
    ano, mes = hoje.year, hoje.month
    print(f"🔍 A obter preços de {mes}/{ano}...")
    atuais = obter_precos(ano, mes, usar_web=True)
    if not atuais:
        print("❌ Preços do mês actual não disponíveis – a execução será abortada.")
        return
    mes_ant = mes-1 if mes>1 else 12
    ano_ant = ano if mes>1 else ano-1
    # Forçamos o uso de dados históricos para o mês anterior (para garantir que as variações são calculadas)
    anteriores = obter_precos(ano_ant, mes_ant, usar_web=False)
    variacoes = calcular_variacoes(atuais, anteriores) if anteriores else {}
    meses_nomes = ["janeiro","fevereiro","março","abril","maio","junho",
                   "julho","agosto","setembro","outubro","novembro","dezembro"]
    titulo = f"ARME atualiza preços máximos dos combustíveis para {meses_nomes[mes-1]} {ano}"
    html = gerar_html(atuais, variacoes, mes, ano)
    print("📝 A publicar no WordPress...")
    post_id = publicar_rascunho(titulo, html)
    print(f"✅ Post publicado! ID: {post_id}")
    print(f"🔗 Ver post: https://fiscocaboverde.com/?p={post_id}")

if __name__ == "__main__":
    main()
