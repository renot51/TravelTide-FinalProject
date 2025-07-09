-- =============================
-- TravelTide: User Session & Trip Analysis
-- =============================
-- Purpose:
-- - Filter active users
-- - Build session and trip metrics
-- - Generate user-based travel perks
-- =============================


-- 1. Sessions from 2023 onwards
WITH sessions_2023 AS (
    SELECT *
    FROM sessions s
    WHERE s.session_start > '2023-01-04'
),

-- 2. Filter users with more than 7 sessions
filtered_users AS (
    SELECT user_id
    FROM sessions_2023
    GROUP BY user_id
    HAVING COUNT(*) > 7
),

-- 3. Enriched session data with user, flight, and hotel info
session_base AS (
    SELECT
        s.session_id,
        s.user_id,
        s.trip_id,
        s.session_start,
        s.session_end,
        EXTRACT(EPOCH FROM s.session_end - s.session_start) AS session_duration,
        s.page_clicks,
        s.flight_discount,
        COALESCE(s.flight_discount_amount, 0) AS flight_discount_amount,
        s.hotel_discount,
        COALESCE(s.hotel_discount_amount, 0) AS hotel_discount_amount,
        s.flight_booked,
        s.hotel_booked,
        s.cancellation,

        -- User info
        u.birthdate,
        u.gender,
        u.married,
        u.has_children,
        u.home_country,
        u.home_city,
        u.home_airport,
        u.home_airport_lat,
        u.home_airport_lon,
        u.sign_up_date,

        -- Flight info
        f.origin_airport,
        f.destination,
        f.destination_airport,
        f.seats,
        f.return_flight_booked,
        f.departure_time,
        f.return_time,
        f.checked_bags,
        f.trip_airline,
        f.destination_airport_lat,
        f.destination_airport_lon,
        f.base_fare_usd,

        -- Hotel info
        h.hotel_name,
        CASE WHEN h.nights < 0 THEN 1 ELSE h.nights END AS nights,
        h.rooms,
        h.check_in_time,
        h.check_out_time,
        h.hotel_per_room_usd AS hotel_price_per_room_night_usd

    FROM sessions_2023 s
    LEFT JOIN users u ON s.user_id = u.user_id
    LEFT JOIN flights f ON s.trip_id = f.trip_id
    LEFT JOIN hotels h ON s.trip_id = h.trip_id
    WHERE s.user_id IN (SELECT user_id FROM filtered_users)
),

-- 4. Mark canceled trips (if explicitly marked as cancelled)
canceled_trips AS (
    SELECT DISTINCT trip_id
    FROM session_base
    WHERE cancellation = TRUE
),

-- 5. Keep only valid (non-canceled) trips
not_canceled_trips AS (
    SELECT *
    FROM session_base
    WHERE trip_id IS NOT NULL
      AND trip_id NOT IN (SELECT trip_id FROM canceled_trips)
),

-- 6. Session-based user metrics
user_base_session AS (
    SELECT
        user_id,
        SUM(page_clicks) AS num_clicks,
        COUNT(DISTINCT session_id) AS num_sessions,
        AVG(session_duration) AS avg_session_duration,
        AVG(checked_bags) AS avg_bags
    FROM session_base
    GROUP BY user_id
),

-- 7. Trip-based user metrics
user_base_trip AS (
    SELECT
        user_id,
        COUNT(DISTINCT trip_id) AS num_trips,

        -- Count number of flights (outbound + return)
        SUM(
            CASE
                WHEN flight_booked = TRUE AND return_flight_booked = TRUE THEN 2
                WHEN flight_booked = TRUE THEN 1
                ELSE 0
            END
        ) AS num_flights,

        -- Hotel spending after discount
        COALESCE(
            SUM(
                (hotel_price_per_room_night_usd * nights * rooms) *
                (1 - COALESCE(hotel_discount_amount, 0))
            ), 0
        ) AS money_spent_hotel,

        -- Days between session and departure
        AVG(EXTRACT(DAY FROM departure_time - session_end)) AS time_after_booking,

        -- Average flight distance (haversine)
        AVG(haversine_distance(
            home_airport_lat, home_airport_lon,
            destination_airport_lat, destination_airport_lon
        )) AS avg_km_flown

    FROM not_canceled_trips
    GROUP BY user_id
),

-- 8. Combine session and trip metrics with demographics
user_metrics AS (
    SELECT
        b.user_id,
        COALESCE(b.num_clicks, 0) AS num_clicks,
        COALESCE(b.num_sessions, 0) AS num_sessions,
        COALESCE(b.avg_session_duration, 0) AS avg_session_duration,
        COALESCE(b.avg_bags, 0) AS avg_bags,

        -- Demographics
        EXTRACT(YEAR FROM AGE(u.birthdate)) AS age,
        u.birthdate,
        u.gender,
        u.married,
        u.has_children,
        u.home_country,
        u.home_city,
        u.home_airport,

        -- Trip metrics
        COALESCE(t.num_trips, 0) AS num_trips,
        COALESCE(t.num_flights, 0) AS num_flights,
        COALESCE(t.money_spent_hotel, 0) AS money_spent_hotel,
        COALESCE(t.time_after_booking, 0) AS time_after_booking,
        COALESCE(t.avg_km_flown, 0) AS avg_km_flown

    FROM user_base_session b
    LEFT JOIN users u ON b.user_id = u.user_id
    LEFT JOIN user_base_trip t ON b.user_id = t.user_id
)

-- 9. Add personalized perk based on rules
SELECT
    *,
    CASE
        WHEN num_trips > 0 THEN
            CASE
                WHEN age < 20 THEN
                    CASE
                        WHEN has_children THEN 'free child ticket'
                        ELSE 'discount at special events'
                    END
                WHEN age > 60 THEN 'meal voucher'
                ELSE
                    CASE
                        WHEN has_children AND avg_bags > 2 THEN 'free child ticket'
                        WHEN num_flights > 9 THEN 'free meal'
                        ELSE '10% off next trip'
                    END
            END
        ELSE '30% off first travel'
    END AS perk
FROM user_metrics;
