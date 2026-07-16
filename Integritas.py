import ctypes
import re
import sys
import os
import processamento
import validador
import importador_legado  # OBRIGATÓRIO ESTAR NO TOPO
import importador_sihd    # OBRIGATÓRIO ESTAR NO TOPO
from banco_dados import BancoAIH
from login_ui import TelaLogin

# Adiciona o diretório do script ao sys.path para que módulos locais sejam encontrados
script_dir = os.path.dirname(__file__)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

import pandas as pd
# QtCore lida com a lógica e regras de expressão regular
from PyQt6.QtCore import Qt, QRegularExpression, QThread, pyqtSignal, QObject
# QtGui lida apenas com elementos visuais de baixo nível como cores e ícones
from PyQt6.QtGui import QAction, QFont, QColor, QPixmap, QIcon, QRegularExpressionValidator
# O QGraphicsDropShadowEffect deve ser importado de QtWidgets, não de QtGui
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QGridLayout, QLabel, QLineEdit, QComboBox, QPushButton,
                             QFileDialog, QMessageBox, QInputDialog, QDialog, QCheckBox,
                             QScrollArea, QFrame, QTableWidget, QTableWidgetItem,
                             QHeaderView, QAbstractItemView, QMenu, QListWidget,
                             QListWidgetItem, QTabWidget, QGraphicsDropShadowEffect, QColorDialog)

import processamento
import validador
from banco_dados import BancoAIH
from login_ui import TelaLogin


