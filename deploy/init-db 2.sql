--
-- PostgreSQL database dump
--

\restrict eLK4aQ7gfzFdprZfD2IjJ0zdKcgGvZruUBhbWXOe9eQLV6CctrWtjqAWOc8aE4F

-- Dumped from database version 16.14 (Debian 16.14-1.pgdg13+1)
-- Dumped by pg_dump version 16.14 (Debian 16.14-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: bronze; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA bronze;


--
-- Name: gold; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA gold;


--
-- Name: silver; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA silver;


--
-- Name: normalize_street_name(text); Type: FUNCTION; Schema: gold; Owner: -
--

CREATE FUNCTION gold.normalize_street_name(raw_name text) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT TRIM(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    LOWER(UNACCENT(COALESCE(raw_name, ''))),
                    '\([^)]*\)', '', 'g'  -- contenu parenthèses
                ),
                '\m(av|ave|avenue|r|rue|bd|boulevard|crs|cours|pl|place|pont|gr|grande|che|chemin|qu|quai|route|rte|imp|impasse|all|allee|esp|esplanade|promenade|nord|sud|est|ouest|centre|de|du|des|la|le|les|et|a)\M',
                '', 'g'  -- mots fonctionnels
            ),
            '[^a-z0-9 ]', '', 'g'  -- ponctuation
        )
    )
$$;


SET default_table_access_method = heap;

--
-- Name: air_quality; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.air_quality (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    measurement_time timestamp with time zone,
    pm10 real,
    pm2_5 real,
    nitrogen_dioxide real,
    ozone real,
    sulphur_dioxide real,
    carbon_monoxide real,
    european_aqi integer
);


--
-- Name: air_quality_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.air_quality_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: air_quality_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.air_quality_id_seq OWNED BY bronze.air_quality.id;


--
-- Name: calendrier_scolaire; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.calendrier_scolaire (
    id bigint NOT NULL,
    zone character varying(10) NOT NULL,
    description character varying(255) NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    annee_scolaire character varying(20)
);


--
-- Name: calendrier_scolaire_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.calendrier_scolaire_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: calendrier_scolaire_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.calendrier_scolaire_id_seq OWNED BY bronze.calendrier_scolaire.id;


--
-- Name: chantiers; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.chantiers (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    chantier_id character varying(100),
    nom character varying(500),
    type_perturbation character varying(255),
    severite character varying(100),
    date_debut date,
    date_fin date,
    commune character varying(255),
    geom public.geometry(Geometry,4326),
    raw_data jsonb
);


--
-- Name: chantiers_historique; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.chantiers_historique (
    id bigint NOT NULL,
    numero character varying(100),
    nature_chantier character varying(255),
    nature_travaux character varying(255),
    etat character varying(100),
    date_debut date,
    date_fin date,
    mesures_police character varying(500),
    commune character varying(255),
    code_insee character varying(10),
    geom public.geometry(Geometry,4326),
    raw_data jsonb
);


--
-- Name: chantiers_historique_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.chantiers_historique_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chantiers_historique_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.chantiers_historique_id_seq OWNED BY bronze.chantiers_historique.id;


--
-- Name: chantiers_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.chantiers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chantiers_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.chantiers_id_seq OWNED BY bronze.chantiers.id;


--
-- Name: chantiers_voirie; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.chantiers_voirie (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    chantier_id character varying(100),
    nature_travaux character varying(255),
    date_debut date,
    date_fin date,
    commune character varying(255),
    geom public.geometry(Geometry,4326),
    raw_data jsonb
);


--
-- Name: chantiers_voirie_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.chantiers_voirie_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chantiers_voirie_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.chantiers_voirie_id_seq OWNED BY bronze.chantiers_voirie.id;


--
-- Name: comptages; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.comptages (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    site_id character varying(50),
    channel_id character varying(50),
    mobility_type character varying(50),
    count_value integer,
    measurement_time timestamp with time zone,
    geom public.geometry(Point,4326),
    raw_data jsonb
);


--
-- Name: comptages_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.comptages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: comptages_id_seq1; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.comptages_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: comptages_id_seq1; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.comptages_id_seq1 OWNED BY bronze.comptages.id;


--
-- Name: pvotrafic_snapshots; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.pvotrafic_snapshots (
    id bigint NOT NULL,
    collected_at timestamp with time zone DEFAULT now() NOT NULL,
    code text,
    libelle text,
    etat character varying(2),
    vitesse_kmh double precision,
    longueur_m integer,
    fournisseur text,
    lat double precision,
    lon double precision,
    est_a_jour boolean,
    sens smallint,
    data_updated_at timestamp with time zone
);


--
-- Name: healthy_pvotrafic; Type: VIEW; Schema: bronze; Owner: -
--

CREATE VIEW bronze.healthy_pvotrafic AS
 SELECT code,
    count(*) AS n_obs,
    count(DISTINCT etat) AS n_etats,
    count(DISTINCT vitesse_kmh) AS n_vitesses,
    max(vitesse_kmh) AS max_speed
   FROM bronze.pvotrafic_snapshots
  WHERE ((collected_at > (now() - '24:00:00'::interval)) AND (code IS NOT NULL))
  GROUP BY code
 HAVING ((count(*) >= 50) AND (max(vitesse_kmh) > (0)::double precision) AND ((count(DISTINCT etat) >= 2) OR (count(DISTINCT vitesse_kmh) >= 3)));


--
-- Name: trafic_boucles; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.trafic_boucles (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    troncon_id character varying(50),
    troncon_name character varying(255),
    debit integer,
    taux_occupation real,
    vitesse real,
    raw_data jsonb,
    geom public.geometry(Point),
    geom_4326 public.geometry(Point,4326),
    CONSTRAINT chk_dual_geom CHECK ((((geom IS NULL) AND (geom_4326 IS NULL)) OR ((geom IS NOT NULL) AND (geom_4326 IS NOT NULL))))
);


--
-- Name: healthy_sensors; Type: VIEW; Schema: bronze; Owner: -
--

CREATE VIEW bronze.healthy_sensors AS
 WITH parsed AS (
         SELECT (trafic_boucles.troncon_id)::text AS channel_id,
            (NULLIF(regexp_replace(replace(COALESCE((trafic_boucles.raw_data ->> 'vitesse'::text), ''::text), ','::text, '.'::text), '[^0-9.]'::text, ''::text, 'g'::text), ''::text))::double precision AS speed_kmh,
            (trafic_boucles.raw_data ->> 'vitesse'::text) AS raw_vitesse
           FROM bronze.trafic_boucles
          WHERE ((trafic_boucles.fetched_at > (now() - '24:00:00'::interval)) AND (trafic_boucles.troncon_id IS NOT NULL))
        )
 SELECT channel_id,
    count(*) AS n_obs,
    count(DISTINCT speed_kmh) AS n_distinct_speeds,
    min(speed_kmh) AS min_speed,
    max(speed_kmh) AS max_speed,
    (max(speed_kmh) - min(speed_kmh)) AS speed_range
   FROM parsed
  WHERE ((speed_kmh IS NOT NULL) AND (raw_vitesse <> 'Vitesse reglementaire'::text))
  GROUP BY channel_id
 HAVING ((count(*) >= 3) AND (count(DISTINCT speed_kmh) >= 2) AND (max(speed_kmh) >= (15)::double precision) AND ((max(speed_kmh) - min(speed_kmh)) >= (2)::double precision));


--
-- Name: jours_feries; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.jours_feries (
    date_ferie date NOT NULL,
    nom character varying(100) NOT NULL
);


--
-- Name: meteo; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.meteo (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    measurement_time timestamp with time zone,
    temperature_2m real,
    relative_humidity_2m real,
    precipitation real,
    rain real,
    weather_code integer,
    cloud_cover real,
    wind_speed_10m real,
    wind_gusts_10m real,
    visibility real,
    surface_pressure real
);


