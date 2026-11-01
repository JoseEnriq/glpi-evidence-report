# Uso

Como rodar a demonstração em detalhe e como configurar o programa para um GLPI de verdade. Para entender como ele funciona por dentro, veja [arquitetura.md](arquitetura.md).

## Modo demonstração

O `python -m glpi_report.demo` gera um book completo com dados fictícios, sem precisar de GLPI (o servidor é simulado na camada HTTP; detalhes em [arquitetura.md](arquitetura.md#glpi-simulado-e-testes)). Saída esperada (resumida):

```text
13 ticket(s) found in the given period.
Fetched ticket #101 — Usuário bloqueado no Portal do Cliente
...
Technician filter: kept 11 of 13 ticket(s).
Images: 12 available (12 downloaded now, 0 from cache, 1 failed).
[WARNING] Document 514 not downloaded: the downloaded content is not an image (missing permission or error page?)
Evidence report generated: demo_output\evidence_report_demo_2026-08.docx
PDF generated: ...\demo_output\evidence_report_demo_2026-08.pdf
```

O aviso do documento 514 é proposital: o simulador devolve uma página HTML no lugar dessa imagem para mostrar a validação da assinatura.

- O `.docx` e o `.pdf` ficam em `demo_output/`.
- O PDF só é gerado se o [LibreOffice](https://www.libreoffice.org/) estiver instalado; sem ele, sai só o `.docx`.
- Rode de novo para ver o cache em ação (`0 downloaded now, 12 from cache`).
- `python -m glpi_report.demo --clean` apaga o `demo_output/` (inclusive o cache de imagens) e recomeça do zero.

## Configuração no GLPI

Feita uma vez, por quem administra o GLPI, em **Configurar > Geral > API**:

- **Habilitar API Rest:** Sim.
- **Habilitar login com token externo:** Sim (o login com credenciais pode ficar desligado).
- Um **cliente de API** ativo que aceite a máquina que vai rodar o programa, de preferência restrito ao IP dela.

O usuário do token precisa de um perfil que veja todos os chamados e anexos. O recomendado é uma **conta de serviço com perfil de leitura** (Observer ou Read-Only, na entidade raiz, com herança).

## Configuração local

```bash
copy config.example.toml config.toml   # Linux/macOS: cp
copy .env.example .env
```

- **`config.toml`**: uma seção por GLPI, com nome de exibição, URL e técnicos que entram no book do mês.
- **`.env`**: o token de API de cada instância (`GLPI_<CHAVE>_API_USER_TOKEN`). No GLPI: *Minhas configurações > Chaves de acesso remoto > API token*.

Os dois arquivos estão no `.gitignore`.

## Comandos

Rode sempre a partir da raiz do repositório: o `-m` executa um módulo de dentro do pacote `glpi_report`.

```bash
python -m glpi_report.diagnose_api       # confere API, IP liberado, token e perfil de cada GLPI
python -m glpi_report.generate_month     # books do mês anterior de todas as instâncias (.docx + .pdf)
python -m glpi_report.generate_month --month 2026-08 --instances main
python -m glpi_report.generate_report --instance main --period 2026-08-01 2026-08-31 --technician "Ana Ribeiro" --pdf
python -m glpi_report.generate_report --instance main --ids 101,105 --pdf
```

## Agendamento no Windows

O `generate_month.bat` roda o `python -m glpi_report.generate_month`. Aberto com duplo clique, ele espera uma tecla no final para dar tempo de ler a saída. No Agendador de Tarefas, passe o argumento `--scheduled`: não há pausa, e uma execução com falha é informada pelo código de saída.

## Se algo falhar

| Mensagem | Causa provável | O que fazer |
|---|---|---|
| erro de conexão / sem resposta | fora da rede do GLPI | conectar à rede / VPN |
| `Missing API token` / `rejected the login` | token em branco, errado ou regerado | gerar o API token de novo e atualizar o `.env` |
| `ERROR_NOT_ALLOWED_IP` | IP da máquina não liberado (atenção a NAT/proxy: vale o IP que o servidor enxerga) | ajustar o cliente de API |
| `API disabled` | API desligada no GLPI | Configurar > Geral > API |
| `LibreOffice not found` | LibreOffice ausente | instalar ou definir `LIBREOFFICE_PATH` no `.env` |
