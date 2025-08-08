-- Completed results table (supporting both image and video generation)
CREATE TABLE IF NOT EXISTS completed_results (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    image_url TEXT,
    image_prompt TEXT,
    video_url TEXT,
    video_prompt JSONB,
    generation_mode TEXT,  -- 'image', 'video', or 'both'
    title TEXT,
    summary TEXT,
    transcript TEXT,
    prompt_generated TEXT,  -- deprecated, use image_prompt instead
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);

-- Status updates table (matching Firebase structure)
CREATE TABLE IF NOT EXISTS update_status (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    sequence_number INTEGER NOT NULL,
    additional_info JSONB,
    UNIQUE(session_id, sequence_number)
);

-- Update counters table (for sequence management)
CREATE TABLE IF NOT EXISTS update_counters (
    session_id TEXT PRIMARY KEY,
    count INTEGER NOT NULL DEFAULT 0
);

-- OpenAI response data (replaces Firebase Storage JSON)
CREATE TABLE IF NOT EXISTS openai_responses (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    openai_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    model_used TEXT,
    completion_tokens INTEGER,
    prompt_tokens INTEGER,
    total_tokens INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(session_id, openai_id)
);

-- Sessions table (optional, for future expansion)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);