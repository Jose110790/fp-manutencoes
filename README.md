# FP Manutenções — MVP técnico

Aplicação web responsiva inicial para manutenção de buffet infantil.

## Recursos incluídos
- Login administrativo simples por senha.
- Cadastro de usuários, ambientes e equipamentos.
- QR Codes para abrir as páginas dos ambientes/equipamentos.
- Ordens de serviço e atribuição de responsável.
- Portal de orçamento por link individual para terceirizados.
- Orçamentos com mão de obra, frete, vários materiais, quantidade, unidade, preço e fotos.
- Análise de proposta pela gestora: aprovar, recusar, pedir ajustes ou contratar apenas mão de obra.
- Rotinas com procedimentos e registro de execução.
- Banco SQLite local.

## Requisitos
Python 3.10 ou superior.

## Rodar localmente
1. Extraia o ZIP.
2. Abra um terminal dentro da pasta `fp_manutencoes_mvp`.
3. Crie ambiente virtual:
   - Windows: `py -m venv .venv` e `.venv\\Scripts\\activate`
   - macOS/Linux: `python3 -m venv .venv` e `source .venv/bin/activate`
4. Instale as dependências:
   `pip install -r requirements.txt`
5. Configure a senha administrativa e a chave secreta no ambiente. Exemplo macOS/Linux:
   `export FP_ADMIN_PASSWORD='sua-senha-forte'`
   `export FP_SECRET_KEY='uma-chave-longa-e-aleatoria'`
   No PowerShell, use `$env:FP_ADMIN_PASSWORD='sua-senha-forte'` e `$env:FP_SECRET_KEY='uma-chave-longa-e-aleatoria'`.
6. Inicie:
   `python app.py`
7. Abra `http://127.0.0.1:5000`
8. Senha padrão somente para teste local, caso não configure variável de ambiente: `FPtrocar123!` — troque antes de qualquer uso real.

## Preparação de hospedagem Render (não é publicação automática)
O arquivo `render.yaml` inclui uma configuração inicial de serviço web com Gunicorn, armazenamento persistente para SQLite/anexos/QR Codes e uma verificação de saúde. Para usar:
1. Coloque o conteúdo deste projeto em um repositório **privado** no GitHub.
2. No Render, crie um Blueprint a partir desse repositório e revise os recursos e custos antes de confirmar.
3. Defina `FP_ADMIN_PASSWORD` como um segredo forte no painel do Render. `FP_SECRET_KEY` é gerada pelo Blueprint.
4. Faça o primeiro deploy e teste `/healthz` antes de configurar o domínio.
5. Em Settings → Custom Domains, adicione o domínio e siga os registros DNS que o Render exibir. O Render documenta certificados TLS e redirecionamento para HTTPS para domínios personalizados.
6. No Registro.br, registre o domínio desejado se estiver disponível; depois configure os DNS conforme as instruções do Render.

## Importante antes de publicar para usuários reais
Esta configuração é apenas uma etapa de implantação técnica. **Não coloque dados reais nem compartilhe o endereço com a equipe ainda.** O MVP continua com uma senha compartilhada, sem contas individuais nem autorização real por perfil, e precisa de revisão de segurança antes do uso público. A configuração atual usa SQLite em disco persistente, adequada apenas como etapa provisória para uma instalação pequena; para produção multiusuário mais robusta, migrar para PostgreSQL e armazenamento privado de anexos. Também é necessário adicionar proteção CSRF, limites de tentativas de login, auditoria, expiração/revogação de links de orçamento e política de retenção de arquivos.

Este é um MVP para teste e validação, não um sistema pronto para exposição pública. Antes de produção, implemente autenticação individual por usuário e perfis de autorização por rota, proteção CSRF, política de links externos/expiração e uso único, trilha de auditoria completa, backups automáticos testados, armazenamento privado de anexos, configuração de HTTPS e servidor de produção (por exemplo, Gunicorn atrás de um proxy). A integração com WhatsApp ainda é por link manual wa.me; não há envio automático pela API oficial.
A aplicação usa SQLite para facilitar o teste local. Para uso multiusuário online, recomendamos migrar para PostgreSQL e armazenamento privado de arquivos.
As cores atuais são uma proposta provisória (roxo, coral, turquesa e amarelo), não uma reprodução confirmada da identidade oficial do Festeja Park.
