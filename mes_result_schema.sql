
-- Таблица завершённых этапов производства
CREATE TABLE completed_production_steps (
    id SERIAL PRIMARY KEY,
    step_guid UUID REFERENCES production_steps(guid),
    operator_guid UUID REFERENCES operators(guid),
    work_center_guid UUID REFERENCES work_centers(guid),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    actual_duration_min INTEGER,
    result TEXT,
    comment TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица завершённых операций
CREATE TABLE completed_operations (
    id SERIAL PRIMARY KEY,
    operation_guid UUID REFERENCES production_operations(guid),
    operator_guid UUID REFERENCES operators(guid),
    work_center_guid UUID REFERENCES work_centers(guid),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    paused_time INTERVAL,
    actual_duration_min INTEGER,
    status TEXT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Таблица смен оператора
CREATE TABLE shift_sessions (
    id SERIAL PRIMARY KEY,
    operator_guid UUID REFERENCES operators(guid),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    duration_min INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);
