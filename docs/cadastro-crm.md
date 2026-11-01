# Cadastro: só médicos criam conta (CRM conferido)

Toda conta nova passa pelo **Registro profissional** (Figma 1178-7176, na tela de login): nome completo, CPF, data de
nascimento, CRM e UF. O CRM é conferido no **web service oficial do CFM** antes de a conta existir. Sem a chave do CFM
(contrato pendente), ou com o CFM fora do ar, a conta nasce **pendente** e um administrador aprova à mão.

## Fluxo

### Cadastro por e-mail
1. E-mail sem conta → tela **Crie sua conta**: só a senha. O botão **Continuar** não vai ao servidor.
2. **Registro profissional**:
   - Campos: Nome; CPF | Nascimento; CRM | UF. A seta no alto volta para a senha (também quando o tíquete venceu na tela
     do código: ela volta à entrada do Registro, com "A confirmação expirou", sem empilhar outra).
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
- **E-mail confirmado pelo Google:** quem entra pelo Google não confirma o e-mail de novo (nem código, nem passo a
  mais): o Google já confirmou que o e-mail é dele.
  - Vale só quando o próprio Google diz isso: `verified_email` do userinfo v2 ou `email_verified` do `id_token` da troca
    do code (`auth.email_verificado`: precisa de um "sim" e nenhum "não"; sem a informação, é "não").
  - **E-mail não verificado pelo Google** (conta Google aberta com um e-mail de fora, nunca confirmado): a volta do Google
    não entra numa conta que já existe nem leva ao Registro. A tela de login mostra "Esse e-mail não foi verificado pelo
    Google." (`?erro=google_nao_verificado`, com o `next`). Sem isso, bastaria abrir uma conta Google com o e-mail de
    um médico para entrar na conta dele. O e-mail não vai para o log.
