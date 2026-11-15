-- Run once in the Supabase SQL Editor for the bot's persistent visual settings.
-- Only photo file IDs and /start welcome instructions are stored here.
create table if not exists public.bot_persistent_settings (
    key text primary key,
    settings jsonb not null default '{}'::jsonb
);

alter table public.bot_persistent_settings enable row level security;

revoke all on table public.bot_persistent_settings from anon, authenticated;
grant all on table public.bot_persistent_settings to service_role;
