import pandas as pd
import os
import sys  # <-- ADICIONADO AQUI
import unicodedata
from fpdf import FPDF
from banco_dados import BancoAIH
from datetime import datetime

def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funcionando em desenvolvimento e no executável compilado """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def mascarar_cpf(cpf_bruto):
    """Aplica máscara de privacidade (LGPD) ao CPF: ***.123.456-**"""
    cpf = str(cpf_bruto).strip()
    if len(cpf) == 11 and cpf.isdigit():
        return f"***.{cpf[3:6]}.{cpf[6:9]}-**"
    return "***.***.***-**"


def limpar_texto_pdf(texto):
    """Remove acentos e caracteres especiais que causam crash silencioso no motor FPDF."""
    if pd.isna(texto) or texto is None:
        return ""
    return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII')


class RelatorioPDF(FPDF):
    def __init__(self, titulo_relatorio, orientation='L', unit='mm', format='A4', usuario_logado=None):
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.titulo_relatorio = titulo_relatorio
        self.usuario_logado = usuario_logado
        self.alias_nb_pages()  # Habilita a contagem total de páginas

    def header(self):
        caminho_logo_pdf = resource_path("icon_sus.png")
        if os.path.exists(caminho_logo_pdf):
            self.image(caminho_logo_pdf, x=10, y=8, w=25)

        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, self.titulo_relatorio, 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-20)
        self.set_font('Arial', 'I', 8)

        data_hora = datetime.now().strftime("%d/%m/%Y as %H:%M:%S")

        assinatura = ""
        if self.usuario_logado:
            nome = self.usuario_logado.get('nome', 'Utilizador')
            cpf_mascarado = mascarar_cpf(self.usuario_logado.get('cpf', ''))
            assinatura = f"  |  Gerado por: {nome} (CPF: {cpf_mascarado})"
        
        # Formato de página "Página X de Y"
        texto_paginacao = f'  |  Pagina {self.page_no()} de {{nb}}'

        texto_rodape = f'Gerado através do software Integritas AIH em: {data_hora}{assinatura}{texto_paginacao}'
        self.cell(w=0, h=10, txt=texto_rodape, border=0, ln=0, align='C')


def gerar_pdf(df, tipo, competencia, dir_saida, hospitais, usuario_active=None, hospital_info=None):
    """
    Renderiza o DataFrame num documento PDF, com agrupamento por hospital,
    coluna de Unidade incluída na tabela, quebra de linha dinâmica e
    índice numérico que reinicia a cada novo prestador.
    """
    if df.empty:
        return None

    # Configuração dos Títulos e Colunas
    if tipo == 'divergentes':
        titulo_doc = 'Conferencia SIHD - Relatorio de Divergencia de Valores'
        colunas = ['Nº', 'Unidade', 'AIH', 'Paciente', 'V. Local', 'V. SIHD', 'Diferenca']
        larguras = [10, 50, 30, 80, 35, 35, 37]
        idx_multi = [1, 3]
    else:
        titulo_doc = 'Conferencia SIHD - Relatorio de AIHs Nao Coincidentes'
        colunas = ['Nº', 'Unidade', 'AIH', 'Paciente', 'Valor SIHD']
        larguras = [10, 65, 35, 130, 37]
        idx_multi = [1, 3]

    pdf = RelatorioPDF(titulo_relatorio=titulo_doc, orientation='L', usuario_logado=usuario_active)
    pdf.add_page()

    mapa_cnes = {v: k for k, v in hospitais.items()}

    # Agrupamento dos dados por Unidade Hospitalar
    grupos = df.groupby('cnes')

    for cnes, grupo in grupos:
        nome_unidade = limpar_texto_pdf(mapa_cnes.get(str(cnes), str(cnes)))

        # --- AJUSTE ESTRUTURAL: O contador é reiniciado a cada novo prestador ---
        contador = 1

        # Controlo de Quebra de Página
        if pdf.get_y() > 165:
            pdf.add_page()

        # Renderização do Sub-cabeçalho de Agrupamento
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 10)
        cabecalho_grupo = f"Unidade: {nome_unidade}  |  CNES: {cnes}  |  Competencia: {competencia}"

        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 8, cabecalho_grupo, border=1, ln=1, align='L', fill=True)

        # Desenhar Cabeçalhos das Colunas
        pdf.set_font('Arial', 'B', 9)
        for col, larg in zip(colunas, larguras):
            pdf.cell(larg, 7, col, border=1, align='C', fill=False)
        pdf.ln()

        # Renderização Dinâmica de Linhas
        pdf.set_font('Arial', '', 8)
        for row in grupo.itertuples():
            paciente = limpar_texto_pdf(row.paciente if pd.notna(row.paciente) else "Nao Informado")

            if tipo == 'divergentes':
                valores = [str(contador), nome_unidade, str(row.aih), paciente, str(row.v_local_fmt),
                           str(row.v_sihd_fmt), str(row.dif_fmt)]
                aligns = ['C', 'L', 'C', 'L', 'R', 'R', 'R']
            else:
                valores = [str(contador), nome_unidade, str(row.aih), paciente, str(row.v_sihd_fmt)]
                aligns = ['C', 'L', 'C', 'L', 'R']

            # Inteligência de Cálculo de Altura
            w_unidade = pdf.get_string_width(nome_unidade)
            w_paciente = pdf.get_string_width(paciente)

            linhas_u = 1
            if w_unidade > (larguras[1] - 4): linhas_u = 2
            if w_unidade > ((larguras[1] * 2) - 8): linhas_u = 3

            linhas_p = 1
            if w_paciente > (larguras[3] - 4): linhas_p = 2
            if w_paciente > ((larguras[3] * 2) - 8): linhas_p = 3

            num_linhas = max(linhas_u, linhas_p)
            h_linha = 6
            h_total = h_linha * num_linhas

            # Verifica se a próxima linha vai saltar fora da página
            if pdf.get_y() + h_total > 190:
                pdf.add_page()
                pdf.set_font('Arial', 'B', 9)
                for col, larg in zip(colunas, larguras):
                    pdf.cell(larg, 7, col, border=1, align='C')
                pdf.ln()
                pdf.set_font('Arial', '', 8)

            # Memoriza coordenadas de início
            x = pdf.get_x()
            y = pdf.get_y()

            # Desenha as células
            for i in range(len(valores)):
                pdf.rect(x, y, larguras[i], h_total)

                if i in idx_multi:
                    # Células que quebram linha (multi_cell)
                    w_txt = pdf.get_string_width(valores[i])
                    linhas_txt = 1
                    if w_txt > (larguras[i] - 4): linhas_txt = 2
                    if w_txt > ((larguras[i] * 2) - 8): linhas_txt = 3

                    # Centraliza verticalmente o texto dentro do retângulo
                    ajuste_y = y + (h_total / 2) - ((linhas_txt * h_linha) / 2)
                    pdf.set_xy(x, ajuste_y)
                    pdf.multi_cell(larguras[i], h_linha, valores[i], border=0, align=aligns[i])
                else:
                    # Células de linha única
                    pdf.set_xy(x, y)
                    pdf.cell(larguras[i], h_total, valores[i], border=0, ln=0, align=aligns[i])

                x += larguras[i]

            pdf.set_xy(10, y + h_total)

            # Incrementa o contador da linha atual do prestador ativo
            contador += 1

    # Persistência do Ficheiro Físico
    data_fmt_arquivo = f"{competencia[:4]}_{competencia[4:]}"
    
    sufixo_arquivo = ""
    if hospital_info:
        cnes, nome = hospital_info
        # Limpa o nome do hospital para ser seguro para nomes de arquivo
        nome_limpo = "".join(c for c in nome if c.isalnum() or c in (' ', '_')).rstrip().replace(" ", "_")
        sufixo_arquivo = f"_{cnes}_{nome_limpo}"

    nome_arquivo = f"Relatorio_{'Divergentes' if tipo == 'divergentes' else 'Nao_coincidentes'}_{data_fmt_arquivo}{sufixo_arquivo}.pdf"

    caminho_completo = os.path.join(dir_saida, nome_arquivo)
    pdf.output(caminho_completo)

    return caminho_completo

def formatar_moeda_pandas(x):
    """Formata um valor numérico para o padrão monetário brasileiro (R$ 1.234,56)."""
    try:
        v = float(x)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return x


def processar_relatorios_dados(competencia, comparar_valores=True, verificar_aih=True):
    """Processa a auditoria e retorna os DataFrames para exibição na interface."""
    try:
        banco = BancoAIH()
        query_local, query_sihd, conexao = banco.buscar_dados_para_auditoria(competencia)
        # O parâmetro é injetado com segurança na interrogação (?)
        df_local = pd.read_sql_query(query_local, conexao, params=(competencia,), dtype=str)
        df_sihd = pd.read_sql_query(query_sihd, conexao, params=(competencia,), dtype=str)
        conexao.close()

        if df_local.empty and df_sihd.empty:
            return None, None

        # Merge das bases
        df_merge = pd.merge(df_local, df_sihd, on=['competencia', 'cnes', 'aih'], how='outer', indicator=True)

        divergentes = None
        nao_coincidentes = None

        # Lógica 1: Divergentes
        if comparar_valores:
            df_merge['v_num_local'] = pd.to_numeric(df_merge['valor_x'].str.replace(',', '.'), errors='coerce')
            df_merge['v_num_sihd'] = pd.to_numeric(df_merge['valor_y'].str.replace(',', '.'), errors='coerce')

            ambas = df_merge[df_merge['_merge'] == 'both'].copy()

            if not ambas.empty:
                ambas_com_valor = ambas.dropna(subset=['v_num_local', 'v_num_sihd']).copy()

                if not ambas_com_valor.empty:
                    ambas_com_valor['diferenca'] = ambas_com_valor['v_num_local'] - ambas_com_valor['v_num_sihd']
                    div = ambas_com_valor[~ambas_com_valor['diferenca'].between(-0.04, 0.04)].copy()

                    if not div.empty:
                        div['v_local_fmt'] = div['v_num_local'].map(formatar_moeda_pandas)
                        div['v_sihd_fmt'] = div['v_num_sihd'].map(formatar_moeda_pandas)
                        div['dif_fmt'] = div['diferenca'].map(formatar_moeda_pandas)
                        divergentes = div

        # Lógica 2: Não Coincidentes
        if verificar_aih:
            nc = df_merge[df_merge['_merge'] == 'right_only'].copy()
            if not nc.empty:
                nc['v_num_sihd'] = pd.to_numeric(nc['valor_y'].str.replace(',', '.'), errors='coerce')
                nc['v_sihd_fmt'] = nc['v_num_sihd'].map(formatar_moeda_pandas)
                nao_coincidentes = nc

        return divergentes, nao_coincidentes

    except Exception as e:
        raise Exception(f"Falha no processamento: {str(e)}")