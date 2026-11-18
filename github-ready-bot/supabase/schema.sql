-- Run this file once in the Supabase SQL Editor.
-- Visual settings store only photo file IDs and /start welcome instructions.
create table if not exists public.bot_persistent_settings (
    key text primary key,
    settings jsonb not null default '{}'::jsonb
);

alter table public.bot_persistent_settings enable row level security;

revoke all on table public.bot_persistent_settings from anon, authenticated;
grant all on table public.bot_persistent_settings to service_role;

-- One-time private welcome markers. Only hashes of Telegram IDs are stored,
-- so the bot can deduplicate greetings without exposing the IDs in this table.
create table if not exists public.bot_business_welcome_records (
    profile_hash text not null check (profile_hash ~ '^[0-9a-f]{16}$'),
    recipient_hash text not null check (recipient_hash ~ '^[0-9a-f]{16}$'),
    status text not null check (status in ('sending', 'sent')),
    photo_sent boolean not null default false,
    claim_id text not null default '',
    claimed_at timestamptz not null default now(),
    sent_at timestamptz,
    primary key (profile_hash, recipient_hash)
);

alter table public.bot_business_welcome_records enable row level security;
revoke all on table public.bot_business_welcome_records from anon, authenticated;
grant all on table public.bot_business_welcome_records to service_role;

-- Private subscription records: the bot's service role is the only client.
-- data contains the existing JSON fields (including status, dates, invite state,
-- and Telegram receipt file references) so the payment flow remains compatible.
create table if not exists public.bot_subscription_records (
    record_type text not null check (record_type in ('paid', 'free')),
    user_id bigint not null check (user_id > 0),
    username text not null default '',
    status text not null default 'registered',
    expires_at text not null default '',
    updated_at text not null,
    data jsonb not null default '{}'::jsonb,
    primary key (record_type, user_id)
);

create index if not exists bot_subscription_records_status_expiry_idx
    on public.bot_subscription_records (record_type, status, expires_at);

alter table public.bot_subscription_records enable row level security;
revoke all on table public.bot_subscription_records from anon, authenticated;
grant all on table public.bot_subscription_records to service_role;
