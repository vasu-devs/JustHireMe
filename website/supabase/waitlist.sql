-- JustHireMe waitlist storage. Run once in the Supabase SQL editor.
-- Only the website's serverless function (api/waitlist.js) touches this table,
-- using the project's secret/service-role key. RLS is on with no policies, so the
-- public anon key cannot read or write emails.

create table if not exists public.waitlist_signups (
  id bigint generated always as identity primary key,
  email text not null check (email = lower(email) and char_length(email) between 3 and 200),
  list text not null default 'ios' check (list in ('ios', 'cloud')),
  source text check (char_length(source) <= 64),
  created_at timestamptz not null default now(),
  -- Set when the launch email goes out, so a resend only reaches people not yet emailed.
  notified_at timestamptz,
  unique (email, list)
);

alter table public.waitlist_signups enable row level security;
revoke all on table public.waitlist_signups from anon, authenticated;

create index if not exists waitlist_signups_list_created_idx
  on public.waitlist_signups (list, created_at);

-- Launch day: everyone on the iPhone beta list who hasn't been emailed yet.
--   select email from public.waitlist_signups
--   where list = 'ios' and notified_at is null
--   order by created_at;
-- After sending a batch:
--   update public.waitlist_signups set notified_at = now()
--   where list = 'ios' and email = any(:sent_emails);
