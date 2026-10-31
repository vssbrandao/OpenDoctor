# Cadastro: só médicos criam conta (CRM conferido)

Toda conta nova passa pelo **Registro profissional** (Figma 1178-7176, na tela de login): nome completo, CPF, data de
nascimento, CRM e UF. O CRM é conferido no **web service oficial do CFM** antes de a conta existir. Sem a chave do CFM
(contrato pendente), ou com o CFM fora do ar, a conta nasce **pendente** e um administrador aprova à mão.

## Fluxo

### Cadastro por e-mail
1. E-mail sem conta → tela **Crie sua conta**: só a senha. O botão **Continuar** não vai ao servidor.
2. **Registro profissional**:
   - Campos: Nome; CPF | Nascimento; CRM | UF. A seta no alto volta para a senha.
   - **Criar conta** manda, uma vez só, ao `POST /auth/signup/start`: e-mail, senha, nome, CPF, nascimento, CRM e UF.
3. O servidor confere os formatos, depois o CRM no CFM (ou decide pendente), e **só então** manda o código por e-mail:
   - **Nome:** completo, com pelo menos 2 palavras (sem contar "de", "da"… nem "Dr.").
   - **CPF:** com os dígitos verificadores certos.
   - **Nascimento:** data real, de quem tem entre 20 e 100 anos.
   - **CRM:** de 1 a 7 dígitos (veja "CRM e UF" abaixo).
   - **UF:** uma das 27.
4. O tíquete assinado (30 min) leva o nome, o CRM, a UF e a decisão. Nunca leva o CPF nem o nascimento.
5. O código confere em `POST /auth/signup/verify`, e a conta é criada com o CRM e a decisão.
   - **Verificado:** vai para o app.
   - **Pendente:** a tela mostra a espera.

### Conta nova pelo Google
- **Na volta do Google:** e-mail sem conta → `/opendoctor-login.html?registro=google`, direto no Registro profissional.
  - O perfil do Google (e-mail, foto, id) espera num cookie assinado deste navegador: `od_greg`, 15 min, `path=/auth/`.
  - Nada do perfil vai na URL.
- **Criar conta:** `POST /auth/google/registro` confere o CRM e só então cria a conta.
  - Não há código: o Google já confirmou o e-mail.
  - O cookie só cria conta. Se o e-mail ganhou uma conta no meio do caminho, a resposta é `sessao_expirada` e o médico
    entra de novo pelo Google: uma cópia do cookie não vale como login.
- A seta volta para a tela inicial.
- **Contas Google que já existem:** entram como sempre.

### A decisão (`server._crm_decide`)
- **Com `CFM_CHAVE`:**
  1. **Consultar:** a situação tem de ser `A` (regular), e o nome digitado tem de bater com o do CFM.
     - A comparação ignora acentos, maiúsculas, espaços, conectores (de, da, do, dos, das, e) e "Dr./Dra.".
     - O primeiro nome tem de ser igual, e o último sobrenome digitado tem de estar entre as palavras do nome no CFM.
  2. **Validar** (CRM + UF + CPF + nascimento) tem de dar `true`: prova que é o próprio médico.
  - Tudo certo → **verificado** (`crm_fonte = 'cfm'`).
- **Recusas claras:** o cadastro é recusado com a mensagem, e nada é criado (nem código, nem conta):
  - CRM não encontrado (8101);
  - situação irregular;
  - nome diferente;
  - Validar `false`.
- **Fica pendente:**
  - sem chave;
  - CFM fora do ar ou com erro passageiro repetido;
  - chave inválida (3010);
  - pedido recusado (4000/4010/4020).
- **CRM que outra conta (não recusada) já usa:** fica pendente mesmo verificado. Quem tem os dados de um médico não
  abre uma segunda conta sozinho; a página de cadastros mostra o alerta.
- **Limite:** a rota que chama o CFM tem um limite por IP (balde `cfm`: 10 por hora). O Validar responde se um CPF é de
  um CRM, e o limite impede usar o cadastro para testar CPFs.

