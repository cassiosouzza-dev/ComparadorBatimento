import sqlite3
import os
import hashlib # NOVA IMPORTAÇÃO: Essencial para segurança das senhas

class BancoAIH:
    def __init__(self, nome_banco="BD_integritas.db"):
        self.nome_banco = nome_banco
        self.inicializar_banco()

    def conectar(self):
        """Estabelece conexão com o motor SQLite."""
        return sqlite3.connect(self.nome_banco)

    def inicializar_banco(self):
        """Cria a arquitetura de tabelas para digitação, importação, usuários e logs."""
        conexao = self.conectar()
        cursor = conexao.cursor()

        # [Tabelas de AIH e Prestadores mantidas...]
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS aih_digitadas
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           competencia
                           TEXT
                           NOT
                           NULL,
                           cnes
                           TEXT
                           NOT
                           NULL,
                           aih
                           TEXT
                           NOT
                           NULL,
                           valor
                           TEXT
                           NOT
                           NULL,
                           data_registro
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS aihs_importadas_sihd
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           competencia
                           TEXT
                           NOT
                           NULL,
                           cnes
                           TEXT
                           NOT
                           NULL,
                           aih
                           TEXT
                           NOT
                           NULL,
                           valor
                           TEXT
                           NOT
                           NULL,
                           paciente
                           TEXT,
                           data_importacao
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )
                       ''')

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS prestadores
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           cnes
                           TEXT
                           UNIQUE
                           NOT
                           NULL,
                           nome_fantasia
                           TEXT
                           NOT
                           NULL
                       )
                       ''')

        # Tabela de Utilizadores com a nova coluna de Dica
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS usuarios
                       (
                           cpf
                           TEXT
                           PRIMARY
                           KEY,
                           nome
                           TEXT
                           NOT
                           NULL,
                           senha_hash
                           TEXT
                           NOT
                           NULL,
                           dica_senha
                           TEXT,
                           data_criacao
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP
                       )
                       ''')

        # --- BLOCO DE MIGRAÇÃO SEGURA ---
        # Garante que bancos de dados criados antes desta atualização recebam a nova coluna
        try:
            cursor.execute("ALTER TABLE usuarios ADD COLUMN dica_senha TEXT")
        except sqlite3.OperationalError:
            pass  # A coluna já existe, ignora a alteração

        # --- BLOCO DE MIGRAÇÃO: Cor do Prestador ---
        try:
            cursor.execute("ALTER TABLE prestadores ADD COLUMN cor TEXT DEFAULT '#2c3e50'")
        except sqlite3.OperationalError:
            pass  # A coluna já existe
        # Tabela 4: Trilha de Auditoria (Logs)
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS log_auditoria
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           cpf_usuario
                           TEXT
                           NOT
                           NULL,
                           acao
                           TEXT
                           NOT
                           NULL,
                           detalhes
                           TEXT,
                           data_hora
                           TIMESTAMP
                           DEFAULT
                           CURRENT_TIMESTAMP,
                           FOREIGN
                           KEY
                       (
                           cpf_usuario
                       ) REFERENCES usuarios
                       (
                           cpf
                       )
                           )
                       ''')

        # Criação do Utilizador Padrão
        cursor.execute("SELECT count(*) FROM usuarios")
        if cursor.fetchone()[0] == 0:
            cpf_admin = "admin"
            nome_admin = "Administrador do Sistema"
            senha_padrao_hash = hashlib.sha256("admin123".encode('utf-8')).hexdigest()
            dica = "A senha padrão do sistema."

            cursor.execute('''
                           INSERT INTO usuarios (cpf, nome, senha_hash, dica_senha)
                           VALUES (?, ?, ?, ?)
                           ''', (cpf_admin, nome_admin, senha_padrao_hash, dica))

        conexao.commit()
        conexao.close()

    # [Mantenha os outros métodos aqui: inserir_prestador, validar_login, registrar_log, etc...]

    def criar_novo_usuario(self, cpf, nome, senha_texto_puro, dica_senha=""):
        """Permite que os utilizadores se cadastrem no sistema com dica de recuperação."""
        senha_hash = hashlib.sha256(senha_texto_puro.encode('utf-8')).hexdigest()
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            cursor.execute("INSERT INTO usuarios (cpf, nome, senha_hash, dica_senha) VALUES (?, ?, ?, ?)",
                           (cpf, nome, senha_hash, dica_senha))
            conexao.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # CPF já cadastrado
        finally:
            conexao.close()

    def buscar_dica_senha(self, cpf):
        """Retorna a dica de senha associada ao CPF fornecido."""
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT dica_senha FROM usuarios WHERE cpf = ?", (cpf,))
        resultado = cursor.fetchone()
        conexao.close()

        if resultado:
            return resultado[0] if resultado[0] else "Nenhuma dica foi registada para este utilizador."
        return None

    def inserir_prestador(self, cnes, nome, cor="#2c3e50"):
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            cursor.execute("INSERT INTO prestadores (cnes, nome_fantasia, cor) VALUES (?, ?, ?)", (cnes, nome, cor))
            conexao.commit()
            return True
        except sqlite3.IntegrityError:
            return "CNES já cadastrado."
        finally:
            conexao.close()

    def listar_prestadores_completos(self):
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT id, cnes, nome_fantasia, cor FROM prestadores ORDER BY nome_fantasia")
        dados = cursor.fetchall()
        conexao.close()
        return dados


    def excluir_prestador(self, id_prestador):
        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM prestadores WHERE id = ?", (id_prestador,))
        conexao.commit()
        conexao.close()

    def atualizar_prestador(self, id_banco, novo_cnes, novo_nome, nova_cor):
        """Atualiza os dados de um prestador existente no banco de dados."""
        try:
            import sqlite3
            conexao = self.conectar()
            cursor = conexao.cursor()

            cursor.execute("""
                UPDATE prestadores 
                SET cnes = ?, nome_fantasia = ?, cor = ? 
                WHERE id = ?
            """, (novo_cnes, novo_nome, nova_cor, id_banco))

            conexao.commit()
            return True
        except sqlite3.IntegrityError:
            return "O CNES informado já se encontra registado noutra unidade."
        except Exception as e:
            return f"Erro ao atualizar prestador: {str(e)}"
        finally:
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

    # --- MÉTODOS DE GOVERNANÇA, AUTENTICAÇÃO E LOGS ---

    def validar_login(self, cpf: str, senha_texto_puro: str):
        """
        Compara o hash da senha fornecida com o hash armazenado no banco.
        Retorna um dicionário com os dados do usuário se válido, ou None se falhar.
        """
        # Criptografa a senha digitada para comparar com o banco
        senha_hash = hashlib.sha256(senha_texto_puro.encode('utf-8')).hexdigest()

        conexao = self.conectar()
        cursor = conexao.cursor()
        cursor.execute("SELECT cpf, nome FROM usuarios WHERE cpf = ? AND senha_hash = ?",
                       (cpf, senha_hash))
        usuario = cursor.fetchone()
        conexao.close()

        if usuario:
            # Retorna os dados em formato estruturado
            return {"cpf": usuario[0], "nome": usuario[1]}
        return None

    def registrar_log(self, cpf_usuario: str, acao: str, detalhes: str = ""):
        """
        Grava uma ação na trilha de auditoria do sistema.
        """
        try:
            conexao = self.conectar()
            cursor = conexao.cursor()
            cursor.execute('''
                           INSERT INTO log_auditoria (cpf_usuario, acao, detalhes)
                           VALUES (?, ?, ?)
                           ''', (cpf_usuario, acao, detalhes))
            conexao.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao registrar log: {e}")
            return False
        finally:
            conexao.close()

    def listar_logs(self):
        """Retorna todos os registos da trilha de auditoria ordenados por data."""
        conexao = self.conectar()
        cursor = conexao.cursor()

        # Faz um JOIN com a tabela de usuarios para trazer o nome de quem fez a ação
        query = '''
                SELECT l.data_hora, \
                       l.cpf_usuario, \
                       u.nome, \
                       l.acao, \
                       l.detalhes
                FROM log_auditoria l \
                         LEFT JOIN \
                     usuarios u ON l.cpf_usuario = u.cpf
                ORDER BY l.data_hora DESC \
                '''
        cursor.execute(query)
        dados = cursor.fetchall()
        conexao.close()
        return dados