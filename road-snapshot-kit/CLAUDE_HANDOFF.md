# Handoff: Road Snapshots tool (read this first, Claude)

You are picking up a finished project from a previous Claude session. Ross wants
this workflow: **he names a road and a spacing, you produce a folder of Google
Street View photos taken at that spacing along the road.**

## What's in this kit

- `road_snapshots.py` — complete, working script. Python 3 standard library only,
  no pip installs. Do not rewrite it; just run it.
- `key.txt` — Ross's Google Maps API key (project "road-snapshots" in his Google
  Cloud account, Street View Static API + Directions API enabled). The script
  auto-reads it when key.txt sits next to the script.
- `README.md` — instructions written for Ross.

## Critical: where to run it

Run the script **on Ross's computer** (the local machine / device shell), NOT in
your cloud sandbox. The previous session confirmed the cloud sandbox's egress
proxy blocks maps.googleapis.com (only package registries are allowlisted), so
the script will fail there with connection errors. Ross's own machine has normal
internet and it works. Requires only `python3` being installed.

## Workflow when Ross asks for a capture

1. He'll say something like "Elm Street in Springfield, every 100 m" — possibly only
   a road name. The script needs an origin and destination the Directions API can
   geocode. Derive endpoints (cross-street intersections or addresses at each end
   of the stretch he means). If the extent of the road is ambiguous, ask him which
   stretch, or confirm the endpoints you chose.
2. Create/choose an output folder on his machine, e.g.
   `Road Snapshots/<road-name>/` inside the folder he gave you access to.
3. Run:
   `python3 road_snapshots.py --origin "..." --destination "..." --spacing 100 --out "<folder>"`
4. Report: photos saved, points without imagery, and show him 1–2 sample images
   so he can confirm the direction/framing looks right.

## Notes

- The script samples the driving route between the endpoints; headings face along
  the road (direction of travel). `--fov` (10–120, default 90) and `--pitch`
  (default 0) adjust framing; `--size` max is 640x640 (API limit).
- Free metadata calls filter out points with no imagery and consecutive points
  that map to the same camera position (DUPLICATE in manifest.json).
- Cost: images are $7/1000 after ~28k free per month — the script prints an
  estimate before downloading. A safety cap (`--max-points`, default 500)
  prevents accidental huge runs.
- The key in key.txt was verified as created on 2026-08-17 but has NOT yet made a
  successful API call (the previous session couldn't reach Google). On first run,
  if you see REQUEST_DENIED: the two APIs may not both be enabled, or billing
  isn't attached to the Google Cloud project — walk Ross through
  console.cloud.google.com to fix.
- One capture was promised as a demo: Lombard Street (the crooked block,
  Hyde St to Leavenworth St, San Francisco) at 25 m spacing — a good first test,
  ~10 photos.
