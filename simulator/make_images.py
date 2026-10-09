#!/usr/bin/env python3
"""
simulator/make_images.py
Draws the FICTITIOUS "screenshots" used as attachments in demo mode
(simulator/images/*.png). Everything in them is made up; the on-screen
text is in Portuguese because the fictitious company is Brazilian.

Only needs to run again to change the images — the PNGs are committed, so
demo mode itself does not depend on Pillow.

    pip install -r requirements-dev.txt
    python simulator/make_images.py
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
WIDTH, HEIGHT = 1200, 700

BACKGROUND = (245, 247, 250)
WHITE = (255, 255, 255)
GRAY = (120, 128, 140)
LIGHT_GRAY = (225, 229, 235)
TEXT = (40, 44, 52)
NAVY = (31, 56, 100)
BLUE = (59, 130, 246)
GREEN = (46, 125, 50)
RED = (198, 40, 40)
AMBER = (178, 106, 0)


def font(size: int, bold: bool = False):
    # Common system fonts; if none is available, Pillow's built-in font.
    names = ["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def window(title: str, address: str | None = None, dark: bool = False):
    """Window/browser frame; returns (image, draw, content_top_y)."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (30, 30, 30) if dark else BACKGROUND)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, WIDTH, 40], fill=(222, 226, 232))
    for i, color in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        d.ellipse([16 + i * 24, 13, 30 + i * 24, 27], fill=color)
    d.text((100, 10), title, font=font(15), fill=TEXT)
    y = 40
    if address:
        d.rectangle([0, 40, WIDTH, 84], fill=(240, 242, 245))
        d.rounded_rectangle([90, 48, WIDTH - 40, 76], radius=14, fill=WHITE, outline=LIGHT_GRAY)
        d.text((110, 52), address, font=font(15), fill=GRAY)
        y = 84
    return img, d, y


def app_bar(d, y, app_name: str, color=NAVY):
    d.rectangle([0, y, WIDTH, y + 56], fill=color)
    d.text((28, y + 14), app_name, font=font(22, True), fill=WHITE)
    d.text((WIDTH - 260, y + 18), "Empresa Exemplo", font=font(16), fill=(210, 220, 240))
    return y + 56


def button(d, x, y, text, color=BLUE, width=180):
    d.rounded_rectangle([x, y, x + width, y + 42], radius=8, fill=color)
    d.text((x + 18, y + 10), text, font=font(17, True), fill=WHITE)


def input_field(d, x, y, label, value, width=420):
    d.text((x, y), label, font=font(15), fill=GRAY)
    d.rounded_rectangle([x, y + 24, x + width, y + 62], radius=6, fill=WHITE, outline=LIGHT_GRAY)
    d.text((x + 12, y + 33), value, font=font(17), fill=TEXT)


def alert(d, x, y, text, color, width=520):
    d.rounded_rectangle([x, y, x + width, y + 52], radius=6, fill=tuple(min(255, c + 170) for c in color), outline=color)
    d.rectangle([x, y, x + 6, y + 52], fill=color)
    d.text((x + 20, y + 14), text, font=font(17, True), fill=color)


def table(d, x, y, columns, rows, widths, highlight_col=None):
    d.rectangle([x, y, x + sum(widths), y + 40], fill=NAVY)
    cx = x
    for col, w in zip(columns, widths):
        d.text((cx + 12, y + 10), col, font=font(16, True), fill=WHITE)
        cx += w
    y += 40
    for i, row in enumerate(rows):
        d.rectangle([x, y, x + sum(widths), y + 40], fill=WHITE if i % 2 == 0 else (248, 249, 251), outline=LIGHT_GRAY)
        cx = x
        for j, (value, w) in enumerate(zip(row, widths)):
            color = TEXT
            if highlight_col is not None and j == highlight_col:
                color = {"Ativo": GREEN, "Pronta": GREEN, "OK": GREEN, "Concluído": GREEN,
                         "Bloqueado": RED, "Erro": RED, "Falhou": RED, "Pendente": AMBER}.get(value, TEXT)
            d.text((cx + 12, y + 10), value, font=font(16, j == highlight_col), fill=color)
            cx += w
        y += 40
    return y


