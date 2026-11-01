"""A tela de Configurações — a primeira janela do app.

É por aqui que se resolve a pasta de destino, a **pasta compartilhada** (sem a qual a rede
para de entregar downloads) e a ligação com o motor. Também mostra, de cara, o que ainda
falta instalar na máquina.

Roda sozinha: ``python app.py``
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import sistema
import slskd_config
from config import DIAS_ATE_REVALIDAR_COMPARTILHADA, Config

FORMATOS_SEM_PERDA = [("flac", "FLAC"), ("wav", "WAV"), ("aiff", "AIFF"), ("aif", "AIF")]
FORMATOS_COM_PERDA = [("mp3", "MP3"), ("m4a", "M4A"), ("aac", "AAC")]


def _titulo(texto: str) -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setStyleSheet("font-size: 15px; font-weight: 600; margin-top: 4px;")
    return rotulo


def _explicacao(texto: str) -> QLabel:
    rotulo = QLabel(texto)
    rotulo.setWordWrap(True)
    rotulo.setStyleSheet("color: palette(mid); margin-bottom: 6px;")
    return rotulo


class ListaDePastas(QWidget):
    """Várias pastas, com botões de acrescentar e tirar.

    Acervo de DJ não mora num lugar só — são discos diferentes, separados por gênero ou
    por ano. E compartilhar mais é do interesse de quem baixa: quanto mais você oferece,
    menos gente te bloqueia.
    """

    def __init__(self, titulo_do_dialogo: str):
        super().__init__()
        self._titulo = titulo_do_dialogo

        self.lista = QListWidget()
        self.lista.setToolTip("Todas estas pastas são oferecidas à rede Soulseek")
        self.lista.setMinimumHeight(96)

        acrescentar = QPushButton("Acrescentar pasta…")
        acrescentar.clicked.connect(self._acrescentar)
        self.botao_tirar = QPushButton("Tirar a selecionada")
        self.botao_tirar.clicked.connect(self._tirar)

        botoes = QHBoxLayout()
        botoes.addWidget(acrescentar)
        botoes.addWidget(self.botao_tirar)
        botoes.addStretch(1)

        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.addWidget(self.lista)
        fora.addLayout(botoes)

        self.lista.itemSelectionChanged.connect(self._atualizar_botoes)
        self._atualizar_botoes()

    def _acrescentar(self) -> None:
        escolhida = QFileDialog.getExistingDirectory(self, self._titulo)
        if not escolhida:
            return
        caminho = str(Path(escolhida))
        if caminho not in self.valores():  # a mesma pasta duas vezes não ajuda ninguém
            self.lista.addItem(caminho)
        self._atualizar_botoes()

    def _tirar(self) -> None:
        for item in self.lista.selectedItems():
            self.lista.takeItem(self.lista.row(item))
        self._atualizar_botoes()

    def _atualizar_botoes(self) -> None:
        self.botao_tirar.setEnabled(bool(self.lista.selectedItems()))

    def valores(self) -> list[str]:
        return [self.lista.item(i).text() for i in range(self.lista.count())]

    def valor(self) -> str:
        """A primeira. É o que o resto do app pergunta quando só precisa de uma."""
        return self.valores()[0] if self.lista.count() else ""

    def definir(self, pastas) -> None:
        if isinstance(pastas, str):
            pastas = [pastas] if pastas.strip() else []
        self.lista.clear()
        self.lista.addItems([str(p) for p in pastas if str(p).strip()])
        self._atualizar_botoes()


class SeletorDePasta(QWidget):
    """Um campo de caminho com botão de escolher e botão de criar.

    O "Criar" existe porque o caso comum é a pasta ainda não existir — mandar o usuário
    sair da janela, abrir o Explorer e voltar é atrito à toa.
    """

    def __init__(self, titulo_do_dialogo: str):
        super().__init__()
        self._titulo = titulo_do_dialogo

        self.campo = QLineEdit()
        self.campo.setPlaceholderText("nenhuma pasta escolhida")
        escolher = QPushButton("Escolher…")
        escolher.clicked.connect(self._escolher)
        self.criar = QPushButton("Criar")
        self.criar.setToolTip("Cria a pasta no caminho digitado, se ela ainda não existir")
        self.criar.clicked.connect(self._criar)

        linha = QHBoxLayout(self)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.addWidget(self.campo, 1)
        linha.addWidget(escolher)
        linha.addWidget(self.criar)

        self.campo.textChanged.connect(self._atualizar_botao_criar)
        self._atualizar_botao_criar()

    def _escolher(self) -> None:
        escolhida = QFileDialog.getExistingDirectory(self, self._titulo, self.campo.text())
        if escolhida:
            self.campo.setText(str(Path(escolhida)))

    def _criar(self) -> None:
        caminho = self.campo.text().strip()
        if not caminho:
            return
        try:
            Path(caminho).mkdir(parents=True, exist_ok=True)
        except OSError as erro:
            QMessageBox.warning(self, "Não deu para criar", f"{caminho}\n\n{erro}")
            return
        self._atualizar_botao_criar()

    def _atualizar_botao_criar(self) -> None:
        caminho = self.campo.text().strip()
        existe = bool(caminho) and Path(caminho).is_dir()
        self.criar.setEnabled(bool(caminho) and not existe)
        self.campo.setStyleSheet("" if existe or not caminho else "color: #c0392b;")

    def valor(self) -> str:
        return self.campo.text().strip()

    def definir(self, valor: str) -> None:
        self.campo.setText(valor or "")


class TelaConfiguracoes(QWidget):
    def __init__(self, config: Config | None = None):
        super().__init__()
        self.config = config or Config.carregar()

        self.setWindowTitle("Soulseek Auto Downloader — Configurações")
        self.resize(760, 620)

        abas = QTabWidget()
        abas.addTab(self._aba_pastas(), "📁 Pastas")
        abas.addTab(self._aba_motor(), "🔌 Soulseek")
        abas.addTab(self._aba_spotify(), "🎧 Spotify")
        abas.addTab(self._aba_qualidade(), "⭐ Qualidade")
        abas.addTab(self._aba_requisitos(), "✅ Requisitos")

        self.painel_pendencias = QTextEdit()
        self.painel_pendencias.setReadOnly(True)
        self.painel_pendencias.setMaximumHeight(120)

        salvar = QPushButton("Salvar")
        salvar.setDefault(True)
        salvar.clicked.connect(self._salvar)
        conferir = QPushButton("Conferir pendências")
        conferir.clicked.connect(self._mostrar_pendencias)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.close)

        botoes = QHBoxLayout()
        botoes.addWidget(conferir)
        botoes.addStretch(1)
        botoes.addWidget(salvar)
        botoes.addWidget(fechar)

        fora = QVBoxLayout(self)
        fora.addWidget(abas, 1)
        fora.addWidget(_titulo("O que ainda falta"))
        fora.addWidget(self.painel_pendencias)
        fora.addLayout(botoes)

        self._carregar_na_tela()
        self._mostrar_pendencias()

    # ------------------------------------------------------------------ abas

    def _aba_pastas(self) -> QWidget:
        aba = QWidget()
        corpo = QVBoxLayout(aba)

        corpo.addWidget(_titulo("Playlists baixadas do Spotify"))
        corpo.addWidget(
            _explicacao(
                "Cada playlist vira uma <b>subpasta</b> com o nome dela dentro deste caminho. "
                "Os arquivos ficam sempre nesta máquina — é daqui que eles saem para o pendrive."
            )
        )
        self.mae_playlists = SeletorDePasta("Escolha a pasta das playlists")
        corpo.addWidget(self.mae_playlists)

        corpo.addSpacing(14)

        corpo.addWidget(_titulo("Acervo — buscar versão melhor do que você já tem"))
        corpo.addWidget(
            _explicacao(
                "Quando você aponta uma pasta de músicas suas para o app procurar versões "
                "melhores, o resultado vem para cá — <b>separado</b> das playlists, para não "
                "misturar o que é novo com o que é substituição."
            )
        )
        self.mae_acervo = SeletorDePasta("Escolha a pasta do acervo")
        corpo.addWidget(self.mae_acervo)

        corpo.addSpacing(18)

        grupo = QGroupBox("Pastas compartilhadas  —  obrigatórias na prática")
        interno = QVBoxLayout(grupo)
        interno.addWidget(
            _explicacao(
                "<b>Sim, você precisa de uma pasta de compartilhamento para conseguir baixar.</b><br><br>"
                "O servidor do Soulseek não obriga formalmente — quem obriga são as pessoas. "
                "Enquanto seu cliente anunciar <i>“Nothing Shared”</i>, muitos usuários bloqueiam "
                "você automaticamente, e aí os downloads simplesmente param de completar. "
                "Não é etiqueta: é requisito de funcionamento.<br><br>"
                "Você pode oferecer <b>quantas pastas quiser</b> — acervo de DJ raramente "
                "mora num lugar só. Quanto mais você compartilha, menos gente te bloqueia.<br><br>"
                "Todas elas são gravadas no <b>slskd</b> "
                "(<code>shares.directories</code> no <code>slskd.yml</code>)."
            )
        )
        self.compartilhada = ListaDePastas("Escolha mais uma pasta para compartilhar")
        interno.addWidget(self.compartilhada)

        # A reconfirmação periódica: pasta de compartilhamento é a coisa que apodrece em
        # silêncio. O usuário move o acervo, esvazia a pasta, troca de HD — e nada reclama
        # até os downloads pararem semanas depois, sem erro nenhum.
        self.rotulo_confirmacao = QLabel("")
        self.rotulo_confirmacao.setWordWrap(True)
        botao_confirmar = QPushButton("Confirmar que está tudo certo")
        botao_confirmar.setToolTip(
            f"Pedido a cada {DIAS_ATE_REVALIDAR_COMPARTILHADA} dias de uso"
        )
        botao_confirmar.clicked.connect(self._confirmar_compartilhada)

        linha = QHBoxLayout()
        linha.addWidget(self.rotulo_confirmacao, 1)
        linha.addWidget(botao_confirmar)
        interno.addLayout(linha)

        corpo.addWidget(grupo)
        corpo.addStretch(1)
        return aba

    def _aba_spotify(self) -> QWidget:
        aba = QWidget()
        corpo = QVBoxLayout(aba)

        corpo.addWidget(_titulo("Sua conta do Spotify"))
        corpo.addWidget(
            _explicacao(
                "Crie um app em <b>developer.spotify.com/dashboard</b> e cole aqui. O "
                "<b>Redirect URI</b> do app precisa ser exatamente "
                "<code>http://127.0.0.1:8888/callback</code> — com <code>127.0.0.1</code>, "
                "não <code>localhost</code>, que o Spotify recusa.<br><br>"
                "Desde fevereiro de 2026 a API só entrega o <b>conteúdo</b> das playlists "
                "<b>do próprio usuário logado</b>. Playlist de terceiro é lida pelo navegador, "
                "e para isso você marca a opção na tela principal."
            )
        )

        formulario = QFormLayout()
        self.spotify_id = QLineEdit()
        self.spotify_id.setPlaceholderText("Client ID (é público, pode ficar visível)")
        self.spotify_secret = QLineEdit()
        self.spotify_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.spotify_secret.setPlaceholderText("Client Secret (este é segredo)")
        formulario.addRow("Client ID:", self.spotify_id)
        formulario.addRow("Client Secret:", self.spotify_secret)
        corpo.addLayout(formulario)

        corpo.addSpacing(14)

        grupo = QGroupBox("Sua conta")
        dentro = QVBoxLayout(grupo)

        self.rotulo_conta = QLabel("")
        self.rotulo_conta.setWordWrap(True)
        dentro.addWidget(self.rotulo_conta)

        self.botao_entrar = QPushButton("Entrar com o Spotify")
        self.botao_entrar.clicked.connect(self._entrar_no_spotify)
        self.botao_sair = QPushButton("Sair da conta")
        self.botao_sair.setToolTip("Apaga o acesso guardado para você entrar com outra conta")
        self.botao_sair.clicked.connect(self._sair_do_spotify)

        linha = QHBoxLayout()
        linha.addWidget(self.botao_entrar)
        linha.addWidget(self.botao_sair)
        linha.addStretch(1)
        dentro.addLayout(linha)
        corpo.addWidget(grupo)

        corpo.addSpacing(14)

        liberar = QGroupBox("Deixar outras pessoas usarem o seu app")
        interno = QVBoxLayout(liberar)
        interno.addWidget(
            _explicacao(
                "Um app do Spotify nasce em <b>Development Mode</b>: só contas que você "
                "cadastrar à mão conseguem autorizar, e o teto é de <b>25 pessoas</b>. "
                "Quem não estiver na lista recebe erro ao tentar entrar.<br><br>"
                "O botão abre o painel. Lá, entre no seu app → <b>Settings</b> → "
                "<b>User Management</b> e adicione <b>nome e e-mail</b> da conta Spotify "
                "de cada pessoa.<br><br>"
                "<i>Passar de 25 exige pedir o Extended Quota Mode, que passa por revisão "
                "da Spotify — isso ainda não foi confirmado na fonte.</i>"
            )
        )
        botao_painel = QPushButton("Abrir o painel do Spotify para cadastrar usuários")
        botao_painel.clicked.connect(self._abrir_painel_do_spotify)
        interno.addWidget(botao_painel, alignment=Qt.AlignmentFlag.AlignLeft)
        corpo.addWidget(liberar)

        corpo.addStretch(1)
        self._atualizar_conta()
        return aba

    # ------------------------------------------------------------- slskd

    def _atualizar_slskd_yml(self) -> None:
        caminho = slskd_config.achar_yml()
        if caminho is None:
            self.rotulo_slskd_yml.setText("❌ slskd.yml não encontrado — o slskd está instalado?")
            return

        usuario = slskd_config.ler_valor("username", caminho)
        faltam = slskd_config.pendencias(caminho)
        if faltam:
            self.rotulo_slskd_yml.setText(f"⚠️ ainda falta preencher: {', '.join(faltam)}")
        else:
            self.rotulo_slskd_yml.setText(f"✅ configurado como <b>{usuario}</b>")

        if usuario and not self.slsk_usuario.text():
            self.slsk_usuario.setText(usuario)

    def _gravar_no_slskd_yml(self) -> None:
        """Grava usuário, senha e pasta compartilhada no slskd.yml.

        Campo em branco **não apaga** o que já está lá — a senha chega aqui sempre
        vazia (o campo é mascarado), e apagá-la a cada gravação de rotina seria o
        mesmo acidente que já custou o token do Spotify neste projeto.
        """
        pasta = self.compartilhada.valor()
        if pasta and not Path(pasta).is_dir():
            QMessageBox.warning(
                self,
                "A pasta compartilhada não existe",
                f"{pasta}\n\nEscolha uma que exista na aba 📁 Pastas.",
            )
            return

        try:
            onde = slskd_config.gravar(
                usuario=self.slsk_usuario.text(),
                senha=self.slsk_senha.text(),
                pastas=pastas,
            )
        except (FileNotFoundError, OSError) as erro:
            QMessageBox.warning(self, "Não consegui gravar", str(erro))
            return

        self.slsk_senha.clear()
        self._atualizar_slskd_yml()
        QMessageBox.information(
            self,
            "Gravado",
            f"Credenciais gravadas em:\n{onde}\n\n"
            "Desligue e ligue o motor na aba 🔌 Motor para ele ler as credenciais novas.",
        )

    # ----------------------------------------------------------- Spotify

    def _atualizar_conta(self) -> None:
        if self.config.spotify_refresh_token:
            nome = self.config.spotify_nome_da_conta or "(conta conectada)"
            self.rotulo_conta.setText(f"✅ Entrou como <b>{nome}</b>")
            self.botao_entrar.setText("Entrar com outra conta")
            self.botao_sair.setEnabled(True)
        else:
            self.rotulo_conta.setText("⬜ Nenhuma conta conectada.")
            self.botao_entrar.setText("Entrar com o Spotify")
            self.botao_sair.setEnabled(False)

    def _abrir_painel_do_spotify(self) -> None:
        webbrowser.open("https://developer.spotify.com/dashboard")

    def _sair_do_spotify(self) -> None:
        """Apaga o acesso guardado — é o que permite entrar com outra conta.

        Usa `esquecer_segredos()`, o único caminho que apaga segredo de verdade: a
        gravação comum protege segredos justamente para não perdê-los por acidente.
        """
        confirmacao = QMessageBox.question(
            self,
            "Sair da conta do Spotify",
            "Isso apaga o acesso guardado desta máquina.\n\n"
            "O Client ID continua aqui — só a conta sai. Continuar?",
        )
        if confirmacao != QMessageBox.StandardButton.Yes:
            return

        guardados = (self.config.slskd_api_key, self.config.spotify_client_secret)
        self.config.spotify_refresh_token = ""
        self.config.spotify_nome_da_conta = ""
        self.config.esquecer_segredos()
        # `esquecer_segredos` limpa TODOS os segredos; os outros voltam na hora.
        self.config.slskd_api_key, self.config.spotify_client_secret = guardados
        self.config.salvar()

        self._atualizar_conta()
        self._mostrar_pendencias()

    def _entrar_no_spotify(self) -> None:
        client_id = self.spotify_id.text().strip()
        if not client_id:
            QMessageBox.warning(
                self,
                "Falta o Client ID",
                "Cole o Client ID do seu app do Spotify antes de entrar.",
            )
            return

        self.config.spotify_client_id = client_id
        self.botao_entrar.setEnabled(False)
        self.rotulo_conta.setText("⏳ Abrindo o navegador... autorize por lá e volte aqui.")

        from trabalho import TarefaDeEntrada

        self._entrada = TarefaDeEntrada(client_id)
        self._entrada.terminou.connect(self._terminou_a_entrada)
        self._entrada.start()

    def _terminou_a_entrada(self, deu_certo: bool, recado: str) -> None:
        self.botao_entrar.setEnabled(True)
        if not deu_certo:
            self.rotulo_conta.setText(f"❌ {recado}")
            return

        self.config.spotify_refresh_token = self._entrada.refresh_token
        self.config.spotify_nome_da_conta = recado
        self.config.salvar()
        self._atualizar_conta()
        self._mostrar_pendencias()

    def _impedimento_para_confirmar(self) -> str:
        """Motivo de não dar para confirmar a pasta, ou `""` se dá.

        Separado do clique **de propósito**: diálogo modal trava esperando clique, e
        função que decide e exibe diálogo ao mesmo tempo não se testa — o teste fica
        pendurado para sempre no `QMessageBox`. A decisão fica aqui, pura; o aviso fica
        no handler.
        """
        pasta = self.compartilhada.valor()
        if not pasta:
            return "Escolha uma pasta antes de confirmar."
        if not Path(pasta).is_dir():
            return (
                f"Essa pasta não existe:\n{pasta}\n\n"
                "Confirmar uma pasta que não existe seria pior que não perguntar nada — "
                "você ficaria achando que está compartilhando."
            )
        return ""

    def _confirmar_compartilhada(self) -> bool:
        impedimento = self._impedimento_para_confirmar()
        if impedimento:
            QMessageBox.warning(self, "Confira a pasta antes", impedimento)
            return False

        self.config.confirmar_compartilhada()
        self._atualizar_confirmacao()
        self._mostrar_pendencias()
        return True

    def _atualizar_confirmacao(self) -> None:
        dias = self.config.dias_desde_confirmacao()
        if dias is None:
            texto = "⬜ Nunca confirmada."
        elif self.config.precisa_revalidar_compartilhada():
            texto = f"⚠️ Confirmada há {dias} dias — passou do prazo."
        elif dias == 0:
            texto = "✅ Confirmada hoje."
        else:
            texto = f"✅ Confirmada há {dias} dia(s)."
        self.rotulo_confirmacao.setText(texto)

    def _aba_motor(self) -> QWidget:
        aba = QWidget()
        corpo = QVBoxLayout(aba)

        corpo.addWidget(_titulo("Sua conta do Soulseek"))
        corpo.addWidget(
            _explicacao(
                "É com esta conta que o motor entra na rede. Ela fica no "
                "<code>slskd.yml</code>, e este painel grava lá — você não precisa "
                "abrir o arquivo.<br><br>"
                "A <b>pasta compartilhada</b> é a da aba 📁 Pastas: ela é gravada aqui "
                "junto, porque o slskd precisa dela para entrar."
            )
        )

        conta = QFormLayout()
        self.slsk_usuario = QLineEdit()
        self.slsk_usuario.setPlaceholderText("seu usuário do Soulseek")
        self.slsk_senha = QLineEdit()
        self.slsk_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.slsk_senha.setPlaceholderText("deixe em branco para manter a atual")
        conta.addRow("Usuário:", self.slsk_usuario)
        conta.addRow("Senha:", self.slsk_senha)
        corpo.addLayout(conta)

        self.rotulo_slskd_yml = QLabel("")
        self.rotulo_slskd_yml.setWordWrap(True)
        botao_gravar = QPushButton("Gravar no slskd.yml")
        botao_gravar.clicked.connect(self._gravar_no_slskd_yml)

        linha_conta = QHBoxLayout()
        linha_conta.addWidget(botao_gravar)
        linha_conta.addWidget(self.rotulo_slskd_yml, 1)
        corpo.addLayout(linha_conta)

        corpo.addWidget(
            _explicacao(
                "⚠️ Depois de gravar, <b>desligue e ligue o motor</b> na aba 🔌 Motor — "
                "o slskd lê as credenciais ao iniciar."
            )
        )

        corpo.addSpacing(16)
        corpo.addWidget(_titulo("Ligação com o slskd"))
        corpo.addWidget(
            _explicacao(
                "O slskd é o cliente moderno da rede Soulseek, que roda como serviço e "
                "conversa por HTTP. A chave de API fica no <code>slskd.yml</code>, em "
                "<code>web.authentication.api_keys</code>."
            )
        )

        formulario = QFormLayout()
        self.slskd_url = QLineEdit()
        self.slskd_url.setPlaceholderText("http://localhost:5030")
        self.slskd_chave = QLineEdit()
        self.slskd_chave.setEchoMode(QLineEdit.EchoMode.Password)
        self.slskd_chave.setPlaceholderText("a chave do slskd.yml")
        formulario.addRow("Endereço:", self.slskd_url)
        formulario.addRow("Chave de API:", self.slskd_chave)
        corpo.addLayout(formulario)

        testar = QPushButton("Testar conexão")
        testar.clicked.connect(self._testar_slskd)
        self.resultado_teste = QLabel("")
        self.resultado_teste.setWordWrap(True)

        linha = QHBoxLayout()
        linha.addWidget(testar)
        linha.addWidget(self.resultado_teste, 1)
        corpo.addLayout(linha)

        corpo.addSpacing(12)
        aviso = QFrame()
        aviso.setFrameShape(QFrame.Shape.StyledPanel)
        dentro = QVBoxLayout(aviso)
        dentro.addWidget(
            _explicacao(
                "⚠️ <b>Uma conta, um cliente por vez.</b> O servidor do Soulseek derruba a "
                "sessão antiga quando a mesma conta entra de novo. Se você deixar o slskd e o "
                "SoulseekQt antigo ligados juntos com a mesma conta, eles vão se expulsar em "
                "loop. Use duas contas, ou alterne."
            )
        )
        corpo.addWidget(aviso)

        corpo.addStretch(1)
        return aba

    def _aba_qualidade(self) -> QWidget:
        aba = QWidget()
        corpo = QVBoxLayout(aba)

        corpo.addWidget(_titulo("Formatos que valem a pena baixar"))
        corpo.addWidget(_explicacao("O que não estiver marcado é descartado com motivo escrito."))

        self.caixas_formato: dict[str, QCheckBox] = {}

        sem_perda = QGroupBox("Sem perda")
        linha_sp = QHBoxLayout(sem_perda)
        for chave, rotulo in FORMATOS_SEM_PERDA:
            caixa = QCheckBox(rotulo)
            self.caixas_formato[chave] = caixa
            linha_sp.addWidget(caixa)
        linha_sp.addStretch(1)
        corpo.addWidget(sem_perda)

        com_perda = QGroupBox("Com perda")
        linha_cp = QHBoxLayout(com_perda)
        for chave, rotulo in FORMATOS_COM_PERDA:
            caixa = QCheckBox(rotulo)
            self.caixas_formato[chave] = caixa
            linha_cp.addWidget(caixa)
        linha_cp.addStretch(1)
        corpo.addWidget(com_perda)

        formulario = QFormLayout()
        self.min_mp3 = QSpinBox()
        self.min_mp3.setRange(64, 320)
        self.min_mp3.setSuffix(" kbps")
        self.min_aac = QSpinBox()
        self.min_aac.setRange(64, 320)
        self.min_aac.setSuffix(" kbps")
        self.min_aac.setToolTip("AAC rende mais por bit: 256 equivale, na prática, a 320 de MP3")
        self.quantidade = QSpinBox()
        self.quantidade.setRange(1, 5)
        self.quantidade.setToolTip(
            "Quantas versões baixar por música, para comparar os espectrogramas depois. "
            "O app prefere usuários diferentes — duas do mesmo usuário caem juntas se ele sair."
        )
        formulario.addRow("Mínimo para MP3:", self.min_mp3)
        formulario.addRow("Mínimo para AAC/M4A:", self.min_aac)
        formulario.addRow("Versões por música:", self.quantidade)
        corpo.addLayout(formulario)

        corpo.addSpacing(12)
        corpo.addWidget(_titulo("Limite de buscas da rede"))
        corpo.addWidget(
            _explicacao(
                "O servidor <b>bane por 30 minutos</b> quem busca demais. O padrão "
                "(34 a cada 220 s) é o número usado pelas ferramentas consolidadas — "
                "aumentar é pedir para ser banido no meio de uma playlist."
            )
        )
        limites = QFormLayout()
        self.buscas_janela = QSpinBox()
        self.buscas_janela.setRange(1, 34)
        self.janela_s = QSpinBox()
        self.janela_s.setRange(220, 3600)
        self.janela_s.setSuffix(" s")
        limites.addRow("Buscas por janela:", self.buscas_janela)
        limites.addRow("Tamanho da janela:", self.janela_s)
        corpo.addLayout(limites)

        corpo.addStretch(1)
        return aba

    def _aba_requisitos(self) -> QWidget:
        aba = QWidget()
        corpo = QVBoxLayout(aba)

        corpo.addWidget(_titulo("O que a máquina já tem"))
        corpo.addWidget(
            _explicacao(
                "Estes são programas de sistema, instalados à parte — o app não os carrega dentro de si."
            )
        )

        self.painel_requisitos = QTextEdit()
        self.painel_requisitos.setReadOnly(True)
        corpo.addWidget(self.painel_requisitos, 1)

        reconferir = QPushButton("Conferir de novo")
        reconferir.clicked.connect(self._atualizar_requisitos)
        corpo.addWidget(reconferir, alignment=Qt.AlignmentFlag.AlignLeft)

        self._atualizar_requisitos()
        return aba

    # --------------------------------------------------------------- ações

    def _atualizar_requisitos(self) -> None:
        ffmpeg = sistema.encontrar_ffmpeg()
        ffprobe = sistema.encontrar_ffprobe()

        def marca(achado) -> str:
            return f"✅ {achado}" if achado else "⬜ não encontrado"

        linhas = [
            f"<b>Sistema:</b> {sistema.nome_do_sistema()}",
            "",
            f"<b>ffmpeg</b> (espectrograma) — {marca(ffmpeg)}",
            f"<b>ffprobe</b> (tags e especificações) — {marca(ffprobe)}",
            "",
            f"<b>Configurações gravadas em:</b><br><code>{Config.caminho_padrao()}</code>",
            "",
            f"<b>Pasta de dados do app:</b><br><code>{sistema.pasta_de_dados()}</code>",
        ]
        if not ffmpeg:
            linhas += [
                "",
                "Sem o ffmpeg o app ainda lê nomes e busca, mas <b>não gera espectrograma</b> "
                "e não mede a frequência de corte — que é o que denuncia o “MP3 320” falso.",
            ]
        self.painel_requisitos.setHtml("<br>".join(linhas))

    def _testar_slskd(self) -> None:
        url = self.slskd_url.text().strip() or "http://localhost:5030"
        chave = self.slskd_chave.text().strip()
        alvo = f"{url.rstrip('/')}/api/v0/application"

        pedido = urllib.request.Request(alvo, headers={"X-API-Key": chave})
        try:
            with urllib.request.urlopen(pedido, timeout=5) as resposta:
                dados = json.loads(resposta.read().decode("utf-8"))
            estado = dados.get("server", {}).get("state", "?")
            self.resultado_teste.setText(f"✅ slskd respondeu. Servidor: {estado}")
            self.resultado_teste.setStyleSheet("color: #1e8449;")
        except urllib.error.HTTPError as erro:
            recado = "chave de API recusada" if erro.code in (401, 403) else f"HTTP {erro.code}"
            self.resultado_teste.setText(f"❌ {recado}")
            self.resultado_teste.setStyleSheet("color: #c0392b;")
        except Exception:
            self.resultado_teste.setText(
                f"❌ não respondeu em {alvo} — o slskd está instalado e rodando?"
            )
            self.resultado_teste.setStyleSheet("color: #c0392b;")

    def _carregar_na_tela(self) -> None:
        c = self.config
        padrao = sistema.pasta_de_musicas_padrao()
        self.mae_playlists.definir(c.pasta_mae_playlists or str(padrao / "Playlists"))
        self.mae_acervo.definir(c.pasta_mae_acervo or str(padrao / "Acervo"))
        self.compartilhada.definir(c.todas_as_compartilhadas())
        self._atualizar_confirmacao()
        self._atualizar_slskd_yml()
        self.spotify_id.setText(c.spotify_client_id)
        self.spotify_secret.setText(c.spotify_client_secret)
        self.slskd_url.setText(c.slskd_url)
        self.slskd_chave.setText(c.slskd_api_key)
        for chave, caixa in self.caixas_formato.items():
            caixa.setChecked(chave in c.formatos_aceitos)
        self.min_mp3.setValue(c.minimo_mp3_kbps)
        self.min_aac.setValue(c.minimo_aac_kbps)
        self.quantidade.setValue(c.quantidade_por_faixa)
        self.buscas_janela.setValue(c.buscas_por_janela)
        self.janela_s.setValue(c.janela_de_buscas_s)

    def _recolher_da_tela(self) -> Config:
        c = self.config
        c.pasta_mae_playlists = self.mae_playlists.valor()
        c.pasta_mae_acervo = self.mae_acervo.valor()
        c.definir_compartilhadas(self.compartilhada.valores())
        c.spotify_client_id = self.spotify_id.text().strip()
        c.spotify_client_secret = self.spotify_secret.text().strip()
        c.slskd_url = self.slskd_url.text().strip()
        c.slskd_api_key = self.slskd_chave.text().strip()
        c.formatos_aceitos = [k for k, caixa in self.caixas_formato.items() if caixa.isChecked()]
        c.minimo_mp3_kbps = self.min_mp3.value()
        c.minimo_aac_kbps = self.min_aac.value()
        c.quantidade_por_faixa = self.quantidade.value()
        c.buscas_por_janela = self.buscas_janela.value()
        c.janela_de_buscas_s = self.janela_s.value()
        return c

    def _mostrar_pendencias(self) -> None:
        pendencias = self._recolher_da_tela().problemas()
        if not pendencias:
            self.painel_pendencias.setHtml(
                "✅ <b>Configuração completa.</b> Falta o slskd instalado e rodando para "
                "o app conseguir buscar de verdade."
            )
            return
        itens = "".join(f"<li>{p}</li>" for p in pendencias)
        self.painel_pendencias.setHtml(f"<ul style='margin-left:-20px'>{itens}</ul>")

    def _salvar(self) -> None:
        onde = self._recolher_da_tela().salvar()
        self._mostrar_pendencias()
        QMessageBox.information(self, "Salvo", f"Configurações gravadas em:\n\n{onde}")


def abrir() -> int:
    app = QApplication.instance() or QApplication([])
    tela = TelaConfiguracoes()
    tela.show()
    return app.exec()
