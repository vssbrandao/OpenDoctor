-- Prescrições: o papel da receita do médico (A4 ou A5), em Configurações.
alter table users add column if not exists receita_papel text check (receita_papel in ('A4', 'A5'));
