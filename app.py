import os
import re
import sys

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QLabel, QLineEdit, QComboBox, QPushButton,
                             QFileDialog, QMessageBox, QInputDialog, QDialog, QCheckBox,
                             QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
                             QHeaderView, QAbstractItemView, QMenu)

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

        self.resize(1100, 700) # Aumentado para acomodar nova coluna

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

    def setup_ui(self):
        menu_bar = self.menuBar()

        menu_navegacao = menu_bar.addMenu("Navegação")
        menu_importacao = menu_bar.addMenu("Importação")
        menu_auditoria = menu_bar.addMenu("Auditoria")

        act_painel = QAction("Painel de Sincronização", self)
        act_painel.triggered.connect(self.mostrar_status)
        menu_navegacao.addAction(act_painel)

        act_digitar = QAction("Lançamento Manual", self)
        act_digitar.triggered.connect(self.abrir_tela_digitar)
        menu_navegacao.addAction(act_digitar)

        act_prestadores = QAction("Gerenciar Prestadores", self)
        act_prestadores.triggered.connect(self.abrir_tela_prestadores)
        menu_navegacao.addAction(act_prestadores)

        act_imp_legado = QAction("Importar TXT (Digitação Local)", self)
        act_imp_legado.triggered.connect(self.executar_importacao_legado)
        menu_importacao.addAction(act_imp_legado)

        act_imp_sihd = QAction("Importar Base SIHD", self)
        act_imp_sihd.triggered.connect(self.selecionar_base_sihd)
        menu_importacao.addAction(act_imp_sihd)

        act_processar = QAction("Executar Auditoria", self)
        act_processar.triggered.connect(self.processar_dados)
        menu_auditoria.addAction(act_processar)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

    def limpar_tela(self):
        while self.main_layout.count() > 0:
            item = self.main_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    # --- MÓDULOS DE PRESTADORES ---

    def abrir_tela_prestadores(self):
        self.limpar_tela()
        self.carregando_tabela = True

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        btn_voltar = QPushButton("⬅ Voltar ao Painel")
        btn_voltar.clicked.connect(self.mostrar_status)
        lbl_titulo = QLabel("Cadastro de Prestadores")
        lbl_titulo.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        top_layout.addWidget(btn_voltar)
        top_layout.addStretch()
        top_layout.addWidget(lbl_titulo)
        top_layout.addStretch()
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
                QMessageBox.information(self, "Sucesso", f"Importados {qtd} registos do governo para {comp}")
                self.mostrar_status()
        elif ok:
            QMessageBox.warning(self, "Erro", "Competência inválida!")

    # --- INTERFACES VISUAIS ---

    def abrir_tela_digitar(self):
        self.limpar_tela()
        self.carregando_tabela = True

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)

        btn_voltar = QPushButton("⬅ Voltar ao Painel")
        btn_voltar.setFixedWidth(150)
        btn_voltar.clicked.connect(self.mostrar_status)

        lbl_titulo = QLabel("Lançamento Manual de AIH")
        lbl_titulo.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        top_layout.addWidget(btn_voltar)
        top_layout.addStretch()
        top_layout.addWidget(lbl_titulo)
        top_layout.addStretch()
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

        btn_salvar = QPushButton("💾 Salvar")
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

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_logo = QLabel()
        caminho_logo = os.path.join(os.path.dirname(__file__), "icon_btm.png")
        pixmap = QPixmap(caminho_logo)

        if not pixmap.isNull():
            pixmap_redimensionado = pixmap.scaledToHeight(70, Qt.TransformationMode.SmoothTransformation)
            lbl_logo.setPixmap(pixmap_redimensionado)
        else:
            lbl_logo.setText("[Logo]")
            lbl_logo.setStyleSheet("color: #e74c3c; font-weight: bold;")

        lbl_titulo = QLabel("Batimento - Comparador de Registros de AIH")
        # A folha de estilo (stylesheet) tem precedência sobre setFont.
        # Unificamos todas as propriedades de estilo aqui para garantir a aplicação.
        lbl_titulo.setStyleSheet("font-family: Arial; font-size: 42px; font-weight: bold; color: #007acc;")

        # Logo da Direita (SUS)
        lbl_logo_sus = QLabel()
        caminho_logo_sus = os.path.join(os.path.dirname(__file__), "icon_sus.png")
        pixmap_sus = QPixmap(caminho_logo_sus)
        if not pixmap_sus.isNull():
            pixmap_sus_redim = pixmap_sus.scaledToHeight(70, Qt.TransformationMode.SmoothTransformation)
            lbl_logo_sus.setPixmap(pixmap_sus_redim)

        header_layout.addWidget(lbl_logo)
        header_layout.addSpacing(15)
        header_layout.addWidget(lbl_titulo)
        header_layout.addSpacing(15)
        header_layout.addWidget(lbl_logo_sus)

        self.main_layout.addWidget(header_widget)
        self.main_layout.addSpacing(15)

        locais = self.banco.listar_competencias_locais()
        sihds = self.banco.listar_competencias_sihd()
        todas_competencias = sorted(list(set(locais) | set(sihds)), reverse=True)

        self.tabela_status = QTableWidget()
        self.tabela_status.setColumnCount(2)
        self.tabela_status.setRowCount(len(todas_competencias))
        self.tabela_status.setHorizontalHeaderLabels(["Digitação Local", "Base SIHD (Governo)"])
        self.tabela_status.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela_status.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_status.cellDoubleClicked.connect(self.abrir_detalhes_competencia)

        for row, comp in enumerate(todas_competencias):
            data_fmt = f"{comp[4:]}/{comp[:4]}"
            item_local = QTableWidgetItem(data_fmt if comp in locais else "Inexistente")
            item_local.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_local.setData(Qt.ItemDataRole.UserRole, comp)
            item_local.setForeground(QColor("#27ae60") if comp in locais else QColor("#e74c3c"))
            if not comp in locais: item_local.setFont(QFont("Arial", 11, QFont.Weight.Bold))

            item_sihd = QTableWidgetItem(data_fmt if comp in sihds else "Inexistente")
            item_sihd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sihd.setData(Qt.ItemDataRole.UserRole, comp)
            item_sihd.setForeground(QColor("#27ae60") if comp in sihds else QColor("#e74c3c"))
            if not comp in sihds: item_sihd.setFont(QFont("Arial", 11, QFont.Weight.Bold))

            self.tabela_status.setItem(row, 0, item_local)
            self.tabela_status.setItem(row, 1, item_sihd)

        self.tabela_status.setStyleSheet("""
                QTableWidget { background-color: #ffffff; gridline-color: #dcdcdc; border: 1px solid #ced4da; }
                QHeaderView::section { background-color: #f8f9fa; padding: 8px; border: 1px solid #dcdcdc; font-weight: bold; }
            """)
        self.main_layout.addWidget(self.tabela_status)

        btn_atualizar = QPushButton("Atualizar Painel")
        btn_atualizar.setFixedWidth(200)
        btn_atualizar.clicked.connect(self.mostrar_status)
        self.main_layout.addWidget(btn_atualizar, alignment=Qt.AlignmentFlag.AlignCenter)

    def abrir_detalhes_competencia(self, row, col):
        item = self.tabela_status.item(row, col)
        if not item or item.text() == "Inexistente": return
        self.desenhar_tela_detalhes(item.data(Qt.ItemDataRole.UserRole), "Local" if col == 0 else "SIHD")

    def desenhar_tela_detalhes(self, comp, origem):
        self.limpar_tela()
        self.carregando_tabela = True

        data_fmt = f"{comp[4:]}/{comp[:4]}"
        lbl_titulo = QLabel(f"Detalhamento: Competência {data_fmt} - Base {origem}")
        lbl_titulo.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        self.main_layout.addWidget(lbl_titulo)

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)

        btn_voltar = QPushButton("⬅ Voltar ao Painel")
        btn_voltar.clicked.connect(self.mostrar_status)

        self.txt_busca = QLineEdit()
        self.txt_busca.setPlaceholderText("Buscar por AIH, CNES, Nome do Hospital ou Paciente...")
        self.txt_busca.textChanged.connect(self.filtrar_tabela_detalhes)

        top_layout.addWidget(btn_voltar)
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
        else: # SIHD
            dados = self.banco.buscar_registros_sihd(comp)
            self.tabela_detalhes.setColumnCount(6)
            self.tabela_detalhes.setHorizontalHeaderLabels(["ID", "CNES", "Nome do Hospital", "AIH", "Valor", "Paciente"])
            self.tabela_detalhes.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.tabela_detalhes.setRowCount(len(dados))
        for row_idx, linha_dados in enumerate(dados):
            id_reg = linha_dados[0]
            cnes = linha_dados[1]
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
            else: # SIHD
                aih, valor, paciente = linha_dados[2], linha_dados[3], linha_dados[4]
                self.tabela_detalhes.setItem(row_idx, 3, QTableWidgetItem(aih))
                item_valor = QTableWidgetItem(formatar_para_real(valor))
                item_valor.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabela_detalhes.setItem(row_idx, 4, item_valor)
                self.tabela_detalhes.setItem(row_idx, 5, QTableWidgetItem(paciente))

        self.tabela_detalhes.hideColumn(0)
        self.tabela_detalhes.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.main_layout.addWidget(self.tabela_detalhes)

        if origem == "Local":
            btn_excluir = QPushButton("🗑️ Excluir Registro Selecionado")
            btn_excluir.setStyleSheet("background-color: #e74c3c;")
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
        locais = self.banco.listar_competencias_locais()
        sihds = self.banco.listar_competencias_sihd()
        comps = sorted(list(set(locais) | set(sihds)), reverse=True)

        if not comps:
            QMessageBox.warning(self, "Erro", "Nenhuma base encontrada no banco.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Configurar Auditoria")
        dialog.setFixedSize(400, 300)
        dialog_layout = QVBoxLayout(dialog)

        dialog_layout.addWidget(QLabel("Selecione o Mês:"))
        cb_comp = QComboBox()
        cb_comp.addItems(comps)
        dialog_layout.addWidget(cb_comp)

        dialog_layout.addSpacing(20)
        lbl_modo = QLabel("Modo de Comparação:")
        lbl_modo.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        dialog_layout.addWidget(lbl_modo)

        check_valores = QCheckBox("Comparar Valores Financeiros")
        check_valores.setChecked(True)
        dialog_layout.addWidget(check_valores)

        check_aih = QCheckBox("Verificar Presença de nº AIH")
        check_aih.setChecked(True)
        dialog_layout.addWidget(check_aih)

        dialog_layout.addSpacing(20)
        btn_iniciar = QPushButton("Iniciar Processamento")

        def confirmar():
            comp = cb_comp.currentText()
            val_checked = check_valores.isChecked()
            aih_checked = check_aih.isChecked()

            if not val_checked and not aih_checked:
                QMessageBox.warning(dialog, "Atenção", "Selecione ao menos um critério.")
                return

            dialog.accept()

            dict_hospitais = self.obter_prestadores_dict()

            resultado = processamento.processar_relatorios(
                comp,
                os.getcwd(),
                dict_hospitais,
                comparar_valores=val_checked,
                verificar_aih=aih_checked
            )

            if isinstance(resultado, tuple):
                QMessageBox.information(self, "Sucesso", "Auditoria concluída com rigor.")
            else:
                QMessageBox.critical(self, "Erro", resultado)

        btn_iniciar.clicked.connect(confirmar)
        dialog_layout.addWidget(btn_iniciar)
        dialog.exec()

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


if __name__ == "__main__":
    app = QApplication(sys.argv)
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