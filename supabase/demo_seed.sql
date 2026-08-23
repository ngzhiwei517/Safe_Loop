-- SafeLoop's deterministic, rerunnable demonstration site.
-- Run after migrations and seed.sql. All IDs are fixed so ON CONFLICT can make
-- the script safe to repeat without updating append-only workflow evidence.

begin;

-- Make the six base identities usable through Supabase email/password Auth.
-- These credentials are for local/demo projects only and must never be loaded
-- into a production project that contains real users or reports.
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

update auth.users
set instance_id = '00000000-0000-0000-0000-000000000000',
    aud = 'authenticated',
    role = 'authenticated',
    encrypted_password = extensions.crypt(
      'SafeLoopDemo!2026',
      extensions.gen_salt('bf')
    ),
    email_confirmed_at = coalesce(email_confirmed_at, now()),
    confirmation_token = coalesce(confirmation_token, ''),
    recovery_token = coalesce(recovery_token, ''),
    email_change_token_new = coalesce(email_change_token_new, ''),
    email_change = coalesce(email_change, ''),
    phone_change = coalesce(phone_change, ''),
    phone_change_token = coalesce(phone_change_token, ''),
    email_change_token_current = coalesce(email_change_token_current, ''),
    reauthentication_token = coalesce(reauthentication_token, ''),
    raw_app_meta_data = '{"provider":"email","providers":["email"]}'::jsonb,
    created_at = coalesce(created_at, now()),
    updated_at = now()
where id in (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000004',
  '00000000-0000-0000-0000-000000000005',
  '00000000-0000-0000-0000-000000000006'
);

insert into auth.identities (
  user_id, provider_id, identity_data, provider,
  last_sign_in_at, created_at, updated_at
)
select
  user_row.id,
  user_row.id::text,
  jsonb_build_object(
    'sub', user_row.id::text,
    'email', user_row.email,
    'email_verified', true,
    'phone_verified', false
  ),
  'email',
  now(),
  now(),
  now()
from auth.users user_row
where user_row.id in (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000004',
  '00000000-0000-0000-0000-000000000005',
  '00000000-0000-0000-0000-000000000006'
)
on conflict (provider_id, provider) do nothing;

insert into public.profiles (
  id, role, preferred_lang, display_name, is_on_duty
) values
  ('00000000-0000-0000-0000-000000000001', 'reporter', 'en', 'Worker Tan', true),
  ('00000000-0000-0000-0000-000000000002', 'reporter', 'zh-CN', '王师傅', true),
  ('00000000-0000-0000-0000-000000000003', 'reviewer', 'en', 'Lim Wei Sheng', true),
  ('00000000-0000-0000-0000-000000000004', 'responsible', 'en', 'Ah Hock', true),
  ('00000000-0000-0000-0000-000000000005', 'crew', 'en', 'Crew Member', true),
  ('00000000-0000-0000-0000-000000000006', 'admin', 'en', 'Site Admin', true)
on conflict (id) do update set
  role = excluded.role,
  preferred_lang = excluded.preferred_lang,
  display_name = excluded.display_name,
  is_on_duty = excluded.is_on_duty;

create temporary table demo_report_data (
  seq smallint primary key,
  final_status text not null,
  urgency_value text not null,
  reporter_id uuid not null,
  lang_original text not null,
  description_original text not null,
  description_en text,
  location_text text not null,
  activity text not null,
  age_days integer not null,
  is_confidential boolean not null default false
) on commit drop;

