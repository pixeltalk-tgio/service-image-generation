-- Migration to add Cloudinary support fields
-- Run this after the main neon_tables.sql

-- Add Cloudinary-specific columns to completed_results
ALTER TABLE completed_results 
ADD COLUMN IF NOT EXISTS audio_url TEXT,  -- Cloudinary URL for audio (if archived)
ADD COLUMN IF NOT EXISTS cloudinary_image_id TEXT,  -- Cloudinary public_id for image
ADD COLUMN IF NOT EXISTS cloudinary_video_id TEXT,  -- Cloudinary public_id for video
ADD COLUMN IF NOT EXISTS cloudinary_audio_id TEXT,  -- Cloudinary public_id for audio
ADD COLUMN IF NOT EXISTS cloudinary_metadata JSONB,  -- Store full Cloudinary response
ADD COLUMN IF NOT EXISTS user_folder TEXT,  -- User folder identifier in Cloudinary
ADD COLUMN IF NOT EXISTS video_thumbnail_url TEXT;  -- Thumbnail URL for video

-- Create index on user_folder for faster user-specific queries
CREATE INDEX IF NOT EXISTS idx_user_folder ON completed_results(user_folder);

-- Create index on created_at for cleanup queries
CREATE INDEX IF NOT EXISTS idx_created_at ON completed_results(created_at);

-- Add Cloudinary tracking table for resource management
CREATE TABLE IF NOT EXISTS cloudinary_resources (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,  -- 'image', 'video', 'audio'
    public_id TEXT NOT NULL UNIQUE,
    secure_url TEXT NOT NULL,
    folder_path TEXT,
    user_folder TEXT,
    format TEXT,
    size_bytes INTEGER,
    width INTEGER,
    height INTEGER,
    duration FLOAT,  -- For video/audio
    eager_urls JSONB,  -- Different sizes/formats
    tags TEXT[],
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB,
    FOREIGN KEY (session_id) REFERENCES completed_results(session_id) ON DELETE CASCADE
);

-- Create indexes for cloudinary_resources
CREATE INDEX IF NOT EXISTS idx_cloudinary_session ON cloudinary_resources(session_id);
CREATE INDEX IF NOT EXISTS idx_cloudinary_user ON cloudinary_resources(user_folder);
CREATE INDEX IF NOT EXISTS idx_cloudinary_type ON cloudinary_resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_cloudinary_created ON cloudinary_resources(created_at);

-- Add comment to track migration
COMMENT ON TABLE cloudinary_resources IS 'Added for Cloudinary integration - tracks uploaded media resources';