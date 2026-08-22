-- Stable local demo identities; authentication is wired in a later phase.
insert into profiles (id, role, preferred_lang) values
  ('00000000-0000-0000-0000-000000000001', 'reporter', 'en'),
  ('00000000-0000-0000-0000-000000000002', 'reporter', 'zh-CN'),
  ('00000000-0000-0000-0000-000000000003', 'reviewer', 'en'),
  ('00000000-0000-0000-0000-000000000004', 'responsible', 'en'),
  ('00000000-0000-0000-0000-000000000005', 'crew', 'en'),
  ('00000000-0000-0000-0000-000000000006', 'admin', 'en')
on conflict (id) do update set role = excluded.role, preferred_lang = excluded.preferred_lang;