--
-- Name: meteo_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.meteo_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: meteo_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.meteo_id_seq OWNED BY bronze.meteo.id;


--
-- Name: parkings; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.parkings (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    parking_id character varying(50),
    parking_name character varying(255),
    available_spots integer,
    total_spots integer,
    occupation_rate real,
    geom public.geometry(Point,4326),
    raw_data jsonb
);


--
-- Name: parkings_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.parkings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: parkings_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.parkings_id_seq OWNED BY bronze.parkings.id;


--
-- Name: prix_carburants; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.prix_carburants (
    collected_at timestamp with time zone DEFAULT now() NOT NULL,
    carburant text NOT NULL,
    prix_moyen_eur_l numeric(5,3) NOT NULL,
    prix_min numeric(5,3),
    prix_max numeric(5,3),
    nb_stations integer,
    zone text DEFAULT 'metropole_lyon'::text NOT NULL
);


--
-- Name: pvotrafic_snapshots_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.pvotrafic_snapshots_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pvotrafic_snapshots_id_seq1; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.pvotrafic_snapshots_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pvotrafic_snapshots_id_seq1; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.pvotrafic_snapshots_id_seq1 OWNED BY bronze.pvotrafic_snapshots.id;


--
-- Name: tcl_vehicles; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.tcl_vehicles (
    id integer NOT NULL,
    fetched_at timestamp with time zone NOT NULL,
    vehicle_ref character varying NOT NULL,
    line_ref_raw character varying,
    line_ref character varying,
    latitude double precision,
    longitude double precision,
    delay_seconds integer DEFAULT 0,
    recorded_at timestamp with time zone,
    raw_data jsonb
);


--
-- Name: tcl_vehicles_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.tcl_vehicles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tcl_vehicles_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.tcl_vehicles_id_seq OWNED BY bronze.tcl_vehicles.id;


--
-- Name: tomtom_flow; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.tomtom_flow (
    id bigint NOT NULL,
    collected_at timestamp with time zone NOT NULL,
    point_name character varying(255) NOT NULL,
    query_lat double precision,
    query_lon double precision,
    current_speed_kmh real,
    free_flow_speed_kmh real,
    ratio_congestion real,
    confidence real,
    frc character varying(10),
    road_closure boolean DEFAULT false
);


--
-- Name: tomtom_flow_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.tomtom_flow_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tomtom_flow_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.tomtom_flow_id_seq OWNED BY bronze.tomtom_flow.id;


--
-- Name: trafic_boucles_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.trafic_boucles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trafic_boucles_id_seq1; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.trafic_boucles_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trafic_boucles_id_seq1; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.trafic_boucles_id_seq1 OWNED BY bronze.trafic_boucles.id;


--
-- Name: trafic_vitesse_brute; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.trafic_vitesse_brute (
    id integer NOT NULL,
    fetched_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    raw_data jsonb NOT NULL
);


--
-- Name: trafic_vitesse_brute_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.trafic_vitesse_brute_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trafic_vitesse_brute_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.trafic_vitesse_brute_id_seq OWNED BY bronze.trafic_vitesse_brute.id;


--
-- Name: velov; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.velov (
    id bigint NOT NULL,
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    station_id character varying(50),
    station_name character varying(255),
    num_bikes_available integer,
    num_docks_available integer,
    is_installed boolean,
    is_renting boolean,
    is_returning boolean,
    lat double precision,
    lon double precision,
    geom public.geometry(Point,4326)
);


--
-- Name: velov_id_seq; Type: SEQUENCE; Schema: bronze; Owner: -
--

CREATE SEQUENCE bronze.velov_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: velov_id_seq; Type: SEQUENCE OWNED BY; Schema: bronze; Owner: -
--

ALTER SEQUENCE bronze.velov_id_seq OWNED BY bronze.velov.id;


--
-- Name: vitesse_limite_ref; Type: TABLE; Schema: bronze; Owner: -
--

