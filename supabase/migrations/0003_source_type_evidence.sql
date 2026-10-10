-- Amplia os valores de documents.source_type para o nível de evidência
-- derivado do PublicationType do PubMed (usado no rerank e no selo de evidência).
-- Idempotente: pode rodar mais de uma vez.

begin;

alter table public.documents
  drop constraint if exists documents_source_type_check;

alter table public.documents
  add constraint documents_source_type_check
  check (source_type in (
    'guideline', 'protocol', 'article',
    'meta-analysis', 'systematic-review', 'rct',
    'secondary-analysis', 'observational', 'review'
  ));

commit;
