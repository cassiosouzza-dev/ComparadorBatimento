import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit,
                             QPushButton, QCheckBox, QMessageBox)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QPixmap, QIcon

from banco_dados import BancoAIH


class TelaCadastroUsuario(QDialog):
    def __init__(self, banco):
        super().__init__()
        self.banco = banco
        self.configurar_interface()

    def configurar_interface(self):
        self.setWindowTitle("Cadastro de Novo Utilizador")
        # Altura ajustada para acomodar o novo campo
        self.setFixedSize(380, 580)
        self.setStyleSheet("background-color: #f5f7fa; font-family: 'Segoe UI', Arial, sans-serif;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(30, 20, 30, 30)

        lbl_titulo = QLabel("Criar Conta")
        lbl_titulo.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)

        lbl_sub = QLabel("Preencha os dados abaixo para aceder ao sistema.")
        lbl_sub.setStyleSheet("font-size: 13px; color: #7f8c8d; margin-bottom: 10px;")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sub.setWordWrap(True)
        layout.addWidget(lbl_sub)

        estilo_input = """
            QLineEdit {
                padding: 10px;
                border: 1px solid #ced4da;
                border-radius: 5px;
                background-color: #ffffff;
                color: #212529;
                font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #007acc; }
            QLabel {
                color: #34495e;
                font-weight: bold;
                font-size: 13px;
                margin-top: 2px;
            }
        """
        self.setStyleSheet(self.styleSheet() + estilo_input)

        # Campos Pessoais
        layout.addWidget(QLabel("CPF (Apenas números):"))
        self.input_cpf = QLineEdit()
        self.input_cpf.setPlaceholderText("Ex: 12345678900")
        self.input_cpf.setMaxLength(11)
        layout.addWidget(self.input_cpf)

        layout.addWidget(QLabel("Nome Completo:"))
        self.input_nome = QLineEdit()
        self.input_nome.setPlaceholderText("Seu nome e sobrenome")
        layout.addWidget(self.input_nome)

        # Campos de Segurança
        layout.addWidget(QLabel("Senha de Acesso:"))
        self.input_senha = QLineEdit()
        self.input_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_senha.setPlaceholderText("••••••••")
        layout.addWidget(self.input_senha)

        layout.addWidget(QLabel("Confirmar Senha:"))
        self.input_conf_senha = QLineEdit()
        self.input_conf_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_conf_senha.setPlaceholderText("••••••••")
        layout.addWidget(self.input_conf_senha)

        # NOVO CAMPO: Dica de Senha
        layout.addWidget(QLabel("Palavra-chave / Dica de Senha:"))
        self.input_dica = QLineEdit()
        self.input_dica.setPlaceholderText("Ex: Nome do meu primeiro animal")
        layout.addWidget(self.input_dica)

        layout.addSpacing(15)

        btn_salvar = QPushButton("Confirmar Cadastro")
        btn_salvar.setStyleSheet("""
            QPushButton {
                background-color: #007acc; 
                color: white; 
                padding: 12px; 
                font-weight: bold; 
                font-size: 15px;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover { background-color: #005f9e; }
        """)
        btn_salvar.clicked.connect(self.processar_cadastro)
        layout.addWidget(btn_salvar)
        layout.addStretch()

    def processar_cadastro(self):
        cpf = self.input_cpf.text().strip()
        nome = self.input_nome.text().strip()
        senha = self.input_senha.text().strip()
        conf_senha = self.input_conf_senha.text().strip()
        dica = self.input_dica.text().strip()

        if not cpf or not nome or not senha:
            QMessageBox.warning(self, "Aviso", "Os campos CPF, Nome e Senha são obrigatórios.")
            return

        if senha != conf_senha:
            QMessageBox.warning(self, "Aviso", "As senhas introduzidas não coincidem.")
            return

        sucesso = self.banco.criar_novo_usuario(cpf, nome, senha, dica)

        if sucesso:
            QMessageBox.information(self, "Sucesso", f"Conta criada com sucesso para:\n{nome}")
            self.banco.registrar_log(cpf, "Auto-cadastro",
                                     "O utilizador registou-se no sistema a partir da Tela de Login.")
            self.accept()
        else:
            QMessageBox.critical(self, "Erro",
                                 "Não foi possível realizar o cadastro.\nVerifique se este CPF já se encontra registado.")


