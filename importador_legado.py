import validador
import re
from banco_dados import BancoAIH


def importar_txt_para_sqlite(caminho_txt):
    banco = BancoAIH()
    conexao = banco.conectar()
    cursor = conexao.cursor()

    sucessos = 0
    erros_validacao = 0
    duplicados = 0

    try:
        # Passo 1: Carregar registros existentes para memória para busca ultra rápida
        cursor.execute("SELECT competencia || cnes || aih FROM aih_digitadas")
        cache_existentes = set(row[0] for row in cursor.fetchall())

        # Passo 2: Iniciar Transação Única
        cursor.execute("BEGIN TRANSACTION")

        with open(caminho_txt, 'r', encoding='utf-8', errors='replace') as f:
            for linha in f:
                partes = linha.strip().split(';')

                # Tolerância: Aceita linhas a partir de 3 colunas (sem valor)
                if len(partes) >= 3:
                    comp = partes[0].strip()
                    cnes = partes[1].strip()
                    aih = partes[2].strip()

                    # Validação matemática (rápida em memória)
                    if not validador.validar_aih(aih):
                        erros_validacao += 1
                        continue

                    # Verificação via cache (O(1) - instantânea)
                    chave = f"{comp}{cnes}{aih}"
                    if chave in cache_existentes:
                        duplicados += 1
                        continue

                    # --- SANITIZAÇÃO RIGOROSA DO VALOR (Proteção da Matemática) ---
                    valor_raw = partes[3].strip() if len(partes) > 3 else ""
                    valor_limpo = "-"

                    if valor_raw and valor_raw not in ["", "0", "0,00", "None"]:
                        # Remove formatação textual e pontos de milhar do TXT hospitalar
                        v_temp = valor_raw.replace("R$", "").replace(" ", "").replace(".", "")

                        # Se sobrar apenas números e vírgula, formata com duas casas decimais
                        if re.match(r"^\d+(,\d+)?$", v_temp):
                            try:
                                valor_float = float(v_temp.replace(",", "."))
                                valor_limpo = f"{valor_float:.2f}".replace(".", ",")
                            except ValueError:
                                pass  # Mantém o "-" se falhar a conversão

                    # Inserção preparada (fica em buffer na memória)
                    cursor.execute('''
                                   INSERT INTO aih_digitadas (competencia, cnes, aih, valor)
                                   VALUES (?, ?, ?, ?)
                                   ''', (comp, cnes, aih, valor_limpo))

                    # Atualiza o cache para evitar duplicados dentro do próprio arquivo TXT
                    cache_existentes.add(chave)
                    sucessos += 1

        # Passo 3: Gravação física única no disco
        conexao.commit()
        return sucessos, erros_validacao, duplicados

    except Exception as e:
        conexao.rollback()  # Cancela tudo em caso de falha crítica
        return f"Erro na migração: {str(e)}"
    finally:
        conexao.close()