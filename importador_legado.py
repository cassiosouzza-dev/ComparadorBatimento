import validador
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

        with open(caminho_txt, 'r', encoding='utf-8') as f:
            for linha in f:
                partes = linha.strip().split(';')

                # Tolerância: Aceita linhas a partir de 3 colunas (sem valor)
                if len(partes) >= 3:
                    comp = partes[0].strip()
                    cnes = partes[1].strip()
                    aih = partes[2].strip()

                    # Tenta capturar a 4ª coluna. Se não existir ou for vazia, atribui o traço
                    valor_raw = partes[3].strip() if len(partes) > 3 else ""
                    valor = "-" if not valor_raw or valor_raw in ["", "0", "0,00", "None"] else valor_raw

                    # Validação matemática (rápida em memória)
                    if not validador.validar_aih(aih):
                        erros_validacao += 1
                        continue

                    # Verificação via cache (O(1) - instantânea)
                    chave = f"{comp}{cnes}{aih}"
                    if chave in cache_existentes:
                        duplicados += 1
                        continue

                    # Inserção preparada (fica em buffer na memória)
                    cursor.execute('''
                                   INSERT INTO aih_digitadas (competencia, cnes, aih, valor)
                                   VALUES (?, ?, ?, ?)
                                   ''', (comp, cnes, aih, valor))

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