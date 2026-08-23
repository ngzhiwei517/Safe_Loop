-- Stable local demo identities. These placeholder Auth rows intentionally have
-- no password or identity; browser-test users are created through the Auth admin
-- API so this seed does not depend on Auth's private password schema.
insert into auth.users (id, email, raw_user_meta_data) values
  ('00000000-0000-0000-0000-000000000001', 'reporter-en@example.test', '{"full_name":"Worker Tan"}'::jsonb),
  ('00000000-0000-0000-0000-000000000002', 'reporter-zh@example.test', '{"full_name":"王师傅"}'::jsonb),
  ('00000000-0000-0000-0000-000000000003', 'reviewer@example.test', '{"full_name":"Lim Wei Sheng"}'::jsonb),
  ('00000000-0000-0000-0000-000000000004', 'responsible@example.test', '{"full_name":"Ah Hock"}'::jsonb),
  ('00000000-0000-0000-0000-000000000005', 'crew@example.test', '{"full_name":"Crew Member"}'::jsonb),
  ('00000000-0000-0000-0000-000000000006', 'admin@example.test', '{"full_name":"Site Admin"}'::jsonb)
on conflict (id) do update set
  email = excluded.email,
  raw_user_meta_data = excluded.raw_user_meta_data;

insert into profiles (id, role, preferred_lang) values
  ('00000000-0000-0000-0000-000000000001', 'reporter', 'en'),
  ('00000000-0000-0000-0000-000000000002', 'reporter', 'zh-CN'),
  ('00000000-0000-0000-0000-000000000003', 'reviewer', 'en'),
  ('00000000-0000-0000-0000-000000000004', 'responsible', 'en'),
  ('00000000-0000-0000-0000-000000000005', 'crew', 'en'),
  ('00000000-0000-0000-0000-000000000006', 'admin', 'en')
on conflict (id) do update set role = excluded.role, preferred_lang = excluded.preferred_lang;
