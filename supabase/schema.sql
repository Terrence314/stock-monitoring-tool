-- ─────────────────────────────────────────────────────────────────────────────
-- Stock Monitoring Tool — Supabase Schema
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Favourites — cross-device starred tickers
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists favourites (
  ticker      text primary key,
  added_at    timestamptz default now()
);

-- Allow anonymous read/write (personal tool — tickers are not sensitive data)
alter table favourites enable row level security;

create policy "anon_read_favourites"  on favourites
  for select using (true);

create policy "anon_write_favourites" on favourites
  for insert with check (true);

create policy "anon_delete_favourites" on favourites
  for delete using (true);

-- 2. Portfolio transactions — replaces data/portfolio_transactions.json
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists portfolio_transactions (
  id          bigint generated always as identity primary key,
  ticker      text        not null,
  action      text        not null check (action in ('BUY', 'SELL')),
  shares      numeric     not null,
  price       numeric     not null,
  trade_date  date        not null default current_date,
  notes       text,
  created_at  timestamptz default now()
);

-- Allow anonymous read/write
alter table portfolio_transactions enable row level security;

create policy "anon_read_portfolio"  on portfolio_transactions
  for select using (true);

create policy "anon_write_portfolio" on portfolio_transactions
  for insert with check (true);

create policy "anon_update_portfolio" on portfolio_transactions
  for update using (true);

create policy "anon_delete_portfolio" on portfolio_transactions
  for delete using (true);

-- 3. Settings — user preferences (theme, view mode, etc.)
-- ─────────────────────────────────────────────────────────────────────────────
create table if not exists settings (
  key         text primary key,
  value       text,
  updated_at  timestamptz default now()
);

alter table settings enable row level security;

create policy "anon_read_settings"  on settings for select using (true);
create policy "anon_write_settings" on settings for insert with check (true);
create policy "anon_update_settings" on settings for update using (true);