# --- one function per image ---------------------------------------------------

def portal_login_error():
    img, d, y = window("Portal do Cliente — Entrar", "https://portal.example.com/entrar")
    y = app_bar(d, y, "Portal do Cliente")
    d.rounded_rectangle([340, y + 50, 860, y + 520], radius=12, fill=WHITE, outline=LIGHT_GRAY)
    d.text((380, y + 80), "Acesse sua conta", font=font(28, True), fill=TEXT)
    alert(d, 380, y + 140, "Usuário bloqueado após 5 tentativas.", RED, 440)
    input_field(d, 380, y + 220, "Usuário", "fernanda.lopes", 440)
    input_field(d, 380, y + 305, "Senha", "••••••••••", 440)
    button(d, 380, y + 400, "Entrar", width=440)
    return img


def user_unlocked():
    img, d, y = window("Administração — Usuários", "https://portal.example.com/admin/usuarios")
    y = app_bar(d, y, "Administração do Portal")
    d.text((40, y + 30), "Usuários", font=font(26, True), fill=TEXT)
    alert(d, 40, y + 80, "Usuário fernanda.lopes desbloqueado com sucesso.", GREEN, 620)
    table(d, 40, y + 160, ["Usuário", "Nome", "Último acesso", "Situação"],
          [["fernanda.lopes", "Fernanda Lopes", "12/08/2026 09:41", "Ativo"],
           ["gabriel.rocha", "Gabriel Rocha", "12/08/2026 08:15", "Ativo"],
           ["helena.duarte", "Helena Duarte", "11/08/2026 17:02", "Ativo"],
           ["usuario.teste", "Usuário de Teste", "02/03/2026 10:00", "Bloqueado"]],
          [260, 360, 300, 200], highlight_col=3)
    return img


def print_queue_stuck():
    img, d, y = window("Fila de impressão — IMP-ADM-02")
    d.text((40, y + 30), "IMP-ADM-02 (Administrativo, 2º andar)", font=font(24, True), fill=TEXT)
    alert(d, 40, y + 80, "A impressora está offline — trabalhos parados na fila.", RED, 640)
    table(d, 40, y + 160, ["Documento", "Proprietário", "Páginas", "Status"],
          [["Relatório mensal.pdf", "gabriel.rocha", "12", "Erro"],
           ["Contrato 0815.docx", "helena.duarte", "4", "Erro"],
           ["Planilha custos.xlsx", "igor.pacheco", "2", "Pendente"]],
          [420, 300, 160, 240], highlight_col=3)
    return img


def printer_ready():
    img, d, y = window("Painel da impressora — IMP-ADM-02", "http://imp-adm-02.example.local")
    y = app_bar(d, y, "Servidor Web da Impressora", (60, 70, 85))
    alert(d, 40, y + 30, "Status: Pronta — página de teste impressa.", GREEN, 560)
    table(d, 40, y + 120, ["Item", "Valor"],
          [["Endereço IP", "192.0.2.45 (fixo)"], ["Toner", "68%"], ["Bandeja 1", "OK"],
           ["Driver no servidor", "Atualizado"], ["Fila de impressão", "Pronta"]],
          [400, 500], highlight_col=1)
    return img