### CRM e UF
- **Máscaras:** CPF `000.000.000-00`; nascimento `DD/MM/AAAA`; CRM só números (até 7); UF 2 letras maiúsculas.
- **CRM colado ou digitado com a UF:** a UF vai para o campo UF e fica só o número. Exemplos:
  - `CRM-SP 123456`, `CRM/SP 123.456`, `SP 123456`, `123456/SP`, `123456-SP`;
  - `52-1234/RJ` vira 1234 (o 52- com que o RJ mostra os números);
  - `1234567-P/SP` vira 1234567 (inscrição provisória);
  - `300-EMFE-1234567` vira 1234567.
- A mesma regra roda no servidor (`cfm.separa_crm`) e na página (`separaCrm`).

## A espera: conta pendente, recusada ou a confirmar
- **O que a conta acessa:** ela entra, mas só chega ao que é público: `/me`, `/auth/*`, a tela de login, sair e `/assets/`.
- **O resto** é barrado pela regra central (middleware `_no_cache_html` + `_crm_bloqueio`):
  - **Páginas:** voltam para a tela de login, que mostra a espera.
    - Pendente: título "Estamos conferindo seu CRM", com um texto curto e "Sair".
    - Recusado: uma mensagem curta.
  - **Rotas da API:** respondem `403 {"error": "crm_pendente" | "crm_recusado" | "crm_confirmar"}`.
- **`/me`:** devolve `bloqueio` com o motivo.
- **Login com senha e outros logins:** a resposta traz `bloqueio`, e a tela mostra a espera em vez de abrir o app.
- **Contas anteriores a esta regra** (`crm_status` vazio; as 3 que existiam): seguem exatamente como antes.

## Aprovação à mão (administradores)
- **Quem é administrador:** a variável **`ADMIN_EMAILS`** no Render.
  - E-mails separados por vírgula, comparados em minúsculas.
  - Nenhum e-mail fica no código. Sem a variável, ninguém é administrador.
