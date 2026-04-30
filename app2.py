import os
import re
import sys
import ctypes
import pandas as pd

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QLabel, QLineEdit, QComboBox, QPushButton,
                             QFileDialog, QMessageBox, QInputDialog, QDialog, QCheckBox,
                             QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
                             QHeaderView, QAbstractItemView, QMenu, QListWidget, QListWidgetItem, QTabWidget)

from PyQt6.QtGui import QAction, QFont, QColor, QPixmap, QIcon
from PyQt6.QtCore import Qt

import processamento
import validador
from banco_dados import BancoAIH


def formatar_para_real(valor):
    """Converte o valor do banco (ex: 1500,00) para o padrão de auditoria (R$ 1.500,00)."""
    if not valor: return "R$ 0,00"
    try:
        # Previne erros caso a string já venha formatada
        v_str = str(valor).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        v_float = float(v_str)
        # Formata com separador de milhar americano, depois inverte ponto e vírgula
        return f"R$ {v_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return str(valor)


def limpar_valor_real(valor_formatado):
    """Remove a máscara visual para persistência matemática no banco (ex: 1500,00)."""
    return str(valor_formatado).replace("R$", "").replace(" ", "").replace(".", "")


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Batimento - Comparador de Registros de AIH")

        # Define o ícone da janela
        caminho_icone = os.path.join(os.path.dirname(__file__), "icon_btm.ico")
        if os.path.exists(caminho_icone):
            self.setWindowIcon(QIcon(caminho_icone))

        self.resize(1100, 700)  # Aumentado para acomodar nova coluna

        self.banco = BancoAIH()
        self.carregar_prestadores_padrao()  # Inicializa hospitais na 1ª execução

        self.setup_ui()
        self.mostrar_status()

    def carregar_prestadores_padrao(self):
        """Insere os hospitais da região caso a tabela esteja vazia."""
        prestadores = self.banco.listar_prestadores_completos()
        if not prestadores:
            hospitais_iniciais = {
                "Fundação Dilson Godinho": "2219646",
                "Hospital Aroldo Tourinho": "2219638",
                "Hospital Universitário Clemente Faria": "2219654",
                "Hospital das Clínicas": "7366108",
                "Prontosocor": "2219662",
                "Santa Casa de Montes Claros": "2149990"
            }
            for nome, cnes in hospitais_iniciais.items():
                self.banco.inserir_prestador(cnes, nome)

    def obter_prestadores_dict(self):
        """Converte a tabela do banco no formato {Nome: CNES} para o sistema."""
        dados = self.banco.listar_prestadores_completos()
        return {nome: cnes for _, cnes, nome in dados}

    def obter_mapeamento_cnes_nome(self):
        """Cria um dicionário de CNES para Nome para consulta rápida."""
        dados = self.banco.listar_prestadores_completos()
        return {cnes: nome for _, cnes, nome in dados}

    def destacar_menu(self, botao_ativo):
        """Atualiza a propriedade CSS dos botões para sinalizar a aba ativa."""
        # Agrupa apenas os botões que alteram a tela principal
        botoes_navegacao = [self.btn_painel, self.btn_digitar, self.btn_prestadores]

        for btn in botoes_navegacao:
            # Define o estado verdadeiro apenas para o botão que foi clicado
            btn.setProperty("active", btn == botao_ativo)

            # Força o motor do PyQt6 a recalcular e aplicar o CSS imediatamente
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def setup_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Layout base que divide a tela: Esquerda (Sidebar) e Direita (Conteúdo)
        self.base_layout = QHBoxLayout(self.central_widget)
        self.base_layout.setContentsMargins(0, 0, 0, 0)
        self.base_layout.setSpacing(0)

        # --- CONSTRUÇÃO DA SIDEBAR ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(230)

        # A propriedade [active="true"] manterá o botão marcado como se o rato estivesse em cima
        self.sidebar.setStyleSheet("""
                    QFrame {
                        background-color: #2c3e50;
                    }
                    QPushButton {
                        background-color: transparent;
                        color: #ecf0f1;
                        text-align: left;
                        padding: 12px 20px;
                        font-size: 15px;
                        font-family: "Segoe UI";
                        font-weight: bold;
                        border-radius: 0px;
                        border: none;
                    }
                    QPushButton:hover, QPushButton[active="true"] {
                        background-color: #34495e;
                        color: #ffffff;
                        border-left: 5px solid #007acc;
                    }
                """)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        sidebar_layout.setSpacing(5)

        lbl_logo_sidebar = QLabel("Auditoria SIHD")
        lbl_logo_sidebar.setStyleSheet("color: #ffffff; font-size: 22px; font-weight: bold; padding-left: 15px;")
        sidebar_layout.addWidget(lbl_logo_sidebar)
        sidebar_layout.addSpacing(30)

        # --- INSTANCIAÇÃO DOS BOTÕES (COM SELF.) ---
        self.btn_painel = QPushButton("Painel de Sincronização")
        self.btn_painel.clicked.connect(self.mostrar_status)

        self.btn_digitar = QPushButton("Lançamento Manual")
        self.btn_digitar.clicked.connect(self.abrir_tela_digitar)

        self.btn_prestadores = QPushButton("Gestão de Prestadores")
        self.btn_prestadores.clicked.connect(self.abrir_tela_prestadores)

        # Linha separadora discreta
        linha1 = QFrame()
        linha1.setFrameShape(QFrame.Shape.HLine)
        linha1.setStyleSheet("background-color: #34495e; margin: 0px 15px;")

        btn_imp_legado = QPushButton("📂 Importar TXT Local")
        btn_imp_legado.clicked.connect(self.executar_importacao_legado)

        btn_imp_sihd = QPushButton("📥 Importar Base SIHD")
        btn_imp_sihd.clicked.connect(self.selecionar_base_sihd)

        linha2 = QFrame()
        linha2.setFrameShape(QFrame.Shape.HLine)
        linha2.setStyleSheet("background-color: #34495e; margin: 0px 15px;")

        # Instanciação estritamente técnica, sem iconografia
        btn_auditoria = QPushButton("Executar Conferência")
        btn_auditoria.clicked.connect(self.processar_dados)

        # Estilo dedicado: Transforma o item numa caixa de ação primária (Call to Action)
        btn_auditoria.setStyleSheet("""
                    QPushButton {
                        background-color: #007acc; /* Azul sólido de destaque corporativo */
                        color: #ffffff;
                        text-align: center; /* Centraliza o texto, quebrando o padrão alinhado à esquerda */
                        font-weight: bold;
                        border-radius: 5px;
                        margin: 0px 15px 15px 15px; /* Descola o botão das bordas da sidebar */
                        border: none;
                    }
                    QPushButton:hover {
                        background-color: #005999;
                        border-left: none; /* Previne a sobreposição do estilo hover padrão da sidebar */
                    }
                """)

        sidebar_layout.addWidget(btn_auditoria)
        # Destaca o botão principal da aplicação
        btn_auditoria.setStyleSheet(btn_auditoria.styleSheet() + "color: #f1c40f;")

        # Adiciona os botões ao layout da sidebar com o prefixo 'self.'
        sidebar_layout.addWidget(self.btn_painel)
        sidebar_layout.addWidget(self.btn_digitar)
        sidebar_layout.addWidget(self.btn_prestadores)

        sidebar_layout.addSpacing(15)
        sidebar_layout.addWidget(linha1)
        sidebar_layout.addSpacing(15)
        sidebar_layout.addWidget(btn_imp_legado)
        sidebar_layout.addWidget(btn_imp_sihd)
        sidebar_layout.addStretch()  # Empurra a auditoria para a base
        sidebar_layout.addWidget(linha2)
        sidebar_layout.addSpacing(15)
        sidebar_layout.addWidget(btn_auditoria)

        self.base_layout.addWidget(self.sidebar)

        # --- ÁREA DE CONTEÚDO DINÂMICO (DIREITA) ---
        self.content_frame = QFrame()
        self.content_frame.setObjectName("FrameConteudo")  # Define um ID para o seletor

        # O seletor '#' isola a cor de fundo, protegendo o estilo dos botões internos
        self.content_frame.setStyleSheet("#FrameConteudo { background-color: #f5f5f5; }")

        self.main_layout = QVBoxLayout(self.content_frame)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        self.base_layout.addWidget(self.content_frame)

    def limpar_tela(self):
        while self.main_layout.count() > 0:
            item = self.main_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # --- MÓDULOS DE PRESTADORES ---

    def abrir_tela_prestadores(self):
        self.limpar_tela()
        self.destacar_menu(self.btn_prestadores)  # Marca a aba atual
        self.carregando_tabela = True

        # Substitua a montagem do top_bar por esta:
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)

        lbl_titulo = QLabel("Cadastro de Prestadores")
        lbl_titulo.setStyleSheet("""
                    font-size: 32px; 
                    font-weight: bold; 
                    color: #2c3e50;
                    background: transparent;
                """)
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        top_layout.addWidget(lbl_titulo)
        self.main_layout.addWidget(top_bar)

        frame_cad = QFrame()
        layout_cad = QHBoxLayout(frame_cad)
        self.ent_cnes_novo = QLineEdit()
        self.ent_cnes_novo.setPlaceholderText("CNES")
        self.ent_nome_novo = QLineEdit()
        self.ent_nome_novo.setPlaceholderText("Nome Fantasia")
        btn_add = QPushButton("Adicionar Prestador")
        btn_add.clicked.connect(self.salvar_novo_prestador)

        layout_cad.addWidget(self.ent_cnes_novo)
        layout_cad.addWidget(self.ent_nome_novo)
        layout_cad.addWidget(btn_add)
        self.main_layout.addWidget(frame_cad)

        self.tabela_prestadores = QTableWidget()
        self.tabela_prestadores.setColumnCount(3)
        self.tabela_prestadores.setHorizontalHeaderLabels(["ID", "CNES", "Nome Fantasia"])
        self.tabela_prestadores.hideColumn(0)
        self.tabela_prestadores.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela_prestadores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.tabela_prestadores.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela_prestadores.customContextMenuRequested.connect(self.menu_contexto_prestador)

        self.main_layout.addWidget(self.tabela_prestadores)
        self.atualizar_grade_prestadores()
        self.carregando_tabela = False

    def salvar_novo_prestador(self):
        cnes = self.ent_cnes_novo.text().strip()
        nome = self.ent_nome_novo.text().strip()
        if cnes and nome:
            res = self.banco.inserir_prestador(cnes, nome)
            if res is True:
                self.atualizar_grade_prestadores()
                self.ent_cnes_novo.clear()
                self.ent_nome_novo.clear()
            else:
                QMessageBox.warning(self, "Erro", str(res))

    def atualizar_grade_prestadores(self):
        dados = self.banco.listar_prestadores_completos()
        self.tabela_prestadores.setRowCount(len(dados))
        for r_idx, linha in enumerate(dados):
            for c_idx, valor in enumerate(linha):
                item = QTableWidgetItem(str(valor))
                if c_idx == 0: item.setData(Qt.ItemDataRole.UserRole, valor)
                self.tabela_prestadores.setItem(r_idx, c_idx, item)

    def menu_contexto_prestador(self, pos):
        item = self.tabela_prestadores.itemAt(pos)
        if item is None: return

        linha = item.row()
        self.tabela_prestadores.selectRow(linha)

        menu = QMenu(self)
        acao_remover = QAction("Excluir Prestador (X)", self)
        acao_remover.triggered.connect(self.excluir_prestador)
        menu.addAction(acao_remover)
        menu.exec(self.tabela_prestadores.viewport().mapToGlobal(pos))

    def excluir_prestador(self):
        linha = self.tabela_prestadores.currentRow()
        if linha < 0: return

        resposta = QMessageBox.question(self, "Confirmar Exclusão",
                                        "Deseja realmente remover este prestador?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if resposta == QMessageBox.StandardButton.Yes:
            id_banco = self.tabela_prestadores.item(linha, 0).data(Qt.ItemDataRole.UserRole)
            self.banco.excluir_prestador(id_banco)
            self.atualizar_grade_prestadores()

    # --- MÓDULOS DE AÇÃO E IMPORTAÇÃO ---

    def executar_importacao_legado(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo TXT Legado", "",
                                                 "Arquivos de Texto (*.txt)")
        if caminho:
            import importador_legado
            resultado = importador_legado.importar_txt_para_sqlite(caminho)
            if isinstance(resultado, tuple):
                s, e, d = resultado
                QMessageBox.information(self, "Importação Concluída",
                                        f"Importados: {s}\nInválidos: {e}\nJá existentes: {d}")
                self.mostrar_status()
            else:
                QMessageBox.critical(self, "Erro", resultado)

    def selecionar_base_sihd(self):
        comp, ok = QInputDialog.getText(self, "Importar SIHD", "Digite a competência (AAAAMM):")

        if ok and comp and len(comp) == 6 and comp.isdigit():
            caminho, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo do SIHD", "",
                                                     "Arquivos de Texto (*.txt)")
            if caminho:
                import importador_sihd
                qtd = importador_sihd.importar_sihd_para_db(caminho, comp)
                QMessageBox.information(self, "Sucesso", f"Importados {qtd} registos do SIHD para {comp}")
                self.mostrar_status()
        elif ok:
            QMessageBox.warning(self, "Erro", "Competência inválida!")

    # --- INTERFACES VISUAIS ---

    def abrir_tela_digitar(self):
        self.limpar_tela()
        self.destacar_menu(self.btn_digitar)  # Marca a aba atual
        self.carregando_tabela = True

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)

        lbl_titulo = QLabel("Lançamento Manual de AIH")
        # Força o tamanho e remove o fundo para evitar conflitos de herança
        lbl_titulo.setStyleSheet("""
                    font-size: 32px; 
                    font-weight: bold; 
                    color: #2c3e50;
                    background: transparent;
                """)
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        top_layout.addWidget(lbl_titulo)
        self.main_layout.addWidget(top_bar)

        form_widget = QWidget()
        form_layout = QGridLayout(form_widget)

        self.ent_competencia = QLineEdit()
        self.ent_competencia.setPlaceholderText("AAAAMM")
        self.ent_competencia.setMaxLength(6)
        self.ent_competencia.textChanged.connect(self.verificar_carga_automatica)

        self.hospitais_atuais = self.obter_prestadores_dict()
        self.cb_hospital = QComboBox()
        self.cb_hospital.addItems(list(self.hospitais_atuais.keys()))

        self.ent_aih = QLineEdit()
        self.ent_aih.setPlaceholderText("Número da AIH")
        self.ent_aih.returnPressed.connect(self.salvar_aih)

        self.ent_valor = QLineEdit()
        self.ent_valor.setPlaceholderText("Valor (opcional)")
        self.ent_valor.returnPressed.connect(self.salvar_aih)

        form_layout.addWidget(QLabel("Competência:"), 0, 0)
        form_layout.addWidget(self.ent_competencia, 0, 1)
        form_layout.addWidget(QLabel("Unidade:"), 0, 2)
        form_layout.addWidget(self.cb_hospital, 0, 3)

        form_layout.addWidget(QLabel("AIH:"), 1, 0)
        form_layout.addWidget(self.ent_aih, 1, 1)

        form_layout.addWidget(QLabel("Valor:"), 2, 0)
        form_layout.addWidget(self.ent_valor, 2, 1)

        btn_salvar = QPushButton("Salvar Registro")
        btn_salvar.setFixedWidth(120)
        btn_salvar.clicked.connect(self.salvar_aih)
        form_layout.addWidget(btn_salvar, 2, 3, alignment=Qt.AlignmentFlag.AlignRight)

        self.main_layout.addWidget(form_widget)

        self.main_layout.addWidget(QLabel("Registros Digitados nesta Competência:"))
        self.tabela_digitacao = QTableWidget()
        self.tabela_digitacao.setColumnCount(5)
        self.tabela_digitacao.setHorizontalHeaderLabels(["ID", "CNES", "Nome do Hospital", "AIH", "Valor"])
        self.tabela_digitacao.hideColumn(0)
        self.tabela_digitacao.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela_digitacao.itemChanged.connect(self.salvar_edicao_direta_digitacao)

        self.tabela_digitacao.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela_digitacao.customContextMenuRequested.connect(self.abrir_menu_contexto_digitacao)

        self.main_layout.addWidget(self.tabela_digitacao)
        self.carregando_tabela = False

    def verificar_carga_automatica(self, texto):
        if len(texto) == 6:
            self.atualizar_grade_digitacao(texto)

    def atualizar_grade_digitacao(self, comp):
        self.carregando_tabela = True
        dados = self.banco.buscar_registros_locais(comp)
        self.tabela_digitacao.setRowCount(len(dados))

        mapa_cnes_nome = self.obter_mapeamento_cnes_nome()

        for row_idx, linha in enumerate(dados):
            id_reg, cnes, aih, valor = linha
            nome_hospital = mapa_cnes_nome.get(cnes, "Não encontrado")

            item_id = QTableWidgetItem(str(id_reg))
            item_id.setData(Qt.ItemDataRole.UserRole, id_reg)
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabela_digitacao.setItem(row_idx, 0, item_id)

            self.tabela_digitacao.setItem(row_idx, 1, QTableWidgetItem(cnes))
            self.tabela_digitacao.setItem(row_idx, 2, QTableWidgetItem(nome_hospital))
            self.tabela_digitacao.setItem(row_idx, 3, QTableWidgetItem(aih))

            item_valor = QTableWidgetItem(formatar_para_real(valor))
            item_valor.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabela_digitacao.setItem(row_idx, 4, item_valor)

        self.carregando_tabela = False

    def salvar_edicao_direta_digitacao(self, item):
        if self.carregando_tabela: return

        row = item.row()
        col_ui = item.column()
        mapa_colunas = {1: 1, 3: 2, 4: 3}

        if col_ui not in mapa_colunas:
            return

        col_db = mapa_colunas[col_ui]
        id_reg = self.tabela_digitacao.item(row, 0).data(Qt.ItemDataRole.UserRole)

        novo_valor = limpar_valor_real(item.text().strip()) if col_ui == 4 else item.text().strip()

        if self.banco.atualizar_registro_local(id_reg, col_db, novo_valor):
            if col_ui == 4:
                self.carregando_tabela = True
                item.setText(formatar_para_real(novo_valor))
                self.carregando_tabela = False
            item.setBackground(QColor("#e8f8f5"))

    def salvar_aih(self):
        comp = self.ent_competencia.text().strip()
        hospital_nome = self.cb_hospital.currentText()
        cnes = self.hospitais_atuais[hospital_nome]
        aih = self.ent_aih.text().strip()
        valor_raw = self.ent_valor.text().strip()

        valor_limpo = limpar_valor_real(valor_raw) if valor_raw else "0,00"

        if len(comp) != 6 or not comp.isdigit():
            QMessageBox.warning(self, "Erro", "Competência inválida.")
            return

        if valor_raw and not re.match(r"^\d+(,\d{2})?$", valor_limpo):
            QMessageBox.warning(self, "Erro", "Formato de valor inválido (use vírgula).")
            return

        if not validador.validar_aih(aih):
            QMessageBox.critical(self, "AIH Inválida", "Falha no dígito verificador.")
            return

        sucesso = self.banco.inserir_registro(comp, cnes, aih, valor_limpo)

        if sucesso:
            self.atualizar_grade_digitacao(comp)
            self.ent_aih.clear()
            self.ent_valor.clear()
            self.ent_aih.setFocus()
        else:
            QMessageBox.critical(self, "Erro de Persistência", "Falha ao gravar o registro no banco de dados.")

    # --- STATUS E DETALHES ---

    def mostrar_status(self):
        self.limpar_tela()
        self.destacar_menu(self.btn_painel)  # Marca a aba atual

        # Cabeçalho SUS centralizado e equilibrado
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_logo = QLabel()
        caminho_logo = os.path.join(os.path.dirname(__file__), "icon_sus.png")
        pixmap = QPixmap(caminho_logo)
        if not pixmap.isNull():
            lbl_logo.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
        else:
            lbl_logo.setText("[LOGO]")

        # Título Oficial do Sistema
        lbl_titulo = QLabel("Batimento - Comparador de Registros de AIH")

        # Usamos setStyleSheet para "atropelar" a configuração global de 14px
        lbl_titulo.setStyleSheet("""
                font-size: 35px; 
                font-weight: bold; 
                color: #2c3e50;
                background: transparent;
            """)

        header_layout.addWidget(lbl_logo)
        header_layout.addSpacing(20)
        header_layout.addWidget(lbl_titulo)
        self.main_layout.addWidget(header_container)
        self.main_layout.addSpacing(20)

        # --- ESTRUTURA CENTRALIZADA DA TABELA ---
        # Criamos um container para impedir que a tabela estique até as bordas da janela
        table_container = QWidget()
        table_central_layout = QHBoxLayout(table_container)
        table_central_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        locais = self.banco.listar_competencias_locais()
        sihds = self.banco.listar_competencias_sihd()
        todas_competencias = sorted(list(set(locais) | set(sihds)), reverse=True)

        self.tabela_status = QTableWidget()
        self.tabela_status.setColumnCount(2)
        self.tabela_status.setRowCount(len(todas_competencias))
        self.tabela_status.setHorizontalHeaderLabels(["Digitação Local", "Base SIHD"])

        # Ajustes de Dimensão: Tabela estreita e sem números de linha
        self.tabela_status.setFixedWidth(520)  # Largura fixa para evitar o efeito "esticado"
        self.tabela_status.setMinimumHeight(400)
        self.tabela_status.verticalHeader().setVisible(False)  # Remove a coluna 1, 2, 3...
        self.tabela_status.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabela_status.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_status.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_status.cellDoubleClicked.connect(self.abrir_detalhes_competencia)

        # --- NOVA IMPLEMENTAÇÃO: REMOVE O FOCO AUTOMÁTICO ---
        self.tabela_status.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabela_status.clearSelection()

        # --- REATIVAÇÃO DO MENU DE CONTEXTO ---
        self.tabela_status.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela_status.customContextMenuRequested.connect(self.menu_contexto_status)
        # --------------------------------------

        header = self.tabela_status.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for row, comp in enumerate(todas_competencias):
            data_fmt = f"{comp[4:]}/{comp[:4]}"

            # Status Local
            existe_local = comp in locais
            item_local = QTableWidgetItem(data_fmt if existe_local else "Pendente")
            item_local.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_local.setData(Qt.ItemDataRole.UserRole, comp)

            # Cor técnica: Verde para OK, Cinza suave para pendente (menos agressivo que vermelho total)
            if existe_local:
                item_local.setForeground(QColor("#27ae60"))
                item_local.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            else:
                item_local.setForeground(QColor("#95a5a6"))

            # Status SIHD
            existe_sihd = comp in sihds
            item_sihd = QTableWidgetItem(data_fmt if existe_sihd else "Pendente")
            item_sihd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sihd.setData(Qt.ItemDataRole.UserRole, comp)

            if existe_sihd:
                item_sihd.setForeground(QColor("#27ae60"))
                item_sihd.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            else:
                item_sihd.setForeground(QColor("#95a5a6"))

            self.tabela_status.setItem(row, 0, item_local)
            self.tabela_status.setItem(row, 1, item_sihd)

        self.tabela_status.setStyleSheet("""
            QTableWidget { 
                background-color: #ffffff; 
                gridline-color: #f0f0f0; 
                border: 1px solid #dcdcdc; 
                border-radius: 8px;
            }
            QHeaderView::section { 
                background-color: #f8f9fa; 
                padding: 12px; 
                border-bottom: 2px solid #007acc; 
                font-weight: bold; 
            }
        """)

        table_central_layout.addWidget(self.tabela_status)
        self.main_layout.addWidget(table_container)
        self.main_layout.addSpacing(20)

        # Botão de ação centralizado
        btn_atualizar = QPushButton("🔄 Atualizar Painel")
        btn_atualizar.setFixedWidth(220)
        btn_atualizar.clicked.connect(self.mostrar_status)
        self.main_layout.addWidget(btn_atualizar, alignment=Qt.AlignmentFlag.AlignCenter)

        self.tabela_status.clearSelection()

    def abrir_detalhes_competencia(self, row, col):
        item = self.tabela_status.item(row, col)
        if not item or item.text() == "Inexistente": return
        self.desenhar_tela_detalhes(item.data(Qt.ItemDataRole.UserRole), "Local" if col == 0 else "SIHD")

    def desenhar_tela_detalhes(self, comp, origem):
        self.limpar_tela()
        self.destacar_menu(self.btn_painel)  # Mantém o Painel marcado, pois Detalhes é um subnível dele
        self.carregando_tabela = True

        data_fmt = f"{comp[4:]}/{comp[:4]}"
        lbl_titulo = QLabel(f"Detalhamento: Competência {data_fmt} - Base {origem}")
        lbl_titulo.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50;")
        self.main_layout.addWidget(lbl_titulo)

        # Cabeçalho simplificado apenas com a busca
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 10, 0, 10)

        self.txt_busca = QLineEdit()
        self.txt_busca.setPlaceholderText("Pesquisar nesta lista...")
        self.txt_busca.setMinimumHeight(35)
        self.txt_busca.textChanged.connect(self.filtrar_tabela_detalhes)

        top_layout.addWidget(self.txt_busca)
        self.main_layout.addWidget(top_bar)

        self.tabela_detalhes = QTableWidget()
        self.tabela_detalhes.setStyleSheet("""
                QTableWidget { background-color: #ffffff; gridline-color: #dcdcdc; }
                QHeaderView::section { background-color: #f8f9fa; font-weight: bold; }
            """)

        mapa_cnes_nome = self.obter_mapeamento_cnes_nome()

        if origem == "Local":
            dados = self.banco.buscar_registros_locais(comp)
            self.tabela_detalhes.setColumnCount(5)
            self.tabela_detalhes.setHorizontalHeaderLabels(["ID", "CNES", "Nome do Hospital", "AIH", "Valor"])
            self.tabela_detalhes.itemChanged.connect(self.salvar_edicao_celula)
        else:  # SIHD
            dados = self.banco.buscar_registros_sihd(comp)
            self.tabela_detalhes.setColumnCount(6)
            # Rótulos atualizados: Valor movido para a última posição
            self.tabela_detalhes.setHorizontalHeaderLabels(
                ["ID", "CNES", "Nome do Hospital", "AIH", "Paciente", "Valor"])
            self.tabela_detalhes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.tabela_detalhes.setRowCount(len(dados))
        for row_idx, linha_dados in enumerate(dados):
            id_reg, cnes = linha_dados[0], linha_dados[1]
            nome_hospital = mapa_cnes_nome.get(cnes, "Não encontrado")

            item_id = QTableWidgetItem(str(id_reg))
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_id.setData(Qt.ItemDataRole.UserRole, id_reg)
            self.tabela_detalhes.setItem(row_idx, 0, item_id)

            self.tabela_detalhes.setItem(row_idx, 1, QTableWidgetItem(cnes))
            self.tabela_detalhes.setItem(row_idx, 2, QTableWidgetItem(nome_hospital))

            if origem == "Local":
                aih, valor = linha_dados[2], linha_dados[3]
                self.tabela_detalhes.setItem(row_idx, 3, QTableWidgetItem(aih))
                item_valor = QTableWidgetItem(formatar_para_real(valor))
                item_valor.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabela_detalhes.setItem(row_idx, 4, item_valor)
            else:  # SIHD
                aih, valor, paciente = linha_dados[2], linha_dados[3], linha_dados[4]
                self.tabela_detalhes.setItem(row_idx, 3, QTableWidgetItem(aih))
                # Paciente agora no índice 4
                self.tabela_detalhes.setItem(row_idx, 4, QTableWidgetItem(paciente))
                # Valor formatado agora no índice 5
                item_valor = QTableWidgetItem(formatar_para_real(valor))
                item_valor.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabela_detalhes.setItem(row_idx, 5, item_valor)

        self.tabela_detalhes.hideColumn(0)
        self.tabela_detalhes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.main_layout.addWidget(self.tabela_detalhes)

        if origem == "Local":
            btn_excluir = QPushButton("Excluir Registro Selecionado")
            btn_excluir.setStyleSheet("background-color: #e74c3c; color: white;")
            btn_excluir.clicked.connect(self.excluir_registro_selecionado)
            self.main_layout.addWidget(btn_excluir, alignment=Qt.AlignmentFlag.AlignRight)

        self.carregando_tabela = False

    def filtrar_tabela_detalhes(self, texto):
        termo = texto.lower()
        for row in range(self.tabela_detalhes.rowCount()):
            mostrar_linha = any(
                item and termo in item.text().lower()
                for col in range(self.tabela_detalhes.columnCount())
                if (item := self.tabela_detalhes.item(row, col))
            )
            self.tabela_detalhes.setRowHidden(row, not mostrar_linha)

    def salvar_edicao_celula(self, item):
        if self.carregando_tabela: return

        row = item.row()
        col_ui = item.column()
        mapa_colunas = {1: 1, 3: 2, 4: 3}

        if col_ui not in mapa_colunas:
            return

        col_db = mapa_colunas[col_ui]
        id_banco = self.tabela_detalhes.item(row, 0).data(Qt.ItemDataRole.UserRole)

        novo_valor = limpar_valor_real(item.text().strip()) if col_ui == 4 else item.text().strip()

        if self.banco.atualizar_registro_local(id_banco, col_db, novo_valor):
            if col_ui == 4:
                self.carregando_tabela = True
                item.setText(formatar_para_real(novo_valor))
                self.carregando_tabela = False
            item.setBackground(QColor("#e8f8f5"))
        else:
            QMessageBox.warning(self, "Falha", "Não foi possível atualizar o banco de dados.")

    def excluir_registro_selecionado(self):
        linha_selecionada = self.tabela_detalhes.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Atenção", "Selecione uma linha para excluir.")
            return

        resposta = QMessageBox.question(self, "Confirmar Exclusão",
                                        "Tem certeza que deseja excluir este registro?\nEsta ação não pode ser desfeita.",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if resposta == QMessageBox.StandardButton.Yes:
            id_banco = self.tabela_detalhes.item(linha_selecionada, 0).data(Qt.ItemDataRole.UserRole)
            if self.banco.excluir_registro_local(id_banco):
                self.tabela_detalhes.removeRow(linha_selecionada)
            else:
                QMessageBox.critical(self, "Erro", "Falha ao excluir o registro no banco de dados.")

    # --- PROCESSAMENTO ---

    def processar_dados(self):
        """Abre uma janela compacta para seleção rápida da competência de auditoria."""
        # Consolida competências de ambas as bases (Local e SIHD)
        locais = self.banco.listar_competencias_locais()
        sihds = self.banco.listar_competencias_sihd()
        comps = sorted(list(set(locais) | set(sihds)), reverse=True)

        if not comps:
            QMessageBox.warning(self, "Erro", "Nenhuma base encontrada no banco para auditoria.")
            return

        # Configuração do Diálogo Pequeno e Objetivo
        dialog = QDialog(self)
        dialog.setWindowTitle("Selecionar Competência")
        dialog.setFixedSize(320, 420)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Escolha o mês para auditoria:"))

        # Lista com Barra de Rolagem
        self.lista_comps = QListWidget()
        self.lista_comps.setStyleSheet("QListWidget { background-color: #ffffff; border: 1px solid #ced4da; }")

        for c in comps:
            # Exibe MM/AAAA mas mantém AAAAMM nos dados do item
            item = QListWidgetItem(f"{c[4:]}/{c[:4]}")
            item.setData(Qt.ItemDataRole.UserRole, c)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lista_comps.addItem(item)

        # Inteligência: Seleciona e foca na primeira (mais recente) automaticamente
        if self.lista_comps.count() > 0:
            self.lista_comps.setCurrentRow(0)
            self.lista_comps.scrollToTop()

        layout.addWidget(self.lista_comps)

        # Opções de Auditoria Compactas
        check_valores = QCheckBox("Comparar Valores (Divergentes)")
        check_valores.setChecked(True)
        layout.addWidget(check_valores)

        check_aih = QCheckBox("Conferir nº AIH (Não Coincidentes)")
        check_aih.setChecked(True)
        layout.addWidget(check_aih)

        # Botão de Execução
        btn_iniciar = QPushButton("GERAR")
        btn_iniciar.setMinimumHeight(40)

        def confirmar():
            item_sel = self.lista_comps.currentItem()
            if not item_sel: return

            comp = item_sel.data(Qt.ItemDataRole.UserRole)
            val_checked = check_valores.isChecked()
            aih_checked = check_aih.isChecked()

            if not val_checked and not aih_checked:
                QMessageBox.warning(dialog, "Atenção", "Selecione um critério.")
                return

            dialog.accept()
            dict_hospitais = self.obter_prestadores_dict()

            try:
                # Chama o novo processamento sem gerar PDFs
                df_div, df_nc = processamento.processar_relatorios_dados(
                    comp, comparar_valores=val_checked, verificar_aih=aih_checked
                )

                if (df_div is None or df_div.empty) and (df_nc is None or df_nc.empty):
                    QMessageBox.information(self, "Concluído",
                                            "Auditoria finalizada. Não foram encontradas divergências!")
                    return

                # Renderiza a nova tela na área principal
                self.exibir_resultados_auditoria(comp, df_div, df_nc, dict_hospitais)

            except Exception as e:
                QMessageBox.critical(self, "Erro", str(e))

        btn_iniciar.clicked.connect(confirmar)
        layout.addWidget(btn_iniciar)

        dialog.exec()

    def exibir_resultados_auditoria(self, comp, df_div, df_nc, dict_hospitais):
        self.limpar_tela()

        # O módulo ativo passa a ser o próprio painel, mas não precisa forçar estilo, pois veio do pop-up
        data_fmt = f"{comp[4:]}/{comp[:4]}"

        # --- CABEÇALHO COM TÍTULO E BOTÃO EXPORTAR ---
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)

        lbl_titulo = QLabel(f"Resultados da Conferência - {data_fmt}")
        lbl_titulo.setStyleSheet("font-size: 28px; font-weight: bold; color: #2c3e50;")

        # Criação do Botão de Exportar com Menu Suspenso (Dropdown)
        btn_exportar = QPushButton("📥 Exportar Resultados")
        btn_exportar.setStyleSheet("background-color: #27ae60; color: white;")
        menu_exportar = QMenu(self)

        act_pdf = QAction("📄 Exportar como PDF", self)
        act_pdf.triggered.connect(lambda: self.exportar_resultados_pdf(comp, df_div, df_nc, dict_hospitais))

        act_excel = QAction("📊 Exportar como Excel (.xlsx)", self)
        act_excel.triggered.connect(lambda: self.exportar_resultados_excel(comp, df_div, df_nc))

        menu_exportar.addAction(act_pdf)
        menu_exportar.addAction(act_excel)
        btn_exportar.setMenu(menu_exportar)

        top_layout.addWidget(lbl_titulo)
        top_layout.addStretch()
        top_layout.addWidget(btn_exportar)
        self.main_layout.addWidget(top_bar)

        # --- ABAS (TABS) ---
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ced4da; background-color: #ffffff; }
            QTabBar::tab { background: #e0e0e0; padding: 10px 20px; font-weight: bold; }
            QTabBar::tab:selected { background: #ffffff; border-top: 3px solid #007acc; }
        """)

        mapa_cnes = {v: k for k, v in dict_hospitais.items()}

        # ABA 1: DIVERGENTES
        if df_div is not None and not df_div.empty:
            tab_div = QWidget()
            layout_div = QVBoxLayout(tab_div)

            tabela_div = QTableWidget()
            tabela_div.setColumnCount(6)
            tabela_div.setHorizontalHeaderLabels(["Unidade", "AIH", "Paciente", "V. Local", "V. SIHD", "Diferença"])
            tabela_div.setRowCount(len(df_div))
            tabela_div.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

            for i, row in enumerate(df_div.itertuples()):
                nome_unidade = mapa_cnes.get(row.cnes, row.cnes)
                paciente = row.paciente if pd.notnull(row.paciente) else "Não Informado"

                tabela_div.setItem(i, 0, QTableWidgetItem(nome_unidade))
                tabela_div.setItem(i, 1, QTableWidgetItem(str(row.aih)))
                tabela_div.setItem(i, 2, QTableWidgetItem(str(paciente)))

                # Valores alinhados à direita
                i_loc = QTableWidgetItem(row.v_local_fmt)
                i_loc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela_div.setItem(i, 3, i_loc)

                i_sihd = QTableWidgetItem(row.v_sihd_fmt)
                i_sihd.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela_div.setItem(i, 4, i_sihd)

                i_dif = QTableWidgetItem(row.dif_fmt)
                i_dif.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                i_dif.setForeground(QColor("#c0392b"))  # Diferença a vermelho para destaque
                tabela_div.setItem(i, 5, i_dif)

            tabela_div.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            layout_div.addWidget(tabela_div)
            tabs.addTab(tab_div, f"Divergência de Valores ({len(df_div)})")

        # ABA 2: NÃO COINCIDENTES
        if df_nc is not None and not df_nc.empty:
            tab_nc = QWidget()
            layout_nc = QVBoxLayout(tab_nc)

            tabela_nc = QTableWidget()
            tabela_nc.setColumnCount(4)
            tabela_nc.setHorizontalHeaderLabels(["Unidade", "AIH", "Paciente", "Valor SIHD"])
            tabela_nc.setRowCount(len(df_nc))
            tabela_nc.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

            for i, row in enumerate(df_nc.itertuples()):
                nome_unidade = mapa_cnes.get(row.cnes, row.cnes)
                paciente = row.paciente if pd.notnull(row.paciente) else "Não Informado"

                tabela_nc.setItem(i, 0, QTableWidgetItem(nome_unidade))
                tabela_nc.setItem(i, 1, QTableWidgetItem(str(row.aih)))
                tabela_nc.setItem(i, 2, QTableWidgetItem(str(paciente)))

                i_sihd = QTableWidgetItem(row.v_sihd_fmt)
                i_sihd.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela_nc.setItem(i, 3, i_sihd)

            tabela_nc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            layout_nc.addWidget(tabela_nc)
            tabs.addTab(tab_nc, f"Não Coincidentes - Faltantes ({len(df_nc)})")

        self.main_layout.addWidget(tabs)

    def exportar_resultados_excel(self, comp, df_div, df_nc):
        import pandas as pd
        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório Excel", f"Auditoria_SIHD_{comp}.xlsx",
                                                 "Excel (*.xlsx)")
        if caminho:
            try:
                # O ExcelWriter permite salvar várias abas no mesmo ficheiro
                with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
                    if df_div is not None and not df_div.empty:
                        # Seleciona apenas as colunas numéricas puras para cálculos no Excel
                        df_exp_div = df_div[
                            ['cnes', 'aih', 'paciente', 'v_num_local', 'v_num_sihd', 'diferenca']].copy()
                        df_exp_div.columns = ['CNES', 'AIH', 'Paciente', 'Valor Digitação', 'Valor Governo',
                                              'Diferença Numérica']
                        df_exp_div.to_excel(writer, sheet_name='Divergentes', index=False)

                    if df_nc is not None and not df_nc.empty:
                        df_exp_nc = df_nc[['cnes', 'aih', 'paciente', 'v_num_sihd']].copy()
                        df_exp_nc.columns = ['CNES', 'AIH', 'Paciente', 'Valor Governo']
                        df_exp_nc.to_excel(writer, sheet_name='Faltantes na Local', index=False)

                QMessageBox.information(self, "Sucesso", "Ficheiro Excel gerado com sucesso!")
            except ImportError:
                QMessageBox.critical(self, "Dependência Faltante",
                                     "Por favor, instale o openpyxl executando o comando no terminal:\npip install openpyxl")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao exportar Excel: {str(e)}")

    def exportar_resultados_pdf(self, comp, df_div, df_nc, hospitais):
        dir_saida = QFileDialog.getExistingDirectory(self, "Selecione a Pasta para Salvar os PDFs")
        if dir_saida:
            try:
                pdfs = []
                if df_div is not None and not df_div.empty:
                    p1 = processamento.gerar_pdf(df_div, 'divergentes', comp, dir_saida, hospitais)
                    if p1: pdfs.append(p1)

                if df_nc is not None and not df_nc.empty:
                    p2 = processamento.gerar_pdf(df_nc, 'nao_coincidentes', comp, dir_saida, hospitais)
                    if p2: pdfs.append(p2)

                if pdfs:
                    QMessageBox.information(self, "Sucesso",
                                            f"{len(pdfs)} arquivo(s) PDF gerado(s) com sucesso na pasta selecionada.")
                    # Abertura automática opcional
                    import platform, subprocess
                    for p in pdfs:
                        if platform.system() == 'Windows':
                            os.startfile(p)
                        else:
                            subprocess.call(['open', p])
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao exportar PDF: {str(e)}")


    def abrir_menu_contexto_digitacao(self, pos):
        item = self.tabela_digitacao.itemAt(pos)
        if item is None: return

        linha = item.row()
        self.tabela_digitacao.selectRow(linha)

        menu = QMenu(self)
        acao_remover = QAction("Remover Registro (X)", self)
        acao_remover.triggered.connect(self.excluir_da_digitacao)
        menu.addAction(acao_remover)
        menu.exec(self.tabela_digitacao.viewport().mapToGlobal(pos))

    def excluir_da_digitacao(self):
        linha = self.tabela_digitacao.currentRow()
        if linha < 0: return

        resposta = QMessageBox.question(self, "Confirmar Exclusão",
                                        "Tem certeza que deseja remover este registro da base local?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if resposta == QMessageBox.StandardButton.Yes:
            id_reg = self.tabela_digitacao.item(linha, 0).data(Qt.ItemDataRole.UserRole)
            if self.banco.excluir_registro_local(id_reg):
                self.tabela_digitacao.removeRow(linha)
            else:
                QMessageBox.critical(self, "Erro", "Falha ao excluir o registro no banco de dados.")

    def menu_contexto_status(self, pos):
        """Gera menu com opções de exclusão independente ou total."""
        item = self.tabela_status.itemAt(pos)
        if not item: return

        linha = item.row()
        coluna = item.column()
        self.tabela_status.selectRow(linha)

        comp = item.data(Qt.ItemDataRole.UserRole)
        data_fmt = f"{comp[4:]}/{comp[:4]}"

        menu = QMenu(self)

        # Opções dinâmicas baseadas na coluna ou gerais
        acao_local = QAction(f"Excluir apenas Digitação Local ({data_fmt})", self)
        acao_local.triggered.connect(lambda: self.confirmar_exclusao(comp, "Local"))

        acao_sihd = QAction(f"Excluir apenas Base SIHD ({data_fmt})", self)
        acao_sihd.triggered.connect(lambda: self.confirmar_exclusao(comp, "SIHD"))

        acao_total = QAction(f"Excluir Ambas (Limpeza Total {data_fmt})", self)
        acao_total.triggered.connect(lambda: self.confirmar_exclusao(comp, "Total"))

        menu.addAction(acao_local)
        menu.addAction(acao_sihd)
        menu.addSeparator()
        menu.addAction(acao_total)

        menu.exec(self.tabela_status.viewport().mapToGlobal(pos))

    def confirmar_exclusao(self, comp, tipo):
        data_fmt = f"{comp[4:]}/{comp[:4]}"
        msg = f"Confirmar exclusão da base {tipo} para a competência {data_fmt}?"
        if tipo == "Total":
            msg = f"ATENÇÃO: Isso excluirá permanentemente os dados LOCAIS e do SIHD de {data_fmt}. Confirmar?"

        resposta = QMessageBox.question(self, "Aviso de Exclusão", msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if resposta == QMessageBox.StandardButton.Yes:
            if tipo == "Local":
                self.banco.limpar_local_competencia(comp)
            elif tipo == "SIHD":
                self.banco.limpar_sihd_competencia(comp)  # Já existe no seu banco_dados.py
            else:
                self.banco.excluir_competencia_total(comp)

            self.mostrar_status()


if __name__ == "__main__":
    # --- INTEGRAÇÃO NATIVA COM WINDOWS ---
    # Força a barra de tarefas a reconhecer a aplicação como independente
    if os.name == 'nt':  # Verifica se o sistema é Windows
        myappid = 'auditoria.batimento.app.1.0'  # ID arbitrário e único
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)

    # Definição do ícone global da aplicação (afeta a barra de tarefas)
    caminho_icone_app = os.path.join(os.path.dirname(__file__), "icon_btm.ico")
    if os.path.exists(caminho_icone_app):
        app.setWindowIcon(QIcon(caminho_icone_app))

    app.setStyle("Fusion")

    app.setStyleSheet("""
        QWidget { background-color: #f5f5f5; color: #2c3e50; font-family: "Segoe UI", Arial, sans-serif; font-size: 14px; }
        QMenuBar { background-color: #ffffff; border-bottom: 1px solid #dcdcdc; }
        QMenuBar::item:selected { background-color: #e0e0e0; }
        QMenu { background-color: #ffffff; border: 1px solid #dcdcdc; }
        QMenu::item:selected { background-color: #007acc; color: #ffffff; }
        QPushButton { background-color: #007acc; color: #ffffff; border: none; padding: 8px; border-radius: 4px; font-weight: bold; }
        QPushButton:hover { background-color: #005999; }
        QLineEdit, QComboBox { background-color: #ffffff; border: 1px solid #ced4da; padding: 5px; border-radius: 3px; }
        QScrollArea { border: 1px solid #ced4da; background-color: #ffffff; }
        QFrame { border: none; }
        QTableWidget { font-family: "Segoe UI"; font-size: 13px; }
    """)

    window = App()
    window.show()
    sys.exit(app.exec())