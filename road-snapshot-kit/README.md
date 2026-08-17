# Road Snapshots

Street View photos at fixed increments along any road, saved into a folder.

## The easy way (with Claude)

1. Put this kit folder somewhere inside a folder the Claude desktop app has
   access to.
2. In a Claude conversation started on this computer, say:
   "Read CLAUDE_HANDOFF.md in my road-snapshot kit, then capture
   <road / start / end> every <N> meters into a folder."
3. Photos land in the folder you asked for, numbered in order down the road
   (001_0m.jpg, 002_50m.jpg, ...) plus a manifest.json with coordinates,
   headings, and the date each photo was taken by Google.

## The manual way (terminal)

    python3 road_snapshots.py \
      --origin "Lombard St & Hyde St, San Francisco" \
      --destination "Lombard St & Leavenworth St, San Francisco" \
      --spacing 25 \
      --out "./lombard"

Useful options: --fov 10..120 (zoom, default 90), --pitch (tilt, default 0),
--size (max 640x640). The API key is read from key.txt automatically.

## Costs

Street View images: $7 per 1,000 after ~28,000 free per month ($200 monthly
credit). The script checks availability with free calls first and prints a cost
estimate before downloading anything. Keep key.txt private.