class TelaLogin(QDialog):
    def __init__(self):
        super().__init__()
        self.banco = BancoAIH()
        self.usuario_autenticado = None
        self.config = QSettings("SecretariaSaude_MOC", "IntegritasAIH")
        self.configurar_interface()
        self.carregar_credenciais_salvas()

    def configurar_interface(self):
        self.setWindowTitle("Integritas - Autenticação")
        # Altura ajustada para acomodar o novo botão de esqueci a senha
        self.setFixedSize(350, 520)
        self.setStyleSheet("background-color: #f8f9fa;")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)

        lbl_logo = QLabel()
        caminho_logo = os.path.join(os.path.dirname(__file__), "icon_sus.png")
        pixmap = QPixmap(caminho_logo)
        if not pixmap.isNull():
            lbl_logo.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_logo)

        lbl_titulo = QLabel("Autenticação do Sistema")
        lbl_titulo.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_titulo)
        layout.addSpacing(10)

        lbl_cpf = QLabel("Login (CPF):")
        lbl_cpf.setStyleSheet("color: #34495e; font-weight: bold;")
        self.input_cpf = QLineEdit()
        self.input_cpf.setPlaceholderText("Digite seu acesso")
        self.input_cpf.setStyleSheet("padding: 8px; border: 1px solid #bdc3c7; border-radius: 4px; background: white;")
        layout.addWidget(lbl_cpf)
        layout.addWidget(self.input_cpf)

        lbl_senha = QLabel("Senha:")
        lbl_senha.setStyleSheet("color: #34495e; font-weight: bold;")
        self.input_senha = QLineEdit()
        self.input_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_senha.setPlaceholderText("Digite sua senha")
        self.input_senha.setStyleSheet(
            "padding: 8px; border: 1px solid #bdc3c7; border-radius: 4px; background: white;")
        layout.addWidget(lbl_senha)
        layout.addWidget(self.input_senha)

        self.chk_lembrar = QCheckBox("Lembrar minhas credenciais")
        self.chk_lembrar.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(self.chk_lembrar)
        layout.addSpacing(15)

        self.btn_entrar = QPushButton("Acessar Integritas")
        self.btn_entrar.setStyleSheet("""
            QPushButton { background-color: #007acc; color: white; font-weight: bold; padding: 10px; border-radius: 4px; }
            QPushButton:hover { background-color: #005f9e; }
        """)
        self.btn_entrar.clicked.connect(self.processar_login)
        layout.addWidget(self.btn_entrar)

        # Botão: Esqueci a Senha
        self.btn_esqueci = QPushButton("Esqueci a Senha")
        self.btn_esqueci.setStyleSheet("""
            QPushButton { background-color: transparent; color: #7f8c8d; text-decoration: underline; border: none; margin-top: 0px; }
            QPushButton:hover { color: #34495e; }
        """)
        self.btn_esqueci.clicked.connect(self.recuperar_senha)
        layout.addWidget(self.btn_esqueci)

        # Botão: Cadastrar
        self.btn_cadastrar = QPushButton("Primeiro Acesso? Cadastre-se")
        self.btn_cadastrar.setStyleSheet("""
            QPushButton { background-color: transparent; color: #007acc; font-weight: bold; text-decoration: underline; border: none; }
            QPushButton:hover { color: #005f9e; }
        """)
        self.btn_cadastrar.clicked.connect(self.abrir_tela_cadastro)
        layout.addWidget(self.btn_cadastrar)

    def carregar_credenciais_salvas(self):
        if self.config.value("lembrar", False, type=bool):
            self.input_cpf.setText(str(self.config.value("cpf", "")))
            self.input_senha.setText(str(self.config.value("senha", "")))
            self.chk_lembrar.setChecked(True)

    def processar_login(self):
        cpf = self.input_cpf.text().strip()
        senha = self.input_senha.text().strip()

        if not cpf or not senha:
            QMessageBox.warning(self, "Aviso", "Preencha todos os campos.")
            return

        usuario = self.banco.validar_login(cpf, senha)

        if usuario:
            self.usuario_autenticado = usuario
            if self.chk_lembrar.isChecked():
                self.config.setValue("lembrar", True)
                self.config.setValue("cpf", cpf)
                # A linha que salvava a senha em texto plano foi removida por segurança
            else:
                self.config.clear()

            self.banco.registrar_log(cpf, "Login", "Acesso autorizado ao sistema")
            self.accept()
        else:
            QMessageBox.critical(self, "Acesso Negado", "Credenciais incorretas ou utilizador inexistente.")
            self.input_senha.clear()
            self.input_senha.setFocus()

    def recuperar_senha(self):
        """Busca e exibe a dica de senha com base no CPF preenchido."""
        cpf = self.input_cpf.text().strip()

        if not cpf:
            QMessageBox.information(self, "Recuperação",
                                    "Por favor, digite o seu CPF no campo de Login e clique novamente em 'Esqueci a Senha'.")
            self.input_cpf.setFocus()
            return

        dica = self.banco.buscar_dica_senha(cpf)

        if dica:
            QMessageBox.information(self, "Dica de Senha", f"A dica cadastrada para a sua conta é:\n\n'{dica}'")
        else:
            QMessageBox.warning(self, "Não Encontrado", "O CPF introduzido não possui cadastro no sistema.")

    def abrir_tela_cadastro(self):
        dialog = TelaCadastroUsuario(self.banco)
        dialog.exec()