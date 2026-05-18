import pandas as pd
import re
import validador
from banco_dados import BancoAIH


def importar_sihd_para_db(caminho_file, competencia_manual):
    """
    Importa a base SIHD com deteção automática de estrutura e validações robustas.
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

            idx_cnes = 1 if colunas_totais >= 5 else 0
            idx_aih = 2 if colunas_totais >= 5 else 1
            idx_valor = 3 if colunas_totais >= 5 else 2
            idx_paciente = 4 if colunas_totais >= 5 else 3

            df = pd.read_csv(caminho_file, sep=';', header=None, names=range(20), dtype=str)

            for _, row in df.iterrows():
                cnes = str(row[idx_cnes]).strip() if pd.notnull(row[idx_cnes]) else ""
                aih = str(row[idx_aih]).strip() if pd.notnull(row[idx_aih]) else ""
                
                if not (cnes.isdigit() and len(cnes) == 7):
                    continue

                if cnes and validador.validar_aih(aih):
                    comp = str(row[0]).strip() if colunas_totais >= 5 and pd.notnull(row[0]) else competencia_manual
                    valor_raw = str(row[idx_valor]).strip() if pd.notnull(row[idx_valor]) else ""
                    paciente = str(row[idx_paciente]).strip() if pd.notnull(row[idx_paciente]) else "Não Informado"
                    valor_limpo = "-"

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
                        cnes = linha[6:13].strip()

                        if not (cnes.isdigit() and len(cnes) == 7):
                            continue

                        if validador.validar_aih(aih):
                            valor_raw = linha[26:36].strip()
                            paciente = linha[36:86].strip() if len(linha) >= 86 else "Não Informado"
                            valor_limpo = "-"
                            if valor_raw and valor_raw.lower() not in ["", "0", "0,00", "0.00", "none"]:
                                v_temp = valor_raw.replace("R$", "").replace(" ", "").replace(".", "")
                                if re.match(r"^\d+(,\d+)?$", v_temp):
                                    try:
                                        valor_float = float(v_temp.replace(",", "."))
                                        valor_limpo = f"{valor_float:.2f}".replace(".", ",")
                                    except ValueError:
                                        pass
                            dados_para_db.append((competencia_manual, cnes, aih, valor_limpo, paciente))

        if dados_para_db:
            comp_limpeza = dados_para_db[0][0]
            banco.limpar_sihd_competencia(comp_limpeza)
            sucesso = banco.inserir_sihd_em_massa(dados_para_db)
            return len(dados_para_db) if sucesso else "Erro na gravação do banco."
        return 0
    except Exception as e:
        return f"Erro crítico na importação inteligente: {str(e)}"