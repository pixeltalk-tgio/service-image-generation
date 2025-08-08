-- Add video support columns to existing completed_results table
-- Run this if your table already exists and needs updating

ALTER TABLE completed_results 
ADD COLUMN IF NOT EXISTS image_prompt TEXT,
ADD COLUMN IF NOT EXISTS video_url TEXT,
ADD COLUMN IF NOT EXISTS video_prompt JSONB,
ADD COLUMN IF NOT EXISTS generation_mode TEXT;

-- Optional: Update any existing rows to have generation_mode = 'image' if they have an image_url
UPDATE completed_results 
SET generation_mode = 'image' 
WHERE generation_mode IS NULL AND image_url IS NOT NULL;

-- Optional: Copy prompt_generated to image_prompt for backwards compatibility
UPDATE completed_results 
SET image_prompt = prompt_generated 
WHERE image_prompt IS NULL AND prompt_generated IS NOT NULL;