CREATE TABLE bronze.vitesse_limite_ref (
    code text NOT NULL,
    libelle text,
    vitesse_limite integer NOT NULL,
    codetroncon text,
    matched_distance_m real,
    source text DEFAULT 'grandlyon:pvochausseetrottoir'::text NOT NULL,
    matched_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: channel_tomtom_mapping; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.channel_tomtom_mapping (
    channel_id character varying(50) NOT NULL,
    tomtom_point_name character varying(255) NOT NULL,
    tomtom_lat double precision,
    tomtom_lon double precision,
    distance_m integer
);


--
-- Name: channels_ref; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.channels_ref (
    channel_id character varying(50) NOT NULL,
    site_id character varying(50),
    site_name character varying(255),
    mobility_type character varying(50),
    direction character varying(10),
    sens smallint,
    lat double precision,
    lon double precision,
    geom public.geometry(Point,4326),
    commune character varying(10),
    nb_voies smallint,
    debit_max_horaire integer
);


--
-- Name: dim_gnn_adjacency; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.dim_gnn_adjacency (
    node_u integer NOT NULL,
    node_v integer NOT NULL,
    is_connected boolean DEFAULT true,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: dim_spatial_grid_mapping; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.dim_spatial_grid_mapping (
    node_idx integer NOT NULL,
    properties_twgid character varying(100) NOT NULL,
    matrix_i integer NOT NULL,
    matrix_j integer NOT NULL,
    h3_id character varying(15) NOT NULL,
    lat double precision,
    lon double precision,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: dim_temps; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.dim_temps (
    tranche_5min timestamp with time zone NOT NULL,
    tranche_15min timestamp with time zone NOT NULL,
    tranche_horaire timestamp with time zone NOT NULL,
    date_calcul date NOT NULL,
    heure smallint NOT NULL,
    minute_5 smallint NOT NULL,
    jour_semaine smallint NOT NULL,
    is_weekend boolean NOT NULL,
    mois smallint NOT NULL,
    trimestre smallint NOT NULL,
    saison character varying(10) NOT NULL,
    is_ferie boolean,
    is_vacances_a boolean,
    annee smallint NOT NULL
);


--
-- Name: fact_traffic_series; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.fact_traffic_series (
    "timestamp" timestamp with time zone NOT NULL,
    node_idx integer NOT NULL,
    properties_vitesse double precision NOT NULL,
    imputed boolean DEFAULT false
);


--
-- Name: features_traffic; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.features_traffic (
    id bigint NOT NULL,
    channel_id character varying(50) NOT NULL,
    measurement_time timestamp with time zone NOT NULL,
    count_value integer,
    hour_of_day smallint,
    day_of_week smallint,
    month smallint,
    is_weekend boolean,
    sin_hour real,
    cos_hour real,
    sin_dow real,
    cos_dow real,
    avg_temperature real,
    avg_precipitation real,
    avg_cloud_cover real,
    rain_prob real,
    avg_rain real,
    is_raining smallint,
    weather_code smallint,
    mobility_type character varying(50),
    lat double precision,
    lon double precision,
    nearby_chantiers smallint DEFAULT 0,
    nb_voies smallint,
    debit_max_horaire integer,
    taux_saturation real,
    voies_bloquees smallint DEFAULT 0,
    voies_disponibles smallint,
    taux_saturation_effectif real,
    is_school_holiday boolean,
    is_public_holiday boolean,
    vitesse_tomtom_kmh real,
    vitesse_libre_kmh real,
    ratio_congestion real,
    lag_1h real,
    lag_2h real,
    lag_3h real,
    lag_6h real,
    lag_12h real,
    lag_24h real,
    lag_48h real,
    lag_168h real,
    rolling_mean_3h real,
    rolling_mean_6h real,
    rolling_mean_24h real,
    delta_1h real
);


--
-- Name: features_traffic_id_seq; Type: SEQUENCE; Schema: gold; Owner: -
--

CREATE SEQUENCE gold.features_traffic_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: features_traffic_id_seq; Type: SEQUENCE OWNED BY; Schema: gold; Owner: -
--

ALTER SEQUENCE gold.features_traffic_id_seq OWNED BY gold.features_traffic.id;


--
-- Name: h3_trafic_live; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.h3_trafic_live (
    hex_id text NOT NULL,
    sens character varying(4) DEFAULT '?'::character varying NOT NULL,
    etat character(1) NOT NULL,
    mean_speed double precision,
    nb_troncons integer DEFAULT 0 NOT NULL,
    computed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT h3_trafic_live_etat_check CHECK ((etat = ANY (ARRAY['V'::bpchar, 'O'::bpchar, 'R'::bpchar, 'G'::bpchar])))
);


--
-- Name: h3_trafic_predictions; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.h3_trafic_predictions (
    hex_id text NOT NULL,
    horizon_h integer NOT NULL,
    etat_pred character(1) NOT NULL,
    etat_label character varying(20) NOT NULL,
    speed_pred numeric(6,2),
    vitesse_limite numeric(6,2),
    label character varying(256),
    axis_key text,
    libelle character varying(255),
    calculated_at timestamp with time zone NOT NULL,
    lat double precision,
    lon double precision
);


--
-- Name: model_drift_reports; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.model_drift_reports (
    computed_at timestamp with time zone NOT NULL,
    dataset_drift boolean NOT NULL,
    drift_share numeric(5,4) NOT NULL,
    n_ref integer,
    n_current integer,
    ref_from timestamp with time zone,
    ref_to timestamp with time zone,
    current_from timestamp with time zone,
    current_to timestamp with time zone,
    report jsonb NOT NULL
);


--
-- Name: tcl_vehicle_realtime; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.tcl_vehicle_realtime (
    id integer NOT NULL,
    recorded_at timestamp with time zone NOT NULL,
    vehicle_ref character varying NOT NULL,
    line_ref character varying,
    latitude double precision,
    longitude double precision,
    delay_seconds integer DEFAULT 0,
    is_delayed boolean
);


--
-- Name: multimodal_status_grid; Type: VIEW; Schema: gold; Owner: -
--

CREATE VIEW gold.multimodal_status_grid AS
 WITH trafic_grid AS (
         SELECT round((pvotrafic_snapshots.lat)::numeric, 2) AS grid_lat,
            round((pvotrafic_snapshots.lon)::numeric, 2) AS grid_lon,
            avg(NULLIF(pvotrafic_snapshots.vitesse_kmh, (0)::double precision)) AS vitesse_moyenne,
            count(*) AS nb_troncons,
            (((sum(
                CASE
                    WHEN ((pvotrafic_snapshots.etat)::text = ANY ((ARRAY['R'::character varying, 'O'::character varying])::text[])) THEN 1
                    ELSE 0
                END))::double precision / (count(*))::double precision) * (100)::double precision) AS pct_congestion
           FROM bronze.pvotrafic_snapshots
          WHERE (pvotrafic_snapshots.collected_at >= (now() - '01:00:00'::interval))
          GROUP BY (round((pvotrafic_snapshots.lat)::numeric, 2)), (round((pvotrafic_snapshots.lon)::numeric, 2))
        ), velov_grid AS (
         SELECT round((velov.lat)::numeric, 2) AS grid_lat,
            round((velov.lon)::numeric, 2) AS grid_lon,
            sum(velov.num_bikes_available) AS total_velos_dispo,
            sum(velov.num_docks_available) AS total_places_libres
           FROM bronze.velov
          WHERE (velov.fetched_at >= (now() - '00:15:00'::interval))
          GROUP BY (round((velov.lat)::numeric, 2)), (round((velov.lon)::numeric, 2))
        ), tcl_grid AS (
         SELECT round((tcl_vehicle_realtime.latitude)::numeric, 2) AS grid_lat,
            round((tcl_vehicle_realtime.longitude)::numeric, 2) AS grid_lon,
            avg(tcl_vehicle_realtime.delay_seconds) AS retard_moyen_sec,
            count(*) AS nb_vehicules_tcl,
            (((sum(
                CASE
                    WHEN tcl_vehicle_realtime.is_delayed THEN 1
                    ELSE 0
                END))::double precision / (count(*))::double precision) * (100)::double precision) AS pct_tcl_retard
           FROM gold.tcl_vehicle_realtime
          WHERE (tcl_vehicle_realtime.recorded_at >= (now() - '01:00:00'::interval))
          GROUP BY (round((tcl_vehicle_realtime.latitude)::numeric, 2)), (round((tcl_vehicle_realtime.longitude)::numeric, 2))
        ), meteo_global AS (
         SELECT meteo.temperature_2m,
            meteo.precipitation
           FROM bronze.meteo
          ORDER BY meteo.fetched_at DESC
         LIMIT 1
        )
 SELECT COALESCE(t.grid_lat, v.grid_lat, c.grid_lat) AS lat,
    COALESCE(t.grid_lon, v.grid_lon, c.grid_lon) AS lon,
    COALESCE(t.vitesse_moyenne, (0)::double precision) AS vitesse_voiture_kmh,
    COALESCE(t.pct_congestion, (0)::double precision) AS pct_congestion_route,
    COALESCE(c.retard_moyen_sec, (0)::numeric) AS retard_tcl_sec,
    COALESCE(c.pct_tcl_retard, (0)::double precision) AS pct_tcl_retard,
    COALESCE(v.total_velos_dispo, (0)::bigint) AS velos_dispo,
    m.temperature_2m,
    m.precipitation
   FROM (((trafic_grid t
     FULL JOIN velov_grid v ON (((t.grid_lat = v.grid_lat) AND (t.grid_lon = v.grid_lon))))
     FULL JOIN tcl_grid c ON (((COALESCE(t.grid_lat, v.grid_lat) = c.grid_lat) AND (COALESCE(t.grid_lon, v.grid_lon) = c.grid_lon))))
     CROSS JOIN meteo_global m)
  WHERE (COALESCE(t.grid_lat, v.grid_lat, c.grid_lat) IS NOT NULL);


--
-- Name: traffic_features_live; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.traffic_features_live (
    id bigint NOT NULL,
    channel_id text NOT NULL,
    fetched_at timestamp with time zone NOT NULL,
    computed_at timestamp with time zone DEFAULT now() NOT NULL,
    speed_kmh double precision,
    vitesse_limite_kmh double precision,
    lag_1 double precision,
    lag_2 double precision,
    lag_3 double precision,
    delta_current double precision,
    delta_1 double precision,
    rolling_mean_3 double precision,
    hour_of_day smallint,
    day_of_week smallint,
    is_weekend smallint,
    sin_hour double precision,
    cos_hour double precision,
    sin_dow double precision,
    cos_dow double precision,
    channel_hash double precision,
    temperature_2m double precision,
    precipitation double precision,
    rain double precision,
    is_raining smallint,
    visibility double precision,
    wind_speed_10m double precision,
    weather_code smallint,
    lat double precision,
    lon double precision,
    importance_code smallint DEFAULT 0 NOT NULL,
    x_2154 double precision,
    y_2154 double precision,
    is_vacances boolean DEFAULT false,
    is_ferie boolean DEFAULT false
);


--
-- Name: TABLE traffic_features_live; Type: COMMENT; Schema: gold; Owner: -
--

COMMENT ON TABLE gold.traffic_features_live IS 'Features ML pour prédiction vitesse trafic. Alimentée toutes les 15 min par dag_transform_silver_to_gold. 26 features exactes pour XGBoost (matches FEATURE_COLS train_live_speed_model.py). Rétention 30 jours.';


--
-- Name: COLUMN traffic_features_live.channel_hash; Type: COMMENT; Schema: gold; Owner: -
--

COMMENT ON COLUMN gold.traffic_features_live.channel_hash IS 'hash(channel_id) % 1_000_000 — identifiant numérique stable du tronçon. Médiane stockée dans model meta pour valeurs OOD (tronçons non vus en training).';


--
-- Name: mv_fact_traffic_pivot; Type: MATERIALIZED VIEW; Schema: gold; Owner: -
--

CREATE MATERIALIZED VIEW gold.mv_fact_traffic_pivot AS
 SELECT t.fetched_at AS "timestamp",
    m.node_idx,
    t.speed_kmh AS properties_vitesse
   FROM (gold.traffic_features_live t
     JOIN gold.dim_spatial_grid_mapping m ON (((m.properties_twgid)::text = t.channel_id)))
  ORDER BY t.fetched_at, m.node_idx
  WITH NO DATA;


--
-- Name: predictions_vs_actuals; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.predictions_vs_actuals (
    axis_key text NOT NULL,
    horizon_h integer NOT NULL,
    calculated_at timestamp with time zone NOT NULL,
    target_at timestamp with time zone NOT NULL,
    matched_at timestamp with time zone NOT NULL,
    speed_pred numeric(6,2) NOT NULL,
    speed_actual numeric(6,2) NOT NULL,
    abs_error numeric(6,2) GENERATED ALWAYS AS (abs((speed_pred - speed_actual))) STORED,
    signed_error numeric(6,2) GENERATED ALWAYS AS ((speed_pred - speed_actual)) STORED,
    inserted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: road_importance_ref; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.road_importance_ref (
    hex_id text NOT NULL,
    road_gid integer NOT NULL,
    road_name text,
    importance text,
    importance_code smallint DEFAULT 0 NOT NULL,
    sens text
);


--
-- Name: sensor_road_importance; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.sensor_road_importance (
    channel_id text NOT NULL,
    importance_code smallint DEFAULT 0 NOT NULL,
    importance_label text
);


--
-- Name: stgcn_predictions_live; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.stgcn_predictions_live (
    predicted_for timestamp with time zone NOT NULL,
    input_window_end timestamp with time zone NOT NULL,
    node_idx integer NOT NULL,
    properties_twgid character varying(100),
    predicted_speed_kmh double precision NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: tarifs_modes; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.tarifs_modes (
    id integer NOT NULL,
    mode text NOT NULL,
    produit text NOT NULL,
    produit_label text NOT NULL,
    age_min integer,
    age_max integer,
    prix_eur numeric(6,3) NOT NULL,
    duree_min integer,
    notes text,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: tarifs_modes_id_seq; Type: SEQUENCE; Schema: gold; Owner: -
--

CREATE SEQUENCE gold.tarifs_modes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tarifs_modes_id_seq; Type: SEQUENCE OWNED BY; Schema: gold; Owner: -
--

ALTER SEQUENCE gold.tarifs_modes_id_seq OWNED BY gold.tarifs_modes.id;


--
-- Name: tcl_vehicle_realtime_id_seq; Type: SEQUENCE; Schema: gold; Owner: -
--

CREATE SEQUENCE gold.tcl_vehicle_realtime_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tcl_vehicle_realtime_id_seq; Type: SEQUENCE OWNED BY; Schema: gold; Owner: -
--

ALTER SEQUENCE gold.tcl_vehicle_realtime_id_seq OWNED BY gold.tcl_vehicle_realtime.id;


--
-- Name: traffic_features_live_id_seq; Type: SEQUENCE; Schema: gold; Owner: -
--

CREATE SEQUENCE gold.traffic_features_live_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: traffic_features_live_id_seq; Type: SEQUENCE OWNED BY; Schema: gold; Owner: -
--

ALTER SEQUENCE gold.traffic_features_live_id_seq OWNED BY gold.traffic_features_live.id;


--
-- Name: trafic_predictions; Type: TABLE; Schema: gold; Owner: -
--

CREATE TABLE gold.trafic_predictions (
    axis_key text NOT NULL,
    horizon_h integer NOT NULL,
    calculated_at timestamp with time zone NOT NULL,
    speed_pred numeric(6,2),
    etat_pred character(1),
    color character varying(7),
    vitesse_limite_kmh numeric(6,2),
    label character varying(256),
    model_version character varying(32),
    lat double precision,
    lon double precision,
    x_2154 double precision,
    y_2154 double precision
);


--
-- Name: TABLE trafic_predictions; Type: COMMENT; Schema: gold; Owner: -
--

COMMENT ON TABLE gold.trafic_predictions IS 'Prédictions pré-calculées de vitesse live. Alimentée toutes les heures par dag_live_speed_retrain après entraînement des 4 modèles XGBoost. Une ligne par axe + horizon + timestamp. Permet au dashboard de simplement lire les prédictions sans calcul direct.';


--
-- Name: COLUMN trafic_predictions.axis_key; Type: COMMENT; Schema: gold; Owner: -
--

COMMENT ON COLUMN gold.trafic_predictions.axis_key IS 'Identifiant tronçon (ex: "12345") - jointure sur pvotrafic_snapshots.code';


--
-- Name: COLUMN trafic_predictions.horizon_h; Type: COMMENT; Schema: gold; Owner: -
--

COMMENT ON COLUMN gold.trafic_predictions.horizon_h IS 'Horizon de prédiction en heures: 0=H+5min, 1=H+1h, 3=H+3h, 6=H+6h';


--
-- Name: COLUMN trafic_predictions.calculated_at; Type: COMMENT; Schema: gold; Owner: -
--

COMMENT ON COLUMN gold.trafic_predictions.calculated_at IS 'Timestamp du calcul (quand le DAG a lancé la prédiction). Permet de nettoyer les anciennes lignes.';


--
-- Name: meteo_hourly; Type: TABLE; Schema: silver; Owner: -
--

CREATE TABLE silver.meteo_hourly (
    measurement_time timestamp with time zone NOT NULL,
    temperature_2m double precision,
    precipitation double precision,
    rain double precision,
    cloud_cover double precision,
    weather_code integer,
    visibility double precision,
    wind_speed_10m double precision,
    wind_gusts_10m double precision,
    uv_index real,
    humidity double precision,
    fetched_at timestamp with time zone,
    is_forecast boolean
);


--
-- Name: trafic_boucles_clean; Type: TABLE; Schema: silver; Owner: -
--

CREATE TABLE silver.trafic_boucles_clean (
    channel_id text NOT NULL,
    fetched_at timestamp with time zone NOT NULL,
    speed_kmh double precision,
    vitesse_limite_kmh double precision,
    is_sanitary boolean DEFAULT true,
    geom public.geometry(Point,4326),
    silver_updated_at timestamp with time zone DEFAULT now(),
    geom_2154 public.geometry(Point,2154)
);


--
-- Name: trafic_vitesse_propre; Type: TABLE; Schema: silver; Owner: -
--

CREATE TABLE silver.trafic_vitesse_propre (
    id_rue integer,
    properties_twgid character varying(100),
    properties_gid bigint,
    properties_libelle text,
    properties_sens text,
    properties_etat text,
    properties_vitesse double precision,
    properties_last_update timestamp with time zone,
    properties_est_a_jour boolean,
    speed_category text,
    speed_color_map text,
    geometry_wgs84_wkt text,
    points_json jsonb,
    hexes_json jsonb,
    merged_h3_geometry_json jsonb,
    transformed_at timestamp with time zone NOT NULL
);


--
-- Name: air_quality id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.air_quality ALTER COLUMN id SET DEFAULT nextval('bronze.air_quality_id_seq'::regclass);


--
-- Name: calendrier_scolaire id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.calendrier_scolaire ALTER COLUMN id SET DEFAULT nextval('bronze.calendrier_scolaire_id_seq'::regclass);


--
-- Name: chantiers id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.chantiers ALTER COLUMN id SET DEFAULT nextval('bronze.chantiers_id_seq'::regclass);


--
-- Name: chantiers_historique id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.chantiers_historique ALTER COLUMN id SET DEFAULT nextval('bronze.chantiers_historique_id_seq'::regclass);


--
-- Name: chantiers_voirie id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.chantiers_voirie ALTER COLUMN id SET DEFAULT nextval('bronze.chantiers_voirie_id_seq'::regclass);


--
-- Name: comptages id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.comptages ALTER COLUMN id SET DEFAULT nextval('bronze.comptages_id_seq1'::regclass);


--
-- Name: meteo id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.meteo ALTER COLUMN id SET DEFAULT nextval('bronze.meteo_id_seq'::regclass);


--
-- Name: parkings id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.parkings ALTER COLUMN id SET DEFAULT nextval('bronze.parkings_id_seq'::regclass);


--
-- Name: pvotrafic_snapshots id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.pvotrafic_snapshots ALTER COLUMN id SET DEFAULT nextval('bronze.pvotrafic_snapshots_id_seq1'::regclass);


--
-- Name: tcl_vehicles id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.tcl_vehicles ALTER COLUMN id SET DEFAULT nextval('bronze.tcl_vehicles_id_seq'::regclass);


--
-- Name: tomtom_flow id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.tomtom_flow ALTER COLUMN id SET DEFAULT nextval('bronze.tomtom_flow_id_seq'::regclass);


--
-- Name: trafic_boucles id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.trafic_boucles ALTER COLUMN id SET DEFAULT nextval('bronze.trafic_boucles_id_seq1'::regclass);


--
-- Name: trafic_vitesse_brute id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.trafic_vitesse_brute ALTER COLUMN id SET DEFAULT nextval('bronze.trafic_vitesse_brute_id_seq'::regclass);


--
-- Name: velov id; Type: DEFAULT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.velov ALTER COLUMN id SET DEFAULT nextval('bronze.velov_id_seq'::regclass);


--
-- Name: features_traffic id; Type: DEFAULT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.features_traffic ALTER COLUMN id SET DEFAULT nextval('gold.features_traffic_id_seq'::regclass);


--
-- Name: tarifs_modes id; Type: DEFAULT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.tarifs_modes ALTER COLUMN id SET DEFAULT nextval('gold.tarifs_modes_id_seq'::regclass);


--
-- Name: tcl_vehicle_realtime id; Type: DEFAULT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.tcl_vehicle_realtime ALTER COLUMN id SET DEFAULT nextval('gold.tcl_vehicle_realtime_id_seq'::regclass);


--
-- Name: traffic_features_live id; Type: DEFAULT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.traffic_features_live ALTER COLUMN id SET DEFAULT nextval('gold.traffic_features_live_id_seq'::regclass);


--
-- Name: air_quality air_quality_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.air_quality
    ADD CONSTRAINT air_quality_pkey PRIMARY KEY (id);


--
-- Name: calendrier_scolaire calendrier_scolaire_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.calendrier_scolaire
    ADD CONSTRAINT calendrier_scolaire_pkey PRIMARY KEY (id);


--
-- Name: calendrier_scolaire calendrier_scolaire_zone_start_date_description_key; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.calendrier_scolaire
    ADD CONSTRAINT calendrier_scolaire_zone_start_date_description_key UNIQUE (zone, start_date, description);


--
-- Name: chantiers_historique chantiers_historique_numero_key; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.chantiers_historique
    ADD CONSTRAINT chantiers_historique_numero_key UNIQUE (numero);


--
-- Name: chantiers_historique chantiers_historique_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.chantiers_historique
    ADD CONSTRAINT chantiers_historique_pkey PRIMARY KEY (id);


--
-- Name: chantiers chantiers_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.chantiers
    ADD CONSTRAINT chantiers_pkey PRIMARY KEY (id);


--
-- Name: chantiers_voirie chantiers_voirie_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.chantiers_voirie
    ADD CONSTRAINT chantiers_voirie_pkey PRIMARY KEY (id);


--
-- Name: comptages comptages_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.comptages
    ADD CONSTRAINT comptages_pkey PRIMARY KEY (id);


--
-- Name: jours_feries jours_feries_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.jours_feries
    ADD CONSTRAINT jours_feries_pkey PRIMARY KEY (date_ferie);


--
-- Name: meteo meteo_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.meteo
    ADD CONSTRAINT meteo_pkey PRIMARY KEY (id);


--
-- Name: parkings parkings_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.parkings
    ADD CONSTRAINT parkings_pkey PRIMARY KEY (id);


--
-- Name: prix_carburants prix_carburants_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.prix_carburants
    ADD CONSTRAINT prix_carburants_pkey PRIMARY KEY (collected_at, carburant, zone);


--
-- Name: pvotrafic_snapshots pvotrafic_snapshots_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.pvotrafic_snapshots
    ADD CONSTRAINT pvotrafic_snapshots_pkey PRIMARY KEY (id);


--
-- Name: tcl_vehicles tcl_vehicles_fetched_at_vehicle_ref_key; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.tcl_vehicles
    ADD CONSTRAINT tcl_vehicles_fetched_at_vehicle_ref_key UNIQUE (fetched_at, vehicle_ref);


--
-- Name: tcl_vehicles tcl_vehicles_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.tcl_vehicles
    ADD CONSTRAINT tcl_vehicles_pkey PRIMARY KEY (id);


--
-- Name: tomtom_flow tomtom_flow_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.tomtom_flow
    ADD CONSTRAINT tomtom_flow_pkey PRIMARY KEY (id);


--
-- Name: tomtom_flow tomtom_flow_point_name_collected_at_key; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.tomtom_flow
    ADD CONSTRAINT tomtom_flow_point_name_collected_at_key UNIQUE (point_name, collected_at);


--
-- Name: trafic_boucles trafic_boucles_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.trafic_boucles
    ADD CONSTRAINT trafic_boucles_pkey PRIMARY KEY (id);


--
-- Name: trafic_vitesse_brute trafic_vitesse_brute_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.trafic_vitesse_brute
    ADD CONSTRAINT trafic_vitesse_brute_pkey PRIMARY KEY (id);


--
-- Name: pvotrafic_snapshots uq_pvotrafic_code_collected; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.pvotrafic_snapshots
    ADD CONSTRAINT uq_pvotrafic_code_collected UNIQUE (code, collected_at);


--
-- Name: velov velov_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.velov
    ADD CONSTRAINT velov_pkey PRIMARY KEY (id);


--
-- Name: vitesse_limite_ref vitesse_limite_ref_pkey; Type: CONSTRAINT; Schema: bronze; Owner: -
--

ALTER TABLE ONLY bronze.vitesse_limite_ref
    ADD CONSTRAINT vitesse_limite_ref_pkey PRIMARY KEY (code);


--
-- Name: channel_tomtom_mapping channel_tomtom_mapping_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.channel_tomtom_mapping
    ADD CONSTRAINT channel_tomtom_mapping_pkey PRIMARY KEY (channel_id);


--
-- Name: channels_ref channels_ref_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.channels_ref
    ADD CONSTRAINT channels_ref_pkey PRIMARY KEY (channel_id);


--
-- Name: dim_gnn_adjacency dim_gnn_adjacency_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.dim_gnn_adjacency
    ADD CONSTRAINT dim_gnn_adjacency_pkey PRIMARY KEY (node_u, node_v);


--
-- Name: dim_spatial_grid_mapping dim_spatial_grid_mapping_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.dim_spatial_grid_mapping
    ADD CONSTRAINT dim_spatial_grid_mapping_pkey PRIMARY KEY (properties_twgid);


--
-- Name: dim_temps dim_temps_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.dim_temps
    ADD CONSTRAINT dim_temps_pkey PRIMARY KEY (tranche_5min);


--
-- Name: fact_traffic_series fact_traffic_series_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.fact_traffic_series
    ADD CONSTRAINT fact_traffic_series_pkey PRIMARY KEY ("timestamp", node_idx);


--
-- Name: features_traffic features_traffic_channel_id_measurement_time_key; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.features_traffic
    ADD CONSTRAINT features_traffic_channel_id_measurement_time_key UNIQUE (channel_id, measurement_time);


--
-- Name: features_traffic features_traffic_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.features_traffic
    ADD CONSTRAINT features_traffic_pkey PRIMARY KEY (id);


--
-- Name: h3_trafic_live h3_trafic_live_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.h3_trafic_live
    ADD CONSTRAINT h3_trafic_live_pkey PRIMARY KEY (hex_id, sens);


--
-- Name: h3_trafic_predictions h3_trafic_predictions_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.h3_trafic_predictions
    ADD CONSTRAINT h3_trafic_predictions_pkey PRIMARY KEY (hex_id, horizon_h);


--
-- Name: model_drift_reports model_drift_reports_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.model_drift_reports
    ADD CONSTRAINT model_drift_reports_pkey PRIMARY KEY (computed_at);


--
-- Name: predictions_vs_actuals predictions_vs_actuals_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.predictions_vs_actuals
    ADD CONSTRAINT predictions_vs_actuals_pkey PRIMARY KEY (axis_key, horizon_h, calculated_at);


--
-- Name: road_importance_ref road_importance_ref_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.road_importance_ref
    ADD CONSTRAINT road_importance_ref_pkey PRIMARY KEY (hex_id, road_gid);


--
-- Name: sensor_road_importance sensor_road_importance_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.sensor_road_importance
    ADD CONSTRAINT sensor_road_importance_pkey PRIMARY KEY (channel_id);


--
-- Name: stgcn_predictions_live stgcn_predictions_live_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.stgcn_predictions_live
    ADD CONSTRAINT stgcn_predictions_live_pkey PRIMARY KEY (predicted_for, node_idx);


--
-- Name: tarifs_modes tarifs_modes_mode_produit_age_min_age_max_key; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.tarifs_modes
    ADD CONSTRAINT tarifs_modes_mode_produit_age_min_age_max_key UNIQUE (mode, produit, age_min, age_max);


--
-- Name: tarifs_modes tarifs_modes_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.tarifs_modes
    ADD CONSTRAINT tarifs_modes_pkey PRIMARY KEY (id);


--
-- Name: tcl_vehicle_realtime tcl_vehicle_realtime_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.tcl_vehicle_realtime
    ADD CONSTRAINT tcl_vehicle_realtime_pkey PRIMARY KEY (id);


--
-- Name: tcl_vehicle_realtime tcl_vehicle_realtime_recorded_at_vehicle_ref_key; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.tcl_vehicle_realtime
    ADD CONSTRAINT tcl_vehicle_realtime_recorded_at_vehicle_ref_key UNIQUE (recorded_at, vehicle_ref);


--
-- Name: traffic_features_live traffic_features_live_channel_id_fetched_at_key; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.traffic_features_live
    ADD CONSTRAINT traffic_features_live_channel_id_fetched_at_key UNIQUE (channel_id, fetched_at);


--
-- Name: traffic_features_live traffic_features_live_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.traffic_features_live
    ADD CONSTRAINT traffic_features_live_pkey PRIMARY KEY (id);


--
-- Name: trafic_predictions trafic_predictions_pkey; Type: CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.trafic_predictions
    ADD CONSTRAINT trafic_predictions_pkey PRIMARY KEY (axis_key, horizon_h, calculated_at);


--
-- Name: meteo_hourly meteo_hourly_pkey; Type: CONSTRAINT; Schema: silver; Owner: -
--

ALTER TABLE ONLY silver.meteo_hourly
    ADD CONSTRAINT meteo_hourly_pkey PRIMARY KEY (measurement_time);


--
-- Name: trafic_boucles_clean trafic_boucles_clean_pkey; Type: CONSTRAINT; Schema: silver; Owner: -
--

ALTER TABLE ONLY silver.trafic_boucles_clean
    ADD CONSTRAINT trafic_boucles_clean_pkey PRIMARY KEY (channel_id, fetched_at);


--
-- Name: idx_air_quality_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_air_quality_time ON bronze.air_quality USING btree (measurement_time);


--
-- Name: idx_bronze_fetched_at; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_bronze_fetched_at ON bronze.trafic_vitesse_brute USING btree (fetched_at DESC);


--
-- Name: idx_bronze_trafic_vitesse_brute_fetched_at; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_bronze_trafic_vitesse_brute_fetched_at ON bronze.trafic_vitesse_brute USING btree (fetched_at DESC);


--
-- Name: idx_calendrier_scolaire_dates; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_calendrier_scolaire_dates ON bronze.calendrier_scolaire USING btree (zone, start_date, end_date);


--
-- Name: idx_chantiers_dates; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_chantiers_dates ON bronze.chantiers USING btree (date_debut, date_fin);


--
-- Name: idx_chantiers_geom; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_chantiers_geom ON bronze.chantiers USING gist (geom);


--
-- Name: idx_chantiers_hist_dates; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_chantiers_hist_dates ON bronze.chantiers_historique USING btree (date_debut, date_fin);


--
-- Name: idx_chantiers_hist_geom; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_chantiers_hist_geom ON bronze.chantiers_historique USING gist (geom);


--
-- Name: idx_chantiers_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_chantiers_time ON bronze.chantiers USING btree (fetched_at);


--
-- Name: idx_chantiers_voirie_geom; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_chantiers_voirie_geom ON bronze.chantiers_voirie USING gist (geom);


--
-- Name: idx_chantiers_voirie_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_chantiers_voirie_time ON bronze.chantiers_voirie USING btree (fetched_at);


--
-- Name: idx_comptages_measurement_brin; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_comptages_measurement_brin ON bronze.comptages USING brin (measurement_time);


--
-- Name: idx_comptages_site; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_comptages_site ON bronze.comptages USING btree (site_id);


--
-- Name: idx_comptages_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_comptages_time ON bronze.comptages USING btree (measurement_time);


--
-- Name: idx_meteo_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_meteo_time ON bronze.meteo USING btree (measurement_time);


--
-- Name: idx_parkings_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_parkings_time ON bronze.parkings USING btree (fetched_at);


--
-- Name: idx_prix_carburants_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_prix_carburants_time ON bronze.prix_carburants USING btree (collected_at DESC);


--
-- Name: idx_pvotrafic_code; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_pvotrafic_code ON bronze.pvotrafic_snapshots USING btree (code, collected_at DESC);


--
-- Name: idx_pvotrafic_collected; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_pvotrafic_collected ON bronze.pvotrafic_snapshots USING btree (collected_at DESC);


--
-- Name: idx_pvotrafic_collected_brin; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_pvotrafic_collected_brin ON bronze.pvotrafic_snapshots USING brin (collected_at);


--
-- Name: idx_tcl_vehicles_fetched; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_tcl_vehicles_fetched ON bronze.tcl_vehicles USING btree (fetched_at DESC);


--
-- Name: idx_tcl_vehicles_fetched_brin; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_tcl_vehicles_fetched_brin ON bronze.tcl_vehicles USING brin (fetched_at);


--
-- Name: idx_tomtom_flow_point; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_tomtom_flow_point ON bronze.tomtom_flow USING btree (point_name);


--
-- Name: idx_tomtom_flow_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_tomtom_flow_time ON bronze.tomtom_flow USING btree (collected_at);


--
-- Name: idx_trafic_boucles_fetched_brin; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_trafic_boucles_fetched_brin ON bronze.trafic_boucles USING brin (fetched_at);


--
-- Name: idx_trafic_boucles_geom_2154; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_trafic_boucles_geom_2154 ON bronze.trafic_boucles USING gist (geom);


--
-- Name: idx_trafic_boucles_geom_4326; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_trafic_boucles_geom_4326 ON bronze.trafic_boucles USING gist (geom_4326);


--
-- Name: idx_trafic_boucles_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_trafic_boucles_time ON bronze.trafic_boucles USING btree (fetched_at);


--
-- Name: idx_trafic_boucles_troncon; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_trafic_boucles_troncon ON bronze.trafic_boucles USING btree (troncon_id);


--
-- Name: idx_velov_fetched_brin; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_velov_fetched_brin ON bronze.velov USING brin (fetched_at);


--
-- Name: idx_velov_station; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_velov_station ON bronze.velov USING btree (station_id);


--
-- Name: idx_velov_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_velov_time ON bronze.velov USING btree (fetched_at);


--
-- Name: idx_vitesse_limite_codetroncon; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_vitesse_limite_codetroncon ON bronze.vitesse_limite_ref USING btree (codetroncon);


--
-- Name: idx_vitesse_limite_ref_code; Type: INDEX; Schema: bronze; Owner: -
--

CREATE INDEX idx_vitesse_limite_ref_code ON bronze.vitesse_limite_ref USING btree (code);


--
-- Name: uq_air_quality_nodup; Type: INDEX; Schema: bronze; Owner: -
--
<<<<<<< HEAD

CREATE UNIQUE INDEX uq_air_quality_nodup ON bronze.air_quality USING btree (measurement_time, pm10, pm2_5, nitrogen_dioxide, ozone, sulphur_dioxide, carbon_monoxide, european_aqi) NULLS NOT DISTINCT;
=======
-- Sprint 8 (2026-06-12) — VIRE. Cette UNIQUE INDEX sur les colonnes
-- extracted (pm10, pm2_5, etc.) plante en duplicate key quand le
-- collecteur insère 2 cycles consécutifs avec colonnes=NULL (les
-- vraies données sont dans raw_data JSONB, pas dans les colonnes).
-- Le collecteur insère 1 ligne par cycle (fetched_at + raw_data) ;
-- il n'y a pas de duplicate au niveau métier puisque fetched_at est
-- déjà indexé.
-- (Sprint 8+1) : on garde idx_bronze_air_quality_fetched_at pour
-- la perf des queries de fraîcheur.

-- CREATE UNIQUE INDEX uq_air_quality_nodup ON bronze.air_quality USING btree (measurement_time, pm10, pm2_5, nitrogen_dioxide, ozone, sulphur_dioxide, carbon_monoxide, european_aqi) NULLS NOT DISTINCT;
>>>>>>> origin/main


--
-- Name: uq_chantiers_nodup; Type: INDEX; Schema: bronze; Owner: -
--
<<<<<<< HEAD

CREATE UNIQUE INDEX uq_chantiers_nodup ON bronze.chantiers USING btree (chantier_id, nom, type_perturbation, severite, date_debut, date_fin, commune) NULLS NOT DISTINCT;
=======
-- Sprint 8 (2026-06-12) — VIRE (même raison que uq_air_quality_nodup).
-- Les vraies données sont dans raw_data JSONB, pas dans les
-- colonnes extracted. La UNIQUE INDEX plante en duplicate key
-- quand on insère plusieurs cycles consécutifs avec colonnes=NULL.

-- CREATE UNIQUE INDEX uq_chantiers_nodup ON bronze.chantiers USING btree (chantier_id, nom, type_perturbation, severite, date_debut, date_fin, commune) NULLS NOT DISTINCT;
>>>>>>> origin/main


--
-- Name: uq_meteo_measurement_time; Type: INDEX; Schema: bronze; Owner: -
--

CREATE UNIQUE INDEX uq_meteo_measurement_time ON bronze.meteo USING btree (measurement_time) WHERE (measurement_time IS NOT NULL);


--
-- Name: uq_trafic_boucles_nodup; Type: INDEX; Schema: bronze; Owner: -
--

CREATE UNIQUE INDEX uq_trafic_boucles_nodup ON bronze.trafic_boucles USING btree (troncon_id, fetched_at) WHERE (troncon_id IS NOT NULL);


--
-- Name: idx_channels_ref_geom; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_channels_ref_geom ON gold.channels_ref USING gist (geom);


--
-- Name: idx_channels_ref_site; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_channels_ref_site ON gold.channels_ref USING btree (site_id);


--
-- Name: idx_dga_v; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_dga_v ON gold.dim_gnn_adjacency USING btree (node_v);


--
-- Name: idx_dim_temps_date; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_dim_temps_date ON gold.dim_temps USING btree (date_calcul, heure, jour_semaine);


--
-- Name: idx_dim_temps_horaire; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_dim_temps_horaire ON gold.dim_temps USING btree (tranche_horaire, date_calcul);


--
-- Name: idx_drift_reports_recent; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_drift_reports_recent ON gold.model_drift_reports USING btree (computed_at DESC);


--
-- Name: idx_dsgm_h3; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_dsgm_h3 ON gold.dim_spatial_grid_mapping USING btree (h3_id);


--
-- Name: idx_dsgm_node; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_dsgm_node ON gold.dim_spatial_grid_mapping USING btree (node_idx);


--
-- Name: idx_ft_channel; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_ft_channel ON gold.features_traffic USING btree (channel_id);


--
-- Name: idx_ft_dow; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_ft_dow ON gold.features_traffic USING btree (day_of_week, hour_of_day);


--
-- Name: idx_ft_time; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_ft_time ON gold.features_traffic USING btree (measurement_time);


--
-- Name: idx_gold_dim_gnn_adjacency_node_v; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_dim_gnn_adjacency_node_v ON gold.dim_gnn_adjacency USING btree (node_v);


--
-- Name: idx_gold_dim_spatial_grid_mapping_h3; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_dim_spatial_grid_mapping_h3 ON gold.dim_spatial_grid_mapping USING btree (h3_id);


--
-- Name: idx_gold_dim_spatial_grid_mapping_node_idx; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_dim_spatial_grid_mapping_node_idx ON gold.dim_spatial_grid_mapping USING btree (node_idx);


--
-- Name: idx_gold_fact_traffic_series_node_idx; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_fact_traffic_series_node_idx ON gold.fact_traffic_series USING btree (node_idx);


--
-- Name: idx_gold_fact_traffic_series_ts_brin; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_fact_traffic_series_ts_brin ON gold.fact_traffic_series USING brin ("timestamp") WITH (pages_per_range='32');


--
-- Name: idx_gold_model_drift_reports_computed_at; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_model_drift_reports_computed_at ON gold.model_drift_reports USING btree (computed_at DESC);


--
-- Name: idx_gold_stgcn_predictions_predicted_for; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_stgcn_predictions_predicted_for ON gold.stgcn_predictions_live USING btree (predicted_for DESC);


--
-- Name: idx_gold_stgcn_predictions_twgid; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_stgcn_predictions_twgid ON gold.stgcn_predictions_live USING btree (properties_twgid);


--
-- Name: idx_gold_traffic_channel; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_traffic_channel ON gold.traffic_features_live USING btree (channel_id, fetched_at DESC);


--
-- Name: idx_gold_traffic_ml; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_traffic_ml ON gold.traffic_features_live USING btree (channel_id, fetched_at) INCLUDE (speed_kmh, lag_1, lag_2, lag_3, delta_current, delta_1, rolling_mean_3);


--
-- Name: idx_gold_traffic_time; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_gold_traffic_time ON gold.traffic_features_live USING btree (fetched_at DESC);


--
-- Name: idx_h3_predictions_horizon; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_h3_predictions_horizon ON gold.h3_trafic_predictions USING btree (horizon_h);


--
-- Name: idx_h3_trafic_live_etat; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_h3_trafic_live_etat ON gold.h3_trafic_live USING btree (etat);


--
-- Name: idx_mv_fact_traffic_pivot_ts_node; Type: INDEX; Schema: gold; Owner: -
--

CREATE UNIQUE INDEX idx_mv_fact_traffic_pivot_ts_node ON gold.mv_fact_traffic_pivot USING btree ("timestamp", node_idx);


--
-- Name: idx_pva_axis_horizon; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_pva_axis_horizon ON gold.predictions_vs_actuals USING btree (axis_key, horizon_h);


--
-- Name: idx_pva_calculated_at; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_pva_calculated_at ON gold.predictions_vs_actuals USING btree (calculated_at DESC);


--
-- Name: idx_pva_horizon_recent; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_pva_horizon_recent ON gold.predictions_vs_actuals USING btree (horizon_h, calculated_at DESC);


--
-- Name: idx_road_importance_ref_code; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_road_importance_ref_code ON gold.road_importance_ref USING btree (importance_code DESC);


--
-- Name: idx_road_importance_ref_hex_id; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_road_importance_ref_hex_id ON gold.road_importance_ref USING btree (hex_id);


--
-- Name: idx_tarifs_modes_mode_age; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_tarifs_modes_mode_age ON gold.tarifs_modes USING btree (mode, age_min, age_max);


--
-- Name: idx_tcl_realtime_recorded; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_tcl_realtime_recorded ON gold.tcl_vehicle_realtime USING btree (recorded_at DESC);


--
-- Name: idx_trafic_predictions_age; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_trafic_predictions_age ON gold.trafic_predictions USING btree (calculated_at DESC);


--
-- Name: idx_trafic_predictions_axis_horizon; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_trafic_predictions_axis_horizon ON gold.trafic_predictions USING btree (axis_key, horizon_h);


--
-- Name: idx_trafic_predictions_horizon_recent; Type: INDEX; Schema: gold; Owner: -
--

CREATE INDEX idx_trafic_predictions_horizon_recent ON gold.trafic_predictions USING btree (horizon_h, calculated_at DESC);


--
-- Name: idx_silver_boucles_channel; Type: INDEX; Schema: silver; Owner: -
--

CREATE INDEX idx_silver_boucles_channel ON silver.trafic_boucles_clean USING btree (channel_id, fetched_at DESC);


--
-- Name: idx_silver_boucles_fetched; Type: INDEX; Schema: silver; Owner: -
--

CREATE INDEX idx_silver_boucles_fetched ON silver.trafic_boucles_clean USING btree (fetched_at DESC);


--
-- Name: idx_silver_meteo_time; Type: INDEX; Schema: silver; Owner: -
--

CREATE INDEX idx_silver_meteo_time ON silver.meteo_hourly USING btree (measurement_time DESC);


--
-- Name: idx_silver_trafic_vitesse_propre_transformed_at; Type: INDEX; Schema: silver; Owner: -
--

CREATE INDEX idx_silver_trafic_vitesse_propre_transformed_at ON silver.trafic_vitesse_propre USING btree (transformed_at DESC);


--
-- Name: idx_silver_trafic_vitesse_propre_twgid; Type: INDEX; Schema: silver; Owner: -
--

CREATE INDEX idx_silver_trafic_vitesse_propre_twgid ON silver.trafic_vitesse_propre USING btree (properties_twgid);


--
-- Name: idx_silver_trafic_vitesse_propre_twgid_ts; Type: INDEX; Schema: silver; Owner: -
--

CREATE INDEX idx_silver_trafic_vitesse_propre_twgid_ts ON silver.trafic_vitesse_propre USING btree (properties_twgid, transformed_at DESC);


--
-- Name: uq_silver_trafic_vitesse_propre_twgid_ts; Type: INDEX; Schema: silver; Owner: -
--

CREATE UNIQUE INDEX uq_silver_trafic_vitesse_propre_twgid_ts ON silver.trafic_vitesse_propre USING btree (properties_twgid, transformed_at);


--
-- Name: channel_tomtom_mapping channel_tomtom_mapping_channel_id_fkey; Type: FK CONSTRAINT; Schema: gold; Owner: -
--

ALTER TABLE ONLY gold.channel_tomtom_mapping
    ADD CONSTRAINT channel_tomtom_mapping_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES gold.channels_ref(channel_id);


--
-- Silver tables added by migrate_realign_v0.3.1
--

CREATE TABLE IF NOT EXISTS silver.tcl_vehicles_clean (
    id              BIGSERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL,
    measurement_time TIMESTAMPTZ NOT NULL,
    line_ref        TEXT NOT NULL,
    direction_ref   TEXT,
    journey_ref     TEXT,
    stop_ref        TEXT,
    delay_seconds   INTEGER,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    raw_data        JSONB,
    CONSTRAINT silver_tcl_uniq UNIQUE (line_ref, journey_ref, stop_ref, measurement_time)
);
CREATE INDEX IF NOT EXISTS idx_silver_tcl_line_time ON silver.tcl_vehicles_clean (line_ref, measurement_time DESC);

CREATE TABLE IF NOT EXISTS silver.velov_clean (
    id                  BIGSERIAL PRIMARY KEY,
    fetched_at          TIMESTAMPTZ NOT NULL,
    measurement_time    TIMESTAMPTZ NOT NULL,
    station_id          TEXT NOT NULL,
    station_name        TEXT,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    num_bikes_available INTEGER,
    num_docks_available INTEGER,
    is_active           BOOLEAN DEFAULT TRUE,
    CONSTRAINT silver_velov_uniq UNIQUE (station_id, measurement_time)
);
CREATE INDEX IF NOT EXISTS idx_silver_velov_station_time ON silver.velov_clean (station_id, measurement_time DESC);

CREATE TABLE IF NOT EXISTS silver.chantiers_actifs (
    id              BIGSERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL,
    chantier_id     TEXT NOT NULL,
    titre           TEXT,
    description     TEXT,
    date_debut      DATE,
    date_fin        DATE,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    is_active       BOOLEAN GENERATED ALWAYS AS (
        date_debut <= CURRENT_DATE AND (date_fin IS NULL OR date_fin >= CURRENT_DATE)
    ) STORED,
    raw_data        JSONB,
    CONSTRAINT silver_chantiers_uniq UNIQUE (chantier_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_silver_chantiers_active ON silver.chantiers_actifs (is_active, date_fin);

--
-- Gold tables added by migrate_realign_v0.3.1
--

CREATE TABLE IF NOT EXISTS gold.bus_delay_segments (
    id                  BIGSERIAL PRIMARY KEY,
    line_ref            TEXT NOT NULL,
    segment_id          TEXT NOT NULL,
    hour_of_day         SMALLINT,
    day_of_week         SMALLINT,
    is_vacances         BOOLEAN,
    is_ferie            BOOLEAN,
    weather_code        INTEGER,
    avg_delay_seconds   REAL,
    p90_delay_seconds   REAL,
    n_observations      INTEGER,
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT gold_bus_delay_uniq UNIQUE (line_ref, segment_id, hour_of_day, day_of_week)
);
CREATE INDEX IF NOT EXISTS idx_gold_bus_delay_line ON gold.bus_delay_segments (line_ref);

CREATE TABLE IF NOT EXISTS gold.infrastructure_bottlenecks (
    id                  BIGSERIAL PRIMARY KEY,
    segment_id          TEXT NOT NULL,
    line_ref            TEXT,
    diagnosis           TEXT NOT NULL,
    bus_delay_seconds   REAL,
    traffic_speed_kmh   REAL,
    traffic_congestion  REAL,
    lat                 DOUBLE PRECISION,
    lon                 DOUBLE PRECISION,
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    n_observations      INTEGER,
    CONSTRAINT gold_infra_uniq UNIQUE (segment_id, line_ref, computed_at)
);
CREATE INDEX IF NOT EXISTS idx_gold_infra_diagnosis ON gold.infrastructure_bottlenecks (diagnosis);

--
-- PostgreSQL database dump complete
--

\unrestrict eLK4aQ7gfzFdprZfD2IjJ0zdKcgGvZruUBhbWXOe9eQLV6CctrWtjqAWOc8aE4F

