# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI-assisted warehouse robot simulation ("Depo Robotu"): a TurtleBot3 Waffle Pi navigates a simulated
12×12 m warehouse in Gazebo, tilts its camera to scan shelves, and identifies boxes by color/size/floor
so a future LLM layer can answer natural-language inventory queries. Code, comments, and log messages
are written in Turkish; keep new code/comments in Turkish to match the existing style.

This package (`depo_robotu`) lives in a colcon workspace at `~/staj_ws`, alongside a sibling package
`turtlebot3_simulations` (a source checkout of ROBOTIS's repo, patched — see "Workspace-level patches"
below). Both packages must build against the same Gazebo (Harmonic, not Classic).

Environment: Ubuntu 22.04 · ROS 2 Humble · Gazebo Sim 8.14.0 (Harmonic) · TurtleBot3 Waffle Pi.

The project plan lives in `yol_haritasi_v3.md` (sprint roadmap) and `NOTLAR.md` (running log of problems
encountered and their fixes, plus environment setup patches). Read `NOTLAR.md` before debugging any
Gazebo/build/TF issue — the fix or the reason a workaround exists is very likely already documented there.

## Common commands

Every new terminal must source the workspace environment first via the `staj` shell alias (defined in
`~/.bashrc`, sets `TURTLEBOT3_MODEL` and `GZ_SIM_RESOURCE_PATH`) before running any `ros2` command.

```bash
staj                        # required once per terminal

# Build (from ~/staj_ws)
colcon build --symlink-install --packages-select depo_robotu
# if turtlebot3_simulations/turtlebot3_gazebo was touched:
colcon build --symlink-install --packages-select turtlebot3_gazebo
# open a NEW terminal after building so the environment picks up changes

# Run the simulation
ros2 launch depo_robotu depo.launch.py

# Run a perception/control node (each is a console_script entry point, see setup.py)
ros2 run depo_robotu kamera_kontrol
ros2 run depo_robotu kat_tespit
ros2 run depo_robotu piksel_kat_tespit
ros2 run depo_robotu renk_probu
ros2 run depo_robotu kutu_tespit

# Drive manually
ros2 run turtlebot3_teleop teleop_keyboard   # w/x forward-back, a/d turn, s/space = stop

# View camera / inspect topics
ros2 run rqt_image_view rqt_image_view /camera/image_raw
ros2 topic list
ros2 topic info /cmd_vel
ros2 topic hz /camera/image_raw

# ament tests (copyright / flake8 / pep257 headers)
colcon test --packages-select depo_robotu
colcon test-result --verbose
```

