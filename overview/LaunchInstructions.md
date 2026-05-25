1. Open:

```powershell
D:\SimWorld\SimWorld.uproject
```

2. Wait for Unreal to load, then press Play.

3. Terminal 1:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\run_bridge_existing.cmd
```

4. Terminal 2:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\run_target_brain.cmd
```

5. Terminal 3:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\run_chaser_brain.cmd
```

6. Optional Terminal 4, for watching team support directly in 2v2 to 5v5:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\run_team_support.cmd
```

`start_chase.cmd` now auto-starts team support when a saved team config exists, so Terminal 4 is optional. Run Terminal 4 manually only when you want the support logs in their own window. When team size changes, close/re-run Terminal 4 if you started it manually. The team support script cleans stale team controller processes before launching the current team size.

In smaller team matches, unused manual drones are parked near `(2800, 2800, 150)` by the bridge so they stay out of the chase area.

Team catches default to `red_1` vs `blue_1` only, so support drones can screen or distract without ending the round. To make any red/blue contact count, set `SIM_TEAM_CATCH_MODE=any` before running Terminal 1.

The team setup prompt can also save `SIM_TEAM_ROUND_MODE=red_elimination`. In that mode caught red drones drop to the ground and stay out until all red drones are caught, then the bridge resets the round.

The existing-actor bridge tries swept Unreal movement when available. In the current UnrealCV runtime, swept movement may be unavailable, so the bridge falls back to direct UnrealCV location updates plus software safety guards.

The direct-movement guard defaults are:

```powershell
$env:SIM_TARGET_BOUND_X="1350"
$env:SIM_TARGET_BOUND_Y="1350"
$env:SIM_ARENA_BOUNDARY_MARGIN_CM="90"
$env:SIMWORLD_DIRECT_ON_SWEEP_BLOCK="0"
```

When Terminal 1 starts, confirm the bridge prints something like:

```text
UE bridge arena guard: enabled=1 bounds=(1350.0,1350.0) margin=90.0 elimination_ground_z=0.0
```

If the visible main wall is not matched by these measurements, adjust `SIM_TARGET_BOUND_X`, `SIM_TARGET_BOUND_Y`, or `SIM_ARENA_BOUNDARY_MARGIN_CM` before running Terminal 1. If a specific cover object or wall still needs tactical avoidance, add it as a manual circular blocker with `SIM_COLLISION_BLOCKERS` or `SIM_TACTICAL_BLOCKERS`.

Optional tactical blockers for smarter cover/routing:

```powershell
$env:SIM_TACTICAL_BLOCKERS="center_pillar,0,0,450,100,700"
$env:SIM_TACTICAL_CLEARANCE_CM="180"
```

The brains and support controllers also reuse `SIM_COLLISION_BLOCKERS` and `SIM_LOS_BLOCKERS` as tactical blockers, so one configured circular blocker can affect visibility, cover, and route-around behavior.

7. Terminal 5:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\start_chase.cmd
```

`start_chase.cmd` sends stop, reset, and start commands directly through the source control helper. It also prints a non-blocking ROS graph diagnostic first. If `/ue_bridge`, `/target_brain`, or `/chaser_brain` are not visible from that shell, the script continues anyway because VPN or DDS discovery settings can hide live nodes. If the watcher later shows `CHASER no chaser commit yet`, restart Terminal 3.

For saved team matches, `start_chase.cmd` also starts `run_team_support.cmd` automatically unless `SIM_TEAM_SUPPORT_AUTOSTART=0` is set. Auto-start output is written to `logs\ros\team_support_autostart.log`.

Stop chase:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\stop_chase.cmd
```

`stop_chase.cmd` publishes `stop_all`, then cleans known live/stale ROS chase processes. If you press Ctrl+C and answer `Y` to `Terminate batch job` inside the bridge, target brain, chaser brain, or team support terminal, that window's process is closed. Restart those terminals before running `start_chase.cmd` again.

`stop_chase.cmd` also cleans known stale source-module and old installed ROS entry-point processes, including `target_brain.exe`, `chaser_brain.exe`, `ue_bridge.exe`, and matching `*-script.py` processes. If movement looks frozen or inconsistent, run `stop_chase.cmd` first and make sure old manually launched brain windows are closed before restarting the bridge/brains.

Change team setup before launch:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\configure_team_match.cmd
```

Return to normal 1v1:

```powershell
cd D:\SimWorld
.\scripts\DroneROS\clear_team_match_config.cmd
```
