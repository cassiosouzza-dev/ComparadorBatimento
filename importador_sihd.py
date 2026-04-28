import pandas as pd
from banco_dados import BancoAIH


def importar_sihd_para_db(caminho_file, competencia_manual):
    """
    Importa a base SIHD com deteção automática de estrutura:
    - 5 colunas: Usa a competência do ficheiro (Ex: Dados março 2026.txt).
    - 4 colunas: Usa a competência informada no sistema.
    - Posicional: Fatiamento por índices (Arquivo bruto).
    """
    banco = BancoAIH()
    dados_para_db = []

    try:
        # 1. Inspeção da primeira linha para determinar a inteligência de leitura
        with open(caminho_file, 'r', encoding='utf-8', errors='replace') as f:
            primeira_linha = f.readline().strip()

        if ';' in primeira_linha:
            # Estratégia A: Ficheiro Delimitado
            partes = primeira_linha.split(';')
            colunas_totais = len(partes)

            # Lemos o ficheiro completo com buffer de colunas para evitar erros de tokenização
            df = pd.read_csv(caminho_file, sep=';', header=None, names=range(20), dtype=str)

            for _, row in df.iterrows():
                if pd.notnull(row[1]) and pd.notnull(row[2]):  # Validação mínima de CNES e AIH
                    if colunas_totais >= 5:
                        # Inteligência: Usa a competência da 1ª coluna do ficheiro
                        dados_para_db.append((row[0], row[1], row[2], row[3], row[4]))
                    else:
                        # Fallback: Usa a competência informada pelo faturista
                        dados_para_db.append((competencia_manual, row[0], row[1], row[2], row[3]))
        else:
            # Estratégia B: Ficheiro Posicional (Arquivo bruto DATASUS)
            with open(caminho_file, 'r', encoding='utf-8', errors='replace') as f:
                for linha in f:
                    if len(linha) > 40:
                        # No formato posicional bruto, a competência costuma ser informada manualmente
                        # ou extraída de cabeçalhos específicos. Aqui mantemos o manual.
                        dados_para_db.append((
                            competencia_manual,
                            linha[6:13].strip(),
                            linha[13:26].strip(),
                            linha[26:36].strip(),
                            linha[36:86].strip()
                        ))

        # 2. Persistência em massa no SQLite
        if dados_para_db:
            # Limpa a competência antes de importar para evitar duplicação em re-importações
            # Se for multimeios, usamos a competência do primeiro registro para limpar
            comp_limpeza = dados_para_db[0][0]
            banco.limpar_sihd_competencia(comp_limpeza)

            sucesso = banco.inserir_sihd_em_massa(dados_para_db)
            return len(dados_para_db) if sucesso else "Erro na gravação do banco."

        return 0
    except Exception as e:
        return f"Erro crítico na importação inteligente: {str(e)}"