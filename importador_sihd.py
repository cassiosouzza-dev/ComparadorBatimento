import pandas as pd
import re
import validador
from banco_dados import BancoAIH


def importar_sihd_para_db(caminho_file, competencia_manual):
    """
    Importa a base SIHD com deteção automática de estrutura:
    - 5 colunas: Usa a competência do ficheiro (Ex: Dados março 2026.txt).
    - 4 colunas: Usa a competência informada no sistema.
    - Posicional: Fatiamento por índices (Arquivo bruto DATASUS).
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

            # --- INTELIGÊNCIA DINÂMICA DE COLUNAS ---
            # Se faltar a competência (colunas < 5), os índices recuam uma posição
            idx_cnes = 1 if colunas_totais >= 5 else 0
            idx_aih = 2 if colunas_totais >= 5 else 1
            idx_valor = 3 if colunas_totais >= 5 else 2
            idx_paciente = 4 if colunas_totais >= 5 else 3

            # Lemos o ficheiro completo com buffer de colunas para evitar erros de tokenização
            df = pd.read_csv(caminho_file, sep=';', header=None, names=range(20), dtype=str)

            for _, row in df.iterrows():
                # O Pandas extrai com base na inteligência calculada acima
                cnes = str(row[idx_cnes]).strip() if pd.notnull(row[idx_cnes]) else ""
                aih = str(row[idx_aih]).strip() if pd.notnull(row[idx_aih]) else ""

                # Validação Matemática: Filtra linhas corrompidas ou cabeçalhos
                if cnes and validador.validar_aih(aih):

                    # --- APLICAÇÃO DA REGRA DE NEGÓCIO ---
                    # Se houver 5 colunas, usa a do ficheiro. Se não, usa a que o faturista digitou.
                    comp = str(row[0]).strip() if colunas_totais >= 5 and pd.notnull(row[0]) else competencia_manual

                    valor_raw = str(row[idx_valor]).strip() if pd.notnull(row[idx_valor]) else ""
                    paciente = str(row[idx_paciente]).strip() if pd.notnull(row[idx_paciente]) else "Não Informado"

                    # --- SANITIZAÇÃO RIGOROSA DO VALOR ---
                    valor_limpo = "-"
                    # Ignora células vazias, zeradas ou o texto "nan" gerado pelo Pandas
                    if valor_raw and valor_raw.lower() not in ["", "0", "0,00", "0.00", "none", "nan"]:
                        v_temp = valor_raw.replace("R$", "").replace(" ", "").replace(".", "")

                        if re.match(r"^\d+(,\d+)?$", v_temp):
                            try:
                                valor_float = float(v_temp.replace(",", "."))
                                valor_limpo = f"{valor_float:.2f}".replace(".", ",")
                            except ValueError:
                                pass

                    dados_para_db.append((comp, cnes, aih, valor_limpo, paciente))
        else:
            # Estratégia B: Ficheiro Posicional (Arquivo bruto DATASUS)
            with open(caminho_file, 'r', encoding='utf-8', errors='replace') as f:
                for linha in f:
                    if len(linha) > 40:
                        aih = linha[13:26].strip()

                        # Proteção contra linhas de cabeçalho e rodapé do DATASUS
                        if validador.validar_aih(aih):
                            cnes = linha[6:13].strip()
                            valor_raw = linha[26:36].strip()
                            paciente = linha[36:86].strip() if len(linha) >= 86 else "Não Informado"

                            # --- SANITIZAÇÃO RIGOROSA DO VALOR ---
                            valor_limpo = "-"
                            if valor_raw and valor_raw.lower() not in ["", "0", "0,00", "0.00", "none"]:
                                v_temp = valor_raw.replace("R$", "").replace(" ", "").replace(".", "")

                                if re.match(r"^\d+(,\d+)?$", v_temp):
                                    try:
                                        valor_float = float(v_temp.replace(",", "."))
                                        valor_limpo = f"{valor_float:.2f}".replace(".", ",")
                                    except ValueError:
                                        pass

                            # Ficheiros posicionais não têm a coluna competência por linha, usa-se a do faturista
                            dados_para_db.append((competencia_manual, cnes, aih, valor_limpo, paciente))

        # 2. Persistência em massa no SQLite
        if dados_para_db:
            # Limpa a competência antes de importar para evitar duplicação em re-importações
            comp_limpeza = dados_para_db[0][0]
            banco.limpar_sihd_competencia(comp_limpeza)

            sucesso = banco.inserir_sihd_em_massa(dados_para_db)
            return len(dados_para_db) if sucesso else "Erro na gravação do banco."

        return 0
    except Exception as e:
        return f"Erro crítico na importação inteligente: {str(e)}"