import pandas as pd
import sqlite3
import os
import platform
import subprocess
from fpdf import FPDF
from banco_dados import BancoAIH


class RelatorioPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Auditoria SIHD - Relatorio de Conferencia', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')


def formatar_moeda_pandas(x):
    """Formata um valor numérico para o padrão monetário brasileiro (R$ 1.234,56)."""
    try:
        v = float(x)
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return x


def gerar_pdf(df, tipo, competencia, dir_saida, hospitais):
    if df.empty:
        return None

    # Relatórios em modo Paisagem (L) para caber Nome + Competência
    pdf = RelatorioPDF(orientation='L')
    pdf.add_page()

    # Inversão correta do dicionário para busca
    cnes_para_nome = {v: k for k, v in hospitais.items()}
    grupos = df.groupby('cnes')

    for cnes, dados in grupos:
        nome_hosp = cnes_para_nome.get(cnes, "HOSPITAL NAO IDENTIFICADO")
        pdf.set_font('Arial', 'B', 11)

        # CABEÇALHO ATUALIZADO: Unidade + CNES + Competência
        texto_cabecalho = f"Unidade: {nome_hosp} | CNES: {cnes} | Competencia: {competencia}"
        pdf.cell(0, 10, texto_cabecalho, 0, 1, 'L')

        pdf.set_font('Arial', 'B', 8)
        if tipo == 'divergentes':
            pdf.cell(32, 8, 'AIH', 1, 0, 'C')
            pdf.cell(25, 8, 'V. Local', 1, 0, 'C')
            pdf.cell(25, 8, 'V. SIHD', 1, 0, 'C')
            pdf.cell(25, 8, 'Diferenca', 1, 0, 'C')
            pdf.cell(150, 8, 'Nome do Paciente', 1, 1, 'L')

            pdf.set_font('Arial', '', 8)
            for _, row in dados.iterrows():
                nome_pac = str(row['paciente']) if pd.notnull(row['paciente']) else "NAO INFORMADO"
                pdf.cell(32, 8, str(row['aih']), 1, 0, 'C')
                pdf.cell(25, 8, row['v_local_fmt'], 1, 0, 'C')
                pdf.cell(25, 8, row['v_sihd_fmt'], 1, 0, 'C')
                pdf.cell(25, 8, row['dif_fmt'], 1, 0, 'C')
                pdf.cell(150, 8, nome_pac[:65], 1, 1, 'L')

        elif tipo == 'nao_coincidentes':
            pdf.cell(35, 8, 'AIH', 1, 0, 'C')
            pdf.cell(35, 8, 'Valor SIHD', 1, 0, 'C')
            pdf.cell(187, 8, 'Nome do Paciente', 1, 1, 'L')

            pdf.set_font('Arial', '', 8)
            for _, row in dados.iterrows():
                nome_pac = str(row['paciente']) if pd.notnull(row['paciente']) else "NAO INFORMADO"
                pdf.cell(35, 8, str(row['aih']), 1, 0, 'C')
                pdf.cell(35, 8, row['v_sihd_fmt'], 1, 0, 'C')
                pdf.cell(187, 8, nome_pac[:80], 1, 1, 'L')

        pdf.ln(5)

    nome_arquivo = f"Relatorio_{tipo.capitalize()}_{competencia}.pdf"
    caminho_pdf = os.path.join(dir_saida, nome_arquivo)
    pdf.output(caminho_pdf)
    return caminho_pdf


def processar_relatorios(competencia, dir_saida, hospitais, comparar_valores=True, verificar_aih=True):
    try:
        banco = BancoAIH()
        query_local, query_sihd, conexao = banco.buscar_dados_para_auditoria(competencia)
        df_local = pd.read_sql_query(query_local, conexao, dtype=str)
        df_sihd = pd.read_sql_query(query_sihd, conexao, dtype=str)
        conexao.close()

        # Merge das bases
        df_merge = pd.merge(df_local, df_sihd, on=['competencia', 'cnes', 'aih'], how='outer', indicator=True)

        pdfs_gerados = []

        # Lógica 1: Divergentes (Só faz sentido se comparar_valores estiver ativo)
        if comparar_valores:
            df_merge['v_num_local'] = df_merge['valor_x'].str.replace(',', '.').astype(float)
            df_merge['v_num_sihd'] = df_merge['valor_y'].str.replace(',', '.').astype(float)

            ambas = df_merge[df_merge['_merge'] == 'both'].copy()
            ambas['diferenca'] = ambas['v_num_local'] - ambas['v_num_sihd']
            divergentes = ambas[~ambas['diferenca'].between(-0.04, 0.04)].copy()

            if not divergentes.empty:
                divergentes['v_local_fmt'] = divergentes['v_num_local'].map(formatar_moeda_pandas)
                divergentes['v_sihd_fmt'] = divergentes['v_num_sihd'].map(formatar_moeda_pandas)
                divergentes['dif_fmt'] = divergentes['diferenca'].map(formatar_moeda_pandas)
                pdf_div = gerar_pdf(divergentes, 'divergentes', competencia, dir_saida, hospitais)
                if pdf_div: pdfs_gerados.append(pdf_div)

        # Lógica 2: Não Coincidentes (Só faz sentido se verificar_aih estiver ativo)
        if verificar_aih:
            nao_coincidentes = df_merge[df_merge['_merge'] == 'right_only'].copy()
            if not nao_coincidentes.empty:
                # Garante que o valor saia formatado mesmo sem cálculo
                nao_coincidentes['v_num_sihd'] = nao_coincidentes['valor_y'].str.replace(',', '.').astype(float)
                nao_coincidentes['v_sihd_fmt'] = nao_coincidentes['v_num_sihd'].map(formatar_moeda_pandas)
                pdf_nc = gerar_pdf(nao_coincidentes, 'nao_coincidentes', competencia, dir_saida, hospitais)
                if pdf_nc: pdfs_gerados.append(pdf_nc)

        # Abertura dos arquivos...
        for pdf in pdfs_gerados:
            if platform.system() == 'Windows':
                os.startfile(pdf)
            else:
                subprocess.call(['open', pdf])

        return len(pdfs_gerados), 0  # Retorno simplificado

    except Exception as e:
        return f"Erro: {str(e)}"