"""A janela principal — o app inteiro, sem terminal nenhum.

Pedido direto: *"quero tudo isso que estamos fazendo no terminal funcionando dentro da
interface, não quero mais nada no terminal. **tudo mesmo**, incluindo o motor do
software sem necessitar de um terminal aberto"*.

Três abas:

* **🎵 Baixar** — cola o link da playlist (ou de uma música, ou o nome escrito à mão),
  escolhe o formato que vai tocar, e acompanha.
* **🔌 Motor** — liga e desliga o slskd em segundo plano, mostra o estado e o log.
* **⚙️ Configurações** — a tela que já existia, embutida aqui.

O trabalho pesado roda em `trabalho.py`, fora desta thread. Qt desenha numa thread só:
qualquer coisa demorada feita aqui congela a janela, e aqui "demorado" é a regra.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import Config
from motor import EstadoDoMotor, Motor
from politica import Foco
from tela_configuracoes import TelaConfiguracoes
from trabalho import Andamento, TarefaDeDownload


class JanelaPrincipal(QMainWindow):
    def __init__(self, config: Config | None = None):
        super().__init__()
        self.config = config or Config.carregar()
        self.motor = Motor()
        self.tarefa: TarefaDeDownload | None = None

        self.setWindowTitle("Soulseek Auto Downloader — by Flowers")
        self.resize(900, 720)

        self.abas = QTabWidget()
        self.abas.addTab(self._aba_baixar(), "🎵 Baixar")
        self.abas.addTab(self._aba_motor(), "🔌 Motor")
        self.tela_config = TelaConfiguracoes(self.config)
        self.abas.addTab(self.tela_config, "⚙️ Configurações")
        self.setCentralWidget(self.abas)

        self.statusBar().showMessage("Pronto.")

        # O estado do motor precisa de relógio próprio. Sem isto, o indicador congela
        # no instante do clique em "Ligar" — quando a porta ainda NÃO abriu — e fica
        # amarelo para sempre, mesmo com o slskd já no ar e trabalhando. Aconteceu: o
        # usuário esperou dez minutos olhando um amarelo que era só tela velha.
        self.relogio = QTimer(self)
        self.relogio.setInterval(2000)
        self.relogio.timeout.connect(self._atualizar_motor)
        self.relogio.start()
        self._atualizar_motor()

    # ------------------------------------------------------------- baixar

    def _aba_baixar(self) -> QWidget:
        aba = QWidget()
        corpo = QVBoxLayout(aba)

        corpo.addWidget(QLabel("<b>Cole aqui</b>"))
        explicacao = QLabel(
            "Link de <b>playlist</b> do Spotify, link de <b>música</b>, ou o "
            "<b>nome escrito à mão</b> — com todo acento, apóstrofo e hífen que a "
            "música realmente tem. Não limpe nada: é da grafia completa que saem as "
            "variantes de busca."
        )
        explicacao.setWordWrap(True)
        explicacao.setStyleSheet("color: palette(mid);")
        corpo.addWidget(explicacao)

        self.campo_entrada = QLineEdit()
        self.campo_entrada.setPlaceholderText(
            "https://open.spotify.com/playlist/...   ou   Djavan - Flor de Lis"
        )
        self.campo_entrada.returnPressed.connect(self._comecar)
        corpo.addWidget(self.campo_entrada)

        linha = QHBoxLayout()
        linha.addWidget(QLabel("Formato que você vai tocar:"))
        self.escolha_foco = QComboBox()
        self.escolha_foco.addItem("Sem perda (AIFF / WAV / FLAC)", Foco.SEM_PERDA)
        self.escolha_foco.addItem("MP3 320", Foco.MP3)
        self.escolha_foco.setToolTip(
            "A segunda cópia vai para este formato. Tocar sempre o mesmo evita que a "
            "diferença de qualidade apareça no meio do set."
        )
        linha.addWidget(self.escolha_foco)
        linha.addStretch(1)

        self.botao_baixar = QPushButton("Baixar")
        self.botao_baixar.setDefault(True)
        self.botao_baixar.clicked.connect(self._comecar)
        self.botao_parar = QPushButton("Parar")
        self.botao_parar.setEnabled(False)
        self.botao_parar.clicked.connect(self._parar)
        linha.addWidget(self.botao_baixar)
        linha.addWidget(self.botao_parar)
        corpo.addLayout(linha)

        self.barra = QProgressBar()
        self.barra.setTextVisible(True)
        corpo.addWidget(self.barra)

        self.rotulo_faixa = QLabel("")
        self.rotulo_faixa.setWordWrap(True)
        corpo.addWidget(self.rotulo_faixa)

        # O que está baixando AGORA, com barra por arquivo. Fica acima das listas
        # porque é a informação que muda a cada segundo — é onde o olho vai.
        self.caixa_baixando = QGroupBox("⬇ Baixando agora")
        self.area_baixando = QVBoxLayout(self.caixa_baixando)
        self.area_baixando.setContentsMargins(10, 6, 10, 6)
        self.rotulo_ocioso = QLabel("nada baixando no momento")
        self.rotulo_ocioso.setStyleSheet("color: palette(mid);")
        self.area_baixando.addWidget(self.rotulo_ocioso)
        corpo.addWidget(self.caixa_baixando)
        self._barras: dict[str, tuple[QLabel, QProgressBar, QWidget]] = {}

        listas = QHBoxLayout()
        self.lista_afazer = self._lista("📋 A fazer", listas)
        self.lista_baixadas = self._lista("✅ Baixadas", listas)
        self.lista_presas = self._lista("⏳ Presas na fila", listas)
        self.lista_faltaram = self._lista("❌ Não vieram", listas)
        corpo.addLayout(listas, 1)

        return aba

    def _lista(self, titulo: str, onde: QHBoxLayout) -> QListWidget:
        caixa = QGroupBox(titulo)
        dentro = QVBoxLayout(caixa)
        lista = QListWidget()
        dentro.addWidget(lista)
        onde.addWidget(caixa)
        return lista

    # -------------------------------------------------------------- motor

    def _aba_motor(self) -> QWidget:
        aba = QWidget()
        corpo = QVBoxLayout(aba)

        explicacao = QLabel(
            "O <b>slskd</b> é o motor que fala com a rede Soulseek. Ele roda aqui em "
            "segundo plano — <b>sem janela de terminal</b>.<br><br>"
            "⏳ A <b>primeira</b> vez demora: ele varre a pasta compartilhada inteira "
            "antes de atender. Parece travado e não está."
        )
        explicacao.setWordWrap(True)
        corpo.addWidget(explicacao)

        self.rotulo_motor = QLabel("")
        self.rotulo_motor.setStyleSheet("font-size: 15px; font-weight: 600;")
        corpo.addWidget(self.rotulo_motor)

        linha = QHBoxLayout()
        self.botao_ligar = QPushButton("Ligar o motor")
        self.botao_ligar.clicked.connect(self._ligar_motor)
        self.botao_desligar = QPushButton("Desligar")
        self.botao_desligar.clicked.connect(self._desligar_motor)
        botao_conferir = QPushButton("Conferir")
        botao_conferir.clicked.connect(self._atualizar_motor)
        linha.addWidget(self.botao_ligar)
        linha.addWidget(self.botao_desligar)
        linha.addWidget(botao_conferir)
        linha.addStretch(1)
        corpo.addLayout(linha)

        corpo.addWidget(QLabel("<b>Log do motor</b>"))
        self.log_motor = QTextEdit()
        self.log_motor.setReadOnly(True)
        corpo.addWidget(self.log_motor, 1)

        return aba

    def _atualizar_motor(self) -> None:
        situacao = self.motor.situacao()
        icones = {
            EstadoDoMotor.RODANDO: "🟢",
            EstadoDoMotor.DE_FORA: "🟢",
            EstadoDoMotor.SUBINDO: "🟡",
            EstadoDoMotor.PARADO: "⚪",
            EstadoDoMotor.FALHOU: "🔴",
        }
        usuario = self.motor.usuario_logado()
        extra = f" — logado como {usuario}" if usuario else ""
        self.rotulo_motor.setText(f"{icones.get(situacao.estado, '⚪')} {situacao}{extra}")

        self.botao_ligar.setEnabled(not situacao.atende)
        # Só derrubamos o que nós subimos: um slskd que o usuário abriu à mão não é
        # nosso para matar.
        self.botao_desligar.setEnabled(self.motor.fomos_nos)

        if self.motor.log:
            self.log_motor.setPlainText("\n".join(self.motor.log_recente(60)))

    def _ligar_motor(self) -> None:
        situacao = self.motor.ligar()
        self._atualizar_motor()
        if situacao.estado is EstadoDoMotor.FALHOU:
            QMessageBox.warning(self, "Não consegui ligar o motor", situacao.detalhe)

    def _desligar_motor(self) -> None:
        self.motor.desligar()
        self._atualizar_motor()

    # ------------------------------------------------------------ baixar

    def _impedimento_para_baixar(self) -> str:
        """Motivo de não dar para começar, ou `""` se dá."""
        if self.tarefa is not None and self.tarefa.isRunning():
            return "Já tem um download em andamento."
        if not self.campo_entrada.text().strip():
            return "Cole um link de playlist, um link de música, ou o nome de uma música."
        # Confere que a pasta EXISTE, não só que o campo está preenchido: a tela de
        # Configurações sugere um caminho padrão no campo, e um caminho sugerido e
        # nunca criado passaria pelo teste de "está vazio?" e quebraria na hora de
        # gravar o primeiro arquivo.
        pasta = self.config.pasta_mae_playlists.strip()
        if not pasta or not Path(pasta).is_dir():
            return (
                "Escolha a pasta das playlists em ⚙️ Configurações — e crie-a, se "
                "ainda não existir (há um botão 'Criar' ao lado do campo)."
            )
        if not self.motor.situacao().atende:
            return "O motor não está no ar. Ligue-o na aba 🔌 Motor."
        return ""

    def _comecar(self) -> None:
        impedimento = self._impedimento_para_baixar()
        if impedimento:
            QMessageBox.information(self, "Falta uma coisa", impedimento)
            return

        for lista in (
            self.lista_afazer,
            self.lista_baixadas,
            self.lista_presas,
            self.lista_faltaram,
        ):
            lista.clear()
        self.barra.setValue(0)

        self.config = self.tela_config.config
        self.tarefa = TarefaDeDownload(
            self.config,
            self.campo_entrada.text(),
            Foco(self.escolha_foco.currentData()),
            motor=self.motor,
        )
        self.tarefa.playlist_lida.connect(self._leu_a_playlist)
        self.tarefa.progrediu.connect(self._andou)
        self.tarefa.terminou.connect(self._acabou)
        self.tarefa.falhou.connect(self._deu_errado)
        self.tarefa.start()

        self.botao_baixar.setEnabled(False)
        self.botao_parar.setEnabled(True)
        self.statusBar().showMessage("Lendo a entrada...")

    def _parar(self) -> None:
        if self.tarefa:
            self.tarefa.pedir_para_parar()
            self.statusBar().showMessage("Vou parar depois desta faixa...")

    def _andou(self, andamento: Andamento) -> None:
        self.barra.setMaximum(max(1, andamento.total))
        self.barra.setValue(andamento.indice)
        self.rotulo_faixa.setText(
            f"[{andamento.indice}/{andamento.total}] {andamento.faixa}"
        )
        # A faixa da vez sai da lista "a fazer": o que sobra ali e o que falta.
        while self.lista_afazer.count() > max(0, andamento.total - andamento.indice):
            self.lista_afazer.takeItem(0)
        self._desenhar_barras(andamento.baixando)
        self._encher(self.lista_baixadas, andamento.baixadas)
        self._encher(self.lista_presas, andamento.presas)
        self._encher(self.lista_faltaram, andamento.nao_vieram + andamento.erros)
        self.statusBar().showMessage(
            f"{len(andamento.baixadas)} baixada(s) · {andamento.porcentagem}%"
        )

    def _leu_a_playlist(self, nome: str, faixas: list) -> None:
        """Mostra a lista inteira ANTES de comecar.

        Ate aqui a janela so dizia qual faixa estava na vez — o usuario nao via o que
        o app ia fazer, nem quantas faltavam de verdade.
        """
        self.lista_afazer.clear()
        self.lista_afazer.addItems(faixas)
        self.abas.setTabText(0, f"🎵 Baixar ({len(faixas)})")
        self.statusBar().showMessage(f"{nome} — {len(faixas)} faixa(s)")

    def _desenhar_barras(self, baixando: list) -> None:
        """Uma linha com nome e barra de % para cada arquivo em transferência.

        As barras são **reaproveitadas** entre as atualizações: criar e destruir
        widgets a cada segundo, por horas, faria a janela piscar e vazar memória. Só
        o valor muda; a linha só nasce quando o arquivo aparece e só morre quando ele
        termina.
        """
        atuais = {nome: pct for nome, pct in baixando}

        for nome in list(self._barras):
            if nome not in atuais:
                _rotulo, _barra, linha = self._barras.pop(nome)
                linha.setParent(None)
                linha.deleteLater()

        for nome, pct in atuais.items():
            if nome not in self._barras:
                linha = QWidget()
                dentro = QHBoxLayout(linha)
                dentro.setContentsMargins(0, 2, 0, 2)

                curto = nome if len(nome) <= 52 else nome[:49] + "..."
                rotulo = QLabel(curto)
                rotulo.setToolTip(nome)
                rotulo.setMinimumWidth(340)

                barra = QProgressBar()
                barra.setRange(0, 100)
                barra.setFormat("%p%")
                barra.setMaximumHeight(16)

                dentro.addWidget(rotulo)
                dentro.addWidget(barra, 1)
                self.area_baixando.addWidget(linha)
                self._barras[nome] = (rotulo, barra, linha)

            self._barras[nome][1].setValue(pct)

        self.rotulo_ocioso.setVisible(not self._barras)

    @staticmethod
    def _encher(lista: QListWidget, itens: list[str]) -> None:
        """Deixa a lista igual a `itens`, mexendo só no que mudou.

        Antes isto só acrescentava o fim, o que valia enquanto o relatório apenas
        crescia. Agora ele é refeito a cada volta, e uma faixa **sai** das presas
        quando o download termina: uma lista que só cresce mostraria a mesma faixa em
        duas colunas, e repetida quando a ordem mudasse.

        Não dá para usar `clear()`: redesenhar tudo a cada segundo, por horas, faria a
        lista piscar e perder a posição da rolagem. Então o item que já existe tem só o
        texto trocado, e sobra/falta é ajustada na ponta.
        """
        for i, texto in enumerate(itens):
            item = lista.item(i)
            if item is None:
                lista.addItem(texto)
            elif item.text() != texto:
                item.setText(texto)

        while lista.count() > len(itens):
            lista.takeItem(lista.count() - 1)

    def _acabou(self, andamento: Andamento, destino: str) -> None:
        self._liberar_botoes()
        self._andou(andamento)
        self.statusBar().showMessage(f"Terminou — {len(andamento.baixadas)} arquivo(s)")
        QMessageBox.information(
            self,
            "Terminou",
            f"{len(andamento.baixadas)} arquivo(s) em:\n{destino}\n\n"
            f"⏳ {len(andamento.presas)} presa(s) na fila\n"
            f"❌ {len(andamento.nao_vieram)} não vieram\n"
            f"💥 {len(andamento.erros)} deram erro",
        )

    def _deu_errado(self, recado: str) -> None:
        self._liberar_botoes()
        self.statusBar().showMessage("Não deu.")
        QMessageBox.warning(self, "Não deu", recado)

    def _liberar_botoes(self) -> None:
        self.botao_baixar.setEnabled(True)
        self.botao_parar.setEnabled(False)

    # ------------------------------------------------------------ fechar

    def closeEvent(self, evento) -> None:  # noqa: N802 - nome exigido pelo Qt
        """Ao fechar a janela, derruba o que subimos — nada de processo órfão."""
        self.relogio.stop()  # senão dispara sobre widget já destruído
        if self.tarefa is not None and self.tarefa.isRunning():
            self.tarefa.pedir_para_parar()
            self.tarefa.wait(5000)
        self.motor.desligar()
        evento.accept()


def abrir() -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    janela = JanelaPrincipal()
    janela.show()
    return app.exec()
