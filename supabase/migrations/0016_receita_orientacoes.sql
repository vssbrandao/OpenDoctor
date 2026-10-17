-- Orientações ao paciente na receita (aba Prescrições): o texto livre do bloco da receita, fora dos remédios
-- ("Beber bastante água"). Sai na folha impressa, abaixo dos remédios; ao emitir, vai junto em cada receita emitida.
alter table receitas add column if not exists orientacoes text not null default '';
