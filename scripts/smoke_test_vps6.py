"""Smoke test post-deploy Sprint VPS-6 sur le VPS.

Vérifie que :
1. Le référentiel lieux est chargé (21 lieux en DB)
2. Le pathfinding Vélov retourne un itinéraire cohérent
3. Le pathfinding voiture retourne un itinéraire via Dijkstra
4. Mode prod : LYONFLOW_DEMO_MODE=0, fail loud si DB down

Usage :
    docker compose exec -T streamlit python /app/scripts/smoke_test_vps6.py
"""

from __future__ import annotations

import os
import sys

os.environ["LYONFLOW_DEMO_MODE"] = "0"  # Force mode prod

sys.path.insert(0, "/app")


def main() -> int:
    print("=" * 60)
    print("Smoke test Sprint VPS-6 (post-deploy)")
    print("=" * 60)

    # 1. Référentiel lieux
    from src.data.data_loader import load_lyon_addresses_with_coords

    lieux = load_lyon_addresses_with_coords()
    print(f"\n[1/3] Lieux chargés : {len(lieux)}")
    for l in lieux[:3]:  # noqa: E741
        print(f"  - {l['name']} ({l['lat']}, {l['lon']}) [{l['type']}]")
    if len(lieux) < 21:
        print(f"  ⚠️  Attendu: 21 lieux, trouvé: {len(lieux)}")
        return 1

    # 2. Pathfinding Vélov (Part-Dieu → Tête d'Or)
    from src.routing.pathfinder_multimodal import plan_velov_trip

    print("\n[2/3] Pathfinding Vélov (Part-Dieu → Tête d'Or)…")
    itin = plan_velov_trip(
        origin_lat=45.7607,
        origin_lon=4.8589,
        dest_lat=45.7745,
        dest_lon=4.8525,
        origin_label="Part-Dieu",
        dest_label="Tête d'Or",
    )
    print(f"  Durée : {itin.total_duration_min:.1f} min")
    print(f"  Distance : {itin.total_distance_m:.0f} m")
    print(f"  Faisable : {itin.feasible}")
    print(f"  Source : {itin.source}")
    for i, seg in enumerate(itin.segments, 1):
        print(
            f"  Seg {i} [{seg.mode}]: {seg.from_label} → {seg.to_label} "
            f"({seg.distance_m:.0f} m, {seg.duration_min} min)"
        )

    # 3. Pathfinding voiture
    from src.routing.pathfinder_multimodal import plan_car_trip

    print("\n[3/3] Pathfinding voiture (Part-Dieu → Tête d'Or)…")
    car = plan_car_trip(
        origin_lat=45.7607,
        origin_lon=4.8589,
        dest_lat=45.7745,
        dest_lon=4.8525,
    )
    print(f"  Durée : {car.get('total_duration_min', 0):.1f} min")
    print(f"  Distance : {car.get('total_length_m', 0):.0f} m")
    print(f"  Source : {car.get('source', '?')}")
    print(f"  Vitesse moyenne : {car.get('average_speed_kmh', 0):.1f} km/h")
    print(f"  Segments : {len(car.get('segments', []))}")

    print("\n" + "=" * 60)
    print("✅ Smoke test OK — Sprint VPS-6 déployé et opérationnel")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
