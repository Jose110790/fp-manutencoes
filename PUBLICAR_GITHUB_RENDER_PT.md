# Publicação do FP Manutenções — GitHub + Render

## Importante
Este pacote é um MVP de validação, não uma versão aprovada para uso público com dados reais. Ele ainda utiliza uma senha administrativa compartilhada e SQLite. Não compartilhe o endereço com a equipe nem cadastre dados sensíveis antes de implementar login individual, permissões por função, proteção CSRF, armazenamento privado de anexos e migração para PostgreSQL.

## A. Criar o repositório privado no GitHub
1. Entre em https://github.com e faça login.
2. Toque/clique no botão `+` e escolha `New repository`.
3. Nome: `fp-manutencoes`.
4. Marque `Private`.
5. Não marque a opção para adicionar README, `.gitignore` ou licença (o projeto já contém esses arquivos).
6. Clique em `Create repository`.

## B. Enviar os arquivos
1. Baixe `FP_Manutencoes_GitHub_Render.zip` e extraia-o no computador.
2. Abra a pasta extraída `fp_manutencoes_mvp`.
3. No repositório recém-criado no GitHub, escolha `Add file` > `Upload files`.
4. Arraste os arquivos e pastas que estão DENTRO de `fp_manutencoes_mvp` para a área de envio (não envie o ZIP como um único arquivo; não envie a pasta externa inteira).
5. Confira se aparecem `app.py`, `requirements.txt`, `render.yaml`, `templates/` e `static/` na raiz do repositório.
6. Em `Commit changes`, use a mensagem `Publica estrutura inicial do FP Manutenções` e confirme.

Se o navegador não permitir enviar pastas, use GitHub Desktop em um computador: clone o repositório vazio, copie para ele o conteúdo da pasta `fp_manutencoes_mvp`, faça commit e `Push origin`.

## C. Criar o serviço no Render
1. Entre em https://render.com e crie sua conta ou entre.
2. Conecte o GitHub e autorize acesso somente ao repositório privado `fp-manutencoes` quando possível.
3. No painel do Render, escolha `New` > `Blueprint` (ou a opção equivalente para criar serviço a partir de `render.yaml`).
4. Selecione o repositório `fp-manutencoes` e a branch principal.
5. Revise o plano e os recursos mostrados antes de confirmar. O arquivo `render.yaml` pede serviço pago `starter` e disco persistente de 1 GB; preços e disponibilidade devem ser conferidos no painel.
6. Ao solicitar `FP_ADMIN_PASSWORD`, crie uma senha forte e única. Não reutilize senha de e-mail ou banco. A chave `FP_SECRET_KEY` deve ser gerada pelo Render conforme o Blueprint.
7. Confirme a criação e espere o deploy terminar. Se falhar, abra `Logs` no Render e copie a mensagem de erro (sem segredos) para análise.
8. Teste a URL temporária que o Render fornece e acrescente `/healthz`. Deve responder `ok`.

## D. Conectar fpmanutencoes.com.br
Faça isso só depois de o serviço estar publicado e funcionando na URL temporária.
1. No serviço web do Render, abra `Settings` > `Custom Domains` > `Add Custom Domain`.
2. Adicione `fpmanutencoes.com.br`. Se quiser que `www.fpmanutencoes.com.br` também funcione, adicione-o separadamente.
3. Copie exatamente os registros DNS mostrados pelo Render. Não use valores de tutoriais antigos.
4. Entre em https://registro.br, abra o domínio e a área de DNS. Se o Registro.br pedir para escolher servidores DNS, mantenha a configuração compatível com o modo DNS que você está usando; insira os registros exigidos pelo Render na zona DNS apropriada. Se o painel não permitir inserir os registros solicitados, pare e envie uma captura de tela sem dados pessoais.
5. Aguarde a propagação. Volte ao Render e confirme que o domínio aparece verificado e que o certificado HTTPS foi emitido.
6. Teste `https://fpmanutencoes.com.br` no Safari e em outro dispositivo.

## E. Antes de uso real
Não coloque dados reais de clientes, funcionários, contratos ou fotos até completar:
- contas individuais e permissões reais por rota;
- proteção CSRF e limitação de tentativas de login;
- migração SQLite para PostgreSQL gerenciado;
- armazenamento privado de anexos e controle de acesso;
- links de orçamento com expiração/revogação;
- backups automáticos e teste de restauração;
- testes de segurança, permissões, QR Codes e fluxos de orçamento.

## Solução de problemas
- `Build failed`: confira os `Logs` de build e se `app.py`, `requirements.txt` e `render.yaml` estão na raiz do repositório.
- `Service failed to start`: abra os logs de runtime; não publique segredos nos pedidos de ajuda.
- Domínio não verificado: confira se os DNS correspondem exatamente aos valores que o Render mostra; não invente nem copie registros de terceiros.
- QR Codes: gere novamente depois de o domínio final funcionar, para que usem o endereço HTTPS público.
