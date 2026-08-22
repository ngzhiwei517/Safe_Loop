-- Tighten checks on an already-applied 0001 migration: NULL CHECK results must fail.

alter table briefings drop constraint if exists briefings_body_check;
alter table quiz_questions drop constraint if exists quiz_questions_question_check;
alter table quiz_questions drop constraint if exists quiz_questions_explanation_check;
alter table quiz_questions drop constraint if exists quiz_questions_options_check;

alter table briefings add constraint briefings_body_has_en check (
  (jsonb_typeof(body->'en') = 'string' and btrim(body->>'en') <> '') is true
);

alter table quiz_questions add constraint quiz_question_has_en check (
  (jsonb_typeof(question->'en') = 'string' and btrim(question->>'en') <> '') is true
);

alter table quiz_questions add constraint quiz_explanation_has_en check (
  (jsonb_typeof(explanation->'en') = 'string' and btrim(explanation->>'en') <> '') is true
);

alter table quiz_questions add constraint quiz_options_have_en check (
  jsonb_options_have_en(options) is true
);
