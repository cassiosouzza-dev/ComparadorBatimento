import pandas as pd
import sqlite3
import os
import platform
import subprocess
from fpdf import FPDF
from banco_dados import BancoAIH
from datetime import datetime


def mascarar_cpf(cpf_bruto):
    """Aplica máscara de privacidade (LGPD) ao CPF: ***.123.456-**"""
    cpf = str(cpf_bruto).strip()
    if len(cpf) == 11 and cpf.isdigit():
        return f"***.{cpf[3:6]}.{cpf[6:9]}-**"
    return "***.***.***-**"


class RelatorioPDF(FPDF):
    def __init__(self, titulo_relatorio, orientation='L', unit='mm', format='A4', usuario_logado=None):
        super().__init__(orientation=orientation, unit=unit, format=format)
        self.titulo_relatorio = titulo_relatorio
        self.usuario_logado = usuario_logado

    def header(self):
        caminho_logo_pdf = os.path.join(os.path.dirname(__file__), "icon_sus.png")
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

        texto_rodape = f'Gerado através do software Integritas AIH em: {data_hora}{assinatura}  |  Pagina {self.page_no()}'
        self.cell(w=0, h=10, txt=texto_rodape, border=0, ln=0, align='C')


def gerar_pdf(df, tipo, competencia, dir_saida, hospitais, usuario_ativo=None):
    """
    Renderiza o DataFrame num documento PDF, com agrupamento por hospital,
    coluna de Unidade incluída na tabela e quebra de linha dinâmica.
    """
    if df.empty:
        return None

    # Configuração dos Títulos e Colunas
    if tipo == 'divergentes':
        titulo_doc = 'Conferência SIHD - Relatório de Divergência de Valores'
        colunas = ['Unidade', 'AIH', 'Paciente', 'V. Local', 'V. SIHD', 'Diferenca']
        larguras = [55, 30, 85, 35, 35, 37]  # Total 277mm
        idx_multi = [0, 2]  # Colunas que podem quebrar linha (Unidade e Paciente)
    else:
        titulo_doc = 'Conferência SIHD - Relatório de AIHs Não Coincidentes'
        colunas = ['Unidade', 'AIH', 'Paciente', 'Valor SIHD']
        larguras = [70, 35, 135, 37]  # Total 277mm
        idx_multi = [0, 2]

    pdf = RelatorioPDF(titulo_relatorio=titulo_doc, orientation='L', usuario_logado=usuario_ativo)
    pdf.add_page()

    mapa_cnes = {v: k for k, v in hospitais.items()}

    # Agrupamento dos dados por Unidade Hospitalar (Restauração da separação que pediu)
    grupos = df.groupby('cnes')

    for cnes, grupo in grupos:
        nome_unidade = mapa_cnes.get(str(cnes), str(cnes))

        # Controlo de Quebra de Página (Evita cortar cabeçalhos ao meio)
        if pdf.get_y() > 165:
            pdf.add_page()

        # Renderização do Sub-cabeçalho de Agrupamento
        pdf.ln(5)
        pdf.set_font('Arial', 'B', 10)
        cabecalho_grupo = f"Unidade: {nome_unidade}  |  CNES: {cnes}  |  Competencia: {competencia}"

        # Desenha uma barra de fundo subtil para destacar a divisão de hospitais
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
            paciente = str(row.paciente) if pd.notnull(row.paciente) else "Nao Informado"

            if tipo == 'divergentes':
                valores = [nome_unidade, str(row.aih), paciente, str(row.v_local_fmt), str(row.v_sihd_fmt),
                           str(row.dif_fmt)]
                aligns = ['L', 'C', 'L', 'R', 'R', 'R']
            else:
                valores = [nome_unidade, str(row.aih), paciente, str(row.v_sihd_fmt)]
                aligns = ['L', 'C', 'L', 'R']

            # Inteligência de Cálculo de Altura
            w_unidade = pdf.get_string_width(nome_unidade)
            w_paciente = pdf.get_string_width(paciente)

            linhas_u = 1
            if w_unidade > (larguras[0] - 4): linhas_u = 2
            if w_unidade > ((larguras[0] * 2) - 8): linhas_u = 3

            linhas_p = 1
            if w_paciente > (larguras[2] - 4): linhas_p = 2
            if w_paciente > ((larguras[2] * 2) - 8): linhas_p = 3

            num_linhas = max(linhas_u, linhas_p)
            h_linha = 6
            h_total = h_linha * num_linhas

            # Verifica se a próxima linha gigante vai saltar fora da página
            if pdf.get_y() + h_total > 190:
                pdf.add_page()
                # Repete os cabeçalhos das colunas na nova folha
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
                pdf.rect(x, y, larguras[i], h_total)  # Borda desenhada manualmente

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

            # Devolve o cursor para o início da próxima linha
            pdf.set_xy(10, y + h_total)

    # Persistência do Ficheiro Físico com a nomenclatura exigida
    data_fmt_arquivo = f"{competencia[:4]}_{competencia[4:]}"

    if tipo == 'divergentes':
        nome_arquivo = f"Relatorio_Divergentes_{data_fmt_arquivo}.pdf"
    else:
        nome_arquivo = f"Relatorio_Nao_coincidentes_{data_fmt_arquivo}.pdf"

    caminho_completo = os.path.join(dir_saida, nome_arquivo)

    try:
        pdf.output(caminho_completo)
        return caminho_completo
    except Exception as e:
        print(f"Erro crítico ao persistir documento PDF: {e}")
        return None


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
        df_local = pd.read_sql_query(query_local, conexao, dtype=str)
        df_sihd = pd.read_sql_query(query_sihd, conexao, dtype=str)
        conexao.close()

        if df_local.empty and df_sihd.empty:
            return None, None

        # Merge das bases
        df_merge = pd.merge(df_local, df_sihd, on=['competencia', 'cnes', 'aih'], how='outer', indicator=True)

        divergentes = None
        nao_coincidentes = None

        # Lógica 1: Divergentes
        if comparar_valores:
            # CORREÇÃO: Removido o .fillna(0.0). Traços ("-") voltam a ser convertidos em NaN (ausentes)
            df_merge['v_num_local'] = pd.to_numeric(df_merge['valor_x'].str.replace(',', '.'), errors='coerce')
            df_merge['v_num_sihd'] = pd.to_numeric(df_merge['valor_y'].str.replace(',', '.'), errors='coerce')

            ambas = df_merge[df_merge['_merge'] == 'both'].copy()

            if not ambas.empty:
                # O dropna atua como filtro: se havia um traço (NaN), a linha é ignorada da divergência de valores.
                # A regra de "conferir apenas a presença" volta a funcionar perfeitamente.
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
                nc['v_num_sihd'] = nc['valor_y'].str.replace(',', '.').astype(float)
                nc['v_sihd_fmt'] = nc['v_num_sihd'].map(formatar_moeda_pandas)
                nao_coincidentes = nc

        return divergentes, nao_coincidentes

    except Exception as e:
        raise Exception(f"Falha no processamento: {str(e)}")