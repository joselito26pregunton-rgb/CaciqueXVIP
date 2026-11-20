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

-- Persistent private inbox for payment-method requests. This stores the
-- selected method/option and request metadata, but never bank-account values,
-- card details, passwords, or credentials.
create table if not exists public.bot_payment_requests (
    request_id text primary key check (request_id ~ '^[0-9a-f]{32}$'),
    user_id bigint not null check (user_id > 0),
    username text not null default '',
    display_name text not null default 'Usuario',
    method text not null,
    payment_option_index integer check (
        payment_option_index is null or payment_option_index >= 0
    ),
    payment_option_label text not null default '',
    user_chat_id bigint not null,
    user_message_id bigint,
    admin_notification_message_id bigint,
    status text not null default 'pending' check (
        status in ('pending', 'approved', 'rejected', 'cancelled')
    ),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    resolved_at timestamptz
);

-- A Telegram account may have only one unresolved payment request at a time.
create unique index if not exists bot_payment_requests_one_pending_per_user_idx
    on public.bot_payment_requests (user_id)
    where status = 'pending';

create index if not exists bot_payment_requests_pending_created_idx
    on public.bot_payment_requests (created_at desc)
    where status = 'pending';

alter table public.bot_payment_requests enable row level security;
revoke all on table public.bot_payment_requests from anon, authenticated;
grant all on table public.bot_payment_requests to service_role;