If Gazebo processes get into a confused state (Entity Tree and scene disagree, changes don't show up),
kill leftover processes before relaunching — `Ctrl+C` does not always take down both `gz sim -s`
(server) and `-g` (client). `tarama_kontrol` is included because `navigasyon_koprusu.py` spawns it as a
subprocess (see its module docstring) — killing `navigasyon_koprusu` with `kill -9`/plain `pkill` leaves
that child running as an orphan, since a subprocess is not attached to the parent's own signal handling:
```bash
pkill -f "gz sim"; pkill -f ruby; pkill -f parameter_bridge; pkill -f robot_state_publisher; pkill -f tarama_kontrol
```

Regenerate warehouse box layout (from `araclar/`):
```bash
python3 kutu_uret.py   # writes kutular.sdf + envanter.json in the current directory
```
`kutular.sdf` fragments must then be pasted into `worlds/depo.sdf`; `envanter.json` is the ground-truth
inventory (box id, shelf address, color, size, position) used to score detections in later sprints.

## Architecture

### Launch (`launch/depo.launch.py`)
Custom launch file replacing ROBOTIS's `empty_world.launch.py`, whose world path is hardcoded and can't
be overridden. It still delegates robot spawning and state publishing to the upstream
`robot_state_publisher.launch.py` / `spawn_turtlebot3.launch.py`. Only the world path
(`worlds/depo.sdf`) is swapped in. `AppendEnvironmentVariable` for the Gazebo model path must run before
`gzserver_cmd` is added (ordering matters — it's a race condition if set after Gazebo starts). A
`ros_gz_bridge parameter_bridge` node bridges `/kamera_acisi` (Float64 → gz.msgs.Double) for camera tilt
control.

### World (`worlds/depo.sdf`)
9 shelves in a 3×3 grid (rows A/B/C × columns 1/2/3), each 3 floors, generated boxes pasted in from
`araclar/kutular.sdf`. Shelf addresses and coordinates: see the table in `NOTLAR.md` ("KARAR 3"). Shelf
collision geometry is one solid block (robot cannot drive under shelves — intentional); visual geometry
is multi-part for looks. Row C shelves face north, rows A/B face south (`RAFLAR` dict in `kutu_uret.py`
encodes this per-shelf orientation).

### Box generation (`araclar/kutu_uret.py`)
Deterministic (seeded, `TOHUM = 42`) generator that fills each shelf floor from both ends inward, leaving
a natural gap in the middle, and writes two paired outputs: `kutular.sdf` (Gazebo model blocks) and
`envanter.json` (ground-truth inventory: id, address, shelf, floor, position, color, size). Shelf/box
geometry constants here (`RAF_UZUNLUK`, `KAT_YUZEYLERI`, `KUTU_TIPLERI`) must stay consistent with the
values baked into `worlds/depo.sdf` and the `KAT_YUKSEKLIKLERI` constant duplicated across the perception
nodes below — there is no single source of truth for these numbers yet, they are kept in sync by hand.

### Perception pipeline (`depo_robotu/`)
A `LaserScan → forward-distance` helper (front ±60°, take the min valid range) is duplicated verbatim
across `kamera_kontrol.py`, `kat_tespit.py`, `piksel_kat_tespit.py`, and `kutu_tespit.py` — an
intentional convention for now, not an abstraction that's been missed. The nodes build on each other in
stages:

1. **`kamera_kontrol.py`** — subscribes to `/hedef_kat` (1/2/3), computes the tilt angle needed to point
   the camera at that floor's known height using LIDAR distance + `atan2`, publishes `/kamera_acisi`.
   This is the "look" half of look-and-move; it does not read back the camera's actual position.
2. **`kat_tespit.py`** — the inverse/verification direction: reads the *actual* camera tilt from TF
   (`base_footprint → camera_link`), casts a ray from the camera's real position/orientation, intersects
   it with the known floor heights, and publishes `/bakilan_kat` (which floor the camera is currently
   looking at). Confirms the TF tree correctly reflects the tilt joint before anything downstream trusts
   it.
3. **`piksel_kat_tespit.py`** — generalizes step 2 from "the center of the view" to "any clicked pixel":
   pinhole-projects a clicked image pixel into a ray (using `/camera/camera_info` intrinsics + TF to
   `camera_rgb_optical_frame`), intersects it with floor heights. Interactive/manual test tool (click on
   the OpenCV window) — a rehearsal for step 4's automatic version.
4. **`kutu_tespit.py`** — the full pipeline: HSV color-masks the image to find boxes, filters contours by
   area and aspect ratio (thin/tall = shelf support post, near-square = box — needed because the blue
   box color and the shelf's blue support posts are nearly indistinguishable in HSV, see the module
   docstring for the exact H values), applies step 3's ray-plane math to the box's center pixel to get
   its floor, estimates size from pixel width + LIDAR distance, and publishes detections as JSON on
   `/tespitler`.
5. **`renk_probu.py`** — standalone calibration tool: click a pixel, print its HSV value. Used to derive
   the HSV thresholds hardcoded in `kutu_tespit.py`'s `RENK_ARALIKLARI`; re-run this whenever lighting or
   box colors in `worlds/depo.sdf` change.

All four TF-consuming nodes assume `base_footprint` and either `camera_link` or
`camera_rgb_optical_frame` exist in the TF tree and that the tilt joint's state is actually published
into it — this was an open risk flagged in `yol_haritasi_v3.md` (Sprint 2C item 1) before `kat_tespit.py`
was written specifically to verify it.

### Workspace-level patches (outside this package)
`turtlebot3_simulations` is built from source (the `jazzy` branch, patched for Humble) rather than apt,
and its `model.sdf` has been hand-edited for camera FOV/tilt and body color. These patches live in a
sibling package, not in this repo, and are lost if the workspace is reinstalled from scratch. Full patch
list, exact `sed` commands, and rationale are in `NOTLAR.md` under "ÖNEMLİ: Workspace yeniden kurulursa"
(patches Y1–Y7) — check there before touching anything under `turtlebot3_simulations/`.
