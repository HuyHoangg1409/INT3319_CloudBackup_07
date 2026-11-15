-- Run only on the fresh cloud_backup_demo database. Fails if table already exists.
\set ON_ERROR_STOP on
BEGIN;
CREATE TABLE public.demo_inventory (
  item_id serial PRIMARY KEY,
  item_name text NOT NULL UNIQUE,
  quantity integer NOT NULL CHECK (quantity >= 0)
);
INSERT INTO public.demo_inventory(item_name, quantity)
SELECT 'San pham ' || g, g * 3 FROM generate_series(1, 100) AS g;
COMMIT;
SELECT COUNT(*) AS expected_100 FROM public.demo_inventory;
SELECT * FROM public.demo_inventory ORDER BY item_id LIMIT 5;
