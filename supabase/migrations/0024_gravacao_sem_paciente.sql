-- Gravação sem paciente (decisão do usuário de 19/11/2026; docs/gravacao.md): na tela "Nova consulta" o médico grava
-- ANTES de escolher o paciente. A gravação fica no servidor com patient_id nulo até o médico ligar um paciente dele
-- (durante ou depois de gravar; POST /prontuario/recordings/patient, só de nulo para um paciente, nunca de um para outro).
-- sem_paciente = a gravação começou sem paciente: fica true para sempre, mesmo depois de ligada. Nessa gravação nunca há
-- rótulo de quem fala (sem o nome o texto não pode ser mascarado antes do rotulador: CLAUDE.md, regra 3) e o envio dos
-- trechos e do áudio sem X-Patient-Id continua aceito depois de ligar (trechos cortados antes chegam sem o cabeçalho).
-- O índice parcial lista as gravações do médico ainda sem paciente. Continua tudo filtrado por user_id no servidor.
-- O app funciona sem esta migração (db.tem_sem_paciente): só a gravação sem paciente responde 503 até ela existir.
-- Tirar o "not null" relaxa uma regra (não apaga nada) e é idempotente; a FK e a cascata de patients ficam.
-- Aplicada primeiro no banco de testes (python -m scripts.setup_test_db); em produção só com o ok do usuário.
alter table recordings alter column patient_id drop not null;
alter table recordings add column if not exists sem_paciente boolean not null default false;
create index if not exists recordings_sem_paciente_idx on recordings (user_id, created_at) where patient_id is null;
alter table recordings enable row level security;