def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funcionando em desenvolvimento e no executável compilado """
    try:
        # Diretório temporário criado pelo empacotador em tempo de execução
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def formatar_para_real(valor):
    """Converte o valor do banco para o padrão de auditoria (R$ 1.500,00) ou '-' se ausente."""
    if not valor or str(valor).strip() in ["", "-", "None"]:
        return "-"
    try:
        v_str = str(valor).replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        v_float = float(v_str)
        return f"R$ {v_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return str(valor)


def limpar_valor_real(valor_formatado):
    """Remove a máscara visual para persistência. Mantém '-' se a entrada for vazia."""
    val = str(valor_formatado).strip()
    if not val or val in ["-", "None"]:
        return "-"
    return val.replace("R$", "").replace(" ", "").replace(".", "")


class WorkerProcessamento(QObject):
    """Trabalhador assíncrono para isolar o processamento pesado da interface gráfica."""
    finalizado = pyqtSignal(object, object)  # Retorna: df_div, df_nc
    erro = pyqtSignal(str)                   # Retorna: mensagem de erro

    def __init__(self, comp, val_checked, aih_checked):
        super().__init__()
        self.comp = comp
        self.val_checked = val_checked
        self.aih_checked = aih_checked

    def run(self):
        try:
            # Esta operação pesada ocorre na CPU sem travar a interface
            df_div, df_nc = processamento.processar_relatorios_dados(
                self.comp, comparar_valores=self.val_checked, verificar_aih=self.aih_checked
            )
            # Envia os resultados de volta
            self.finalizado.emit(df_div, df_nc)
        except Exception as e:
            # Envia o erro de volta
            self.erro.emit(str(e))


class SelecaoHospitalDialog(QDialog):
    """Diálogo para seleção de múltiplos hospitais com checkboxes."""
    def __init__(self, hospitais_disponiveis, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleção de Hospitais para o Relatório")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Marque os hospitais para gerar os relatórios individuais:"))
        
        self.chk_todos = QCheckBox("Marcar/Desmarcar Todos")
        self.chk_todos.stateChanged.connect(self.marcar_todos)
        layout.addWidget(self.chk_todos)
        
        self.lista_hospitais = QListWidget()
        for cnes, nome in hospitais_disponiveis.items():
            item = QListWidgetItem(f"{nome} ({cnes})")
            item.setData(Qt.ItemDataRole.UserRole, cnes)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lista_hospitais.addItem(item)
        layout.addWidget(self.lista_hospitais)
        
        botoes_layout = QHBoxLayout()
        btn_ok = QPushButton("Gerar PDFs")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        botoes_layout.addStretch()
        botoes_layout.addWidget(btn_cancel)
        botoes_layout.addWidget(btn_ok)
        layout.addLayout(botoes_layout)
        
        self.chk_todos.setCheckState(Qt.CheckState.Checked)

    def marcar_todos(self, state):
        check_state = Qt.CheckState(state)
        for i in range(self.lista_hospitais.count()):
            self.lista_hospitais.item(i).setCheckState(check_state)

    def obter_selecionados(self):
        selecionados = {}
        for i in range(self.lista_hospitais.count()):
            item = self.lista_hospitais.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cnes = item.data(Qt.ItemDataRole.UserRole)
                # Extrai o nome do texto do item, removendo o " (CNES)"
                nome = item.text().split('(')[0].strip()
                selecionados[cnes] = nome
        return selecionados


class App(QMainWindow):
    def __init__(self, usuario_ativo=None):
        super().__init__()

        # Armazena o dicionário com os dados do utilizador logado
        self.usuario_ativo = usuario_ativo

        self.setWindowTitle("Integritas AIH - Conferência de Faturamento AIH")

        # Define o ícone da janela
        caminho_icone = resource_path("icon_btm.ico")
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
                "Santa Casa de Montes Claros": "2149990",
                "Otorrino Center": "6209521"
            }
            for nome, cnes in hospitais_iniciais.items():
                self.banco.inserir_prestador(cnes, nome)

    def obter_prestadores_dict(self):
        """Converte a tabela do banco no formato {Nome: CNES} para o sistema."""
        dados = self.banco.listar_prestadores_completos()
        return {nome: cnes for _, cnes, nome, _ in dados}

    def obter_mapeamento_cnes_nome(self):
        """Cria um dicionário de CNES para Nome para consulta rápida."""
        dados = self.banco.listar_prestadores_completos()
        return {cnes: nome for _, cnes, nome, _ in dados}

    def destacar_menu(self, botao_ativo):
        """Atualiza a propriedade CSS dos botões para sinalizar a aba ativa."""
        # Adicionados os botões de Ajuda e Sobre
        botoes_navegacao = [self.btn_painel, self.btn_digitar, self.btn_prestadores, self.btn_ajuda, self.btn_sobre]

        for btn in botoes_navegacao:
            btn.setProperty("active", btn == botao_ativo)
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

        # --- LOGO DO SUS NA SIDEBAR ---
        lbl_logo_sus = QLabel()
        caminho_logo = resource_path("icon_sus.png")
        pixmap_sus = QPixmap(caminho_logo)

        if not pixmap_sus.isNull():
            # Altura ajustada para 40px para não ocupar muito espaço vertical
            lbl_logo_sus.setPixmap(pixmap_sus.scaledToHeight(40, Qt.TransformationMode.SmoothTransformation))

            # Mantém apenas o espaçamento superior, removendo o recuo à esquerda
            lbl_logo_sus.setStyleSheet("padding-top: 15px;")

            # Adiciona ao layout forçando a centralização horizontal
            sidebar_layout.addWidget(lbl_logo_sus, alignment=Qt.AlignmentFlag.AlignHCenter)
            sidebar_layout.addSpacing(5)  # Espaço sutil entre o logo e o título

        lbl_logo_sidebar = QLabel('<b>Integritas</b> <span style="color: #4fc3f7;">AIH</span>')
        lbl_logo_sidebar.setStyleSheet("""
            color: #ffffff; 
            font-size: 24px; 
            padding-left: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #34495e;
        """)
        sidebar_layout.addWidget(lbl_logo_sidebar)
        sidebar_layout.addWidget(lbl_logo_sidebar, alignment=Qt.AlignmentFlag.AlignHCenter)
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

        btn_imp_legado = QPushButton("Importar TXT Local")
        btn_imp_legado.clicked.connect(self.executar_importacao_legado)

        btn_imp_sihd = QPushButton("Importar Base SIHD")
        btn_imp_sihd.clicked.connect(self.selecionar_base_sihd)

        # --- NOVO BOTÃO: EXPORTAR BASE LOCAL ---
        self.btn_exp_local = QPushButton("Exportar Base Local")
        self.btn_exp_local.clicked.connect(self.abrir_exportacao_local)

        self.btn_exp_sihd = QPushButton("Exportar Base SIHD")
        self.btn_exp_sihd.clicked.connect(self.abrir_exportacao_sihd)

        # --- NOVOS BOTÕES: AJUDA E SOBRE ---
        linha_suporte = QFrame()
        linha_suporte.setFrameShape(QFrame.Shape.HLine)
        linha_suporte.setStyleSheet("background-color: #34495e; margin: 0px 15px;")

        # --- NOVO BOTÃO: TRILHA DE AUDITORIA ---
        self.btn_logs = QPushButton("Logs de Utilização")
        self.btn_logs.clicked.connect(self.abrir_tela_logs)

        self.btn_ajuda = QPushButton("Manual do Utilizador")
        self.btn_ajuda.clicked.connect(self.abrir_tela_ajuda)

        self.btn_sobre = QPushButton("Sobre o Sistema")
        self.btn_sobre.clicked.connect(self.abrir_tela_sobre)




        linha2 = QFrame()
        linha2.setFrameShape(QFrame.Shape.HLine)
        linha2.setStyleSheet("background-color: #34495e; margin: 0px 15px;")

        # Instanciação estritamente técnica, sem iconografia
        btn_auditoria = QPushButton("Executar Conferência")
        btn_auditoria.clicked.connect(self.processar_dados)

        # Estilo dedicado: Transforma o item numa caixa de ação primária (Call to Action)
        btn_auditoria.setStyleSheet("""
                    QPushButton {
                        background-color: #0099a6; /* Verde sólido de destaque corporativo */
                        color: #ffffff;
                        text-align: center; /* Centraliza o texto, quebrando o padrão alinhado à esquerda */
                        font-weight: bold;
                        border-radius: 5px;
                        margin: 0px 15px 15px 15px; /* Descola o botão das bordas da sidebar */
                        border: none;
                    }
                    QPushButton:hover {
                        background-color: #0bb1bf;
                        border-left: none; /* Previne a sobreposição do estilo hover padrão da sidebar */
                    }
                """)

        sidebar_layout.addWidget(btn_auditoria)
        # Destaca o botão principal da aplicação
        btn_auditoria.setStyleSheet(btn_auditoria.styleSheet() + "color: #f1c40f;")

        # ADICIONAR AO LAYOUT DA SIDEBAR (Atualize a ordem no final do setup_ui)
        sidebar_layout.addWidget(self.btn_painel)
        sidebar_layout.addWidget(self.btn_digitar)
        sidebar_layout.addWidget(self.btn_prestadores)

        sidebar_layout.addSpacing(15)
        sidebar_layout.addWidget(linha1)
        sidebar_layout.addSpacing(15)

        sidebar_layout.addWidget(btn_imp_legado)
        sidebar_layout.addWidget(btn_imp_sihd)
        sidebar_layout.addWidget(self.btn_exp_local)
        sidebar_layout.addWidget(self.btn_exp_sihd)

        sidebar_layout.addSpacing(15)
        sidebar_layout.addWidget(linha_suporte)
        sidebar_layout.addSpacing(15)

        sidebar_layout.addWidget(self.btn_logs)
        sidebar_layout.addWidget(self.btn_ajuda)
        sidebar_layout.addWidget(self.btn_sobre)

        sidebar_layout.addStretch()  # Empurra a auditoria para a base
        sidebar_layout.addWidget(linha2)
        sidebar_layout.addSpacing(15)
        sidebar_layout.addWidget(btn_auditoria)

        # 1. Fecha e adiciona a sidebar ao layout base
        self.base_layout.addWidget(self.sidebar)

        # 2. RESTAURAÇÃO: Construção da área de conteúdo dinâmico (onde os módulos abrem)
        self.content_frame = QFrame()
        self.content_frame.setObjectName("FrameConteudo")
        self.content_frame.setStyleSheet("#FrameConteudo { background-color: #f5f5f5; }")

        # 3. Criação do main_layout que estava a faltar
        self.main_layout = QVBoxLayout(self.content_frame)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.main_layout.setContentsMargins(20, 20, 20, 20)

        # 4. Adiciona o frame de conteúdo ao layout base
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
        # --- NOVO: Botão de Seleção de Cor ---
        self.cor_selecionada = "#2c3e50"
        self.btn_cor = QPushButton("Cor")
        self.btn_cor.setFixedWidth(60)
        self.btn_cor.setStyleSheet(
            f"background-color: {self.cor_selecionada}; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_cor.clicked.connect(self.escolher_cor_prestador)
        btn_add = QPushButton("Adicionar Prestador")
        btn_add.clicked.connect(self.salvar_novo_prestador)

        layout_cad.addWidget(self.ent_cnes_novo)
        layout_cad.addWidget(self.ent_nome_novo)
        layout_cad.addWidget(self.btn_cor)  # <--- INSERIR ESTA LINHA
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

    def escolher_cor_prestador(self):
        cor = QColorDialog.getColor()
        if cor.isValid():
            self.cor_selecionada = cor.name()
            self.btn_cor.setStyleSheet(
                f"background-color: {self.cor_selecionada}; color: white; font-weight: bold; border-radius: 4px;")

    def salvar_novo_prestador(self):
        cnes = self.ent_cnes_novo.text().strip()
        nome = self.ent_nome_novo.text().strip()
        if cnes and nome:
            res = self.banco.inserir_prestador(cnes, nome, getattr(self, 'cor_selecionada', '#2c3e50'))
            if res is True:
                if self.usuario_ativo:
                    self.banco.registrar_log(self.usuario_ativo['cpf'], "Cadastro de Prestador",
                                             f"Adicionou CNES {cnes} - {nome}")
                self.atualizar_grade_prestadores()
                self.ent_cnes_novo.clear()
                self.ent_nome_novo.clear()
                # Reseta a cor visualmente
                self.cor_selecionada = "#2c3e50"
                self.btn_cor.setStyleSheet(
                    f"background-color: {self.cor_selecionada}; color: white; font-weight: bold; border-radius: 4px;")
            else:
                QMessageBox.warning(self, "Erro", str(res))

    def atualizar_grade_prestadores(self):
        dados = self.banco.listar_prestadores_completos()
        self.tabela_prestadores.setRowCount(len(dados))

        for r_idx, linha in enumerate(dados):
            id_reg, cnes, nome, cor = linha

            item_id = QTableWidgetItem(str(id_reg))
            item_id.setData(Qt.ItemDataRole.UserRole, id_reg)
            self.tabela_prestadores.setItem(r_idx, 0, item_id)

            self.tabela_prestadores.setItem(r_idx, 1, QTableWidgetItem(str(cnes)))

            # Aplica a cor cadastrada para facilitar a identificação visual na própria tela de gestão
            item_nome = QTableWidgetItem(str(nome))
            item_nome.setForeground(QColor(cor))
            fonte = QFont()
            fonte.setBold(True)
            item_nome.setFont(fonte)
            self.tabela_prestadores.setItem(r_idx, 2, item_nome)

    def menu_contexto_prestador(self, pos):
        item = self.tabela_prestadores.itemAt(pos)
        if item is None: return

        linha = item.row()
        self.tabela_prestadores.selectRow(linha)

        menu = QMenu(self)

        # Nova opção de edição
        acao_editar = QAction("✏️ Editar Prestador", self)
        acao_editar.triggered.connect(lambda: self.abrir_edicao_prestador(linha))

        acao_remover = QAction("🗑️ Excluir Prestador (X)", self)
        acao_remover.triggered.connect(self.excluir_prestador)

        menu.addAction(acao_editar)
        menu.addAction(acao_remover)
        menu.exec(self.tabela_prestadores.viewport().mapToGlobal(pos))

    def abrir_edicao_prestador(self, linha):
        """Abre uma janela de diálogo para edição de dados e cor do prestador selecionado."""
        id_banco = self.tabela_prestadores.item(linha, 0).data(Qt.ItemDataRole.UserRole)
        cnes_atual = self.tabela_prestadores.item(linha, 1).text()
        nome_atual = self.tabela_prestadores.item(linha, 2).text()

        # Recupera a cor visual atual (se não houver cor aplicada, assume o padrão)
        cor_atual = "#2c3e50"
        brush = self.tabela_prestadores.item(linha, 2).foreground()
        if brush.color().isValid():
            cor_atual = brush.color().name()

        dialog = QDialog(self)
        dialog.setWindowTitle("Editar Prestador")
        dialog.setFixedSize(350, 280)
        layout = QVBoxLayout(dialog)

        # Campos de texto
        layout.addWidget(QLabel("CNES:"))
        ent_cnes = QLineEdit(cnes_atual)
        layout.addWidget(ent_cnes)

        layout.addWidget(QLabel("Nome Fantasia:"))
        ent_nome = QLineEdit(nome_atual)
        layout.addWidget(ent_nome)

        # Botão de seleção de cor local
        layout.addWidget(QLabel("Cor de Identificação:"))
        btn_cor = QPushButton("Alterar Cor")
        estado_cor = {"atual": cor_atual}  # Estrutura mutável para persistência no escopo aninhado
        btn_cor.setStyleSheet(
            f"background-color: {cor_atual}; color: white; font-weight: bold; border-radius: 4px; padding: 8px;")

        def acao_escolher_cor():
            cor_dialog = QColorDialog.getColor(QColor(estado_cor["atual"]), dialog)
            if cor_dialog.isValid():
                estado_cor["atual"] = cor_dialog.name()
                btn_cor.setStyleSheet(
                    f"background-color: {estado_cor['atual']}; color: white; font-weight: bold; border-radius: 4px; padding: 8px;")

        btn_cor.clicked.connect(acao_escolher_cor)
        layout.addWidget(btn_cor)

        layout.addSpacing(15)

        # Botão de gravação
        btn_salvar = QPushButton("Gravar Alterações")
        btn_salvar.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")

        def acao_salvar():
            novo_cnes = ent_cnes.text().strip()
            novo_nome = ent_nome.text().strip()

            if not novo_cnes or not novo_nome:
                QMessageBox.warning(dialog, "Validação", "Os campos CNES e Nome são de preenchimento obrigatório.")
                return

            resultado = self.banco.atualizar_prestador(id_banco, novo_cnes, novo_nome, estado_cor["atual"])

            if resultado is True:
                # Registo obrigatório da alteração na trilha de auditoria
                if self.usuario_ativo:
                    detalhes = f"Edição do ID {id_banco}: {cnes_atual} -> {novo_cnes} | {nome_atual} -> {novo_nome}"
                    self.banco.registrar_log(self.usuario_ativo['cpf'], "Edição de Prestador", detalhes)

                self.atualizar_grade_prestadores()
                dialog.accept()
            else:
                QMessageBox.critical(dialog, "Erro de Base de Dados", str(resultado))

        btn_salvar.clicked.connect(acao_salvar)
        layout.addWidget(btn_salvar)

        dialog.exec()

    def excluir_prestador(self):
        linha = self.tabela_prestadores.currentRow()
        if linha < 0: return

        resposta = QMessageBox.question(self, "Confirmar Exclusão",
                                        "Deseja realmente remover este prestador?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if resposta == QMessageBox.StandardButton.Yes:
            id_banco = self.tabela_prestadores.item(linha, 0).data(Qt.ItemDataRole.UserRole)

            # --- CORREÇÃO: Captura dos dados visuais antes da exclusão ---
            cnes_excluido = self.tabela_prestadores.item(linha, 1).text()
            nome_excluido = self.tabela_prestadores.item(linha, 2).text()
            # -------------------------------------------------------------

            self.banco.excluir_prestador(id_banco)

            # --- INÍCIO DO LOG ---
            if self.usuario_ativo:
                self.banco.registrar_log(
                    self.usuario_ativo['cpf'],
                    "Exclusão de Prestador",
                    f"Removeu CNES {cnes_excluido} - {nome_excluido}"
                )
            # --- FIM DO LOG ---
            self.atualizar_grade_prestadores()

    # --- MÓDULOS DE AÇÃO E IMPORTAÇÃO ---

    def executar_importacao_legado(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo TXT Legado", "",
                                                 "Arquivos de Texto (*.txt)")
        if caminho:
            resultado = importador_legado.importar_txt_para_sqlite(caminho)
            if isinstance(resultado, tuple):
                s, e, d, err_cnes = resultado
                msg_detalhes = f"Registos importados: {s}\nAIHs com dígito inválido: {e}\nRegistos já existentes (duplicados): {d}\nLinhas com CNES mal formatado: {err_cnes}"
                QMessageBox.information(self, "Importação Concluída", msg_detalhes)
                
                if self.usuario_ativo:
                    nome_arquivo = os.path.basename(caminho)
                    self.banco.registrar_log(
                        self.usuario_ativo['cpf'],
                        "Importação TXT Local",
                        f"Arquivo: {nome_arquivo} | Sucessos: {s}, Inválidos: {e}, Duplicados: {d}, CNES Inválido: {err_cnes}"
                    )
                self.mostrar_status()
            else:
                QMessageBox.critical(self, "Erro na Importação", resultado)

    def selecionar_base_sihd(self):
        comp, ok = QInputDialog.getText(self, "Importar SIHD", "Digite a competência (AAAAMM):")

        if ok and comp and len(comp) == 6 and comp.isdigit():
            caminho, _ = QFileDialog.getOpenFileName(self, "Selecione o arquivo do SIHD", "",
                                                     "Arquivos de Texto (*.txt)")
            if caminho:
                import importador_sihd
                qtd = importador_sihd.importar_sihd_para_db(caminho, comp)
                QMessageBox.information(self, "Sucesso", f"Importados {qtd} registos do SIHD para {comp}")
                # --- INÍCIO DO LOG ---
                if self.usuario_ativo:
                    nome_arquivo = os.path.basename(caminho)
                    self.banco.registrar_log(
                        self.usuario_ativo['cpf'],
                        "Importação SIHD",
                        f"Competência: {comp} | Arquivo: {nome_arquivo} | Qtd: {qtd}"
                    )
                # --- FIM DO LOG ---
                self.mostrar_status()
        elif ok:
            QMessageBox.warning(self, "Erro", "Competência inválida!")

    # --- INTERFACES VISUAIS ---

    def atualizar_estilo_combobox(self, texto):
        if texto in ("Todas as Unidades", ""):
            self.cb_hospital.setStyleSheet("""
                QComboBox {
                    font-size: 16px;
                    font-weight: normal;
                    color: #7f8c8d;
                    padding: 6px;
                }
            """)
        else:
            self.cb_hospital.setStyleSheet("""
                QComboBox {
                    font-size: 16px;
                    font-weight: bold;
                    color: #2c3e50;
                    padding: 6px;
                }
            """)


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

        self.cb_hospital = QComboBox()
        self.hospitais_atuais = self.obter_prestadores_dict()  # Mantido para compatibilidade

        # --- RENDERIZAÇÃO DA COR NO COMBOBOX ---
        dados_hospitais = self.banco.listar_prestadores_completos()
        fonte_combo = QFont()
        fonte_combo.setBold(True)
        fonte_combo.setPointSize(12)

        # Adicionar ANTES do for loop dos hospitais
        self.cb_hospital.addItem("Todas as Unidades")
        # Fonte sem negrito para o item "Todas as Unidades"
        fonte_normal = QFont()
        fonte_normal.setBold(False)
        fonte_normal.setPointSize(12)
        self.cb_hospital.setItemData(0, QColor("#7f8c8d"), Qt.ItemDataRole.ForegroundRole)
        self.cb_hospital.setItemData(0, fonte_normal, Qt.ItemDataRole.FontRole)
        self.cb_hospital.insertSeparator(1)

        for _, cnes, nome, cor in dados_hospitais:
            self.cb_hospital.addItem(nome)
            idx = self.cb_hospital.count() - 1
            self.cb_hospital.setItemData(idx, QColor(cor), Qt.ItemDataRole.ForegroundRole)
            self.cb_hospital.setItemData(idx, fonte_combo, Qt.ItemDataRole.FontRole)

        self.cb_hospital.currentTextChanged.connect(self.atualizar_estilo_combobox)

        self.cb_hospital.currentTextChanged.connect(self.aplicar_filtro_hospital_digitacao)

        # --- ESTILIZAÇÃO EM DESTAQUE PARA UNIDADE ---
        self.cb_hospital.setStyleSheet("""
            QComboBox {
                font-size: 16px; 
                color: #2c3e50; 
                padding: 6px;
            }
        """)

        self.ent_aih = QLineEdit()
        self.ent_aih.setPlaceholderText("Número da AIH")
        # Trava física: aceita estritamente números, limitando a 13 algarismos
        validador_aih = QRegularExpressionValidator(QRegularExpression(r"^[0-9]{0,13}$"))
        self.ent_aih.setValidator(validador_aih)
        self.ent_aih.returnPressed.connect(self.salvar_aih)

        self.ent_valor = QLineEdit()
        self.ent_valor.setPlaceholderText("Valor (opcional)")
        # Trava física: aceita apenas números e, no máximo, uma vírgula seguida de até 2 casas decimais
        validador_valor = QRegularExpressionValidator(QRegularExpression(r"^[0-9]*(,[0-9]{0,2})?$"))
        self.ent_valor.setValidator(validador_valor)
        self.ent_valor.returnPressed.connect(self.salvar_aih)

        # --- REORGANIZAÇÃO DO GRID LAYOUT ---
        lbl_unidade = QLabel("Unidade:")
        lbl_unidade.setStyleSheet("font-weight: bold; font-size: 14px; color: #007acc;")

        # Linha 0: Unidade (Expandida horizontalmente com colspan 3)
        form_layout.addWidget(lbl_unidade, 0, 0)
        form_layout.addWidget(self.cb_hospital, 0, 1, 1, 3)

        # Linha 1: Competência
        form_layout.addWidget(QLabel("Competência:"), 1, 0)
        form_layout.addWidget(self.ent_competencia, 1, 1)

        # Linha 2: AIH
        form_layout.addWidget(QLabel("AIH:"), 2, 0)
        form_layout.addWidget(self.ent_aih, 2, 1)

        # Linha 3: Valor e Botão Salvar
        form_layout.addWidget(QLabel("Valor:"), 3, 0)
        form_layout.addWidget(self.ent_valor, 3, 1)

        btn_salvar = QPushButton("Salvar Registro")
        btn_salvar.setFixedWidth(120)
        btn_salvar.clicked.connect(self.salvar_aih)
        form_layout.addWidget(btn_salvar, 3, 3, alignment=Qt.AlignmentFlag.AlignRight)

        self.main_layout.addWidget(form_widget)

        self.main_layout.addWidget(QLabel("Registros Digitados nesta Competência:"))
        self.tabela_digitacao = QTableWidget()
        self.tabela_digitacao.setColumnCount(5)
        self.tabela_digitacao.setHorizontalHeaderLabels(["ID", "CNES", "Nome do Hospital", "AIH", "Valor"])
        self.tabela_digitacao.hideColumn(0)
        self.tabela_digitacao.verticalHeader().setMinimumWidth(55)  # ← aqui
        self.tabela_digitacao.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # --- BLINDAGEM DA TABELA: Desativa edição direta ---
        self.tabela_digitacao.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Selecionar linha inteira (opcional, mas recomendado para melhor UX)
        self.tabela_digitacao.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        # NOVO: Permite que o utilizador selecione várias linhas segurando Shift ou Ctrl
        self.tabela_digitacao.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self.tabela_digitacao.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela_digitacao.customContextMenuRequested.connect(self.abrir_menu_contexto_digitacao)

        self.main_layout.addWidget(self.tabela_digitacao)
        self.carregando_tabela = False
        self.aplicar_filtro_hospital_digitacao()

    def verificar_carga_automatica(self, texto):
        if len(texto) == 6:
            self.atualizar_grade_digitacao(texto)

    def atualizar_grade_digitacao(self, comp):
        self.carregando_tabela = True
        dados = self.banco.buscar_registros_locais(comp)
        self.tabela_digitacao.setRowCount(len(dados))


        mapa_completo = self.obter_mapeamento_cnes_completo()

        for row_idx, linha in enumerate(dados):
            id_reg, cnes, aih, valor = linha

            # --- RENDERIZAÇÃO DA COR NA TABELA ---
            info_hospital = mapa_completo.get(cnes, {'nome': "Não encontrado", 'cor': "#2c3e50"})
            item_hospital = self.formatar_celula_hospital(info_hospital['nome'], info_hospital['cor'])

            item_id = QTableWidgetItem(str(id_reg))
            item_id.setData(Qt.ItemDataRole.UserRole, id_reg)
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tabela_digitacao.setItem(row_idx, 0, item_id)

            self.tabela_digitacao.setItem(row_idx, 1, QTableWidgetItem(cnes))
            self.tabela_digitacao.setItem(row_idx, 2, item_hospital)  # Item formatado
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
        # NOVA GUARDA: bloqueia salvamento sem hospital específico selecionado
        if self.cb_hospital.currentText() in ("Todas as Unidades", ""):
            QMessageBox.warning(self, "Unidade não selecionada",
                                "Selecione uma unidade específica antes de lançar uma AIH.")
            self.cb_hospital.showPopup()
            return
        comp = self.ent_competencia.text().strip()
        hospital_nome = self.cb_hospital.currentText()
        cnes = self.hospitais_atuais[hospital_nome]
        aih = self.ent_aih.text().strip()
        valor_raw = self.ent_valor.text().strip()

        if len(comp) != 6 or not comp.isdigit():
            QMessageBox.warning(self, "Erro", "Competência inválida.")
            return

        if not validador.validar_aih(aih):
            QMessageBox.critical(self, "AIH Inválida", "Falha no dígito verificador.")
            return

        # --- NOVA TRAVA: TIPAGEM FINANCEIRA RIGOROSA ---
        valor_limpo = "-"
        if valor_raw and valor_raw != "-":
            # Remove o "R$", espaços e pontos de milhar, mantendo apenas a vírgula decimal
            v_temp = valor_raw.replace("R$", "").replace(" ", "").replace(".", "")

            # Valida se o que sobrou é estritamente um número (podendo ter uma vírgula)
            if not re.match(r"^\d+(,\d+)?$", v_temp):
                QMessageBox.warning(self, "Bloqueio de Tipagem",
                                    "O campo de valor só aceita números e vírgula.\nExemplo correto: 1530,50")
                self.ent_valor.setFocus()
                return

            # Padroniza a gravação no banco para ter sempre duas casas decimais
            try:
                valor_float = float(v_temp.replace(",", "."))
                valor_limpo = f"{valor_float:.2f}".replace(".", ",")
            except ValueError:
                QMessageBox.warning(self, "Erro Matemático", "Falha ao processar o valor monetário.")
                return

        if self.banco.registro_existe(comp, cnes, aih):
            QMessageBox.warning(self, "AIH Duplicada",
                                f"A AIH {aih} já foi digitada para a unidade selecionada nesta competência.")
            self.ent_aih.clear()
            self.ent_aih.setFocus()
            return
        # ---------------------------------------------------

        # Dentro do método salvar_aih(self), após inserir o registro no banco:
        sucesso = self.banco.inserir_registro(comp, cnes, aih, valor_limpo)

        if sucesso:
            # NOVO: Registra a ação vinculada ao CPF do utilizador logado
            if self.usuario_ativo:
                detalhes_log = f"Lançou AIH {aih} para CNES {cnes} na comp. {comp}"
                self.banco.registrar_log(self.usuario_ativo['cpf'], "Digitação Manual", detalhes_log)

            self.atualizar_grade_digitacao(comp)
            self.ent_aih.clear()
            # [RESTANTE DO SEU CÓDIGO INTACTO...]
            self.ent_valor.clear()
            self.ent_aih.setFocus()
        else:
            QMessageBox.critical(self, "Erro de Persistência", "Falha ao gravar o registro no banco de dados.")

    # --- STATUS E DETALHES ---

    def mostrar_status(self):
        self.limpar_tela()
        self.destacar_menu(self.btn_painel)

        # Cabeçalho limpo
        header_container = QWidget()
        header_layout = QHBoxLayout(header_container)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_logo = QLabel()
        caminho_logo = os.path.join(os.path.dirname(__file__), "")
        pixmap = QPixmap(caminho_logo)
        if not pixmap.isNull():
            lbl_logo.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
        else:
            lbl_logo.setText("")

        lbl_titulo = QLabel("Sincronização de Registros no Banco de Dados SQLite")
        lbl_titulo.setStyleSheet("""
            font-size: 28px; 
            font-weight: bold; 
            color: #2c3e50;
            background: transparent;
        """)

        header_layout.addWidget(lbl_logo)
        header_layout.addSpacing(20)
        header_layout.addWidget(lbl_titulo)

        self.main_layout.addSpacing(40)
        self.main_layout.addWidget(header_container)
        self.main_layout.addSpacing(20)

        # Container centralizado para a tabela
        table_container_central = QWidget()
        table_central_layout = QHBoxLayout(table_container_central)
        table_central_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Frame com sombra que envolverá a tabela
        table_frame = QFrame()
        table_frame.setFixedWidth(550)
        table_frame.setStyleSheet("background-color: white; border-radius: 8px;")

        sombra_tb = QGraphicsDropShadowEffect()
        sombra_tb.setBlurRadius(15)
        sombra_tb.setColor(QColor(0, 0, 0, 30))
        sombra_tb.setOffset(0, 4)
        table_frame.setGraphicsEffect(sombra_tb)

        table_frame_layout = QVBoxLayout(table_frame)
        table_frame_layout.setContentsMargins(5, 5, 5, 5)

        locais = self.banco.listar_competencias_locais()
        sihds = self.banco.listar_competencias_sihd()
        todas_competencias = sorted(list(set(locais) | set(sihds)), reverse=True)

        self.tabela_status = QTableWidget()
        self.tabela_status.setColumnCount(2)
        self.tabela_status.setRowCount(len(todas_competencias))
        self.tabela_status.setHorizontalHeaderLabels(["Digitação Local", "Base SIHD"])

        self.tabela_status.setMinimumHeight(400)
        self.tabela_status.verticalHeader().setVisible(False)
        self.tabela_status.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabela_status.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_status.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_status.cellDoubleClicked.connect(self.abrir_detalhes_competencia)
        self.tabela_status.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabela_status.clearSelection()

        # Ativação do Mouse Tracking para o Hover
        self.tabela_status.viewport().setMouseTracking(True)
        self.tabela_status.setAttribute(Qt.WidgetAttribute.WA_Hover)

        self.tabela_status.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabela_status.customContextMenuRequested.connect(self.menu_contexto_status)

        # Aumenta ligeiramente a altura das linhas para um aspeto mais respirável
        self.tabela_status.verticalHeader().setDefaultSectionSize(40)

        header = self.tabela_status.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for row, comp in enumerate(todas_competencias):
            data_fmt = f"{comp[4:]}/{comp[:4]}"

            existe_local = comp in locais
            item_local = QTableWidgetItem(data_fmt if existe_local else "Pendente")
            item_local.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_local.setData(Qt.ItemDataRole.UserRole, comp)

            if existe_local:
                item_local.setForeground(QColor("#27ae60"))
                item_local.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            else:
                item_local.setForeground(QColor("#bdc3c7"))

            existe_sihd = comp in sihds
            item_sihd = QTableWidgetItem(data_fmt if existe_sihd else "Pendente")
            item_sihd.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_sihd.setData(Qt.ItemDataRole.UserRole, comp)

            if existe_sihd:
                item_sihd.setForeground(QColor("#27ae60"))
                item_sihd.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            else:
                item_sihd.setForeground(QColor("#bdc3c7"))

            self.tabela_status.setItem(row, 0, item_local)
            self.tabela_status.setItem(row, 1, item_sihd)

        # CSS movido para FORA do laço de repetição
        self.tabela_status.setStyleSheet("""
            QTableWidget { 
                background-color: transparent; 
                gridline-color: #f1f2f6; 
                border: none; 
                outline: none;
            }
            QTableWidget::item {
                border-bottom: 1px solid #f1f2f6;
            }
            QHeaderView::section { 
                background-color: #ffffff; 
                padding: 12px; 
                border: none;
                border-bottom: 2px solid #007acc; 
                font-weight: bold; 
                color: #2c3e50;
            }
            QTableWidget::item:hover {
                background-color: #f4f9ff;
            }
            QTableWidget::item:selected {
                background-color: #e3f0ff; 
                color: #2c3e50;
            }
        """)

        table_frame_layout.addWidget(self.tabela_status)
        table_central_layout.addWidget(table_frame)

        self.main_layout.addWidget(table_container_central)
        self.main_layout.addStretch()


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

            # --- VALIDAÇÃO RESTRITIVA DE INTEGRIDADE DAS BASES ---
            data_fmt = f"{comp[4:]}/{comp[:4]}"

            if comp not in locais:
                QMessageBox.warning(dialog, "Base Faltante",
                                    f"A Digitação Local para a competência {data_fmt} está vazia.\nÉ necessário realizar os lançamentos antes de executar a conferência.")
                return

            if comp not in sihds:
                QMessageBox.warning(dialog, "Base Faltante",
                                    f"A base do SIHD para a competência {data_fmt} não foi importada.\nÉ necessário importar o arquivo do governo antes de executar a conferência.")
                return
            # -----------------------------------------------------

            dialog.accept()  # Fecha a janela de escolha de data
            dict_hospitais = self.obter_prestadores_dict()

            # --- ARQUITETURA ASSÍNCRONA ---
            # 1. Tranca a Interface para evitar dupla submissão e encerramentos forçados
            self.setEnabled(False)

            # Muda o rato para o ícone de ampulheta/rodinha de carregamento
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

            self.statusBar().showMessage(
                f"A processar auditoria pesada para a competência {data_fmt}... Por favor aguarde.")

            # 2. Prepara as Threads de Trabalho Isolado
            self.thread = QThread()
            self.worker = WorkerProcessamento(comp, val_checked, aih_checked)
            self.worker.moveToThread(self.thread)

            # 3. Conexão dos Sinais (O que fazer quando terminar ou falhar?)
            self.thread.started.connect(self.worker.run)

            # --- RECEÇÃO DE DADOS DE VOLTA ---
            def ao_finalizar(df_div_result, df_nc_result):
                # Desliga a thread e limpa a memória
                self.thread.quit()
                self.thread.wait()

                # Destranca a interface e restaura o rato normal
                self.setEnabled(True)
                QApplication.restoreOverrideCursor()
                self.statusBar().clearMessage()

                if (df_div_result is None or df_div_result.empty) and (df_nc_result is None or df_nc_result.empty):
                    QMessageBox.information(self, "Concluído",
                                            "Conferência finalizada. Não foram encontradas divergências!")
                    return

                # Renderiza a nova tela na área principal
                self.exibir_resultados_auditoria(comp, df_div_result, df_nc_result, dict_hospitais)

            def ao_falhar(erro_msg):
                self.thread.quit()
                self.thread.wait()
                self.setEnabled(True)
                QApplication.restoreOverrideCursor()
                self.statusBar().clearMessage()
                QMessageBox.critical(self, "Erro Fatal", erro_msg)

            # Liga os sinais aos métodos de receção
            self.worker.finalizado.connect(ao_finalizar)
            self.worker.erro.connect(ao_falhar)

            # Força a limpeza do worker no fecho da thread (Memory Leak Prevention)
            self.worker.finalizado.connect(self.worker.deleteLater)
            self.worker.erro.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)

            # 4. Inicia o Processamento Paralelo
            self.thread.start()

        btn_iniciar.clicked.connect(confirmar)
        layout.addWidget(btn_iniciar)

        dialog.exec()



    def exportar_resultados_excel(self, comp, df_div, df_nc):
        import pandas as pd

        # Novo padrão de nomenclatura: Relatorio_Resultados_AAAA_MM.xlsx
        data_fmt_arquivo = f"{comp[:4]}_{comp[4:]}"
        nome_arquivo_padrao = f"Relatorio_Resultados_{data_fmt_arquivo}.xlsx"

        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório Excel", nome_arquivo_padrao, "Excel (*.xlsx)")

        if caminho:
            try:
                # Recupera o dicionário de mapeamento CNES -> Nome do Hospital
                mapa_cnes = {v: k for k, v in self.dict_hospitais_atual.items()}

                with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
                    if df_div is not None and not df_div.empty:
                        df_exp_div = df_div[
                            ['cnes', 'aih', 'paciente', 'v_num_local', 'v_num_sihd', 'diferenca']].copy()
                        # Aplica o mapeamento para criar a nova coluna de Unidade
                        df_exp_div['Unidade'] = df_exp_div['cnes'].map(mapa_cnes).fillna(df_exp_div['cnes'])

                        # Reordena as colunas para colocar a Unidade no início
                        df_exp_div = df_exp_div[
                            ['Unidade', 'cnes', 'aih', 'paciente', 'v_num_local', 'v_num_sihd', 'diferenca']]
                        df_exp_div.columns = ['Unidade', 'CNES', 'AIH', 'Paciente', 'Valor Digitação', 'Valor Governo',
                                              'Diferença Numérica']

                        df_exp_div.to_excel(writer, sheet_name='Divergentes', index=False)

                    if df_nc is not None and not df_nc.empty:
                        df_exp_nc = df_nc[['cnes', 'aih', 'paciente', 'v_num_sihd']].copy()
                        # Aplica o mapeamento
                        df_exp_nc['Unidade'] = df_exp_nc['cnes'].map(mapa_cnes).fillna(df_exp_nc['cnes'])

                        # Reordena as colunas
                        df_exp_nc = df_exp_nc[['Unidade', 'cnes', 'aih', 'paciente', 'v_num_sihd']]
                        df_exp_nc.columns = ['Unidade', 'CNES', 'AIH', 'Paciente', 'Valor Governo']

                        df_exp_nc.to_excel(writer, sheet_name='Faltantes na Local', index=False)

                QMessageBox.information(self, "Sucesso", "Ficheiro Excel gerado com sucesso!")

                # --- INÍCIO DO LOG ---
                if hasattr(self, 'usuario_ativo') and self.usuario_ativo:
                    self.banco.registrar_log(self.usuario_ativo['cpf'], "Exportação de Dados",
                                             f"Exportou Relatório de Auditoria para Excel (Comp: {comp})")
                # --- FIM DO LOG ---

            except PermissionError:
                QMessageBox.warning(self, "Acesso Negado",
                                    "O ficheiro Excel encontra-se aberto noutro programa.\nFeche o ficheiro e tente exportar novamente.")
            except ImportError:
                QMessageBox.critical(self, "Dependência Faltante",
                                     "Por favor, instale o openpyxl executando o comando no terminal:\npip install openpyxl")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao exportar Excel: {str(e)}")

    def exportar_resultados_pdf(self, comp, df_div, df_nc, hospitais):
        # 1. Identificar hospitais com dados
        cnes_com_dados = []
        if df_div is not None and not df_div.empty:
            cnes_com_dados.extend(df_div['cnes'].unique())
        if df_nc is not None and not df_nc.empty:
            cnes_com_dados.extend(df_nc['cnes'].unique())
        
        if not cnes_com_dados:
            QMessageBox.warning(self, "Exportação PDF", "Não há dados para gerar relatórios.")
            return

        mapa_cnes_nome_completo = self.obter_mapeamento_cnes_nome()
        hospitais_disponiveis = {cnes: mapa_cnes_nome_completo.get(cnes, cnes) for cnes in sorted(list(set(cnes_com_dados)))}

        # 2. Abrir diálogo de seleção
        dialog = SelecaoHospitalDialog(hospitais_disponiveis, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            hospitais_selecionados = dialog.obter_selecionados()
            if not hospitais_selecionados:
                QMessageBox.warning(self, "Nenhuma Seleção", "Nenhum hospital foi selecionado.")
                return

            dir_saida = QFileDialog.getExistingDirectory(self, "Selecione a Pasta para Salvar os Relatórios PDF")
            if not dir_saida:
                return

            pdfs_gerados = []
            # 4. Loop para gerar um PDF por hospital
            for cnes, nome_hospital in hospitais_selecionados.items():
                df_div_hosp = df_div[df_div['cnes'] == cnes] if df_div is not None else None
                df_nc_hosp = df_nc[df_nc['cnes'] == cnes] if df_nc is not None else None

                try:
                    if df_div_hosp is not None and not df_div_hosp.empty:
                        p1 = processamento.gerar_pdf(
                            df_div_hosp, 'divergentes', comp, dir_saida, hospitais, 
                            usuario_active=self.usuario_ativo, 
                            hospital_info=(cnes, nome_hospital)
                        )
                        if p1: pdfs_gerados.append(p1)
                        
                    if df_nc_hosp is not None and not df_nc_hosp.empty:
                        p2 = processamento.gerar_pdf(
                            df_nc_hosp, 'nao_coincidentes', comp, dir_saida, hospitais, 
                            usuario_active=self.usuario_ativo, 
                            hospital_info=(cnes, nome_hospital)
                        )
                        if p2: pdfs_gerados.append(p2)
                except Exception as e:
                    QMessageBox.critical(self, "Erro ao Gerar PDF", f"Falha ao gerar PDF para {nome_hospital}:\n{e}")
                    continue
            
            if pdfs_gerados:
                QMessageBox.information(self, "Exportação Concluída", f"{len(pdfs_gerados)} arquivo(s) PDF foram gerados com sucesso em:\n{dir_saida}")
                if self.usuario_ativo:
                    self.banco.registrar_log(self.usuario_ativo['cpf'], "Exportação de Relatório (PDF)", f"Gerou {len(pdfs_gerados)} relatório(s) PDF de auditoria para {len(hospitais_selecionados)} hospitais (Comp: {comp})")

    def abrir_menu_contexto_digitacao(self, pos):
        item = self.tabela_digitacao.itemAt(pos)
        if item is None: return

        linha = item.row()

        # Só força a seleção de uma linha única se o utilizador clicar fora do bloco já selecionado
        linhas_selecionadas = set(idx.row() for idx in self.tabela_digitacao.selectedIndexes())
        if linha not in linhas_selecionadas:
            self.tabela_digitacao.selectRow(linha)
            linhas_selecionadas = {linha}

        menu = QMenu(self)

        # Novas opções de edição seguras
        acao_editar_aih = QAction("✏️ Editar Número da AIH", self)
        acao_editar_aih.triggered.connect(lambda: self.abrir_edicao_segura(linha, "aih"))

        acao_editar_valor = QAction("✏️ Editar Valor (R$)", self)
        acao_editar_valor.triggered.connect(lambda: self.abrir_edicao_segura(linha, "valor"))

        # Texto dinâmico: mostra quantos registos vão ser apagados
        qtd = len(linhas_selecionadas)
        texto_remover = f"🗑️ Remover {qtd} Registro(s)" if qtd > 1 else "🗑️ Remover Registro (X)"
        acao_remover = QAction(texto_remover, self)
        acao_remover.triggered.connect(self.excluir_da_digitacao)

        menu.addAction(acao_editar_aih)
        menu.addAction(acao_editar_valor)
        menu.addSeparator()  # Linha divisória visual
        menu.addAction(acao_remover)

        menu.exec(self.tabela_digitacao.viewport().mapToGlobal(pos))

    def abrir_edicao_segura(self, linha, tipo):
        """Abre pop-up seguro para edição e persiste no banco."""
        id_reg = self.tabela_digitacao.item(linha, 0).data(Qt.ItemDataRole.UserRole)
        comp = self.ent_competencia.text().strip()

        if tipo == "aih":
            valor_atual = self.tabela_digitacao.item(linha, 3).text()
            novo_valor, ok = QInputDialog.getText(self, "Edição Segura", "Novo número de AIH:", text=valor_atual)

            if ok and novo_valor.strip():
                aih_limpa = novo_valor.strip()
                if validador.validar_aih(aih_limpa):
                    # O ID do banco está mapeado na coluna 2 para "aih" no seu banco_dados.py
                    if self.banco.atualizar_registro_local(id_reg, 2, aih_limpa):
                        # --- INÍCIO DO LOG ---
                        if self.usuario_ativo:
                            self.banco.registrar_log(
                                self.usuario_ativo['cpf'],
                                "Edição de Registro",
                                f"Alterou Nº AIH para {aih_limpa} no ID {id_reg} (Comp. {comp})"
                            )
                        # --- FIM DO LOG ---
                        self.atualizar_grade_digitacao(comp)  # Recarrega a tabela visualmente
                else:
                    QMessageBox.warning(self, "AIH Inválida", "O dígito verificador falhou.")


        elif tipo == "valor":

            # Remove formatação R$ visual. Se for traço, deixa a caixa em branco para facilitar a digitação

            valor_atual = self.tabela_digitacao.item(linha, 4).text()

            valor_numerico_limpo = limpar_valor_real(valor_atual)

            texto_caixa = "" if valor_numerico_limpo == "-" else valor_numerico_limpo

            novo_valor, ok = QInputDialog.getText(self, "Edição Segura",
                                                  "Novo valor numérico (deixe em branco para ignorar):",
                                                  text=texto_caixa)

            if ok:

                valor_limpo = novo_valor.strip()

                # Se o faturista apagou tudo, converte para traço

                if not valor_limpo or valor_limpo == "-":
                    valor_limpo = "-"

                if valor_limpo == "-" or re.match(r"^\d+(,\d{2})?$", valor_limpo):

                    if self.banco.atualizar_registro_local(id_reg, 3, valor_limpo):
                        self.atualizar_grade_digitacao(comp)

                else:

                    QMessageBox.warning(self, "Erro", "Formato de valor inválido. Use vírgula.")

    def excluir_da_digitacao(self):
        # 1. Coleta os índices únicos das linhas selecionadas
        linhas_selecionadas = set(index.row() for index in self.tabela_digitacao.selectedIndexes())

        if not linhas_selecionadas: return

        qtd = len(linhas_selecionadas)
        msg = f"Tem certeza que deseja remover {qtd} registro(s) da base local?" if qtd > 1 else "Tem certeza que deseja remover este registro da base local?"

        resposta = QMessageBox.question(self, "Confirmar Exclusão", msg,
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if resposta == QMessageBox.StandardButton.Yes:
            comp_atual = self.ent_competencia.text().strip()
            sucesso_total = True
            aihs_excluidas = []

            # 2. Exclusão em ordem reversa (do maior índice para o menor)
            for linha in sorted(linhas_selecionadas, reverse=True):
                id_reg = self.tabela_digitacao.item(linha, 0).data(Qt.ItemDataRole.UserRole)
                aih_excluida = self.tabela_digitacao.item(linha, 3).text()

                # Apaga do banco e, se der certo, apaga da interface
                if self.banco.excluir_registro_local(id_reg):
                    aihs_excluidas.append(aih_excluida)
                    self.tabela_digitacao.removeRow(linha)
                else:
                    sucesso_total = False

            # 3. Tratamento de Logs e Erros
            if sucesso_total:
                # --- INÍCIO DO LOG ---
                if self.usuario_ativo:
                    if qtd == 1:
                        detalhe_log = f"Removeu a AIH {aihs_excluidas[0]} (Comp. {comp_atual})"
                    else:
                        detalhe_log = f"Removeu {qtd} AIHs em lote (Comp. {comp_atual})"

                    self.banco.registrar_log(
                        self.usuario_ativo['cpf'],
                        "Exclusão de Registro",
                        detalhe_log
                    )
                # --- FIM DO LOG ---
            else:
                QMessageBox.warning(self, "Aviso",
                                    "Alguns registros podem não ter sido excluídos corretamente do banco de dados.")

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
            # --- INÍCIO DO LOG ---
            if self.usuario_ativo:
                self.banco.registrar_log(
                    self.usuario_ativo['cpf'],
                    "Limpeza em Massa",
                    f"Excluiu os dados tipo '{tipo}' da competência {comp}"
                )
            # --- FIM DO LOG ---

            self.mostrar_status()

    def exibir_resultados_auditoria(self, comp, df_div, df_nc, dict_hospitais):
        self.limpar_tela()

        # Guarda os dados originais no estado da classe para permitir a filtragem dinâmica
        self.df_div_original = df_div
        self.df_nc_original = df_nc
        self.comp_atual = comp
        self.dict_hospitais_atual = dict_hospitais

        # Extrai a lista de CNES que tiveram pelo menos uma AIH digitada localmente
        # Para isso, precisamos buscar os dados locais originais (antes do merge)
        # Consulta parametrizada de segurança para contagem de abas
        conexao = self.banco.conectar()
        query_filtro = "SELECT DISTINCT cnes FROM aih_digitadas WHERE competencia = ?"
        df_local_puro = pd.read_sql_query(query_filtro, conexao, params=(comp,))
        conexao.close()

        self.cnes_com_digitacao_local = df_local_puro['cnes'].tolist()

        data_fmt = f"{comp[4:]}/{comp[:4]}"

        # --- CABEÇALHO COM TÍTULO, CHECKBOX E BOTÃO EXPORTAR ---
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 15)

        lbl_titulo = QLabel(f"Resultados da Conferência - {data_fmt}")
        lbl_titulo.setStyleSheet("font-size: 28px; font-weight: bold; color: #2c3e50;")

        # Novo Checkbox de Inteligência
        self.chk_filtro_local = QCheckBox("Comparar APENAS hospitais com digitação local")
        self.chk_filtro_local.setStyleSheet("font-weight: bold; color: #007acc; padding-right: 15px;")
        self.chk_filtro_local.stateChanged.connect(self.aplicar_filtro_hospitais)

        # Criação do Botão de Exportar
        self.btn_exportar = QPushButton("📥 Exportar Resultados")
        self.btn_exportar.setStyleSheet("background-color: #27ae60; color: white;")

        # A montagem do menu de exportação ocorrerá após a filtragem para garantir
        # que o ficheiro gerado corresponda ao que está na tela

        top_layout.addWidget(lbl_titulo)
        top_layout.addStretch()
        top_layout.addWidget(self.chk_filtro_local)
        top_layout.addWidget(self.btn_exportar)
        self.main_layout.addWidget(top_bar)

        # Container para as Abas (será destruído e recriado pela filtragem)
        self.container_abas = QWidget()
        self.layout_container_abas = QVBoxLayout(self.container_abas)
        self.layout_container_abas.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.container_abas)

        # Desenha a tela inicial (sem o filtro aplicado)
        self.aplicar_filtro_hospitais()

    def aplicar_filtro_hospitais(self):
        """Aplica ou remove o filtro de prestadores e redesenha a interface."""

        df_div_filtrado = self.df_div_original.copy() if self.df_div_original is not None else None
        df_nc_filtrado = self.df_nc_original.copy() if self.df_nc_original is not None else None

        if self.chk_filtro_local.isChecked():
            if df_div_filtrado is not None and not df_div_filtrado.empty:
                df_div_filtrado = df_div_filtrado[df_div_filtrado['cnes'].isin(self.cnes_com_digitacao_local)]

            if df_nc_filtrado is not None and not df_nc_filtrado.empty:
                df_nc_filtrado = df_nc_filtrado[df_nc_filtrado['cnes'].isin(self.cnes_com_digitacao_local)]

        # Limpa o container de abas antigo
        while self.layout_container_abas.count() > 0:
            item = self.layout_container_abas.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Atualiza as funções do botão de exportação com os dados atuias (filtrados ou não)
        menu_exportar = QMenu(self)
        act_pdf = QAction("📄 Exportar como PDF", self)
        act_pdf.triggered.connect(lambda: self.exportar_resultados_pdf(self.comp_atual, df_div_filtrado, df_nc_filtrado,
                                                                       self.dict_hospitais_atual))

        act_excel = QAction("📊 Exportar como Excel (.xlsx)", self)
        act_excel.triggered.connect(
            lambda: self.exportar_resultados_excel(self.comp_atual, df_div_filtrado, df_nc_filtrado))

        menu_exportar.addAction(act_pdf)
        menu_exportar.addAction(act_excel)
        self.btn_exportar.setMenu(menu_exportar)

        # Renderiza as novas tabelas
        self.redesenhar_abas_auditoria(df_div_filtrado, df_nc_filtrado, self.dict_hospitais_atual)

    def redesenhar_abas_auditoria(self, df_div, df_nc, dict_hospitais):
        import pandas as pd
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
                paciente = row.paciente if pd.notna(row.paciente) else "Não Informado"

                tabela_div.setItem(i, 0, QTableWidgetItem(nome_unidade))
                tabela_div.setItem(i, 1, QTableWidgetItem(str(row.aih)))
                tabela_div.setItem(i, 2, QTableWidgetItem(str(paciente)))

                i_loc = QTableWidgetItem(row.v_local_fmt)
                i_loc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela_div.setItem(i, 3, i_loc)

                i_sihd = QTableWidgetItem(row.v_sihd_fmt)
                i_sihd.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela_div.setItem(i, 4, i_sihd)

                i_dif = QTableWidgetItem(row.dif_fmt)
                i_dif.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                i_dif.setForeground(QColor("#c0392b"))
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
                paciente = row.paciente if pd.notna(row.paciente) else "Não Informado"

                tabela_nc.setItem(i, 0, QTableWidgetItem(nome_unidade))
                tabela_nc.setItem(i, 1, QTableWidgetItem(str(row.aih)))
                tabela_nc.setItem(i, 2, QTableWidgetItem(str(paciente)))

                i_sihd = QTableWidgetItem(row.v_sihd_fmt)
                i_sihd.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tabela_nc.setItem(i, 3, i_sihd)

            tabela_nc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            layout_nc.addWidget(tabela_nc)
            tabs.addTab(tab_nc, f"Não Coincidentes - Faltantes ({len(df_nc)})")

        self.layout_container_abas.addWidget(tabs)

    def abrir_tela_ajuda(self):
        """Renderiza a documentação oficial do sistema."""
        self.limpar_tela()
        self.destacar_menu(self.btn_ajuda)

        lbl_titulo = QLabel("Manual do Utilizador")
        lbl_titulo.setStyleSheet("font-size: 32px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addWidget(lbl_titulo)

        # Utilização de QScrollArea para comportar a documentação expandida
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #ced4da; background-color: #ffffff; border-radius: 8px; }")

        container_scroll = QWidget()
        container_scroll.setStyleSheet("background-color: #ffffff;")
        layout_scroll = QVBoxLayout(container_scroll)
        layout_scroll.setContentsMargins(40, 30, 40, 40)
        layout_scroll.setSpacing(15)

        conteudo_html = """
        <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #2c3e50; font-size: 14px; line-height: 1.6;">

            <p style="margin-bottom: 20px;">Este manual descreve os procedimentos técnicos e as regras de negócio embarcadas no sistema <b>Integritas AIH - Conferência de Faturamento de AIH</b>.</p>

            <h2 style="color: #007acc; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">1. Painel de Sincronização</h2>
            <p>O painel atua como o centro de comando da auditoria, permitindo a monitorização do estado de carga das competências (ex: 03/2026).</p>
            <ul style="margin-top: 5px; margin-bottom: 15px;">
                <li><b>Indicadores Visuais:</b> O texto a verde sinaliza que os dados daquela base (Local ou SIHD) foram devidamente carregados. Texto em cinza indica pendência de importação ou digitação.</li>
                <li><b>Conferência Preliminar:</b> Um duplo clique sobre qualquer competência validada abre uma grelha detalhada com os registos processados. Pode pesquisar AIHs específicas diretamente nessa tela.</li>
                <li><b>Higienização de Dados:</b> O clique direito sobre uma competência ativa um menu de contexto que permite a exclusão segmentada (apenas base Local ou apenas SIHD) ou a limpeza definitiva da competência.</li>
            </ul>

            <h2 style="color: #007acc; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">2. Lançamento Manual (Base Local)</h2>
            <p>Módulo de digitação estruturado com travas rígidas para garantir a integridade financeira.</p>
            <ul style="margin-top: 5px; margin-bottom: 15px;">
                <li><b>Validação de AIH:</b> O sistema valida o algoritmo do DATASUS no ato da inserção. Números com falha estrutural são sumariamente rejeitados.
                    <div style="background-color: #f8f9fa; padding: 12px 15px; border-left: 3px solid #007acc; margin-top: 8px; margin-bottom: 8px; font-size: 13px; color: #34495e;">
                        <b>Mecânica de Cálculo do Módulo 11:</b> A numeração da AIH possui 13 algarismos, sendo o último o Dígito Verificador (DV). O sistema realiza a seguinte prova matemática em milissegundos:
                        <ol style="margin-top: 8px; margin-bottom: 0px; padding-left: 25px;">
                            <li>Isolam-se os 12 primeiros dígitos da AIH (base de cálculo), tratando-os como um único valor inteiro.</li>
                            <li>Divide-se este valor total por 11 e extrai-se o resto desta divisão.</li>
                            <li>O resto obtido corresponde diretamente ao DV esperado. <i>(Exceção da regra: se o resto da divisão for igual a 10, o sistema assume automaticamente que o DV é 0)</i>.</li>
                        </ol>
                    </div>
                </li>
                <li><b>Bloqueio de Duplicidade:</b> É impossível inserir a mesma AIH duas vezes para o mesmo hospital na mesma competência. O sistema deteta a colisão e devolve o foco ao campo de digitação.</li>
                <li><b>Valores Ausentes:</b> Caso o faturista pretenda conferir apenas a presença da AIH, o campo de valor pode ser deixado em branco. O sistema atribuirá um traço ("-"), garantindo que a base não seja poluída com valores zerados (R$ 0,00).</li>
                <li><b>Edição Segura:</b> Para prevenir alterações acidentais, a edição via duplo clique na tabela está bloqueada. Para alterar uma AIH ou valor, clique com o botão direito sobre a linha e selecione a opção desejada no menu de contexto.</li>
            </ul>

            <h2 style="color: #007acc; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">3. Importação de Dados</h2>
            <p>Os módulos de carga em lote operam com tolerância a falhas estruturais.</p>
            <ul style="margin-top: 5px; margin-bottom: 15px;">
                <li><b>Importar TXT Local:</b> Processa extrações do sistema de faturamento do hospital. O motor tolera ficheiros sem a coluna de valor, assumindo automaticamente a ausência como "Não Conferido" ("-").</li>
                <li><b>Importar Base SIHD:</b> Módulo inteligente que deteta se o ficheiro do governo é do tipo delimitado por ponto e vírgula ou posicional bruto, adequando a leitura automaticamente.</li>
            </ul>

            <h2 style="color: #007acc; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">4. Execução de Conferência</h2>
            <p>O motor de cruzamento relacional consolida as divergências através do menu de execução.</p>
            <ul style="margin-top: 5px; margin-bottom: 15px;">
                <li><b>Integridade de Base:</b> A conferência só avança se a competência selecionada possuir simultaneamente no banco de dados a Base Local (digitação manual) e dados do SIHD.</li>
                <li><b>Filtro de Produção:</b> Por predefinição, a aba de "Não Coincidentes" exibe todos os hospitais presentes na base governamental, sem restrições. No entanto, o utilizador pode marcar a opção no topo da tela para filtrar e visualizar apenas os prestadores que possuam dados efetivamente digitados na base local.</li>
                <li><b>Exportação Tática:</b> Os resultados podem ser extraídos para <b>Excel</b> (mantendo o formato numérico puro para cálculos de fórmulas) ou para <b>PDF</b> (estruturado e otimizado para impressão e anexo em processos).</li>
                <li><b>Melhorias em relação ao processo antigo:</b> O que mudou: Em vez de processar listas linha a linha (o que pode ser lento com ficheiros DATASUS gigantescos), o sistema agora carrega os dados num banco SQLite embarcado e processa os cruzamentos matemáticos de forma matricial (em blocos maciços) na memória RAM através do Pandas. O que se manteve: As regras de negócio e a matemática do faturamento (o Módulo 11, a junção de faltantes e o recálculo de divergências) são as mesmas idealizadas na arquitetura inicial em Java. O coração financeiro da ferramenta permanece inalterado.</li>
            </ul>

            <h2 style="color: #007acc; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">5. Exportação de Bases de Dados</h2>
            <p>Módulo dedicado à extração e portabilidade dos dados armazenados localmente, funcionando como ferramenta de backup e análise detalhada.</p>
            <ul style="margin-top: 5px; margin-bottom: 15px;">
                <li><b>Exportar Base Local / Base SIHD:</b> Permite a extração integral ou filtrada por competência (mês/ano) de ambas as matrizes de dados.</li>
                <li><b>Formato Excel (.xlsx):</b> Otimizado para conferência humana e matemática. O motor de exportação converte a máscara de valores textuais em numéricos puros, viabilizando a aplicação imediata de filtros e fórmulas de soma nas colunas financeiras.</li>
                <li><b>Formato de Texto (.txt):</b> Otimizado para backup sistêmico. Gera um arquivo delimitado por ponto e vírgula (;), isento de cabeçalhos. Este arquivo respeita a exata estrutura do importador, podendo ser reimportado pelo sistema a qualquer momento em caso de necessidade de restauração.</li>
            </ul>

            <h2 style="color: #007acc; border-bottom: 2px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">6. Segurança e Trilha de Auditoria</h2>
            <p>Módulo responsável por garantir a integridade de acesso e o mapeamento de todas as ações realizadas no sistema.</p>
            <ul style="margin-top: 5px; margin-bottom: 15px;">
                <li><b>Autenticação Restrita:</b> O acesso ao software é protegido por credenciais individuais (CPF e Senha criptografada). Em caso de esquecimento, o sistema dispõe de uma funcionalidade de "Dica de Senha" para recuperação autônoma local.</li>
                <li><b>Rastreabilidade de Ações (Logs):</b> Todas as operações críticas &mdash; incluindo lançamentos manuais, exclusões, importações de ficheiros e exportação de relatórios para Excel/PDF &mdash; são registadas em banco de dados e vinculadas ao utilizador autenticado que as executou.</li>
                <li><b>Painel de Logs de Utilização:</b> Interface dedicada para consulta do histórico de navegação e operação. Conta com campo de pesquisa em tempo real para facilitar auditorias internas.</li>
                <li><b>Exportação de Segurança:</b> A trilha de auditoria pode ser integralmente exportada para Excel, garantindo total transparência técnica e administrativa sobre o uso da ferramenta e a fuga de informações.</li>
            </ul>
        </div>
        """
        lbl_manual = QLabel(conteudo_html)
        lbl_manual.setWordWrap(True)
        lbl_manual.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lbl_manual.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout_scroll.addWidget(lbl_manual)
        layout_scroll.addStretch()
        scroll.setWidget(container_scroll)

        self.main_layout.addWidget(scroll)

    def abrir_tela_sobre(self):
        """Apresenta os créditos técnicos, arquitetura e metadados do software."""
        self.limpar_tela()
        self.destacar_menu(self.btn_sobre)

        lbl_titulo = QLabel("Sobre o Sistema")
        lbl_titulo.setStyleSheet("font-size: 32px; font-weight: bold; color: #2c3e50; margin-bottom: 20px;")
        lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Container com rolagem para proteger a resolução em monitores menores
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #ced4da; background-color: #ffffff; border-radius: 8px; }")

        container_scroll = QWidget()
        container_scroll.setStyleSheet("background-color: #ffffff;")
        layout_scroll = QVBoxLayout(container_scroll)
        layout_scroll.setContentsMargins(40, 30, 40, 40)
        layout_scroll.setSpacing(15)

        # Estrutura HTML rica, técnica e dividida por tópicos de arquitetura
        texto_sobre = """
        <div style="font-family: 'Segoe UI', Arial, sans-serif; color: #2c3e50; font-size: 14px; line-height: 1.6;">

            <div style="text-align: center; margin-bottom: 30px;">
                <h2 style='color: #007acc; margin-bottom: 5px; font-size: 24px;'>Integritas - Conferência e Faturamento de AIH</h2>
                <p style="color: #7f8c8d; font-size: 14px; margin-top: 0px;">Versão 1.2.0 (Build 2026) | Licença de Uso Interno</p>
            </div>

            <h3 style="color: #2c3e50; border-bottom: 1px solid #ecf0f1; padding-bottom: 5px;">Objetivo do Software</h3>
            <p>Solução tecnológica projetada para o ambiente de faturamento e auditoria hospitalar do Sistema Único de Saúde (SUS). O sistema automatiza o cruzamento de informações de Autorizações de Internação Hospitalar (AIH) entre a digitação manual (local) e a base de dados governamental (SIHD/DATASUS), mitigando perdas financeiras e identificando divergências numéricas com precisão absoluta.</p>

            <h3 style="color: #2c3e50; border-bottom: 1px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">Arquitetura e Stack Tecnológico</h3>
            <ul>
                <li style="margin-bottom: 8px;"><b>Interface Gráfica (GUI):</b> Desenvolvida em <i>PyQt6</i> sob arquitetura orientada a eventos, garantindo renderização nativa e fluidez durante a manipulação de bases volumosas.</li>
                <li style="margin-bottom: 8px;"><b>Motor de Processamento:</b> Utiliza <i>Pandas</i> para operações de <i>merge</i> relacional em memória (In-Memory Processing). Processa dados de forma matricial e vetorizada, cruzando milhares de registos em frações de segundo.</li>
                <li style="margin-bottom: 8px;"><b>Persistência e SGBD:</b> Motor <i>SQLite3</i> embarcado. Armazena os dados em um ficheiro transacional único garantindo propriedades ACID (Atomicidade, Consistência, Isolamento e Durabilidade), sem necessidade de servidores externos.</li>
                <li style="margin-bottom: 8px;"><b>Segurança e Criptografia:</b> Implementação da biblioteca nativa <i>hashlib</i> para o armazenamento de credenciais utilizando algoritmos de <i>hash</i> irreversíveis (SHA-256), garantindo a proteção integral do acesso local.</li>
                <li style="margin-bottom: 8px;"><b>Exportação Tática:</b> Geração de matrizes dinâmicas em Excel via <i>OpenPyXL</i> para filtros manuais e relatórios imutáveis em PDF via <i>FPDF</i>.</li>
                <li style="margin-bottom: 8px;"><b>Compilação Ahead-of-Time:</b> Transpilado de Python para C e compilado como binário autossuficiente (<i>standalone</i>) via <i>Nuitka</i>. Contorna restrições de privilégios de administrador na rede da Secretaria e dispensa interpretadores instalados na máquina cliente.</li>
            </ul>

            <h3 style="color: #2c3e50; border-bottom: 1px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">Modelagem do Banco de Dados</h3>
            <ul>
                <li style="margin-bottom: 8px;"><b>Isolamento de Origem:</b> Separação estrita entre tabelas de produção hospitalar local e retornos governamentais do SIHD para evitar contaminação estrutural.</li>
                <li style="margin-bottom: 8px;"><b>Chaves de Relacionamento:</b> Cruzamento estruturado de forma composta utilizando chaves primárias baseadas em <i>Competência (MM/AAAA)</i> e <i>Número da AIH</i>.</li>
                <li style="margin-bottom: 8px;"><b>Governança e Auditoria Interna:</b> Arquitetura relacional estendida com tabelas dedicadas de utilizadores e logs (Trilha de Auditoria). Utilização de chaves estrangeiras (<i>Foreign Keys</i>) para vincular cada operação crítica (inserção, exclusão e exportação) ao CPF do faturista responsável.</li>
                <li style="margin-bottom: 8px;"><b>Tipagem Rigorosa:</b> Identificadores de AIH processados estritamente como texto (<i>VARCHAR/TEXT</i>) para preservação de zeros à esquerda, garantindo a integridade do cálculo do Módulo 11 (Dígito Verificador). A caixa da AIH rejeita fisicamente qualquer tecla que não seja um número (limitado a 13 posições). A caixa de Valor bloqueia letras e permite apenas a inserção de algarismos numéricos acompanhados de, no máximo, uma única vírgula e duas casas decimais. Isto impede a entrada de dados corrompidos logo na origem.</li>
                <li style="margin-bottom: 8px;"><b>Prevenção de Redundância:</b> Lógica de <i>Upsert</i> nas inserções, assegurando que reprocessamentos de faturamento atualizem as competências sem duplicar registros preexistentes.</li>
            </ul>

            <h3 style="color: #2c3e50; border-bottom: 1px solid #ecf0f1; padding-bottom: 5px; margin-top: 20px;">Engenharia e Desenvolvimento</h3>
            <div style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #007acc; margin-top: 10px;">
                <p style="margin: 0; font-size: 15px;"><b>Cássio de Souza Lopes / João Severo</b></p>
                <p style="margin: 2px 0 0 0; color: #34495e;">Secretaria de Saúde / Regulação</p>
                <p style="margin: 2px 0 0 0; color: #7f8c8d;">Montes Claros, Minas Gerais</p>
            </div>

        </div>
        """

        lbl_desc = QLabel(texto_sobre)
        lbl_desc.setWordWrap(True)
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lbl_desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout_scroll.addWidget(lbl_desc)
        layout_scroll.addStretch()
        scroll.setWidget(container_scroll)

        self.main_layout.addWidget(lbl_titulo)
        self.main_layout.addWidget(scroll)

    def abrir_exportacao_local(self):
        """Abre a janela de parametrização para exportação da base de dados local."""
        locais = self.banco.listar_competencias_locais()
        if not locais:
            QMessageBox.warning(self, "Aviso", "O banco de dados local encontra-se vazio.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Exportar Base Local")
        dialog.setFixedSize(350, 260)
        layout = QVBoxLayout(dialog)

        # Parâmetro 1: Seleção de Escopo
        layout.addWidget(QLabel("Selecione a abrangência dos dados:"))
        cb_comp = QComboBox()
        cb_comp.addItem("Todas as Competências (Backup Completo)", "Todas")
        for c in locais:
            data_fmt = f"{c[4:]}/{c[:4]}"
            cb_comp.addItem(f"Apenas a competência {data_fmt}", c)
        layout.addWidget(cb_comp)
        layout.addSpacing(10)

        # Parâmetro 2: Seleção de Formato
        layout.addWidget(QLabel("Formato do arquivo de saída:"))
        cb_formato = QComboBox()
        cb_formato.addItem("Planilha Excel (.xlsx) - Otimizado para cálculos", "xlsx")
        cb_formato.addItem("Texto Delimitado (.txt) - Otimizado para backup", "txt")
        layout.addWidget(cb_formato)
        layout.addSpacing(15)

        btn_exportar = QPushButton("Processar Exportação")
        btn_exportar.setStyleSheet("background-color: #27ae60; color: white; padding: 10px; font-weight: bold;")

        def acao_exportar():
            comp_selecionada = cb_comp.currentData()
            formato = cb_formato.currentData()
            dialog.accept()
            self.executar_exportacao_local(comp_selecionada, formato)

        btn_exportar.clicked.connect(acao_exportar)
        layout.addWidget(btn_exportar)

        dialog.exec()

    def executar_exportacao_local(self, comp, formato):
        """Conecta ao SQLite, formata os dados conforme o requisito e salva no disco."""
        import pandas as pd
        conexao = self.banco.conectar()

        # Construção dinâmica da Query SQL (Base Local não possui coluna paciente)

        query = "SELECT competencia, cnes, aih, valor FROM aih_digitadas"
        params = ()

        if comp != "Todas":
            query += " WHERE competencia = ?"
            params = (comp,)

        df = pd.read_sql_query(query, conexao, params=params)

        conexao.close()

        # Define o sufixo do nome do arquivo com base na competência selecionada
        sufixo_arquivo = "Completa" if comp == "Todas" else comp

        if df.empty:
            QMessageBox.warning(self, "Aviso", "Nenhum registo encontrado para os parâmetros selecionados.")
            return

        if formato == "xlsx":
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Exportação Excel",
                                                     f"Base_Local_{sufixo_arquivo}.xlsx", "Excel (*.xlsx)")
            if caminho:
                try:
                    df['valor_num'] = pd.to_numeric(df['valor'].str.replace(',', '.'), errors='coerce')
                    df_exp = df[['competencia', 'cnes', 'aih', 'valor_num']].copy()
                    df_exp.columns = ['Competência', 'CNES', 'AIH', 'Valor Digitado']

                    with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
                        df_exp.to_excel(writer, sheet_name='Base Local', index=False)

                    QMessageBox.information(self, "Sucesso", "Base local exportada para Excel com sucesso.")

                    # --- INÍCIO DO LOG (Adicionado à ramificação XLSX) ---
                    if self.usuario_ativo:
                        self.banco.registrar_log(
                            self.usuario_ativo['cpf'],
                            "Exportação de Dados",
                            f"Exportou base LOCAL em .{formato} (Escopo: {comp})"
                        )
                    # --- FIM DO LOG ---
                except Exception as e:
                    QMessageBox.critical(self, "Erro de I/O", f"Falha na gravação do Excel: {str(e)}")

        elif formato == "txt":
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Exportação TXT", f"Base_Local_{sufixo_arquivo}.txt",
                                                     "Texto (*.txt)")
            if caminho:
                try:
                    df.to_csv(caminho, sep=';', header=False, index=False, encoding='utf-8')
                    QMessageBox.information(self, "Sucesso", "Base local exportada para TXT com sucesso.")

                    # --- INÍCIO DO LOG ---
                    if self.usuario_ativo:
                        self.banco.registrar_log(
                            self.usuario_ativo['cpf'],
                            "Exportação de Dados",
                            f"Exportou base LOCAL em .{formato} (Escopo: {comp})"
                        )
                    # --- FIM DO LOG ---
                except Exception as e:
                    QMessageBox.critical(self, "Erro de I/O", f"Falha na gravação do arquivo de texto: {str(e)}")

    def executar_exportacao_sihd(self, comp, formato):
        """Conecta ao SQLite, formata os dados do SIHD e salva no disco."""
        import pandas as pd
        conexao = self.banco.conectar()

        # Construção da Query SQL contemplando a coluna paciente

        query = "SELECT competencia, cnes, aih, valor, paciente FROM aihs_importadas_sihd"
        params = ()

        # --- DECLARAÇÃO DA VARIÁVEL RESTAURADA ---
        sufixo_arquivo = comp if comp != "Todas" else "Todas_Competencias"

        if comp != "Todas":
            query += " WHERE competencia = ?"
            params = (comp,)

        df = pd.read_sql_query(query, conexao, params=params)

        conexao.close()

        # Define o sufixo do nome do arquivo com base na competência selecionada
        sufixo_arquivo = "Completa" if comp == "Todas" else comp

        if df.empty:
            QMessageBox.warning(self, "Aviso", "Nenhum registo encontrado para os parâmetros selecionados.")
            return

        if formato == "xlsx":
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Exportação Excel",
                                                     f"Base_SIHD_{sufixo_arquivo}.xlsx", "Excel (*.xlsx)")
            if caminho:
                try:
                    df_exp = df[['competencia', 'cnes', 'aih', 'paciente', 'valor']].copy()
                    df_exp.columns = ['Competência', 'CNES', 'AIH', 'Nome do Paciente', 'Valor SIHD']

                    with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
                        df_exp.to_excel(writer, sheet_name='Base SIHD', index=False)

                    QMessageBox.information(self, "Sucesso", "Base SIHD exportada para Excel com sucesso.")

                    # --- INÍCIO DO LOG (Adicionado à ramificação XLSX e corrigido para SIHD) ---
                    if self.usuario_ativo:
                        self.banco.registrar_log(
                            self.usuario_ativo['cpf'],
                            "Exportação de Dados",
                            f"Exportou base SIHD em .{formato} (Escopo: {comp})"
                        )
                    # --- FIM DO LOG ---
                except Exception as e:
                    QMessageBox.critical(self, "Erro de I/O", f"Falha na gravação do Excel: {str(e)}")

        elif formato == "txt":
            caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Exportação TXT", f"Base_SIHD_{sufixo_arquivo}.txt",
                                                     "Texto (*.txt)")
            if caminho:
                try:
                    df.to_csv(caminho, sep=';', header=False, index=False, encoding='utf-8')
                    QMessageBox.information(self, "Sucesso", "Base SIHD exportada para TXT com sucesso.")

                    # --- INÍCIO DO LOG (Corrigido para SIHD) ---
                    if self.usuario_ativo:
                        self.banco.registrar_log(
                            self.usuario_ativo['cpf'],
                            "Exportação de Dados",
                            f"Exportou base SIHD em .{formato} (Escopo: {comp})"
                        )
                    # --- FIM DO LOG ---
                except Exception as e:
                    QMessageBox.critical(self, "Erro de I/O", f"Falha na gravação do arquivo de texto: {str(e)}")

    def abrir_exportacao_sihd(self):
        """Abre a janela de parametrização para exportação da base do governo."""
        sihds = self.banco.listar_competencias_sihd()
        if not sihds:
            QMessageBox.warning(self, "Aviso", "A base governamental (SIHD) encontra-se vazia.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Exportar Base SIHD")
        dialog.setFixedSize(350, 260)
        layout = QVBoxLayout(dialog)

        # Parâmetro 1: Seleção de Escopo
        layout.addWidget(QLabel("Selecione a abrangência dos dados:"))
        cb_comp = QComboBox()
        cb_comp.addItem("Todas as Competências (Backup Completo)", "Todas")
        for c in sihds:
            data_fmt = f"{c[4:]}/{c[:4]}"
            cb_comp.addItem(f"Apenas a competência {data_fmt}", c)
        layout.addWidget(cb_comp)
        layout.addSpacing(10)

        # Parâmetro 2: Seleção de Formato
        layout.addWidget(QLabel("Formato do arquivo de saída:"))
        cb_formato = QComboBox()
        cb_formato.addItem("Planilha Excel (.xlsx) - Otimizado para leitura", "xlsx")
        cb_formato.addItem("Texto Delimitado (.txt) - Separador ponto e vírgula", "txt")
        layout.addWidget(cb_formato)
        layout.addSpacing(15)

        btn_exportar = QPushButton("Processar Exportação")
        btn_exportar.setStyleSheet("background-color: #27ae60; color: white; padding: 10px; font-weight: bold;")

        def acao_exportar():
            comp_selecionada = cb_comp.currentData()
            formato = cb_formato.currentData()
            dialog.accept()
            self.executar_exportacao_sihd(comp_selecionada, formato)

        btn_exportar.clicked.connect(acao_exportar)
        layout.addWidget(btn_exportar)

        dialog.exec()

    def abrir_tela_logs(self):
        """Abre a janela de visualização da Trilha de Auditoria."""
        # A janela é acessível a todos
        dialog = TelaLogsAuditoria(self.banco)
        # Injetamos o utilizador ativamente na janela de logs para a auditoria de exportação
        dialog.usuario_ativo = self.usuario_ativo
        dialog.exec()

    def aplicar_filtro_hospital_digitacao(self, *args):
        if not hasattr(self, 'tabela_digitacao') or self.carregando_tabela:
            return

        hospital_selecionado = self.cb_hospital.currentText()
        mostrar_todos = hospital_selecionado in ("Todas as Unidades", "")
        contador = 1
        labels = []

        for row in range(self.tabela_digitacao.rowCount()):
            item_hospital = self.tabela_digitacao.item(row, 2)
            if item_hospital:
                ocultar = False if mostrar_todos else (item_hospital.text() != hospital_selecionado)
                self.tabela_digitacao.setRowHidden(row, ocultar)
                if not ocultar:
                    labels.append(str(contador))
                    contador += 1
                else:
                    labels.append("")
            else:
                self.tabela_digitacao.setRowHidden(row, True)
                labels.append("")

        self.tabela_digitacao.setVerticalHeaderLabels(labels)


    def obter_mapeamento_cnes_completo(self):
        """Retorna dicionário {cnes: {'nome': nome, 'cor': cor}} para as tabelas."""
        dados = self.banco.listar_prestadores_completos()
        return {cnes: {'nome': nome, 'cor': cor} for _, cnes, nome, cor in dados}

    def formatar_celula_hospital(self, texto, cor_hex):
        """Aplica negrito e a cor cadastrada ao item da tabela."""
        item = QTableWidgetItem(texto)
        item.setForeground(QColor(cor_hex))
        fonte = QFont()
        fonte.setBold(True)
        item.setFont(fonte)
        return item

class TelaLogsAuditoria(QDialog):
    def __init__(self, banco):
        super().__init__()
        self.banco = banco
        self.configurar_interface()

    def configurar_interface(self):
        self.setWindowTitle("Logs de Utilização")

        # --- ALTERAÇÃO DE DIMENSIONAMENTO ---
        # Define um limite mínimo para não esmagar a tabela, mas permite expansão total
        self.setMinimumSize(850, 500)
        self.resize(1000, 600)

        # Força o sistema operativo a exibir os botões de Maximizar e Fechar no QDialog
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint)

        self.setStyleSheet("background-color: #f8f9fa; font-family: 'Segoe UI', Arial, sans-serif;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Cabeçalho
        top_layout = QHBoxLayout()

        lbl_titulo = QLabel("Registo de Atividades")
        lbl_titulo.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        top_layout.addWidget(lbl_titulo)

        top_layout.addStretch()

        # Campo de Pesquisa
        self.input_pesquisa = QLineEdit()
        self.input_pesquisa.setPlaceholderText("Pesquisar nos logs...")
        self.input_pesquisa.setFixedWidth(250)
        self.input_pesquisa.setStyleSheet(
            "padding: 8px; border: 1px solid #bdc3c7; border-radius: 4px; background: white; color: #212529;")
        self.input_pesquisa.textChanged.connect(self.filtrar_logs)
        top_layout.addWidget(self.input_pesquisa)

        # Botão Exportar
        btn_exportar = QPushButton("Exportar Excel")
        btn_exportar.setStyleSheet(
            "background-color: #27ae60; color: white; padding: 8px 15px; font-weight: bold; border-radius: 4px;")
        btn_exportar.clicked.connect(self.exportar_logs_excel)
        top_layout.addWidget(btn_exportar)

        layout.addLayout(top_layout)

        # Tabela de Logs
        self.tabela_logs = QTableWidget()
        self.tabela_logs.setColumnCount(5)
        self.tabela_logs.setHorizontalHeaderLabels(["Data / Hora", "CPF", "Utilizador", "Ação", "Detalhes"])
        self.tabela_logs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabela_logs.horizontalHeader().setSectionResizeMode(4,
                                                                 QHeaderView.ResizeMode.Stretch)  # A coluna Detalhes estica ao maximizar a tela
        self.tabela_logs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_logs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_logs.setStyleSheet("""
            QTableWidget { background-color: #ffffff; gridline-color: #dcdcdc; border-radius: 4px; border: 1px solid #ced4da; font-size: 13px; color: #2c3e50;}
            QHeaderView::section { background-color: #f1f2f6; font-weight: bold; padding: 5px; color: #34495e;}
        """)
        layout.addWidget(self.tabela_logs)

        self.carregar_dados()

    def carregar_dados(self):
        """Carrega os logs do banco de dados para a tabela."""
        dados = self.banco.listar_logs()
        self.tabela_logs.setRowCount(len(dados))

        for row_idx, linha in enumerate(dados):
            data_hora, cpf, nome, acao, detalhes = linha

            # Formatação simplificada da data (YYYY-MM-DD HH:MM:SS para DD/MM/YYYY HH:MM:SS)
            if data_hora:
                partes = str(data_hora).split(" ")
                if len(partes) == 2:
                    d, h = partes
                    if len(d) >= 10:
                        d_formatada = f"{d[8:10]}/{d[5:7]}/{d[0:4]}"
                        data_hora = f"{d_formatada} {h}"

            nome_exibicao = str(nome) if nome else "Desconhecido"

            self.tabela_logs.setItem(row_idx, 0, QTableWidgetItem(str(data_hora)))
            self.tabela_logs.setItem(row_idx, 1, QTableWidgetItem(str(cpf)))
            self.tabela_logs.setItem(row_idx, 2, QTableWidgetItem(nome_exibicao))
            self.tabela_logs.setItem(row_idx, 3, QTableWidgetItem(str(acao)))
            self.tabela_logs.setItem(row_idx, 4, QTableWidgetItem(str(detalhes)))

        # Ajusta a largura das colunas baseadas no conteúdo
        for i in range(4):
            self.tabela_logs.resizeColumnToContents(i)

    def filtrar_logs(self, texto):
        """Oculta linhas que não contêm o texto pesquisado."""
        termo = texto.lower()
        for row in range(self.tabela_logs.rowCount()):
            mostrar = False
            for col in range(self.tabela_logs.columnCount()):
                item = self.tabela_logs.item(row, col)
                if item and termo in item.text().lower():
                    mostrar = True
                    break
            self.tabela_logs.setRowHidden(row, not mostrar)

    def exportar_logs_excel(self):
        """Exporta os dados visíveis na tabela para um ficheiro Excel."""
        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar Logs em Excel", "Auditoria_Logs_Integritas.xlsx",
                                                 "Excel (*.xlsx)")
        if not caminho:
            return

        try:
            import pandas as pd

            dados_exportar = []
            headers = [self.tabela_logs.horizontalHeaderItem(i).text() for i in range(self.tabela_logs.columnCount())]

            for row in range(self.tabela_logs.rowCount()):
                if not self.tabela_logs.isRowHidden(row):
                    linha_dados = []
                    for col in range(self.tabela_logs.columnCount()):
                        item = self.tabela_logs.item(row, col)
                        linha_dados.append(item.text() if item else "")
                    dados_exportar.append(linha_dados)

            df = pd.DataFrame(dados_exportar, columns=headers)

            with pd.ExcelWriter(caminho, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name="Trilha de Auditoria")

            QMessageBox.information(self, "Sucesso", "Logs exportados com sucesso!")

            if hasattr(self, 'usuario_ativo') and self.usuario_ativo:
                self.banco.registrar_log(self.usuario_ativo['cpf'], "Exportação de Dados",
                                         "Exportou o Histórico de Auditoria (Logs) para Excel.")

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao exportar logs: {str(e)}")

if __name__ == "__main__":
    # --- INTEGRAÇÃO NATIVA COM WINDOWS ---
    # Força a barra de tarefas a reconhecer a aplicação como independente
    if os.name == 'nt':  # Verifica se o sistema é Windows
        myappid = 'auditoria.integritas.app.1.2'  # ID arbitrário e único
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

    app = QApplication(sys.argv)

    # Definição do ícone global da aplicação (afeta a barra de tarefas)
    caminho_icone_app = resource_path("icon_btm.ico")
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

    # Inicializa a barreira de autenticação
    tela_login = TelaLogin()

    # Executa em modo modal. Se o utilizador for validado (Accepted)
    if tela_login.exec() == QDialog.DialogCode.Accepted:

        # Captura o utilizador validado e injeta na aplicação principal
        usuario_logado = tela_login.usuario_autenticado
        window = App(usuario_ativo=usuario_logado)

        window.show()
        sys.exit(app.exec())
    else:
        # Encerra o processo se a tela de login for fechada sem sucesso
        sys.exit(0)