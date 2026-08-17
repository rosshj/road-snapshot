#!/usr/bin/env python3
"""Road Snapshots - Google Street View photos at fixed increments along a road.

Uses only the Python standard library (no pip installs needed).

Example:
  python3 road_snapshots.py \
    --origin "Lombard St & Hyde St, San Francisco" \
    --destination "Lombard St & Leavenworth St, San Francisco" \
    --spacing 25 --out ./lombard

The API key is read from --key, the GOOGLE_MAPS_KEY environment variable,
or a key.txt file sitting next to this script (in that order).
"""
import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://maps.googleapis.com/maps/api"
R = 6371000.0  # earth radius, meters


def http_json(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def http_bytes(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def decode_polyline(s):
    pts, i, lat, lng = [], 0, 0, 0
    while i < len(s):
        for which in (0, 1):
            result, shift = 0, 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += d
            else:
                lng += d
        pts.append((lat / 1e5, lng / 1e5))
    return pts


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2
         + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def bearing(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = (math.cos(la1) * math.sin(la2)
         - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def waypoint(s):
    """Accept either an address string or 'lat,lng' coordinates."""
    parts = s.split(",")
    if len(parts) == 2:
        try:
            lat, lng = float(parts[0]), float(parts[1])
            return {"location": {"latLng": {"latitude": lat, "longitude": lng}}}
        except ValueError:
            pass
    return {"address": s}


def build_route(origin, destination, key):
    # Uses the Routes API (the legacy Directions API is closed to new projects).
    body = json.dumps({
        "origin": waypoint(origin),
        "destination": waypoint(destination),
        "travelMode": "DRIVE",
    }).encode()
    req = urllib.request.Request(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": ("routes.description,routes.distanceMeters,"
                                 "routes.legs.steps.polyline.encodedPolyline"),
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"Routes API error: HTTP {e.code}\n{detail}\n"
                         "If this says the API is disabled, enable 'Routes API' at\n"
                         "https://console.cloud.google.com/apis/library/routes.googleapis.com")
    if not j.get("routes"):
        raise SystemExit(f"Routes API returned no route: {json.dumps(j)}")
    route = j["routes"][0]
    path = []
    for leg in route["legs"]:
        for step in leg["steps"]:
            for p in decode_polyline(step["polyline"]["encodedPolyline"]):
                if not path or path[-1] != p:
                    path.append(p)
    return {
        "path": path,
        "summary": route.get("description", ""),
        "distance_m": route.get("distanceMeters", 0),
        "start_address": origin,
        "end_address": destination,
    }


def sample_points(path, spacing):
    out, next_d, walked = [], 0.0, 0.0
    for a, b in zip(path, path[1:]):
        seg = haversine(a, b)
        if seg == 0:
            continue
        brg = bearing(a, b)
        while next_d <= walked + seg:
            f = (next_d - walked) / seg
            out.append({
                "lat": round(a[0] + (b[0] - a[0]) * f, 6),
                "lng": round(a[1] + (b[1] - a[1]) * f, 6),
                "heading": round(brg, 1),
                "dist_m": round(next_d),
            })
            next_d += spacing
        walked += seg
    # Look-ahead headings: face the next sample point ("down the road") rather
    # than the local polyline segment — steadier through bends and corners.
    for i in range(len(out) - 1):
        a = (out[i]["lat"], out[i]["lng"])
        b = (out[i + 1]["lat"], out[i + 1]["lng"])
        if haversine(a, b) > 1:  # skip if next sample is (nearly) the same spot
            out[i]["heading"] = round(bearing(a, b), 1)
    return out


def check_imagery(samples, key):
    """Free metadata calls: find which points have imagery, dedupe repeats."""
    def meta(p):
        u = (f"{API}/streetview/metadata?location={p['lat']},{p['lng']}"
             f"&source=outdoor&key={key}")
        try:
            return http_json(u)
        except Exception:
            return {"status": "FETCH_ERROR"}

    with ThreadPoolExecutor(max_workers=10) as ex:
        metas = list(ex.map(meta, samples))

    prev_pano = None
    for p, m in zip(samples, metas):
        if m.get("status") == "OK":
            if m["pano_id"] == prev_pano:
                p["status"] = "DUPLICATE"  # same camera position as previous point
            else:
                p["status"], prev_pano = "OK", m["pano_id"]
            p["pano_id"], p["date"] = m["pano_id"], m.get("date")
            loc = m.get("location", {})
            p["cam_lat"] = round(loc.get("lat", p["lat"]), 6)
            p["cam_lng"] = round(loc.get("lng", p["lng"]), 6)
        else:
            p["status"] = m.get("status", "UNKNOWN")
    return samples


def download(samples, out_dir, key, size, fov, pitch):
    ok = [p for p in samples if p["status"] == "OK"]
    pad = max(4, len(str(len(ok))))  # zero-pad so filenames sort correctly at any scale

    def grab(item):
        idx, p = item
        u = (f"{API}/streetview?size={size}&pano={urllib.parse.quote(p['pano_id'])}"
             f"&heading={p['heading']}&fov={fov}&pitch={pitch}&source=outdoor&key={key}")
        data = http_bytes(u)
        lat = p.get("cam_lat", p["lat"])
        lng = p.get("cam_lng", p["lng"])
        fname = f"{idx + 1:0{pad}d}_{p['dist_m']}m_{lat},{lng}.jpg"
        with open(os.path.join(out_dir, fname), "wb") as f:
            f.write(data)
        p["file"] = fname
        return fname

    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, fname in enumerate(ex.map(grab, enumerate(ok)), 1):
            print(f"  [{i}/{len(ok)}] {fname}")
    return len(ok)


def main():
    ap = argparse.ArgumentParser(description="Street View photos along a road")
    ap.add_argument("--origin", required=True, help="start address/intersection")
    ap.add_argument("--destination", required=True, help="end address/intersection")
    ap.add_argument("--spacing", type=float, default=50, help="meters between photos (default 50)")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--size", default="640x640", help="image size, max 640x640")
    ap.add_argument("--fov", type=float, default=90, help="field of view 10-120 (default 90)")
    ap.add_argument("--pitch", type=float, default=0, help="camera pitch -90..90 (default 0)")
    ap.add_argument("--key", default=None, help="Google Maps API key")
    ap.add_argument("--max-points", type=int, default=500, help="safety cap (default 500)")
    ap.add_argument("--flip", action="store_true",
                    help="face opposite the direction of travel (looking back down the road)")
    args = ap.parse_args()

    key = args.key or os.environ.get("GOOGLE_MAPS_KEY")
    if not key:
        key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key.txt")
        if os.path.exists(key_file):
            key = open(key_file).read().strip()
    if not key:
        raise SystemExit("No API key: use --key, GOOGLE_MAPS_KEY, or key.txt next to the script")

    spacing = max(5.0, args.spacing)
    print(f"Routing: {args.origin} -> {args.destination}")
    route = build_route(args.origin, args.destination, key)
    print(f"  {route['summary'] or 'route'}: {route['distance_m']} m")

    samples = sample_points(route["path"], spacing)
    if args.flip:
        for p in samples:
            p["heading"] = round((p["heading"] + 180) % 360, 1)
    if len(samples) > args.max_points:
        raise SystemExit(f"{len(samples)} points at {spacing} m spacing exceeds cap "
                         f"({args.max_points}). Increase --spacing or --max-points.")
    print(f"Sampling every {spacing:g} m -> {len(samples)} points; checking imagery (free)...")
    samples = check_imagery(samples, key)
    n_ok = sum(1 for p in samples if p["status"] == "OK")
    n_dup = sum(1 for p in samples if p["status"] == "DUPLICATE")
    print(f"  {n_ok} unique photos available, {n_dup} duplicates skipped, "
          f"{len(samples) - n_ok - n_dup} without imagery")
    print(f"  estimated cost: ~${n_ok * 7 / 1000:.2f} (covered by free tier up to ~28k/mo)")

    os.makedirs(args.out, exist_ok=True)
    print("Downloading...")
    n = download(samples, args.out, key, args.size, args.fov, args.pitch)

    manifest = {
        "route": {k: route[k] for k in ("summary", "distance_m", "start_address", "end_address")},
        "spacing_m": spacing,
        "size": args.size, "fov": args.fov, "pitch": args.pitch, "flip": args.flip,
        "points": samples,
    }
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Done: {n} photos + manifest.json in {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