insert into demo_report_data values
  (1, 'draft', 'low', '00000000-0000-0000-0000-000000000001', 'en', 'Loose packaging is collecting beside the loading-bay walkway.', null, 'Loading Bay East', 'Housekeeping', 1, false),
  (2, 'draft', 'critical', '00000000-0000-0000-0000-000000000002', 'zh-CN', 'A座十二层边缘没有护栏，有人正在附近工作。', 'The edge at Tower A level 12 has no guardrail and people are working nearby.', 'Tower A Level 12', 'Work at height', 1, false),
  (3, 'draft', 'medium', '00000000-0000-0000-0000-000000000001', 'en', 'Water is pooling near the temporary stairs after rain.', null, 'Tower B Ground Floor', 'Access route', 2, true),
  (4, 'submitted', 'high', '00000000-0000-0000-0000-000000000001', 'en', 'A mobile scaffold wheel brake does not hold.', null, 'Tower C Level 4', 'Scaffold inspection', 1, false),
  (5, 'submitted', 'medium', '00000000-0000-0000-0000-000000000002', 'zh-CN', '配电箱前面堆着材料，通道被挡住。', 'Materials are stacked in front of the distribution board and block access.', 'Basement Electrical Room', 'Electrical maintenance', 2, false),
  (6, 'submitted', 'low', '00000000-0000-0000-0000-000000000001', 'en', 'A damaged traffic cone is no longer visible to reversing drivers.', null, 'North Vehicle Gate', 'Vehicle movement', 3, false),
  (7, 'clarifying', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '吊装区有东西不对。', 'Something is wrong in the lifting area.', 'Tower B Lifting Zone', 'Lifting', 2, false),
  (8, 'clarifying', 'medium', '00000000-0000-0000-0000-000000000001', 'en', 'The excavation access looks unsafe.', null, 'South Excavation', 'Excavation', 3, false),
  (9, 'clarifying', 'medium', '00000000-0000-0000-0000-000000000002', 'zh-CN', '脚手架旁边有松动的东西。', 'There is something loose beside the scaffold.', 'Tower A Level 7', 'Scaffold inspection', 4, false),
  (10, 'ai_drafted', 'medium', '00000000-0000-0000-0000-000000000001', 'en', 'An extension lead crosses the wet wash area.', null, 'Welfare Block', 'Electrical maintenance', 3, false),
  (11, 'ai_drafted', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '洞口盖板没有固定，也没有标签。', 'The opening cover is unsecured and has no label.', 'Tower D Level 3', 'Work at height', 4, false),
  (12, 'ai_drafted', 'low', '00000000-0000-0000-0000-000000000001', 'en', 'Scrap timber with nails is mixed into the walkway waste.', null, 'Fabrication Yard', 'Housekeeping', 5, false),
  (13, 'under_review', 'critical', '00000000-0000-0000-0000-000000000002', 'zh-CN', '临边护栏被拆掉，开口就在楼梯出口旁。', 'The edge guardrail was removed and the opening is beside the stair exit.', 'Tower B Level 16', 'Work at height', 1, false),
  (14, 'under_review', 'high', '00000000-0000-0000-0000-000000000001', 'en', 'A lifting sling has a visible cut near its eye.', null, 'Tower C Lifting Zone', 'Lifting', 2, false),
  (15, 'under_review', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '挖土机作业时，行人还在回转范围内走动。', 'Pedestrians are walking inside the excavator swing area during operation.', 'South Excavation', 'Excavation', 3, false),
  (16, 'under_review', 'medium', '00000000-0000-0000-0000-000000000001', 'en', 'The temporary lighting cable has exposed inner insulation.', null, 'Basement Ramp', 'Electrical maintenance', 4, true),
  (17, 'under_review', 'low', '00000000-0000-0000-0000-000000000001', 'en', 'Dusty offcuts narrow the marked pedestrian route.', null, 'Fabrication Yard', 'Housekeeping', 6, false),
  (18, 'rejected', 'low', '00000000-0000-0000-0000-000000000001', 'en', 'A permanent wall mark looks like a crack from a distance.', null, 'Tower A Lobby', 'Inspection', 12, false),
  (19, 'rejected', 'medium', '00000000-0000-0000-0000-000000000002', 'zh-CN', '照片里的电缆属于已封闭的旧工作区。', 'The cable in the photo belongs to an old area that is already closed.', 'Old Site Office', 'Inspection', 14, false),
  (20, 'info_requested', 'high', '00000000-0000-0000-0000-000000000001', 'en', 'A worker is using an access platform that appears incomplete.', null, 'Tower D Level 9', 'Work at height', 5, false),
  (21, 'info_requested', 'medium', '00000000-0000-0000-0000-000000000002', 'zh-CN', '有人把化学品桶放在没有标签的托盘上。', 'Chemical drums were placed on an unlabelled tray.', 'Chemical Store', 'Material storage', 7, false),
  (22, 'escalated', 'critical', '00000000-0000-0000-0000-000000000001', 'en', 'Workers entered below a suspended load while lifting continued.', null, 'Tower A Lifting Zone', 'Lifting', 2, false),
  (23, 'escalated', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '分包商重复拆除电梯井口护栏。', 'A subcontractor repeatedly removed the lift-shaft guardrail.', 'Tower C Level 11', 'Work at height', 4, false),
  (24, 'action_assigned', 'critical', '00000000-0000-0000-0000-000000000001', 'en', 'The same edge protection has failed two verification checks.', null, 'Tower A Level 12', 'Work at height', 12, false),
  (25, 'action_assigned', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '脚手架通道退回后仍需要重新固定踢脚板。', 'The scaffold access still needs its toe board secured after being sent back.', 'Tower B Level 8', 'Scaffold inspection', 10, false),
  (26, 'action_assigned', 'high', '00000000-0000-0000-0000-000000000001', 'en', 'The assigned lockout labels are overdue for installation.', null, 'Basement Electrical Room', 'Electrical maintenance', 8, false),
  (27, 'action_assigned', 'medium', '00000000-0000-0000-0000-000000000002', 'zh-CN', '材料通道需要重新划线并清空。', 'The material route needs to be remarked and cleared.', 'Loading Bay West', 'Housekeeping', 5, false),
  (28, 'action_assigned', 'low', '00000000-0000-0000-0000-000000000001', 'en', 'A replacement convex mirror has been assigned for the blind corner.', null, 'South Vehicle Gate', 'Vehicle movement', 4, false),
  (29, 'action_submitted', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '电箱隔离整改已重新提交，等待复查。', 'The electrical isolation correction was resubmitted and awaits verification.', 'Tower D Plant Room', 'Electrical maintenance', 14, false),
  (30, 'action_submitted', 'medium', '00000000-0000-0000-0000-000000000001', 'en', 'A new excavation ladder and landing have been submitted for checking.', null, 'South Excavation', 'Excavation', 9, false),
  (31, 'action_submitted', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '吊装隔离区已经扩大，现场证据已提交。', 'The lifting exclusion zone was enlarged and evidence was submitted.', 'Tower B Lifting Zone', 'Lifting', 7, false),
  (32, 'action_submitted', 'medium', '00000000-0000-0000-0000-000000000001', 'en', 'The repaired scaffold access gate is ready for verification.', null, 'Tower C Level 6', 'Scaffold inspection', 6, false),
  (33, 'verified_closed', 'critical', '00000000-0000-0000-0000-000000000001', 'en', 'Open edge protection failed twice before a fixed guardrail passed verification.', null, 'Tower A Level 12', 'Work at height', 80, false),
  (34, 'verified_closed', 'medium', '00000000-0000-0000-0000-000000000002', 'zh-CN', '地下室行人通道已与车辆路线完全分开。', 'The basement pedestrian route was fully separated from vehicle traffic.', 'Basement Ramp', 'Vehicle movement', 65, false),
  (35, 'lesson_drafted', 'high', '00000000-0000-0000-0000-000000000001', 'en', 'A damaged lifting sling was removed and the lifting team checked the full set.', null, 'Tower C Lifting Zone', 'Lifting', 50, false),
  (36, 'lesson_drafted', 'medium', '00000000-0000-0000-0000-000000000002', 'zh-CN', '挖沟通道安装了固定梯子和防滑平台。', 'A fixed ladder and non-slip landing were installed at the trench access.', 'South Excavation', 'Excavation', 40, false),
  (37, 'lesson_drafted', 'high', '00000000-0000-0000-0000-000000000001', 'en', 'A damaged distribution-board lead was isolated and replaced.', null, 'Tower D Plant Room', 'Electrical maintenance', 35, false),
  (38, 'lesson_published', 'critical', '00000000-0000-0000-0000-000000000002', 'zh-CN', '临边护栏第一次复查不合格，补强后通过并发布了班前简报。', 'The edge guardrail failed its first check, passed after reinforcement, and became a toolbox briefing.', 'Tower A Level 12', 'Work at height', 60, false),
  (39, 'lesson_published', 'high', '00000000-0000-0000-0000-000000000001', 'en', 'A scaffold access gate was repaired, verified, and shared as a crew lesson.', null, 'Tower B Level 8', 'Scaffold inspection', 30, false),
  (40, 'lesson_published', 'high', '00000000-0000-0000-0000-000000000002', 'zh-CN', '配电箱完成上锁挂牌，复查通过后发布双语简报。', 'The distribution board was locked and tagged, verified, and published as a bilingual briefing.', 'Basement Electrical Room', 'Electrical maintenance', 20, false);

