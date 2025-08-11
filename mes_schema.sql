
CREATE TABLE products (
    guid UUID PRIMARY KEY,
    code TEXT,
    name TEXT
);

CREATE TABLE operators (
    guid UUID PRIMARY KEY,
    code TEXT,
    full_name TEXT
);

CREATE TABLE work_centers (
    guid UUID PRIMARY KEY,
    code TEXT,
    name TEXT,
    group_name TEXT
);

CREATE TABLE equipment (
    guid UUID PRIMARY KEY,
    code TEXT,
    name TEXT,
    work_center_guid UUID REFERENCES work_centers(guid)
);

CREATE TABLE production_orders (
    guid UUID PRIMARY KEY,
    code TEXT,
    status TEXT,
    product_guid UUID REFERENCES products(guid),
    quantity INTEGER,
    unit TEXT,
    start_date TIMESTAMP,
    end_date TIMESTAMP
);

CREATE TABLE production_steps (
    guid UUID PRIMARY KEY,
    code TEXT,
    status TEXT,
    name TEXT,
    product_guid UUID REFERENCES products(guid),
    quantity INTEGER,
    unit TEXT,
    planned_duration_min INTEGER,
    work_center_guid UUID REFERENCES work_centers(guid),
    operator_guid UUID REFERENCES operators(guid)
);

CREATE TABLE production_operations (
    guid UUID PRIMARY KEY,
    code TEXT,
    status TEXT,
    name TEXT,
    planned_duration_min INTEGER,
    work_center_guid UUID REFERENCES work_centers(guid),
    operator_guid UUID REFERENCES operators(guid),
    step_guid UUID REFERENCES production_steps(guid),
    actual_start_time TIMESTAMP,
    actual_end_time TIMESTAMP,
    paused_time INTERVAL,
    cancel_reason TEXT
);
