-- Keep reviewer queue filters and urgency-first keyset pagination index-backed.

create extension if not exists pg_trgm;

create index if not exists reports_queue_status_order
  on reports (
    status,
    (case urgency
      when 'critical'::urgency then 4
      when 'high'::urgency then 3
      when 'medium'::urgency then 2
      else 1
    end) desc,
    created_at,
    id
  );

create index if not exists reports_queue_all_order
  on reports (
    (case urgency
      when 'critical'::urgency then 4
      when 'high'::urgency then 3
      when 'medium'::urgency then 2
      else 1
    end) desc,
    created_at,
    id
  );

create index if not exists reports_queue_search_trgm
  on reports using gin ((
    coalesce(human_ref, '') || ' ' ||
    coalesce(description_en, '') || ' ' ||
    coalesce(description_original, '') || ' ' ||
    coalesce(location_text, '') || ' ' ||
    coalesce(activity, '')
  ) gin_trgm_ops);

create index if not exists report_assignments_active_assignee_report
  on report_assignments (assignee_id, report_id) where active;

create index if not exists report_media_queue_thumbnail
  on report_media (report_id, phase, created_at, id)
  include (storage_path, caption);

create index if not exists corrective_actions_report_rework
  on corrective_actions (report_id, rework_count desc);
