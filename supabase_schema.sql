-- Supabase Schema for HQM Momentum Scanner
-- Run this SQL in your Supabase SQL Editor

-- Watchlist (user-scoped)
CREATE TABLE IF NOT EXISTS watchlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    ticker TEXT NOT NULL,
    target_entry_price DECIMAL,
    notes TEXT,
    alert_enabled BOOLEAN DEFAULT FALSE,
    alert_threshold DECIMAL,
    added_date TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, ticker)
);

-- Portfolio positions (user-scoped)
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    ticker TEXT NOT NULL,
    shares INTEGER NOT NULL,
    entry_price DECIMAL NOT NULL,
    entry_date DATE NOT NULL,
    exit_price DECIMAL,
    exit_date DATE,
    status TEXT DEFAULT 'open',
    notes TEXT,
    hqm_score_at_entry DECIMAL,
    UNIQUE(user_id, ticker, entry_date)
);

-- Enable Row-Level Security
ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_positions ENABLE ROW LEVEL SECURITY;

-- RLS Policies (users only see their own data)
CREATE POLICY "Users manage own watchlist" ON watchlist
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users manage own positions" ON portfolio_positions
    FOR ALL USING (auth.uid() = user_id);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_watchlist_user_id ON watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_user_id ON portfolio_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_status ON portfolio_positions(status);