insert into public.reports (
  id, human_ref, reporter_id, status, urgency, lang_original, input_mode,
  description_original, description_en, location_text, activity,
  is_confidential, submitted_at, closed_at, clarify_rounds,
  missing_information, created_at, updated_at
)
select
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  'SL-' || to_char(now(), 'YYYY') || '-' || lpad((10000 + seq)::text, 5, '0'),
  reporter_id,
  final_status::report_status,
  urgency_value::urgency,
  lang_original,
  'typed'::input_mode,
  description_original,
  description_en,
  location_text,
  activity,
  is_confidential,
  case when final_status <> 'draft' then date_trunc('day', now()) - make_interval(days => age_days) + interval '9 hours' end,
  case
    when seq = 33 then date_trunc('day', now()) - make_interval(days => age_days) + interval '83 hours'
    when seq = 38 then date_trunc('day', now()) - make_interval(days => age_days) + interval '58 hours'
    when final_status in ('verified_closed', 'lesson_drafted', 'lesson_published')
      then date_trunc('day', now()) - make_interval(days => age_days) + interval '34 hours'
  end,
  case when final_status = 'clarifying' then 1 else 0 end,
  case
    when final_status = 'clarifying' then '["hazard_detail"]'::jsonb
    when seq = 10 then '["safe_distance", "equipment_owner"]'::jsonb
    else '[]'::jsonb
  end,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '8 hours',
  now()
from demo_report_data
on conflict (id) do nothing;

-- Two explicitly approved procedure revisions back every cited demo action.
insert into public.documents (
  id, title, doc_ref, revision, is_approved, effective_from,
  mime_type, uploaded_by, approved_by, approved_at, created_at
) values
  (
    '62000000-0000-4000-8000-000000000001',
    'Work at Height and Edge Protection Procedure',
    'SOP-WAH-001', '3', true, now() - interval '365 days',
    'application/pdf',
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000003',
    now() - interval '360 days', now() - interval '370 days'
  ),
  (
    '62000000-0000-4000-8000-000000000002',
    'Electrical Isolation and Lockout Procedure',
    'SOP-ELEC-004', '2', true, now() - interval '300 days',
    'application/pdf',
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000003',
    now() - interval '295 days', now() - interval '305 days'
  )
on conflict (id) do nothing;

insert into public.document_chunks (
  id, document_id, chunk_index, section, page, content, embedding, created_at
) values
  (
    '62100000-0000-4000-8000-000000000001',
    '62000000-0000-4000-8000-000000000001', 0, '4.2 Edge protection', 4,
    'Install a secured guardrail before work resumes. The top rail, mid rail and toe board must remain fixed while the edge is open.',
    null, now() - interval '360 days'
  ),
  (
    '62100000-0000-4000-8000-000000000002',
    '62000000-0000-4000-8000-000000000001', 1, '5.1 Scaffold access', 7,
    'Keep scaffold access gates self-closing and secure every toe board before the scaffold is released for use.',
    null, now() - interval '360 days'
  ),
  (
    '62100000-0000-4000-8000-000000000003',
    '62000000-0000-4000-8000-000000000002', 0, '3.1 Isolation', 3,
    'Isolate and lock out the energy source before maintenance starts. Each worker verifies zero energy before touching conductors.',
    null, now() - interval '295 days'
  ),
  (
    '62100000-0000-4000-8000-000000000004',
    '62000000-0000-4000-8000-000000000002', 1, '3.4 Restoration', 5,
    'Only the authorised person removes a lock and restores power after the work area is checked.',
    null, now() - interval '295 days'
  )
on conflict (id) do nothing;