- **A página `/opendoctor-cadastros.html`:**
  - Privada: exige login, e as rotas conferem se é administrador (403 para os outros).
  - **Lista os pendentes:** nome, CRM/UF, data do pedido e alerta de CRM repetido.
  - **Link** para a busca pública do CFM (https://portal.cfm.org.br/busca-medicos/), para conferir à mão.
- **Aprovar / Recusar:**
  - `POST /admin/cadastros/aprovar | recusar` com `{"id"}` (JSON).
  - Só muda uma conta que ainda está pendente: dois cliques não decidem duas vezes.
  - Grava `crm_fonte = 'manual'`.
- **E-mails (Resend):**
  - **Aos administradores**, a cada cadastro pendente: só o nome e o CRM/UF do médico.
  - **Ao médico**, quando é aprovado (conta liberada) ou recusado.
  - A falha do e-mail não desfaz a decisão.

## Contas aprovadas à mão, quando a chave chegar
- **O problema:** o CPF não foi guardado. Quando `CFM_CHAVE` passar a existir, quem tem `crm_fonte = 'manual'` precisa
  confirmar no CFM.
- **Quando:** na próxima vez que abrir o app, a tela pede **uma vez** o CPF e o nascimento (passo "Confirme seu registro").
- **Como:** `POST /auth/crm/confirmar` roda o Validar.
  - **`true`:** `crm_fonte = 'cfm'`, e o app abre.
  - **`false`:** a mensagem aparece e o pedido continua até dar certo.
  - **CFM fora do ar:** pede para tentar de novo em alguns minutos (fechado por padrão).

## O que é guardado (e o que não é)
- **Guardado em `users` (migração `0017_crm.sql`):**
  - `name`, `crm`, `crm_uf`;
  - `crm_status`: NULL = conta antiga; `pendente` | `verificado` | `recusado`;
  - `crm_fonte`: `cfm` | `manual`;
  - `crm_situacao` (a letra do CFM), `crm_verificado_em`, `crm_pedido_em`.
- **Não guardado:** CPF e data de nascimento. Vão só ao CFM, no corpo do SOAP. Não entram em banco, log, tíquete
  assinado, cookie nem e-mail.
- **Log do CFM (`app/cfm.py`):** só a operação, o código de erro e o tempo. Nunca a chave, o CPF ou o nascimento.
- **CRM conferido** (`crm_status = 'verificado'`): não muda em Configurações, porque vai na receita. Contas antigas
  editam como sempre.
- **Especialidade:** não é pedida no cadastro. O médico preenche depois em Configurações.

## O web service do CFM (manual v3.0, 08/2026)
- **Pedido:**
  - `POST https://ws.cfm.org.br:8080/WebServiceConsultaMedicos/ServicoConsultaMedicos`;
  - `Content-Type: text/xml; charset=utf-8`, cabeçalho `SOAPAction: ""` (vazio, obrigatório);
  - só TLS 1.2; namespace `http://servico.cfm.org.br/`.
- **`Consultar(crm, uf, chave)`** → `dadosMedico`:
  - `crm`, `uf`, `nome`, `situacao` (`A` = regular), `tipoInscricao`, `dataAtualizacao`;
  - `especialidade` (repetível).
- **`Validar(crm, uf, cpf, dataNascimento, chave)`** → `resultadoConsulta` `true|false`.
- **Erros:** vêm com HTTP 200 e `codigoErro`.
  - 2010/2030/2040: passageiros; tenta mais uma vez, depois fica indisponível;
  - 3010: chave inválida ou vencida;
  - 4000/4010/4020: pedido inválido;
  - 8101: médico não encontrado.
- **Leitura:** campo que falta não vem. Só as tags conhecidas são lidas, pelo nome. XML com DOCTYPE ou entidades nem é
  lido.

## Contrato com o CFM (passos do dono)
1. Pedir o acesso ao web service pelo **SEI-Medicina**, como representante legal da empresa (CNPJ do OpenDoctor).
2. Juntar os documentos pedidos no manual (da empresa e do representante legal) e protocolar a petição no SEI.
3. Pagar a anuidade, **R$ 948/ano**, por depósito identificado com o CNPJ.
4. O CFM manda a **chave** (8 caracteres) por e-mail.
5. Colar a chave no Render → Environment → **`CFM_CHAVE`** e reiniciar o serviço.
   - Nunca no código, num comando ou numa mensagem.
6. A partir daí:
   - os cadastros novos são conferidos na hora;
   - as contas aprovadas à mão confirmam o CPF e o nascimento uma vez, na próxima vez que abrirem o app.

## Variáveis de ambiente
- **`CFM_CHAVE`:** chave do web service do CFM (segredo). Sem ela, todo cadastro novo fica pendente.
- **`ADMIN_EMAILS`:** e-mails dos administradores, separados por vírgula. Aprovam os cadastros e recebem o aviso.

## Publicar
- **Banco primeiro:** aplicar `0017_crm.sql` no banco de produção **antes** de subir o código.
  - `get_user` já lê as colunas novas: sem elas, ninguém entra.
  - A migração é aditiva (`add column if not exists`).
- **Ordem:** primeiro no banco de testes, depois em produção.
- **Depois de publicar:** definir `ADMIN_EMAILS` no Render, para receber os avisos e abrir a página de cadastros.

## Testes
- **`tests/test_cadastro_crm.py`:**
  - cliente do CFM com respostas XML prontas;
  - cadastro verificado, pendente e recusado;
  - Google;
  - a espera;
  - confirmação;
  - página de cadastros;
  - trava do CRM em Configurações.
- **`tests/test_db_integration.py`:** no banco de testes.
- **`tests/test_laco_de_eventos.py`:** o CFM entra na lista do que só roda fora do laço.
- **`tests/test_security.py`:** as rotas novas sob `/auth/` estão revisadas; as de `/admin/` são privadas.
- **E2E:** `node tests/e2e/cadastro.mjs`. Chrome sem tela, sem servidor; `SHOT=/pasta` salva as telas.
- **Conftest:** zera `CFM_CHAVE`, então nenhum teste chama o CFM de verdade.