def wifi_connected():
    img, d, y = window("Configurações — Rede e Internet")
    d.rectangle([0, y, 280, HEIGHT], fill=(235, 238, 243))
    for i, item in enumerate(["Wi-Fi", "Ethernet", "VPN", "Proxy"]):
        if i == 0:
            d.rounded_rectangle([12, y + 20 + i * 50, 268, y + 62 + i * 50], radius=6, fill=WHITE)
        d.text((32, y + 30 + i * 50), item, font=font(18, i == 0), fill=TEXT)
    d.text((320, y + 30), "Wi-Fi", font=font(28, True), fill=TEXT)
    alert(d, 320, y + 90, "Conectado a EXEMPLO-CORP (5 GHz)", GREEN, 520)
    table(d, 320, y + 180, ["Propriedade", "Valor"],
          [["Segurança", "WPA2-Enterprise"], ["Autenticação", "PEAP (certificado renovado)"],
           ["Sinal", "Excelente"], ["Endereço IPv4", "198.51.100.37"]],
          [300, 520])
    return img


def website(new_banner: bool):
    img, d, y = window("Empresa Exemplo — Página inicial", "https://www.example.com")
    d.rectangle([0, y, WIDTH, y + 70], fill=WHITE)
    d.text((40, y + 20), "EMPRESA EXEMPLO", font=font(24, True), fill=NAVY)
    for i, item in enumerate(["Início", "Serviços", "Notícias", "Contato"]):
        d.text((640 + i * 130, y + 24), item, font=font(17), fill=TEXT)
    y += 70
    if new_banner:
        d.rectangle([0, y, WIDTH, y + 300], fill=(16, 94, 112))
        d.text((80, y + 80), "Semana de Segurança da Informação", font=font(40, True), fill=WHITE)
        d.text((80, y + 150), "De 24 a 28 de agosto — palestras e oficinas abertas", font=font(22), fill=(200, 235, 240))
        button(d, 80, y + 210, "Inscreva-se", (245, 166, 35), 200)
    else:
        d.rectangle([0, y, WIDTH, y + 300], fill=(150, 150, 160))
        d.text((80, y + 110), "Campanha de julho", font=font(40, True), fill=WHITE)
        d.text((80, y + 180), "(banner do mês anterior)", font=font(22), fill=(235, 235, 240))
    for i in range(3):
        x = 60 + i * 370
        d.rounded_rectangle([x, y + 330, x + 340, y + 520], radius=10, fill=WHITE, outline=LIGHT_GRAY)
        d.rectangle([x + 20, y + 350, x + 320, y + 370], fill=LIGHT_GRAY)
        d.rectangle([x + 20, y + 385, x + 260, y + 400], fill=LIGHT_GRAY)
        d.rectangle([x + 20, y + 412, x + 290, y + 427], fill=LIGHT_GRAY)
    return img


def sales_report_fixed():
    img, d, y = window("Sistema de Gestão — Relatório de vendas", "https://gestao.example.com/relatorios/vendas")
    y = app_bar(d, y, "Sistema de Gestão")
    d.text((40, y + 25), "Relatório de vendas por filial — julho/2026", font=font(24, True), fill=TEXT)
    alert(d, 40, y + 75, "Totais recalculados após a correção do filtro de datas.", GREEN, 640)
    table(d, 40, y + 155, ["Filial", "Pedidos", "Valor (R$)", "Conferência"],
          [["Sede", "1.284", "412.930,00", "OK"], ["Filial Norte", "736", "198.410,50", "OK"],
           ["Filial Sul", "902", "251.077,80", "OK"], ["Total", "2.922", "862.418,30", "OK"]],
          [300, 220, 300, 300], highlight_col=3)
    return img


def install_complete():
    img, d, y = window("Instalação — Editor de Diagramas 4.2")
    d.rectangle([0, y, 300, HEIGHT], fill=NAVY)
    d.text((30, y + 40), "Editor de", font=font(26, True), fill=WHITE)
    d.text((30, y + 75), "Diagramas", font=font(26, True), fill=WHITE)
    d.text((30, y + 120), "versão 4.2", font=font(18), fill=(200, 210, 230))
    d.text((340, y + 50), "Instalação concluída", font=font(30, True), fill=TEXT)
    d.rounded_rectangle([340, y + 120, 1140, y + 150], radius=8, fill=GREEN)
    for i, line in enumerate(["• Arquivos copiados", "• Licença corporativa ativada", "• Atalho criado na área de trabalho",
                              "• Integração com o armazenamento em rede configurada"]):
        d.text((340, y + 190 + i * 40), line, font=font(19), fill=GREEN)
    button(d, 960, HEIGHT - 90, "Concluir", width=180)
    return img


