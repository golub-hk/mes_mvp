
-- Продукция
INSERT INTO products (guid, code, name) VALUES
('11111111-1111-1111-1111-111111111111', 'P001', 'Парацетамол'),
('22222222-2222-2222-2222-222222222222', 'P002', 'Аспирин');

-- Операторы
INSERT INTO operators (guid, code, full_name) VALUES
('aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'OP01', 'Иванов Иван'),
('aaaaaaa2-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'OP02', 'Петров Петр');

-- Рабочие центры
INSERT INTO work_centers (guid, code, name, group_name) VALUES
('ccccccc1-cccc-cccc-cccc-cccccccccccc', 'WC01', 'Линия таблетирования', 'Цех 1'),
('ccccccc2-cccc-cccc-cccc-cccccccccccc', 'WC02', 'Линия упаковки', 'Цех 1');

-- Оборудование
INSERT INTO equipment (guid, code, name, work_center_guid) VALUES
('eeeeeee1-eeee-eeee-eeee-eeeeeeeeeeee', 'EQ01', 'Пресс 1', 'ccccccc1-cccc-cccc-cccc-cccccccccccc'),
('eeeeeee2-eeee-eeee-eeee-eeeeeeeeeeee', 'EQ02', 'Упаковщик 1', 'ccccccc2-cccc-cccc-cccc-cccccccccccc');

-- Заказы
INSERT INTO production_orders (guid, code, status, product_guid, quantity, unit, start_date, end_date) VALUES
('33333333-3333-3333-3333-333333333333', 'ORD001', 'в работе', '11111111-1111-1111-1111-111111111111', 10000, 'шт', NOW() - INTERVAL '1 day', NOW() + INTERVAL '2 days');

-- Этапы
INSERT INTO production_steps (guid, code, status, name, product_guid, quantity, unit, planned_duration_min, work_center_guid, operator_guid) VALUES
('44444444-4444-4444-4444-444444444444', 'STEP01', 'К выполнению', 'Таблетирование партии', '11111111-1111-1111-1111-111111111111', 10000, 'шт', 180, 'ccccccc1-cccc-cccc-cccc-cccccccccccc', 'aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaaa');

-- Операции
INSERT INTO production_operations (guid, code, status, name, planned_duration_min, work_center_guid, operator_guid, step_guid, actual_start_time, actual_end_time, paused_time, cancel_reason) VALUES
('55555555-5555-5555-5555-555555555555', 'OPR001', 'Выполнена', 'Прессование таблеток', 90, 'ccccccc1-cccc-cccc-cccc-cccccccccccc', 'aaaaaaa1-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '44444444-4444-4444-4444-444444444444', NOW() - INTERVAL '2 hour', NOW() - INTERVAL '1 hour 10 minutes', '00:05:00', NULL);
