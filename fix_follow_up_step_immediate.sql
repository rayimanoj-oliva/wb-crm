-- IMMEDIATE FIX: Run this SQL to fix the database constraint issue
-- This will drop the follow_up_step column that's causing the NOT NULL constraint error

-- Option 1: Drop the column (recommended if not using it)
ALTER TABLE customers DROP COLUMN IF EXISTS follow_up_step;
ALTER TABLE customers DROP COLUMN IF EXISTS follow_up_status;

-- Option 2: If you need to keep the column but make it nullable (if you're still using it)
-- ALTER TABLE customers ALTER COLUMN follow_up_step DROP NOT NULL;
-- ALTER TABLE customers ALTER COLUMN follow_up_step SET DEFAULT 'initial';

