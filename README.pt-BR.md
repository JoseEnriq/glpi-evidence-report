# glpi-evidence-report

[English](README.md) | **Português**

Gera o "book de evidências" mensal de um contrato de suporte de TI (cada chamado atendido por cada técnico, com histórico, solução e as imagens anexadas) em Word e PDF, direto da API REST do GLPI.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
[![Testes](https://github.com/JoseEnriq/glpi-evidence-report/actions/workflows/tests.yml/badge.svg)](https://github.com/JoseEnriq/glpi-evidence-report/actions/workflows/tests.yml)

| Capa com resumo por técnico | Sumário com links | Chamado com linha do tempo e evidências |
|---|---|---|
| ![Capa](docs/img/cover.png) | ![Sumário](docs/img/contents.png) | ![Chamado](docs/img/ticket.png) |

As imagens e o [PDF de exemplo](docs/sample/evidence_report_sample.pdf) foram gerados pelo modo demonstração, com dados fictícios. O book é em português porque foi feito para um contrato brasileiro; o código é em inglês.

## Por que eu fiz

No meu trabalho, a equipe precisa comprovar todo mês os atendimentos de um contrato de serviço. O documento era montado a partir dos e-mails de notificação do GLPI, e um print só entrava se alguém tivesse movido o e-mail certo para a pasta certa. Era lento, dependia de uma pessoa e muitas imagens se perdiam, principalmente as anexadas aos acompanhamentos e à solução, e não ao chamado em si.

## Como funciona

O programa fala com a API REST do GLPI, em modo somente leitura:

1. abre uma sessão com um token de API, sem guardar senha;
2. busca os chamados do período com paginação e traz 6 chamados em paralelo;
3. reúne os anexos do chamado, dos acompanhamentos e da solução, sem duplicar;
4. baixa as imagens para um cache em disco, conferindo a assinatura de cada arquivo;
5. monta o Word com python-docx e converte em PDF com o LibreOffice headless.

Um único comando gera os books do mês anterior de todos os GLPIs configurados. Diagramas e organização dos módulos estão em [docs/arquitetura.md](docs/arquitetura.md).

## Decisões

- **Anexos de três origens.** A maior parte das imagens que faltavam estava nos acompanhamentos e na solução, então consulto o `Document_Item` de cada um deles, não só o do chamado.
- **Validar os bytes, não a resposta.** O download de um documento pode voltar como uma página HTML de login ou de erro com status 200. Confiro a assinatura PNG/JPEG/GIF/BMP antes de salvar qualquer coisa como imagem.
- **Confiar no `Content-Range`, não no tamanho da página.** Alguns servidores devolvem páginas menores que as pedidas, então a paginação segue o total informado pelo servidor.
- **Perfil de menor privilégio.** Depois do login a sessão costuma estar no Self-Service, que não vê os chamados de outros usuários. O programa troca para o perfil de menor privilégio que vê, dando preferência aos de leitura.
- **6 threads de propósito.** Cada chamado custa uns 12 pedidos; poucas threads e um cache de usuários e categorias deixam a geração rápida sem sobrecarregar o GLPI.

A tabela completa, com referências ao código, fica em [docs/arquitetura.md](docs/arquitetura.md#decisões-técnicas).

## Resultados

Do uso em produção no meu trabalho:

- os books mensais de todas as nossas instâncias do GLPI saem de um único comando, sem passo manual, e podem rodar pelo Agendador de Tarefas do Windows;
- as imagens anexadas aos acompanhamentos e às soluções agora entram no book;
- antes de abandonar o acesso direto ao banco, comparei campo a campo a saída da API com uma leitura do banco até baterem, e só então removi a conexão com o banco.

## Rodar a demonstração

Não precisa de GLPI: um servidor simulado responde na camada HTTP, então o programa real roda inteiro.

```bash
git clone https://github.com/JoseEnriq/glpi-evidence-report.git
cd glpi-evidence-report
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python demo.py
```

O `.docx` e o `.pdf` ficam em `demo_output/`. O PDF precisa do [LibreOffice](https://www.libreoffice.org/) instalado; sem ele, sai só o `.docx`.

## Usar com o seu GLPI

É preciso ter a API REST habilitada com login por token externo, um cliente de API que aceite a sua máquina e um token de usuário com perfil de leitura. Depois, copie o `config.example.toml` e o `.env.example`, preencha as instâncias e os tokens e rode `python diagnose_api.py` para conferir o acesso. O passo a passo, os comandos e os problemas comuns estão em [docs/uso.md](docs/uso.md).

## Testes

```bash
pip install -r requirements-dev.txt
pytest
```

Os testes cobrem as funções puras e o fluxo de ponta a ponta contra o GLPI simulado (erro 503 passageiro, página HTML servida como imagem, paginação além do limite do servidor) e rodam no GitHub Actions, em Ubuntu e Windows.

---

© 2026 JoseEnriq. Todos os direitos reservados. Peça de portfólio: fique à vontade para ler o código e rodar a demonstração, mas não copie, modifique nem redistribua sem autorização.
