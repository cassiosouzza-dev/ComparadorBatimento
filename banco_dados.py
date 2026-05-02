import sqlite3
import os

class BancoAIH:
    def __init__(self, nome_banco="BD_integritas.db"):
        self.nome_banco = nome_banco
        self.inicializar_banco()

    def conectar(self):
        """Estabelece conexão com o motor SQLite."""
        return sqlite3.connect(self.nome_banco)

    def inicializar_banco(self):
        """Cria a arquitetura de tabelas para digitação e importação SIHD."""
        conexao = self.conectar()
        cursor = conexao.cursor()

        # Tabela 1: Registros de digitação manual (Faturista)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aih_digitadas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competencia TEXT NOT NULL,
                cnes TEXT NOT NULL,
                aih TEXT NOT NULL,
                valor TEXT NOT NULL,
                data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Tabela 2: Base importada do SIHD (Governo)
        # Inclui a coluna 'paciente' que não existe na digitação manual
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aihs_importadas_sihd (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competencia TEXT NOT NULL,
                cnes TEXT NOT NULL,
                aih TEXT NOT NULL,
                valor TEXT NOT NULL,
                paciente TEXT,
                data_importacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
                    CREATE TABLE IF NOT EXISTS prestadores (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cnes TEXT UNIQUE NOT NULL,
                        nome_fantasia TEXT NOT NULL
                    )
                ''')

        conexao.commit()
        conexao.close()

    def inserir_prestador(self, cnes, nome):
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            cursor.execute("INSERT INTO prestadores (cnes, nome_fantasia) VALUES (?, ?)", (cnes, nome))
            conexao.commit()
            return True
        except sqlite3.IntegrityError:
            return "CNES já cadastrado."
        finally:
            conexao.close()

    def listar_prestadores_completos(self):
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT id, cnes, nome_fantasia FROM prestadores ORDER BY nome_fantasia")
        dados = cursor.fetchall()
        conexao.close()
        return dados

    def excluir_prestador(self, id_prestador):
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM prestadores WHERE id = ?", (id_prestador,))
        conexao.commit()
        conexao.close()

    # --- MÉTODOS PARA DIGITAÇÃO MANUAL ---

    def inserir_registro(self, competencia: str, cnes: str, aih: str, valor: str) -> bool:
        """Insere uma única AIH digitada manualmente."""
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            cursor.execute('''
                INSERT INTO aih_digitadas (competencia, cnes, aih, valor)
                VALUES (?, ?, ?, ?)
            ''', (competencia, cnes, aih, valor))
            conexao.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao inserir digitação: {e}")
            return False
        finally:
            conexao.close()

    # --- MÉTODOS PARA BASE SIHD (IMPORTAÇÃO) ---

    def inserir_sihd_em_massa(self, dados_lista):
        """
        Realiza a inserção de múltiplos registros de uma vez.
        Crucial para a performance em arquivos grandes.
        """
        conexao = self.conectar()
        cursor = conexao.cursor()
        # Iniciamos uma transação para acelerar a escrita no disco
        cursor.execute("BEGIN TRANSACTION")
        try:
            cursor.executemany('''
                INSERT INTO aihs_importadas_sihd (competencia, cnes, aih, valor, paciente)
                VALUES (?, ?, ?, ?, ?)
            ''', dados_lista)
            conexao.commit()
            return True
        except sqlite3.Error as e:
            conexao.rollback()
            print(f"Erro na importação em massa: {e}")
            return False
        finally:
            conexao.close()

    def limpar_sihd_competencia(self, competencia):
        """Remove dados de uma competência específica antes de reimportar."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM aihs_importadas_sihd WHERE competencia = ?", (competencia,))
        conexao.commit()
        conexao.close()

    # --- MÉTODOS DE CONSULTA ---

    def buscar_dados_para_auditoria(self, competencia):
        """
        Busca os dados de ambas as tabelas para uma competência específica.
        Retorna as queries e a conexão para o processamento com Pandas.
        """
        conexao = self.conectar()
        query_local = f"SELECT competencia, cnes, aih, valor FROM aih_digitadas WHERE competencia = '{competencia}'"
        query_sihd = f"SELECT competencia, cnes, aih, valor, paciente FROM aihs_importadas_sihd WHERE competencia = '{competencia}'"
        return query_local, query_sihd, conexao

    def registro_existe(self, competencia, cnes, aih):
        """Evita duplicados na digitação manual."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute('''
            SELECT id FROM aih_digitadas 
            WHERE competencia = ? AND cnes = ? AND aih = ?
        ''', (competencia, cnes, aih))
        existe = cursor.fetchone() is not None
        conexao.close()
        return existe

    def listar_competencias_locais(self):
        """Lista competências com digitação manual."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT DISTINCT competencia FROM aih_digitadas ORDER BY competencia DESC")
        dados = [row[0] for row in cursor.fetchall()]
        conexao.close()
        return dados

    def listar_competencias_sihd(self):
        """Lista competências com bases importadas do SIHD."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT DISTINCT competencia FROM aihs_importadas_sihd ORDER BY competencia DESC")
        dados = [row[0] for row in cursor.fetchall()]
        conexao.close()
        return dados

    def buscar_registros_locais(self, competencia):
        """Retorna todos os registros locais de uma competência."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT id, cnes, aih, valor FROM aih_digitadas WHERE competencia = ?", (competencia,))
        dados = cursor.fetchall()
        conexao.close()
        return dados

    def buscar_registros_sihd(self, competencia):
        """Retorna todos os registros do SIHD de uma competência."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT id, cnes, aih, valor, paciente FROM aihs_importadas_sihd WHERE competencia = ?",
                       (competencia,))
        dados = cursor.fetchall()
        conexao.close()
        return dados

    def atualizar_registro_local(self, id_registro, coluna, novo_valor):
        """Atualiza uma célula específica na base local."""
        # Mapeamento seguro das colunas permitidas
        colunas_validas = {1: 'cnes', 2: 'aih', 3: 'valor'}
        if coluna not in colunas_validas:
            return False

        nome_coluna = colunas_validas[coluna]
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            cursor.execute(f"UPDATE aih_digitadas SET {nome_coluna} = ? WHERE id = ?", (novo_valor, id_registro))
            conexao.commit()
            return True
        except Exception as e:
            print(f"Erro na atualização: {e}")
            return False
        finally:
            conexao.close()

    def excluir_registro_local(self, id_registro):
        """Remove um registro da base local."""
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            cursor.execute("DELETE FROM aih_digitadas WHERE id = ?", (id_registro,))
            conexao.commit()
            return True
        except Exception:
            return False
        finally:
            conexao.close()

    def excluir_competencia_total(self, competencia):
        """Remove todos os registros (Locais e SIHD) de uma competência específica."""
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            # Executa a limpeza nas duas frentes de dados do sistema
            cursor.execute("DELETE FROM aih_digitadas WHERE competencia = ?", (competencia,))
            cursor.execute("DELETE FROM aihs_importadas_sihd WHERE competencia = ?", (competencia,))
            conexao.commit()
            return True
        except Exception as e:
            print(f"Erro ao excluir competência: {e}")
            return False
        finally:
            conexao.close()

    def limpar_local_competencia(self, competencia):
        """Remove apenas os dados da digitação local de uma competência."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM aih_digitadas WHERE competencia = ?", (competencia,))
        conexao.commit()
        conexao.close()