def vpn_connected():
    img, d, y = window("Cliente VPN Exemplo")
    d.ellipse([480, y + 60, 720, y + 300], fill=(220, 240, 222), outline=GREEN, width=6)
    d.text((540, y + 155), "Conectado", font=font(26, True), fill=GREEN)
    table(d, 250, y + 350, ["Item", "Valor"],
          [["Servidor", "vpn.example.com"], ["Protocolo", "IKEv2"], ["Tempo conectado", "00:12:47"],
           ["Perfil", "Acesso remoto — colaboradores"]],
          [300, 400])
    return img


def backup_restore():
    img, d, y = window("Restauração de arquivos — Servidor de Backup", "https://backup.example.local/restauracoes")
    y = app_bar(d, y, "Console de Backup", (60, 70, 85))
    alert(d, 40, y + 30, "Restauração concluída: 214 arquivos (1,8 GB).", GREEN, 560)
    table(d, 40, y + 120, ["Origem", "Ponto de restauração", "Destino", "Resultado"],
          [["\\\\arquivos\\financeiro\\2026", "11/08/2026 23:00", "local original", "Concluído"],
           ["\\\\arquivos\\financeiro\\modelos", "11/08/2026 23:00", "local original", "Concluído"]],
          [360, 260, 240, 240], highlight_col=3)
    return img


def service_restarted():
    img, d, y = window("Terminal — srv-app-01", dark=True)
    lines = [
        ("$ sudo systemctl status app-agendamentos", (220, 220, 220)),
        ("● app-agendamentos.service - Agendamentos (fictício)", (220, 220, 220)),
        ("   Active: failed (Result: exit-code)", (240, 90, 90)),
        ("$ sudo journalctl -u app-agendamentos -n 3", (220, 220, 220)),
        ("   ERRO: disco /var/log 100% utilizado", (240, 90, 90)),
        ("$ sudo logrotate -f /etc/logrotate.d/app-agendamentos", (220, 220, 220)),
        ("$ sudo systemctl restart app-agendamentos", (220, 220, 220)),
        ("$ sudo systemctl status app-agendamentos", (220, 220, 220)),
        ("   Active: active (running) since 19/08/2026 10:42", (110, 210, 110)),
        ("$ df -h /var/log", (220, 220, 220)),
        ("   /dev/sdb1   20G   6,1G   14G   31%  /var/log", (110, 210, 110)),
    ]
    mono = None
    for name in ["consola.ttf", "DejaVuSansMono.ttf", "cour.ttf"]:
        try:
            mono = ImageFont.truetype(name, 19)
            break
        except OSError:
            continue
    mono = mono or font(19)
    for i, (text, color) in enumerate(lines):
        d.text((30, y + 30 + i * 36), text, font=mono, fill=color)
    return img


IMAGES = {
    "portal_login_error.png": portal_login_error,
    "user_unlocked.png": user_unlocked,
    "print_queue_stuck.png": print_queue_stuck,
    "printer_ready.png": printer_ready,
    "wifi_connected.png": wifi_connected,
    "site_old_banner.png": lambda: website(False),
    "site_new_banner.png": lambda: website(True),
    "sales_report_fixed.png": sales_report_fixed,
    "install_complete.png": install_complete,
    "vpn_connected.png": vpn_connected,
    "backup_restore.png": backup_restore,
    "service_restarted.png": service_restarted,
}


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for name, draw in IMAGES.items():
        path = os.path.join(OUTPUT_DIR, name)
        # optimize=True and no metadata: small files with nothing about the machine
        draw().save(path, optimize=True)
        print(f"{path} ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    main()
