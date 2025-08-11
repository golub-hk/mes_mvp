
-- Продукция
CREATE TABLE products (
    guid UUID PRIMARY KEY,
    code TEXT,
    name TEXT
);

-- Операторы
CREATE TABLE operators (
    guid UUID PRIMARY KEY,
    code TEXT,
    full_name TEXT,
    login TEXT UNIQUE,
    password_hash TEXT
);

-- Рабочие центры
CREATE TABLE work_centers (
    guid UUID PRIMARY KEY,
    code TEXT,
    name TEXT,
    group_name TEXT
);

-- Оборудование
CREATE TABLE equipment (
    guid UUID PRIMARY KEY,
    code TEXT,
    name TEXT,
    work_center_guid UUID
);

-- Заказы
CREATE TABLE production_orders (
    guid UUID PRIMARY KEY,
    code TEXT,
    status TEXT,
    product_guid UUID,
    quantity INTEGER,
    unit TEXT,
    start_date TIMESTAMP,
    end_date TIMESTAMP
);

-- Этапы
CREATE TABLE production_steps (
    guid UUID PRIMARY KEY,
    code TEXT,
    status TEXT,
    name TEXT,
    product_guid UUID,
    quantity INTEGER,
    unit TEXT,
    planned_duration_min INTEGER,
    work_center_guid UUID,
    operator_guid UUID
);

-- Операции
CREATE TABLE production_operations (
    guid UUID PRIMARY KEY,
    code TEXT,
    status TEXT,
    name TEXT,
    planned_duration_min INTEGER,
    work_center_guid UUID,
    operator_guid UUID,
    step_guid UUID,
    actual_start_time TIMESTAMP,
    actual_end_time TIMESTAMP,
    paused_time INTERVAL,
    cancel_reason TEXT
);

-- Завершённые этапы
CREATE TABLE completed_production_steps (
    id SERIAL PRIMARY KEY,
    step_guid UUID,
    operator_guid UUID,
    work_center_guid UUID,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    actual_duration_min INTEGER,
    result TEXT,
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Завершённые операции
CREATE TABLE completed_operations (
    id SERIAL PRIMARY KEY,
    operation_guid UUID,
    operator_guid UUID,
    work_center_guid UUID,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    paused_time INTERVAL,
    actual_duration_min INTEGER,
    status TEXT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Смены операторов
CREATE TABLE shift_sessions (
    id SERIAL PRIMARY KEY,
    operator_guid UUID,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    duration_min INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
