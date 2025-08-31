-- Habilitar extensiones para datos espaciales y busquedas de texto
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Tipos enum para datos categoricos
CREATE TYPE risk_level AS ENUM ('VERY_LOW', 'LOW', 'MEDIUM', 'HIGH', 'VERY_HIGH');
CREATE TYPE trend_direction AS ENUM ('IMPROVING', 'STABLE', 'WORSENING');

-- Tabla para datos de crimenes o robos
CREATE TABLE IF NOT EXISTS crime_incidents (
    id SERIAL PRIMARY KEY,
    incident_date TIMESTAMP NOT NULL,
    incident_type VARCHAR(100) NOT NULL,
    modalidad VARCHAR(100),
    localidad VARCHAR(100),
    upz VARCHAR(100),
    barrio VARCHAR(255),
    zona VARCHAR(50),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    location GEOMETRY(Point, 4326),
    source VARCHAR(50) DEFAULT 'SIEDCO',
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_incident UNIQUE (incident_date, latitude, longitude)
);

-- Tabla para ciclorutas
CREATE TABLE IF NOT EXISTS bike_lanes (
    id SERIAL PRIMARY KEY,
    lane_id VARCHAR(100) UNIQUE,
    name VARCHAR(255),
    localidad VARCHAR(100),
    length_km DECIMAL(10, 3),
    lane_type VARCHAR(50),
    condition VARCHAR(50),
    geometry GEOMETRY(LineString, 4326),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Tabla para estacionamientos de bicis
CREATE TABLE IF NOT EXISTS bike_parking (
    id SERIAL PRIMARY KEY,
    parking_id VARCHAR(100) UNIQUE,
    name VARCHAR(255),
    address VARCHAR(500),
    localidad VARCHAR(100),
    upz VARCHAR(100),
    capacity INTEGER,
    security_level VARCHAR(50),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    location GEOMETRY(Point, 4326),
    is_public BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Tabla para zonas como localidades y UPZ (Unidad de Planteamiento Zonal)
CREATE TABLE IF NOT EXISTS zones (
    id SERIAL PRIMARY KEY,
    zone_code VARCHAR(50) UNIQUE,
    zone_type VARCHAR(20) CHECK (zone_type IN ('LOCALIDAD', 'UPZ', 'BARRIO')),
    name VARCHAR(255) NOT NULL,
    parent_zone_code VARCHAR(50),
    area_km2 DECIMAL(10, 3),
    population INTEGER,
    geometry GEOMETRY(Polygon, 4326),
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (parent_zone_code) REFERENCES zones(zone_code)
);

-- Tabla principal para puntajes de seguridad por zona
CREATE TABLE IF NOT EXISTS zone_safety_scores (
    id SERIAL PRIMARY KEY,
    zone_code VARCHAR(50) NOT NULL,
    calculation_date DATE NOT NULL,
    safety_score DECIMAL(5, 2) CHECK (safety_score >= 0 AND safety_score <= 100),
    risk_level risk_level NOT NULL,
    -- Metricas
    thefts_last_7_days INTEGER DEFAULT 0,
    thefts_last_30_days INTEGER DEFAULT 0,
    thefts_last_90_days INTEGER DEFAULT 0,
    theft_density_per_km2 DECIMAL(10, 3),
    -- Infraestructura
    bike_lane_coverage_km DECIMAL(10, 3),
    bike_lane_density_per_km2 DECIMAL(10, 3),
    safe_parking_spots INTEGER DEFAULT 0,
    parking_density_per_km2 DECIMAL(10, 3),
    -- Tendencias
    trend trend_direction DEFAULT 'STABLE',
    trend_percentage DECIMAL(5, 2),
    -- Recomendaciones
    best_hours JSONB,
    safe_routes JSONB,
    avoid_areas JSONB,
    parking_locations JSONB,
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_zone_date UNIQUE (zone_code, calculation_date),
    FOREIGN KEY (zone_code) REFERENCES zones(zone_code)
);

-- Tabla para rastrear trabajos ETL
CREATE TABLE IF NOT EXISTS etl_jobs (
    id SERIAL PRIMARY KEY,
    job_id UUID DEFAULT gen_random_uuid(),
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    records_processed INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indices para mejorar el rendimiento de consultas
CREATE INDEX idx_crime_date ON crime_incidents(incident_date DESC);
CREATE INDEX idx_crime_location ON crime_incidents USING GIST(location);
CREATE INDEX idx_crime_localidad ON crime_incidents(localidad);
CREATE INDEX idx_crime_type ON crime_incidents(incident_type);

CREATE INDEX idx_bike_lanes_geometry ON bike_lanes USING GIST(geometry);
CREATE INDEX idx_bike_lanes_localidad ON bike_lanes(localidad);

CREATE INDEX idx_parking_location ON bike_parking USING GIST(location);
CREATE INDEX idx_parking_localidad ON bike_parking(localidad);

CREATE INDEX idx_zones_geometry ON zones USING GIST(geometry);
CREATE INDEX idx_zones_type ON zones(zone_type);

CREATE INDEX idx_safety_scores_zone ON zone_safety_scores(zone_code);
CREATE INDEX idx_safety_scores_date ON zone_safety_scores(calculation_date DESC);
CREATE INDEX idx_safety_scores_risk ON zone_safety_scores(risk_level);

-- Vistas para consultas mas faciles
CREATE OR REPLACE VIEW v_current_safety_scores AS
SELECT DISTINCT ON (zone_code)
    zss.*,
    z.name as zone_name,
    z.zone_type,
    z.area_km2
FROM zone_safety_scores zss
JOIN zones z ON zss.zone_code = z.zone_code
ORDER BY zone_code, calculation_date DESC;

CREATE OR REPLACE VIEW v_high_risk_zones AS
SELECT * FROM v_current_safety_scores
WHERE risk_level IN ('HIGH', 'VERY_HIGH')
ORDER BY safety_score ASC;

-- Funcion para calcular puntaje de seguridad
CREATE OR REPLACE FUNCTION calculate_safety_score(
    p_thefts_30d INTEGER,
    p_theft_density DECIMAL,
    p_parking_density DECIMAL,
    p_bikelane_density DECIMAL
) RETURNS DECIMAL AS $$
DECLARE
    v_score DECIMAL;
BEGIN
    -- Formula ponderada para puntaje de seguridad (0-100, mas alto es mas seguro)
    v_score := 100;

    -- Restar puntos por robos (max -50 puntos)
    v_score := v_score - LEAST(p_thefts_30d * 2, 50);

    -- Restar puntos por densidad de robos (max -20 puntos)
    v_score := v_score - LEAST(p_theft_density * 5, 20);

    -- Sumar puntos por densidad de estacionamientos (max +15 puntos)
    v_score := v_score + LEAST(p_parking_density * 3, 15);

    -- Sumar puntos por densidad de ciclorutas (max +15 puntos)
    v_score := v_score + LEAST(p_bikelane_density * 3, 15);

    -- Asegurar que el puntaje este entre 0 y 100
    RETURN GREATEST(0, LEAST(100, v_score));
END;
$$ LANGUAGE plpgsql;