- **Na volta do Google:** e-mail sem conta → `/opendoctor-login.html?registro=google` (com o `next` da página de
  origem, se houver), direto no Registro profissional.
  - O perfil do Google (e-mail, foto, id) espera num cookie assinado deste navegador: `od_greg`, 15 min, `path=/auth/`.
    Ele leva a marca `ev` (e-mail confirmado pelo Google); o `/auth/google/registro` recusa o cookie sem ela (um de antes
    desta conferência pede para entrar pelo Google de novo).
  - Nada do perfil vai na URL. O `registro=google` e o `next` ficam nela até a conta existir: recarregar a página volta
    ao Registro, e a seta tira só o `registro`.
  - **Uma aba, uma volta do Google:** o cookie é um por navegador (a última volta vale). A volta põe `r` (aleatório) no
    cookie e na URL do Registro, e o Criar conta manda o `r` da aba; o de outra aba recebe `google_outra_aba` ("Você
    começou outro cadastro com o Google em outra aba…") e não cria a conta do outro e-mail com os dados digitados nesta.
  - **A seta apaga o perfil guardado** (`POST /auth/google/registro/cancelar`, só JSON, com o `r` da aba: o perfil de
    outra aba fica, e um formulário de outro site não apaga nada); o Sair também apaga (e o `od_oauth`, o
    `od_oauth_cal`). Num F5 da entrada antiga do histórico, ninguém cria a conta deste e-mail.
- **Criar conta:** `POST /auth/google/registro` confere o CRM e só então cria a conta.
  - Não há código: o Google já confirmou o e-mail.
  - O cookie só cria conta. Se o e-mail (ou a conta Google, pelo `sub`) ganhou uma conta no meio do caminho, a resposta
    é `sessao_expirada` e o médico entra de novo pelo Google: uma cópia do cookie não vale como login.
- **A agenda, logo depois** (pedido do dono, 31/10): com a conta criada, a tela de login vai direto ao Google pedir a
  permissão do Google Agenda. É a mesma conexão de Integrações, já aberta na conta do médico: um toque em Permitir.
  - O login pelo Google continua pedindo só nome, e-mail e foto. O botão do Google aparece antes do e-mail, então nessa
    hora não se sabe quem vai criar conta: pedir a agenda ali seria pedi-la a todo login.
  - **Resposta:** o `/auth/google/registro` devolve `agenda` (a URL do Google: o escopo da agenda, `login_hint` com o
    e-mail, `access_type=offline`, `prompt=consent`) e põe o nonce no cookie `od_oauth_cal`. A tela de login vai para lá
    em vez do `redirect`, mesmo na conta pendente. Nada do Registro vai na URL.
  - **O state** é o da conexão de Integrações (`k=cal`, a conta, o nonce deste navegador), com `ap=1` e o destino do
    cadastro (`nx`). A volta grava a agenda com a mesma conferência: nonce neste navegador, a conta logada nele, o mesmo
    provedor.
  - **Volta (`_agenda_volta`):** o destino do cadastro, com a agenda ou sem ela (cancelou, desmarcou a caixa da agenda,
    o Google falhou, outro navegador, mais de 15 min na tela do Google), sem mensagem de erro: a conta já existe e a
    agenda se conecta depois em Integrações. Conta que ainda não usa o app vai para a espera com esse destino no `next`,
    que abre quando liberar.
    - **Prazo:** o state vencido não grava nada, mas o da agenda do cadastro (`ap=1`, assinatura conferida) ainda escolhe
      o destino; os outros vencidos continuam em "Erro de conexão".
    - **O Voltar** da tela do Google não passa pelo servidor: antes de sair, a tela de login troca o `registro=google` da
      URL pelo `next` com o destino do cadastro, e o Voltar (com ou sem o cache do navegador) vai a ele, ou à espera, que
      mantém o `next` (inclusive num F5).
  - **As boas-vindas vão na sessão** (não no endereço): a sessão da conta que acabou de nascer (cadastro por e-mail ou
    pelo Google) leva a marca `bv` (`auth.set_session`). O `/me` devolve `boas_vindas: true` quando a conta já usa o app;
    a agenda mostra o aviso e chama `POST /me/boas-vindas`, que tira a marca (não volta ao recarregar). Assim elas
    chegam depois da aprovação (mesmo com a aba da espera fechada, no mesmo navegador) e da confirmação do CPF, e nunca
    a outra conta que entre no mesmo navegador. Um `?bemvindo` antigo na URL só é apagado.
    - **O texto segue a agenda de verdade:** a 1ª resposta do `/calendar/events` decide ("Sua agenda do Google já está
      conectada", sem o link; senão, o convite "Conectar agenda"; sem resposta em 3 s, o convite).
  - **Conta pendente:** a agenda já fica conectada, pronta para a aprovação. Se o cadastro for **recusado**, a conexão é
    apagada (todos os provedores); a aprovação não mexe nela.
    - **Recusa com o médico ainda na tela do Google:** a volta não grava na conta recusada; a troca que já estava em
      andamento relê a conta depois de gravar e, recusada, apaga (a recusa grava a decisão antes de apagar: nenhuma
      ordem deixa a agenda).
    - **Limpeza diária** (`db.cleanup_old_records`): apaga a agenda de toda conta recusada, para a falha da recusa (o 2º
      clique dá 409 e não apaga de novo) e o que escapar.
  - O cadastro por e-mail e senha não muda: a agenda continua em Integrações (e no convite das boas-vindas).
- **Contas Google cujo `sub` é de outra conta**, mesmo quando o e-mail novo tem conta própria: o aviso de conta ligada a
  outro e-mail (abaixo), em vez de "Erro de conexão" a cada tentativa. No log do login que falha, só o tipo do erro (o
  do banco traria o `sub`).
- A seta volta para a tela inicial.
- **Contas Google que já existem:** entram como sempre, desde que o Google tenha confirmado o e-mail.
- **Conta Google cujo e-mail mudou no Google** (o `sub` já é de uma conta do OpenDoctor com o e-mail antigo): nem o
  Registro de uma conta nova (o CPF iria ao CFM e a conta não seria criada: `google_sub` é único), nem entrar sozinho na
  outra conta. A tela diz "Esta conta Google está ligada a outro e-mail no OpenDoctor. Entre com o e-mail da sua conta."
  (`?erro=google_outro_email`).

### A decisão (`server._crm_decide`)
- **Com `CFM_CHAVE`:**
  1. **Consultar:** a situação tem de ser `A` (regular), e o nome digitado tem de bater com o do CFM.
     - A comparação ignora acentos (também o acento colado separado da letra, de PDF ou do macOS: tudo em NFC),
       maiúsculas, espaços, conectores (de, da, do, dos, das, e) e "Dr./Dra.".
     - O primeiro nome tem de ser igual, e o último sobrenome digitado tem de estar entre os **sobrenomes** do CFM: não
       vale repetir o primeiro nome ("Ana Ana"), e o nome digitado precisa de 2 palavras diferentes.
     - Apóstrofo junto ou separado: D'Ávila = Davila = Ávila; Sant'Anna = Santanna.
     - Sufixos: Jr. = Júnior, Fº = Filho. Se o último digitado é um sufixo (Filho, Júnior, Neto, Sobrinho), vale também
       o sobrenome antes dele.
     - A mesma regra de palavras roda na página (`palavras`), que só confere se há nome e sobrenome.
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
  - Conferido no início **e de novo na hora de criar a conta**, no banco (`db._CRM_DECISAO`, com uma trava por CRM/UF:
    `pg_advisory_xact_lock`). Dois cadastros do mesmo CRM começados juntos (o tíquete espera o código por até 30 min)
    não viram os dois verificados: o segundo a confirmar o código nasce pendente, sem fonte, e os administradores
    recebem o aviso.
- **Limites** (o Validar responde se um CPF e uma data de nascimento são do médico de um CRM; sem eles, o cadastro
  público viraria um jeito de descobrir a data de um médico):
  - **Por CRM/UF, de qualquer IP:** no máximo 5 conferências no CFM a cada 24 h (`server.CRM_TENTATIVAS`), contadas no
    banco (`cfm_tentativas`, migração `0018`; vale entre processos). Passou disso, o cadastro fica **pendente** sem
    chamar o CFM, e a resposta é a mesma com a data certa ou errada.
  - **Por IP:** balde `cfm`, 10 por hora. IPv6 conta pelo prefixo **/64** (trocar de endereço dentro dele não ganha um
    limite novo); vale para todos os baldes.
  - Valem também no cadastro pelo Google (`/auth/google/registro`).
  - Não adotado: chamar o CFM só depois do código de e-mail. A decisão do dono é recusar antes de mandar o código
    (nada é criado nem enviado num cadastro recusado); o limite por CRM já tira o oráculo.
- **Chave recusada (3010):** vai para o log e avisa os administradores por e-mail (no máximo a cada 12 h por
  processo): é sinal de chave colada errada ou contrato vencido.

### CRM e UF
- **Máscaras:** CPF `000.000.000-00`; nascimento `DD/MM/AAAA`; CRM só números (até 7); UF 2 letras maiúsculas.
  - O cursor fica depois do mesmo número de dígitos (apagar ou digitar no meio não o joga para o fim). Apagar logo
    depois de um ponto, barra ou traço apaga o dígito antes dele.
  - Nascimento com 1 dígito e barra: `1/5/1985` vira `01/05/1985` (digitado ou colado).
  - O nascimento (no Registro e no "Confirme seu registro") tem `autocomplete="off"`: o navegador não sugere a data
    guardada (computador da clínica, de mais de um médico). O CPF e o CRM já eram `off`.
  - CRM com mais de 7 dígitos não é cortado sem aviso: os zeros à esquerda saem (`00123456` → `123456`, como no
    servidor) e, se ainda passar de 7, aparece "Confira o CRM.".
- **Enter** (ou "Próximo" no celular) passa para o campo seguinte: Nome → CPF → Nascimento → CRM → UF. Só o Enter na UF
  manda o cadastro.
- **Erros:** curtos nas meias colunas, para caberem numa linha ("Digite a data.", "Confira o CRM."). O "Não achamos
  este CRM no CFM" fala do número e da UF: fica numa linha só embaixo dos dois, e mexer em qualquer um deles o tira.
  Cada envio limpa os erros do envio anterior.
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
      - A tela pergunta ao `/me` a cada **30 s**, só com a aba à vista: com a aba escondida, para; ao voltar, pergunta
        logo se já passaram 30 s desde a última vez (nunca mais de uma vez a cada 30 s).
      - **Liberada** (`bloqueio` vazio): vai para o app, no mesmo destino que o login daria (o `redirect` da resposta
        do login, que passou por `auth.safe_next`; depois de recarregar, o `next` da URL pela mesma regra, ou a agenda).
      - **Recusada:** mostra a recusa e para de perguntar. **Sessão que acabou:** volta para entrar.
      - **Banco fora do ar:** o `/me` responde `503` (não diz que a sessão acabou) e a tela confere de novo em 30 s.
      - No teste ponta a ponta, `window.OD_ESPERA_MS` encurta o intervalo (nenhum link consegue mudá-lo).
    - Recusado: uma mensagem curta.
  - **Rotas da API:** respondem `403 {"error": "crm_pendente" | "crm_recusado" | "crm_confirmar"}`.
- **`/me`:** devolve `bloqueio` com o motivo.
- **Login com senha e outros logins:** a resposta traz `bloqueio`, e a tela mostra a espera em vez de abrir o app.
- **Conta criada:** a página apaga o CPF, o nascimento, a senha (e a confirmação da nova senha) e o tíquete. O Voltar do
  navegador continua na espera (não reabre o Registro com o CPF à vista).
- **Voltar pelo cache do navegador:** as senhas e o CPF/nascimento da confirmação saem sempre.
  - **Cadastro em andamento** (a tela estava na senha, no Registro, no código ou na nova senha): quem saiu para ler os
    Termos ou a Política encontra a tela como deixou (o tíquete, o Google e o que já digitou).
  - **O resto** (foi para o app, saiu da espera pelo "Sair", largou o cadastro na tela inicial): o cadastro inteiro sai da
    página (nome, CPF, nascimento, CRM, UF e senha) e o `/me` é conferido de novo; sem sessão, a tela inicial (o Voltar
    seguinte não reabre a espera).
- **Resposta que chega depois de a pessoa mudar algo** (`aqui()` na página): toda resposta só mexe na tela se ela
  continua na mesma etapa, com o mesmo e-mail (no Criar conta, com a mesma senha e os mesmos campos; no código, com o
  mesmo tíquete). Ex.: tocou a
  seta enquanto o CFM conferia e trocou a senha: o código não abre com a senha antiga, e a tela pede "Criar conta" de
  novo. Login concluído vale sempre (a sessão já existe). O tíquete que vence com a pessoa já no Registro mostra o aviso
  ali; em outra etapa, só é descartado. A seta que desiste do Google apaga o Registro (ele não volta).
- **Contas anteriores a esta regra** (`crm_status` vazio; as 3 que existiam): seguem exatamente como antes.

## Aprovação à mão (administradores)
- **Quem é administrador:** a variável **`ADMIN_EMAILS`** no Render.
  - E-mails separados por vírgula, comparados em minúsculas. Aspas em volta (da lista ou de cada e-mail) são ignoradas.
  - Nenhum e-mail fica no código. Sem a variável, ninguém é administrador.
- **A página `/opendoctor-cadastros.html`:**
  - Privada: exige login, e as rotas conferem se é administrador (403 para os outros).
  - **Lista os pendentes:** nome, e-mail, CRM/UF, data do pedido e alerta de CRM repetido.
  - **Lista "Aprovados à mão, sem confirmação no CFM"** (veja abaixo): nome, e-mail, CRM/UF, data da aprovação e as
    confirmações que não bateram nas últimas 24 h (com o aviso de limite do dia).
  - Cada lista mostra até 200 contas, as mais antigas primeiro (`server.ADMIN_LISTA`). Com mais, a página avisa
    ("Mostrando os 200…") e, ao esvaziar a lista, pede para recarregar em vez de dizer que não há outro.
  - Nome e e-mail entram como texto (`textContent`), nunca como HTML.
  - **Link** para a busca pública do CFM (https://portal.cfm.org.br/busca-medicos/), para conferir à mão.
- **Aprovar / Recusar:**
  - `POST /admin/cadastros/aprovar | recusar` com `{"id"}` (JSON).
  - Só muda uma conta que ainda está pendente: dois cliques não decidem duas vezes.
  - Grava `crm_fonte = 'manual'`.
  - Recusar apaga a agenda conectada no cadastro pelo Google (a falha só vai para o log).
- **E-mails (Resend):**
  - **Aos administradores**, a cada cadastro pendente: só o nome e o CRM/UF do médico. Um a um: o endereço que o
    Resend recusa não impede os outros. O nome digitado não vira link, neste e em todo e-mail (a saudação do código
    também): um espaço de largura zero depois de cada ponto.
  - **Ao médico**, quando é aprovado (conta liberada) ou recusado. Com a chave do CFM, a aprovação diz que o 1º acesso
    confirma o CPF e o nascimento (`crm_aprovado_confirmar`), em vez de "já pode usar".
  - A falha do e-mail não desfaz a decisão.

## Contas aprovadas à mão, quando a chave chegar
- **O problema:** o CPF não foi guardado. Quando `CFM_CHAVE` passar a existir, quem tem `crm_fonte = 'manual'` precisa
  confirmar no CFM.
- **Quando:** **no login** seguinte à chegada da chave, a tela pede **uma vez** o CPF e o nascimento (passo "Confirme
  seu registro"). O pedido fica marcado na sessão (`cc` no cookie assinado, `server._cc_ao_entrar`): a sessão que já
  estava aberta quando a chave chegou continua (o médico no meio do atendimento não perde a agenda nem o prontuário).
  - **Pendente aprovado com a chave no ar:** a sessão que nasce numa conta pendente, com a chave já configurada, também
    leva a marca. Se um administrador aprova a conta com essa sessão aberta (na espera), a tela passa para "Confirme seu
    registro" antes de abrir o app: a aprovação confere o nome e o CRM, não o CPF (o cadastro pode ter ficado pendente
    justamente pelo limite de CPFs que não bateram).
- **Como:** `POST /auth/crm/confirmar` roda o Validar.
  - **`true`:** `crm_fonte = 'cfm'`, a sessão perde a marca e o app abre.
  - **`false`:** pelo manual, o Validar responde `false` também com a chave errada ou vencida (sem código). Por isso o
    `false` é conferido com o **Consultar**, com a mesma chave:
    - **o Consultar respondeu** (o médico, ou "CRM não encontrado"): a chave é boa, então não bateu. A mensagem
      aparece e o pedido continua até dar certo. Limite **por conta** (não por IP: os colegas da mesma clínica não gastam
      o dela): 5 que não bateram a cada 24 h (`server.CONF_FALHAS`, no banco); passou, a tela pede para tentar no dia
      seguinte;
    - **o Consultar não respondeu** (3010 e os outros abaixo): como o CFM sem responder.
  - **O CFM não respondeu** (fora do ar, erro passageiro repetido, chave inválida ou vencida — 3010): a conta já foi
    aprovada por um administrador, então **esta sessão segue** (resposta `adiado`); o pedido volta no próximo login.
    O 3010 avisa os administradores e não gasta o limite da conta.
- **A saída para quem ficou preso:** se o Validar insiste em `false` (aprovada com o CRM digitado errado, cadastro do
  CFM divergente), o administrador usa **"Liberar sem confirmar"** na página de cadastros, depois de conferir o médico por
  outro meio.
  - `POST /admin/cadastros/liberar` com `{"id"}` (JSON), só administrador (403 para os outros).
  - Grava `users.crm_dispensado_em` (migração `0019_crm_dispensado.sql`). A conta nunca mais é pedida a confirmar
    (`server._crm_a_confirmar`), e as sessões abertas dela, que nasceram com a marca `cc`, deixam de ser barradas.
  - Só conta aprovada à mão (`verificado` + `manual`); as outras respondem `409 nao_manual`. Liberar de novo não muda
    nada (fica a data da primeira).
  - A conta liberada sai da lista. Não há e-mail ao médico: o administrador avisa.
  - A lista aparece também sem a chave do CFM (com o aviso de que, por enquanto, ninguém é pedido a confirmar).

## Entrar e sair (revisto contra o servidor de verdade, 31/10)
O `scripts/preview_login.py` roda o servidor de verdade contra o banco de testes, com o Google, o CFM e o e-mail simulados
(veja o docstring); foi com ele que o login e o cadastro foram testados de ponta a ponta. O que mudou:
- **Bloqueio por senhas erradas** (5 → 15 min, por conta): o aparelho de onde a conta já entrou (cookie `od_dev`,
  `db.device_known`) entra com a senha certa durante o bloqueio. Quem sabe só o e-mail não tranca o médico; de outro
  aparelho, ou com a senha errada, a mesma resposta "bloqueado", sem contar mais erro. O aparelho é conferido antes da
  senha: de um aparelho desconhecido o hash nem é calculado, e o tempo da resposta não diz se a senha confere.
- **Códigos por e-mail** (nova senha e cadastro): de um IP só, 5 por hora para o mesmo e-mail (`codigo_email`, que só
  conta o pedido que enviou); o teto do e-mail é 10 por hora (`db.CODE_MAX_PER_HOUR`). Na nova senha, o aparelho
  conhecido da conta fica fora dos dois (os 30 s continuam). Os 30 s entre envios contam do último código que ainda dá
  para usar: o usado e o que acabou nas tentativas não seguram o novo. A mensagem do limite não acusa a pessoa.
- **Chutes no código:** além das 5 por código, as erradas somadas de todos os códigos do e-mail: 25 por hora e 50 por
  dia (`db.CODE_MAX_WRONG_PER_*`); passou disso, nem o código certo vale ("Muitas tentativas erradas para este
  e-mail…", `tentativas_email`). Mais códigos não dão mais chutes.
- **Tela do código:** o código errado esvazia as 6 caixas (redigitar não manda códigos misturados); "Editar" corrige o
  e-mail; o Reenviar que o servidor segurou diz quanto falta.
- **Regras da senha** iguais na tela e no servidor (emoji conta 1; "²" não é número; "ª" não é minúscula), e o
  `senha_fraca` pinta a lista com o que o servidor recusou.
- **Conta só Google que cria a 1ª senha:** o aviso é "Uma senha foi criada…" (`created`), não "alterada".
- **Sair** (`GET /auth/logout`): vindo de outro site (`Sec-Fetch-Site` cross-site/same-site) não desloga nem apaga os
  rascunhos (Clear-Site-Data). O do próprio site apaga a sessão, o `od_greg`, o `od_oauth` e o `od_oauth_cal`.
- **Destino depois de entrar** (`auth.safe_next` e o `safeNext` da página): o caminho decodificado, sem "." nem "..",
  sem controle, nunca `/auth/` (o navegador resolve `/./auth/logout` para o `/auth/logout`).
- **Computador compartilhado:** o que a agenda guarda no aparelho (o prontuário aberto, as conversas do assistente, os
  rascunhos) é da conta que guardou (`localStorage.od_uid`); outra conta que entra no navegador não o vê (sai do
  aparelho antes de as telas lerem). O que foi guardado antes desta versão não tem dono: as conversas e o prontuário
  aberto saem na 1ª abertura; os rascunhos ficam (só abrem no paciente deles, que é de uma conta só). E o servidor não cria pelo nome o paciente cujo id é de outro médico
  (`db.patient_id_exists`): só o id que não é de ninguém (excluído) cai no nome.
- **CSP:** de fora, só o arquivo exato do mermaid (nunca o host inteiro do CDN). Todas as páginas declaram o ícone
  (`/assets/login/logo-simbolo.svg`), e o navegador não pede o `/favicon.ico`, que é privado.

## O que é guardado (e o que não é)
- **Guardado em `users` (migração `0017_crm.sql`):**
  - `name`, `crm`, `crm_uf`;
  - `crm_status`: NULL = conta antiga; `pendente` | `verificado` | `recusado`;
  - `crm_fonte`: `cfm` | `manual`;
  - `crm_situacao` (a letra do CFM), `crm_verificado_em`, `crm_pedido_em`.
- **`users.crm_dispensado_em` (migração `0019_crm_dispensado.sql`):** quando um administrador liberou a conta aprovada à
  mão sem a confirmação no CFM (NULL = não liberada). Não sai em `/me`.
- **Contador `cfm_tentativas` (migração `0018_cfm_tentativas.sql`, RLS ligado):** só a chave (`crm:UF:NUMERO` ou
  `conf:<id da conta>`) e a hora. Limpo depois de 2 dias (`db.RETENTION`).
- **Não guardado:** CPF e data de nascimento. Vão só ao CFM, no corpo do SOAP. Não entram em banco, log, tíquete
  assinado, cookie nem e-mail.
- **Log do CFM (`app/cfm.py`):** só a operação, o código de erro e o tempo. Nunca a chave, o CPF ou o nascimento.
- **CRM conferido** (`crm_status = 'verificado'`): não muda em Configurações, porque vai na receita. Contas antigas O nome também não muda (foi conferido junto, e vai com o CRM na receita).
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
- **Leitura:** campo que falta não vem. Só as tags conhecidas são lidas, pelo nome. Só UTF-8, e o próprio parser
  (expat) recusa DOCTYPE e entidades, em qualquer codificação (não é uma busca de bytes, que um UTF-16 escaparia).

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
- **Banco primeiro:** aplicar `0017_crm.sql` e `0018_cfm_tentativas.sql` no banco de produção **antes** de subir o
  código.
  - `get_user` já lê as colunas novas: sem elas, ninguém entra. O cadastro com a chave usa `cfm_tentativas`.
  - As migrações são aditivas (`add column if not exists`, `create table if not exists`).
- **`0019_crm_dispensado.sql` (o dono aplica em produção ANTES de subir o código desta versão):**
  - SQL: `alter table users add column if not exists crm_dispensado_em timestamptz;` (aditiva, sem dado, sem tabela
    nova).
  - Se o código subir antes, nada quebra: o servidor confere se a coluna existe (`db.tem_dispensa`; "não" é conferido
    de novo a cada minuto) e, sem ela, lê o usuário como antes. Ninguém fica liberado, e "Liberar sem confirmar"
    responde `503 migracao_pendente` (a página avisa e deixa o botão desligado). Aplicada a migração, passa a valer
    sozinho, sem reiniciar.
- **Ordem:** primeiro no banco de testes, depois em produção.
- **Depois de publicar:** definir `ADMIN_EMAILS` no Render, para receber os avisos e abrir a página de cadastros.

## Testes
- **`tests/test_cadastro_crm.py`:**
  - cliente do CFM com respostas XML prontas;
  - cadastro verificado, pendente e recusado;
  - Google, inclusive o e-mail não verificado pelo Google (recusado na conta que existe e na nova; verificado segue
    igual), o `email_verified`/`verified_email` lido do userinfo e do `id_token`, e o cookie do Registro sem a marca;
  - a agenda depois do Registro pelo Google: a URL (só os parâmetros da conexão, nada do Registro), o state e o
    cookie; a volta conectada (`bemvindo=agenda`), na conta pendente (a espera com o destino) e sem a permissão
    (cancelou, desmarcou, erro, outro navegador, prazo vencido: `bemvindo=1`, nada gravado); a recusa antes e durante a
    troca; recusar apaga a conexão, aprovar não; o `bemvindo` fora do `next` (`tests/test_login.py`);
  - a espera;
  - confirmação (pedida no login; CFM sem responder deixa a sessão seguir; limite por conta);
  - "Liberar sem confirmar": só administrador (403), só conta aprovada à mão (409), de novo sem mudar nada, a sessão
    barrada que volta a usar o app, o login sem o pedido e o servidor sem a migração 0019 (login como antes, 503);
  - limites por CRM (qualquer IP) e por IP (IPv6 pelo /64); CRM repetido decidido na hora de criar;
  - nome com apóstrofo, sufixo, acento separado (NFD) e o primeiro nome repetido; XML com DTD em UTF-16;
  - página de cadastros (com o e-mail);
  - nascimento com `autocomplete="off"`;
  - trava do CRM em Configurações.
- **`tests/test_db_integration.py`:** no banco de testes, inclusive dois cadastros do mesmo CRM ao mesmo tempo (um só
  fica verificado), o contador `cfm_tentativas`, o e-mail na lista de pendentes e a liberação sem confirmar (lista dos
  aprovados à mão com as falhas, só conta aprovada à mão, a data da primeira liberação fica) e a limpeza que tira a
  agenda só da conta recusada.
  - A 0019 vai ao banco de testes sozinha (o `scripts.setup_test_db` refaz todas): com as mesmas travas dele (marca de
    banco de testes, projeto diferente do de produção), aplicar só o arquivo da 0019.
- **`tests/test_laco_de_eventos.py`:** o CFM entra na lista do que só roda fora do laço.
- **`tests/test_security.py`:** as rotas novas sob `/auth/` estão revisadas; as de `/admin/` são privadas.
- **E2E:** `node tests/e2e/cadastro.mjs`. Chrome sem tela, sem servidor; `SHOT=/pasta` salva as telas.
  - A espera com o relógio curto (`OD_ESPERA_MS` = 250 ms) e a aba escondida simulada; o intervalo de verdade (30 s);
    o aviso do Google não verificado; a lista dos aprovados à mão e o "Liberar sem confirmar".
  - O Registro pelo Google vai à permissão da agenda (também a conta pendente); o Voltar dela abre o app (ou a espera,
    que liberada abre o destino) com `bemvindo=1`; a espera depois da agenda abre o destino com `bemvindo=agenda`.
    `node tests/e2e/agenda.mjs`: as boas-vindas pela agenda de verdade (`=1` e `=agenda`, com e sem agenda conectada).
- **Conftest:** zera `CFM_CHAVE`, então nenhum teste chama o CFM de verdade.