insert into public.clarifications (
  id, report_id, round, gap, question, created_at
)
select
  ('63500000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  1,
  'hazard_detail',
  case
    when lang_original = 'zh-CN' then '请说明哪里有危险，以及谁可能受影响。'
    else 'What is unsafe, and who could be affected?'
  end,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '11 hours'
from demo_report_data
where final_status = 'clarifying'
on conflict (id) do nothing;

insert into public.ai_drafts (
  id, report_id, version, provider, provider_ref, raw_json,
  observed_facts, assumptions, missing_information,
  proposed_category, proposed_urgency, suggested_owner_role,
  suggested_action, confidence, needs_escalation, escalation_reason,
  citations, validation, validation_errors,
  latency_ms, tokens_in, tokens_out, created_at
)
select
  ('63400000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  1,
  'stub',
  'demo-stub-' || lpad(seq::text, 2, '0'),
  jsonb_build_object('fixture', 'demo', 'report_sequence', seq),
  case when seq = 10 then '[]'::jsonb else jsonb_build_array(coalesce(description_en, description_original)) end,
  '[]'::jsonb,
  case
    when activity not in ('Work at height', 'Scaffold inspection', 'Electrical maintenance')
      then '["approved_procedure"]'::jsonb
    else '[]'::jsonb
  end,
  case
    when activity in ('Work at height', 'Scaffold inspection') then 'work at height'
    when activity = 'Electrical maintenance' then 'electrical isolation'
    when activity = 'Lifting' then 'lifting operation'
    when activity = 'Excavation' then 'excavation access'
    when activity = 'Vehicle movement' then 'vehicle segregation'
    else lower(activity)
  end,
  urgency_value::urgency,
  'responsible'::role,
  case
    when activity in ('Work at height', 'Scaffold inspection')
      then 'Install a secured guardrail before work resumes.'
    when activity = 'Electrical maintenance'
      then 'Isolate and lock out the energy source before maintenance starts.'
    else null
  end,
  case when seq = 10 then 0.35 else 0.88 end,
  final_status = 'escalated',
  case when final_status = 'escalated' then 'Immediate human escalation recorded by the reviewer.' end,
  case
    when activity in ('Work at height', 'Scaffold inspection') then jsonb_build_array(
      jsonb_build_object(
        'document_id', '62000000-0000-4000-8000-000000000001',
        'doc_ref', 'SOP-WAH-001', 'revision', '3',
        'section', '4.2 Edge protection', 'page', 4,
        'quote', 'Install a secured guardrail before work resumes.'
      )
    )
    when activity = 'Electrical maintenance' then jsonb_build_array(
      jsonb_build_object(
        'document_id', '62000000-0000-4000-8000-000000000002',
        'doc_ref', 'SOP-ELEC-004', 'revision', '2',
        'section', '3.1 Isolation', 'page', 3,
        'quote', 'Isolate and lock out the energy source before maintenance starts.'
      )
    )
    else '[]'::jsonb
  end,
  case when seq = 10 then 'invalid'::validation_status else 'valid'::validation_status end,
  case when seq = 10 then '["observed_facts_required", "confidence_below_threshold"]'::jsonb else '[]'::jsonb end,
  18 + seq,
  120 + seq,
  55 + seq,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '11 hours'
from demo_report_data
where final_status in (
  'ai_drafted', 'under_review', 'rejected', 'info_requested', 'escalated',
  'action_assigned', 'action_submitted', 'verified_closed',
  'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

insert into public.review_decisions (
  id, report_id, reviewer_id, decision, corrections,
  correction_reason, reason, created_at
)
select
  ('63300000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  '00000000-0000-0000-0000-000000000003',
  case
    when final_status = 'rejected' then 'reject'::review_decision
    when final_status = 'info_requested' then 'request_info'::review_decision
    when final_status = 'escalated' then 'escalate'::review_decision
    else 'approve'::review_decision
  end,
  case when seq in (24, 29, 33, 38, 40) then
    jsonb_build_object(
      'action', jsonb_build_object(
        'before', case
          when activity in ('Work at height', 'Scaffold inspection') then 'Install a secured guardrail before work resumes.'
          when activity = 'Electrical maintenance' then 'Isolate and lock out the energy source before maintenance starts.'
          else null
        end,
        'after', case
          when activity = 'Electrical maintenance' then 'Install lockout tags and verify zero energy before work resumes.'
          else 'Install and inspect fixed edge protection before the area reopens.'
        end
      )
    )
  end,
  case when seq in (24, 29, 33, 38, 40) then 'Reviewer made the action specific to this site location.' end,
  case
    when final_status = 'rejected' then 'The observation does not describe a current site hazard.'
    when final_status = 'info_requested' then 'The exact equipment and affected work area are required.'
    when final_status = 'escalated' then 'Work must stop until the safety lead reviews the repeated exposure.'
  end,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '16 hours'
from demo_report_data
where final_status in (
  'rejected', 'info_requested', 'escalated', 'action_assigned',
  'action_submitted', 'verified_closed', 'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

insert into public.report_assignments (
  id, report_id, assignee_id, case_role, due_at, active, created_at
)
select
  ('63000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  '00000000-0000-0000-0000-000000000004',
  'responsible'::case_role,
  case
    when seq = 24 then now() - interval '3 days'
    when seq = 25 then now() - interval '2 days'
    when seq = 26 then now() - interval '1 day'
    when final_status = 'action_assigned' then now() + make_interval(days => seq - 25)
    else date_trunc('day', now()) - make_interval(days => age_days) + interval '4 days'
  end,
  true,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '16 hours'
from demo_report_data
where final_status in (
  'action_assigned', 'action_submitted', 'verified_closed',
  'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

insert into public.corrective_actions (
  id, report_id, assignment_id, action_text, status,
  rework_count, due_at, completed_note, submitted_at, created_at
)
select
  ('63100000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  ('63000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  case
    when activity = 'Electrical maintenance' then 'Install lockout tags and verify zero energy before work resumes.'
    when activity in ('Work at height', 'Scaffold inspection') then 'Install and inspect fixed edge protection before the area reopens.'
    when activity = 'Lifting' then 'Replace damaged lifting gear and re-establish the exclusion zone.'
    when activity = 'Excavation' then 'Install a secured access ladder and a level landing.'
    when activity = 'Vehicle movement' then 'Separate the pedestrian route from moving vehicles.'
    else 'Clear and mark the access route before work resumes.'
  end,
  case
    when final_status = 'action_assigned' then 'assigned'::action_status
    when final_status = 'action_submitted' then 'submitted'::action_status
    else 'verified'::action_status
  end,
  case
    when seq in (24, 33) then 2
    when seq in (25, 29, 38) then 1
    else 0
  end,
  case
    when seq = 24 then now() - interval '3 days'
    when seq = 25 then now() - interval '2 days'
    when seq = 26 then now() - interval '1 day'
    when final_status = 'action_assigned' then now() + make_interval(days => seq - 25)
    else date_trunc('day', now()) - make_interval(days => age_days) + interval '4 days'
  end,
  case
    when final_status in ('action_submitted', 'verified_closed', 'lesson_drafted', 'lesson_published')
      or seq in (24, 25)
      then 'Completed the assigned correction and checked the work area.'
  end,
  case
    when final_status in ('action_submitted', 'verified_closed', 'lesson_drafted', 'lesson_published')
      or seq in (24, 25)
      then date_trunc('day', now()) - make_interval(days => age_days) + interval '32 hours'
  end,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '16 hours'
from demo_report_data
where final_status in (
  'action_assigned', 'action_submitted', 'verified_closed',
  'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

create temporary table demo_verification_data (
  seq smallint not null,
  cycle smallint not null,
  passed boolean not null,
  event_hours integer not null,
  reason text,
  notes text not null,
  primary key (seq, cycle)
) on commit drop;

insert into demo_verification_data values
  (24, 1, false, 26, 'The mid rail is loose at the north end.', 'The edge protection moved under the hand check.'),
  (24, 2, false, 50, 'The toe board still leaves a gap at the corner.', 'The second inspection found an open corner below the rail.'),
  (25, 1, false, 26, 'The toe board is fixed at only one end.', 'The scaffold access remains incomplete.'),
  (29, 1, false, 26, 'The isolation tag does not identify the circuit.', 'The first submission did not prove the correct circuit was isolated.'),
  (33, 1, false, 26, 'The mid rail is loose at the north end.', 'The first guardrail installation moved under load.'),
  (33, 2, false, 50, 'The toe board still leaves a gap at the corner.', 'The second installation left an open corner.'),
  (33, 3, true, 75, null, 'Fixed top rail, mid rail and toe board passed the physical inspection.'),
  (34, 1, true, 26, null, 'Pedestrian barriers and crossing signs were complete and secure.'),
  (35, 1, true, 26, null, 'The damaged sling was quarantined and the replacement set passed inspection.'),
  (36, 1, true, 26, null, 'The ladder and landing were fixed, level and clear.'),
  (37, 1, true, 26, null, 'Lockout was applied and zero energy was verified before the cable was replaced.'),
  (38, 1, false, 26, 'The guardrail base plate is not fully anchored.', 'The first installation could move at the base.'),
  (38, 2, true, 50, null, 'All anchors, rails and toe boards passed the follow-up inspection.'),
  (39, 1, true, 26, null, 'The access gate self-closed and the toe board remained secure.'),
  (40, 1, true, 26, null, 'The lockout labels matched the circuit and zero energy was confirmed.');

insert into public.verifications (
  id, report_id, corrective_action_id, reviewer_id,
  passed, checklist, notes, reason, new_due_at, created_at
)
select
  ('63200000-0000-4000-8000-' || lpad((item.seq * 10 + item.cycle)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(item.seq::text, 12, '0'))::uuid,
  ('63100000-0000-4000-8000-' || lpad(item.seq::text, 12, '0'))::uuid,
  '00000000-0000-0000-0000-000000000003',
  item.passed,
  jsonb_build_object(
    'area_safe', item.passed,
    'work_matches_action', item.passed,
    'evidence_checked', true
  ),
  item.notes,
  item.reason,
  case when not item.passed then
    date_trunc('day', now()) - make_interval(days => report.age_days)
      + make_interval(hours => item.event_hours) + interval '3 days'
  end,
  date_trunc('day', now()) - make_interval(days => report.age_days)
    + make_interval(hours => item.event_hours)
from demo_verification_data item
join demo_report_data report on report.seq = item.seq
on conflict (id) do nothing;

insert into public.closure_receipts (
  id, report_id, verification_id, corrective_action_id,
  reporter_id, reporter_locale, action_text, verification_notes,
  verified_by_id, verified_by_name, before_media_id, after_media_id, created_at
)
select
  ('64300000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  ('63200000-0000-4000-8000-' || lpad((report.seq * 10 + case when report.seq = 33 then 3 when report.seq = 38 then 2 else 1 end)::text, 12, '0'))::uuid,
  ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  report.reporter_id,
  report.lang_original,
  action.action_text,
  verification.notes,
  '00000000-0000-0000-0000-000000000003',
  'Lim Wei Sheng',
  null,
  null,
  verification.created_at
from demo_report_data report
join public.corrective_actions action
  on action.id = ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
join public.verifications verification
  on verification.id = ('63200000-0000-4000-8000-' || lpad((report.seq * 10 + case when report.seq = 33 then 3 when report.seq = 38 then 2 else 1 end)::text, 12, '0'))::uuid
where report.final_status in ('verified_closed', 'lesson_drafted', 'lesson_published')
on conflict (id) do nothing;

insert into public.briefings (
  id, report_id, version, body, status, target_activity, target_location,
  valid_from, valid_to, qr_token, approved_by, approved_at, created_at
)
select
  ('64000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  1,
  jsonb_build_object(
    'en', case
      when activity = 'Electrical maintenance' then E'## What happened\nElectrical work was exposed to an uncontrolled energy source.\n\n## Why it matters\nUnexpected power can cause fatal injury.\n\n## What to do differently\nIsolate, lock out and verify zero energy before touching conductors.'
      when activity = 'Scaffold inspection' then E'## What happened\nScaffold access protection was incomplete.\n\n## Why it matters\nAn open gate or loose toe board can expose people to a fall or falling object.\n\n## What to do differently\nCheck the gate and every toe board before releasing the scaffold.'
      else E'## What happened\nEdge protection was incomplete.\n\n## Why it matters\nAn open edge can cause a fatal fall.\n\n## What to do differently\nInstall and inspect the top rail, mid rail and toe board before work resumes.'
    end,
    'zh-CN', case
      when activity = 'Electrical maintenance' then E'## 发生了什么\n电气作业的能源没有受到控制。\n\n## 为什么重要\n意外通电可能造成致命伤害。\n\n## 以后怎么做\n接触导体前，必须隔离、上锁挂牌并确认零能量。'
      when activity = 'Scaffold inspection' then E'## 发生了什么\n脚手架通道防护不完整。\n\n## 为什么重要\n敞开的门或松动的踢脚板会造成坠落或物体打击风险。\n\n## 以后怎么做\n开放脚手架前，检查通道门和每块踢脚板。'
      else E'## 发生了什么\n临边防护不完整。\n\n## 为什么重要\n敞开的临边可能造成致命坠落。\n\n## 以后怎么做\n复工前安装并检查上栏杆、中栏杆和踢脚板。'
    end
  ),
  case when final_status = 'lesson_published' then 'published'::briefing_status else 'draft'::briefing_status end,
  activity,
  location_text,
  case when final_status = 'lesson_published' then now() - interval '14 days' end,
  case when final_status = 'lesson_published' then now() + interval '180 days' end,
  case when final_status = 'lesson_published' then 'demo-safeloop-briefing-' || lpad(seq::text, 6, '0') || '-sg' end,
  case when final_status = 'lesson_published' then '00000000-0000-0000-0000-000000000003'::uuid end,
  case when final_status = 'lesson_published' then now() - interval '14 days' end,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '40 hours'
from demo_report_data
where final_status in ('lesson_drafted', 'lesson_published')
on conflict (id) do nothing;

insert into public.quiz_questions (
  id, briefing_id, position, question, explanation,
  options, correct_option, created_at
)
select
  ('64100000-0000-4000-8000-' || lpad((report.seq * 10 + position)::text, 12, '0'))::uuid,
  ('64000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  position,
  case position
    when 1 then '{"en":"When may work restart?","zh-CN":"什么时候可以复工？"}'::jsonb
    when 2 then '{"en":"Who checks the correction?","zh-CN":"谁来检查整改？"}'::jsonb
    else '{"en":"What should a worker do when protection is missing?","zh-CN":"发现防护缺失时，工人应该怎么做？"}'::jsonb
  end,
  case position
    when 1 then '{"en":"Restart only after the assigned correction is installed and checked.","zh-CN":"只有完成并检查指定整改后，才能复工。"}'::jsonb
    when 2 then '{"en":"The named reviewer records the verification result.","zh-CN":"指定复查人记录复查结果。"}'::jsonb
    else '{"en":"Stop, keep clear and report the missing protection.","zh-CN":"停止作业、远离危险区并报告防护缺失。"}'::jsonb
  end,
  case position
    when 1 then '[{"en":"After installation and inspection","zh-CN":"安装并检查后"},{"en":"When the shift ends","zh-CN":"下班后"},{"en":"After a photo is taken","zh-CN":"拍照后"},{"en":"Whenever work is urgent","zh-CN":"工作紧急时"}]'::jsonb
    when 2 then '[{"en":"Any passer-by","zh-CN":"任何路人"},{"en":"The named reviewer","zh-CN":"指定复查人"},{"en":"Only the reporter","zh-CN":"只有报告人"},{"en":"No one","zh-CN":"不需要人"}]'::jsonb
    else '[{"en":"Continue carefully","zh-CN":"小心继续"},{"en":"Move the warning sign","zh-CN":"移动警告牌"},{"en":"Stop and report it","zh-CN":"停止并报告"},{"en":"Wait until tomorrow","zh-CN":"等到明天"}]'::jsonb
  end,
  position - 1,
  briefing.created_at
from demo_report_data report
cross join generate_series(1, 3) as position
join public.briefings briefing
  on briefing.id = ('64000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
where report.final_status in ('lesson_drafted', 'lesson_published')
on conflict (id) do nothing;

create temporary table demo_quiz_response_data (
  report_seq smallint not null,
  position smallint not null,
  respondent_id uuid,
  selected_option smallint not null,
  is_correct boolean not null,
  response_marker smallint not null,
  primary key (report_seq, position, response_marker)
) on commit drop;

insert into demo_quiz_response_data values
  (38, 1, '00000000-0000-0000-0000-000000000005', 0, true, 1),
  (38, 2, '00000000-0000-0000-0000-000000000005', 0, false, 1),
  (38, 3, '00000000-0000-0000-0000-000000000005', 2, true, 1),
  (38, 2, null, 1, true, 9),
  (39, 1, '00000000-0000-0000-0000-000000000004', 3, false, 1),
  (39, 2, '00000000-0000-0000-0000-000000000004', 1, true, 1),
  (39, 3, '00000000-0000-0000-0000-000000000004', 0, false, 1),
  (39, 3, null, 2, true, 9),
  (40, 1, '00000000-0000-0000-0000-000000000001', 0, true, 1),
  (40, 2, '00000000-0000-0000-0000-000000000001', 1, true, 1),
  (40, 3, '00000000-0000-0000-0000-000000000001', 1, false, 1),
  (40, 1, null, 0, true, 9);

insert into public.quiz_responses (
  id, question_id, respondent_id, selected_option, is_correct, created_at
)
select
  ('64200000-0000-4000-8000-' || lpad((report_seq * 100 + position * 10 + response_marker)::text, 12, '0'))::uuid,
  ('64100000-0000-4000-8000-' || lpad((report_seq * 10 + position)::text, 12, '0'))::uuid,
  respondent_id,
  selected_option,
  is_correct,
  now() - make_interval(days => 12 - report_seq % 3) + make_interval(hours => position)
from demo_quiz_response_data
on conflict (id) do nothing;

-- Audit rows tell the same legal story as the state machine. Event IDs are
-- deterministic so rerunning this file cannot duplicate timeline history.
insert into public.audit_log (
  id, report_id, actor_type, actor_id, event,
  source, target, reason, metadata, created_at
)
select
  ('66000000-0000-4000-8000-' || lpad((seq * 100 + 1)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  'human'::actor_type, reporter_id, 'report_created',
  null, 'draft'::report_status, null, '{}'::jsonb,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '8 hours'
from demo_report_data
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((seq * 100 + 2)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  'human'::actor_type, reporter_id, 'submit',
  'draft'::report_status, 'submitted'::report_status, null, '{}'::jsonb,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '9 hours'
from demo_report_data where final_status <> 'draft'
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((seq * 100 + 3)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  'ai'::actor_type, null, 'start_clarification',
  'submitted'::report_status, 'clarifying'::report_status, null, '{}'::jsonb,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '11 hours'
from demo_report_data where final_status = 'clarifying'
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((seq * 100 + 3)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  'ai'::actor_type, null, 'draft_without_clarification',
  'submitted'::report_status, 'ai_drafted'::report_status, null,
  jsonb_build_object('ai_draft_id', ('63400000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid),
  date_trunc('day', now()) - make_interval(days => age_days) + interval '11 hours'
from demo_report_data
where final_status in (
  'ai_drafted', 'under_review', 'rejected', 'info_requested', 'escalated',
  'action_assigned', 'action_submitted', 'verified_closed',
  'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((seq * 100 + 4)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  'system'::actor_type, null, 'queue_for_review',
  'ai_drafted'::report_status, 'under_review'::report_status, null, '{}'::jsonb,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '12 hours'
from demo_report_data
where final_status in (
  'under_review', 'rejected', 'info_requested', 'escalated',
  'action_assigned', 'action_submitted', 'verified_closed',
  'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((seq * 100 + 5)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000003',
  case
    when final_status = 'rejected' then 'reject'
    when final_status = 'info_requested' then 'request_info'
    when final_status = 'escalated' then 'escalate'
    else 'approve_action'
  end,
  'under_review'::report_status,
  case
    when final_status = 'rejected' then 'rejected'::report_status
    when final_status = 'info_requested' then 'info_requested'::report_status
    when final_status = 'escalated' then 'escalated'::report_status
    else 'action_assigned'::report_status
  end,
  case
    when final_status = 'rejected' then 'The observation does not describe a current site hazard.'
    when final_status = 'info_requested' then 'The exact equipment and affected work area are required.'
    when final_status = 'escalated' then 'Work must stop until the safety lead reviews the repeated exposure.'
  end,
  jsonb_build_object(
    'review_decision_id',
    ('63300000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid
  ),
  date_trunc('day', now()) - make_interval(days => age_days) + interval '16 hours'
from demo_report_data
where final_status in (
  'rejected', 'info_requested', 'escalated', 'action_assigned',
  'action_submitted', 'verified_closed', 'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((report.seq * 100 + 6)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000004',
  'submit_evidence',
  'action_assigned'::report_status,
  'action_submitted'::report_status,
  null,
  jsonb_build_object(
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'media_ids', '[]'::jsonb
  ),
  date_trunc('day', now()) - make_interval(days => report.age_days) + interval '32 hours'
from demo_report_data report
where report.seq in (24, 25, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40)
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((item.seq * 100 + 7)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(item.seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000003',
  'verification_failed',
  'action_submitted'::report_status,
  'action_assigned'::report_status,
  item.reason,
  jsonb_build_object(
    'verification_id', ('63200000-0000-4000-8000-' || lpad((item.seq * 10 + 1)::text, 12, '0'))::uuid,
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(item.seq::text, 12, '0'))::uuid,
    'rework_count', 1
  ),
  date_trunc('day', now()) - make_interval(days => report.age_days) + interval '34 hours'
from demo_verification_data item
join demo_report_data report on report.seq = item.seq
where item.cycle = 1 and not item.passed
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((report.seq * 100 + 8)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000004',
  'submit_evidence',
  'action_assigned'::report_status,
  'action_submitted'::report_status,
  null,
  jsonb_build_object(
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'media_ids', '[]'::jsonb
  ),
  date_trunc('day', now()) - make_interval(days => report.age_days) + interval '56 hours'
from demo_report_data report
where report.seq in (24, 29, 33, 38)
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((item.seq * 100 + 9)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(item.seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000003',
  'verification_failed',
  'action_submitted'::report_status,
  'action_assigned'::report_status,
  item.reason,
  jsonb_build_object(
    'verification_id', ('63200000-0000-4000-8000-' || lpad((item.seq * 10 + 2)::text, 12, '0'))::uuid,
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(item.seq::text, 12, '0'))::uuid,
    'rework_count', 2
  ),
  date_trunc('day', now()) - make_interval(days => report.age_days) + interval '58 hours'
from demo_verification_data item
join demo_report_data report on report.seq = item.seq
where item.cycle = 2 and not item.passed
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((report.seq * 100 + 10)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000004',
  'submit_evidence',
  'action_assigned'::report_status,
  'action_submitted'::report_status,
  null,
  jsonb_build_object(
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'media_ids', '[]'::jsonb
  ),
  date_trunc('day', now()) - make_interval(days => report.age_days) + interval '80 hours'
from demo_report_data report
where report.seq = 33
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((report.seq * 100 + 11)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000003',
  'verify_and_close',
  'action_submitted'::report_status,
  'verified_closed'::report_status,
  null,
  jsonb_build_object(
    'verification_id', verification.id,
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
  ),
  verification.created_at
from demo_report_data report
join public.verifications verification
  on verification.id = ('63200000-0000-4000-8000-' || lpad((report.seq * 10 + case when report.seq = 33 then 3 when report.seq = 38 then 2 else 1 end)::text, 12, '0'))::uuid
where report.final_status in ('verified_closed', 'lesson_drafted', 'lesson_published')
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((report.seq * 100 + 12)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  'ai'::actor_type, null, 'draft_lesson',
  'verified_closed'::report_status, 'lesson_drafted'::report_status, null,
  jsonb_build_object(
    'briefing_id', ('64000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'briefing_version', 1
  ),
  briefing.created_at
from demo_report_data report
join public.briefings briefing
  on briefing.id = ('64000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
where report.final_status in ('lesson_drafted', 'lesson_published')
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
select
  ('66000000-0000-4000-8000-' || lpad((report.seq * 100 + 13)::text, 12, '0'))::uuid,
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  'human'::actor_type,
  '00000000-0000-0000-0000-000000000003',
  'publish_lesson',
  'lesson_drafted'::report_status, 'lesson_published'::report_status, null,
  jsonb_build_object('briefing_id', briefing.id),
  briefing.approved_at
from demo_report_data report
join public.briefings briefing
  on briefing.id = ('64000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
where report.final_status = 'lesson_published'
on conflict (id) do nothing;

insert into public.alerts (
  id, report_id, raised_by, raised_at, location_text, created_at
) values (
  '65100000-0000-4000-8000-000000000001',
  '61000000-0000-4000-8000-000000000002',
  '00000000-0000-0000-0000-000000000002',
  now() - interval '2 minutes',
  'Tower A Level 12',
  now() - interval '2 minutes'
)
on conflict (id) do nothing;

insert into public.audit_log
  (id, report_id, actor_type, actor_id, event, source, target, reason, metadata, created_at)
values (
  '66000000-0000-4000-8000-000000000214',
  '61000000-0000-4000-8000-000000000002',
  'human',
  '00000000-0000-0000-0000-000000000002',
  'alert_raised',
  'draft',
  'draft',
  null,
  jsonb_build_object('alert_id', '65100000-0000-4000-8000-000000000001'::uuid),
  now() - interval '2 minutes'
)
on conflict (id) do nothing;

-- Assignment, send-back, overdue, closure, lesson and urgent notifications.
insert into public.notifications (
  id, recipient_id, kind, entity_type, entity_id, payload, read_at, delivery_date, created_at
)
select
  ('65000000-0000-4000-8000-' || lpad((seq * 100 + 1)::text, 12, '0'))::uuid,
  '00000000-0000-0000-0000-000000000004',
  'assigned', 'report',
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  jsonb_build_object(
    'report_id', ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
    'assignment_id', ('63000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid
  ),
  case when final_status not in ('action_assigned', 'action_submitted') then now() - interval '10 days' end,
  null,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '16 hours'
from demo_report_data
where final_status in (
  'action_assigned', 'action_submitted', 'verified_closed',
  'lesson_drafted', 'lesson_published'
)
on conflict (id) do nothing;

insert into public.notifications
  (id, recipient_id, kind, entity_type, entity_id, payload, read_at, delivery_date, created_at)
select
  ('65000000-0000-4000-8000-' || lpad((report.seq * 100 + 2)::text, 12, '0'))::uuid,
  '00000000-0000-0000-0000-000000000004',
  'sent_back', 'report',
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  jsonb_build_object(
    'report_id', ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'verification_id', ('63200000-0000-4000-8000-' || lpad((report.seq * 10 + 1)::text, 12, '0'))::uuid,
    'rework_count', action.rework_count
  ),
  case when report.final_status not in ('action_assigned', 'action_submitted') then now() - interval '8 days' end,
  null,
  date_trunc('day', now()) - make_interval(days => report.age_days) + interval '34 hours'
from demo_report_data report
join public.corrective_actions action
  on action.id = ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
where report.seq in (24, 25, 29, 33, 38)
on conflict (id) do nothing;

insert into public.notifications
  (id, recipient_id, kind, entity_type, entity_id, payload, read_at, delivery_date, created_at)
select
  ('65000000-0000-4000-8000-' || lpad((report.seq * 10000 + day_offset * 10 + 3)::text, 12, '0'))::uuid,
  '00000000-0000-0000-0000-000000000004',
  'overdue', 'report',
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  jsonb_build_object(
    'report_id', ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'assignment_id', ('63000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'days_overdue', case report.seq when 24 then 3 when 25 then 2 else 1 end + day_offset
  ),
  null,
  (current_date - day_offset),
  (current_date - day_offset)::timestamptz + interval '8 hours'
from demo_report_data report
cross join generate_series(0, 1) as day_offset
where report.seq in (24, 25, 26)
on conflict (id) do nothing;

insert into public.notifications
  (id, recipient_id, kind, entity_type, entity_id, payload, read_at, delivery_date, created_at)
select
  ('65000000-0000-4000-8000-' || lpad((seq * 100 + 4)::text, 12, '0'))::uuid,
  reporter_id,
  'info_requested', 'report',
  ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
  jsonb_build_object(
    'report_id', ('61000000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid,
    'review_id', ('63300000-0000-4000-8000-' || lpad(seq::text, 12, '0'))::uuid
  ),
  null, null,
  date_trunc('day', now()) - make_interval(days => age_days) + interval '16 hours'
from demo_report_data where final_status = 'info_requested'
on conflict (id) do nothing;

insert into public.notifications
  (id, recipient_id, kind, entity_type, entity_id, payload, read_at, delivery_date, created_at)
select
  ('65000000-0000-4000-8000-' || lpad((report.seq * 100 + 5)::text, 12, '0'))::uuid,
  report.reporter_id,
  'report_closed', 'report',
  ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
  jsonb_build_object(
    'report_id', ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'corrective_action_id', ('63100000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid,
    'verification_id', receipt.verification_id,
    'receipt_id', receipt.id
  ),
  null, null, receipt.created_at
from demo_report_data report
join public.closure_receipts receipt
  on receipt.report_id = ('61000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
where report.final_status in ('verified_closed', 'lesson_drafted', 'lesson_published')
on conflict (id) do nothing;

insert into public.notifications
  (id, recipient_id, kind, entity_type, entity_id, payload, read_at, delivery_date, created_at)
select
  ('65000000-0000-4000-8000-' || lpad((report.seq * 100 + 6)::text, 12, '0'))::uuid,
  '00000000-0000-0000-0000-000000000005',
  'briefing_published', 'briefing', briefing.id,
  jsonb_build_object('briefing_id', briefing.id, 'report_id', briefing.report_id),
  null, null, briefing.approved_at
from demo_report_data report
join public.briefings briefing
  on briefing.id = ('64000000-0000-4000-8000-' || lpad(report.seq::text, 12, '0'))::uuid
where report.final_status = 'lesson_published'
on conflict (id) do nothing;

insert into public.notifications
  (id, recipient_id, kind, entity_type, entity_id, payload, read_at, delivery_date, created_at)
values
  (
    '65000000-0000-4000-8000-000000000207',
    '00000000-0000-0000-0000-000000000003',
    'alert_raised', 'alert',
    '65100000-0000-4000-8000-000000000001',
    jsonb_build_object(
      'alert_id', '65100000-0000-4000-8000-000000000001'::uuid,
      'report_id', '61000000-0000-4000-8000-000000000002'::uuid
    ),
    null, null, now() - interval '2 minutes'
  ),
  (
    '65000000-0000-4000-8000-000000000208',
    '00000000-0000-0000-0000-000000000006',
    'alert_raised', 'alert',
    '65100000-0000-4000-8000-000000000001',
    jsonb_build_object(
      'alert_id', '65100000-0000-4000-8000-000000000001'::uuid,
      'report_id', '61000000-0000-4000-8000-000000000002'::uuid
    ),
    null, null, now() - interval '2 minutes'
  )
on conflict (id) do nothing;

-- Fail the load if the site would not satisfy the Step 6.4 demo contract.
do $$
declare
  demo_report_count integer;
  demo_status_count integer;
  demo_document_count integer;
  demo_published_count integer;
  demo_rework_count integer;
  demo_quiz_briefing_count integer;
  demo_identity_count integer;
  demo_timeline_count integer;
begin
  select count(*), count(distinct status)
  into demo_report_count, demo_status_count
  from public.reports
  where id::text like '61000000-0000-4000-8000-%';

  select count(*) into demo_document_count
  from public.documents
  where id::text like '62000000-0000-4000-8000-%' and is_approved;

  select count(*) into demo_published_count
  from public.briefings
  where id::text like '64000000-0000-4000-8000-%'
    and status = 'published'::briefing_status;

  select count(*) into demo_rework_count
  from public.corrective_actions
  where id::text like '63100000-0000-4000-8000-%' and rework_count >= 1;

  select count(distinct briefing.id) into demo_quiz_briefing_count
  from public.briefings briefing
  join public.quiz_questions question on question.briefing_id = briefing.id
  join public.quiz_responses response on response.question_id = question.id
  where briefing.id::text like '64000000-0000-4000-8000-%'
    and briefing.status = 'published'::briefing_status;

  select count(*) into demo_identity_count
  from auth.identities
  where user_id in (
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000004',
    '00000000-0000-0000-0000-000000000005',
    '00000000-0000-0000-0000-000000000006'
  ) and provider = 'email';

  select count(*) into demo_timeline_count
  from public.reports report
  where report.id::text like '61000000-0000-4000-8000-%'
    and exists (
      select 1 from public.audit_log event
      where event.report_id = report.id and event.target = report.status
    );

  if demo_report_count <> 40 then
    raise exception 'demo seed expected 40 reports, found %', demo_report_count;
  end if;
  if demo_status_count <> 13 then
    raise exception 'demo seed expected all 13 statuses, found %', demo_status_count;
  end if;
  if demo_document_count <> 2 then
    raise exception 'demo seed expected 2 approved documents, found %', demo_document_count;
  end if;
  if demo_published_count <> 3 then
    raise exception 'demo seed expected 3 published briefings, found %', demo_published_count;
  end if;
  if demo_rework_count < 2 then
    raise exception 'demo seed expected at least 2 rework cases, found %', demo_rework_count;
  end if;
  if demo_quiz_briefing_count <> 3 then
    raise exception 'demo seed expected quiz responses for 3 published briefings, found %', demo_quiz_briefing_count;
  end if;
  if demo_identity_count <> 6 then
    raise exception 'demo seed expected 6 email identities, found %', demo_identity_count;
  end if;
  if demo_timeline_count <> 40 then
    raise exception 'demo seed expected final-status audit evidence for 40 reports, found %', demo_timeline_count;
  end if;
end $$;

commit;
