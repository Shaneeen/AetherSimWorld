# Launch Instructions

## Easier staged launch

Open the Unreal project and press Play first if you need the bridge or vision to talk to Unreal.

For the normal 5v5 demo, you can let the launcher open the required terminals one by one:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\run_demo.cmd -Set5v5
```

If you want to personally check that each window has finished loading before the next one opens:

```powershell
.\launch\run_demo.cmd -Set5v5 -Manual
```

To keep the runtime more orderly, use Windows Terminal tabs instead of separate cmd windows:

```powershell
.\launch\run_demo.cmd -Set5v5 -Tabs
.\launch\run_demo.cmd -Set5v5 -Tabs -Manual
```

Useful options:

```powershell
.\launch\run_demo.cmd -Set5v5 -StopFirst
.\launch\run_demo.cmd -Set5v5 -Vision
.\launch\run_demo.cmd -Set5v5 -ImageVision
.\launch\run_demo.cmd -Set5v5 -NoStart
.\launch\run_demo.cmd -Set5v5 -NoWatch
.\launch\run_demo.cmd -Set5v5 -DryRun
```

`-Vision` starts one visual observer, defaulting to `blue_1`. You can choose another observer:

```powershell
.\launch\run_demo.cmd -Set5v5 -Vision -Observer red_1
```

If checking whether vision ran after a match, look for `vision_*.log` in `logs\ros` when vision was autostarted by team support, or search the latest `python_*.log` files for `visual_observer`/`Vision observer ready` when vision was opened manually.

Stop all runtime processes:

```powershell
.\launch\stop.cmd
```

Start another round without closing bridge, brains, support, or panel:

```powershell
.\launch\new_round.cmd
```

Review the latest run with the VLM supervisor:

```powershell
.\launch\review_latest_run.cmd
```

Reports are saved under `logs\run_reports\`, keeping only the newest two.

## Manual launch

1. Open the Unreal project and press Play.

```powershell
C:\CodeSimWorld\AetherSimWorld\SimWorld.uproject
```

2. Set team mode once.

For 5v5:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\set_teams_5v5.cmd
```

For normal 1v1:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\clear_teams.cmd
```

3. Terminal 1: bridge.

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\bridge.cmd
```

4. Terminal 2: target brain.

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\target.cmd
```

5. Terminal 3: chaser brain.

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\chaser.cmd
```

6. Terminal 4: panel.

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\panel.cmd
```

The panel shows chasers on top and targets on bottom. Each row has five slots and pulses when a drone fires a new action.

7. Optional Terminal 5: vision observer.

Use this when testing VLM-assisted team decisions:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\vision.cmd
```

You can choose the observer drone:

```powershell
.\launch\vision.cmd blue_1
.\launch\vision.cmd red_1
.\launch\vision.cmd blue_1 --image
.\launch\vision_image.cmd blue_1
```

Defaults:

```text
SIM_VISION_OBSERVER=blue_1
SIM_VISION_IMAGE_VLM_ENABLED=0
SIM_VISION_CAMERA_ID=0
SIM_VISION_CAMERA_WIDTH=320
SIM_VISION_CAMERA_HEIGHT=240
SIM_VLM_MODEL=qwen3-vl:latest
SIM_VLM_API_URL=http://10.8.0.132:11434/api/generate
SIM_VLM_TIMEOUT_SEC=90
SIM_VISION_REQUEST_TIMEOUT_SEC=180
SIM_VISION_VLM_INTERVAL_SEC=20
SIM_VISION_MIN_POSES_FOR_VLM=8
SIM_VLM_NUM_CTX=512
SIM_VLM_NUM_PREDICT=256
```

The node publishes `/sim/vision_scene`. Team coordinators use that scene summary only as a tactical hint; movement still goes through the normal team controller. To auto-start primary red and blue vision observers with team support, set `SIM_VISION_AUTOSTART=1` before running `launch\start.cmd`.

Default live vision uses a fast VLM context scene so the run proves `source=vlm:qwen3-vl:latest:context`. Turn on full image VLM only after the image smoke test passes:

```powershell
$env:SIM_VISION_IMAGE_VLM_ENABLED=1
.\launch\vision.cmd blue_1
```

Or use the explicit image launch form:

```powershell
.\launch\vision.cmd blue_1 --image
.\launch\vision_image.cmd blue_1
.\launch\run_demo.cmd -Set5v5 -ImageVision
```

In the next run report, image VLM only counts as true when the vision log shows a non-context source such as `source=vlm:qwen3-vl:latest` and nonzero `frame_bytes`. If it says `image_vlm=0` or `frame_bytes=n/a`, the run used context VLM, not camera-image VLM.

The observer now logs each request, UnrealCV camera readiness/capture bytes, and image-to-VLM request timing. If the large VLM is too slow, you should still see `Vision observer timeout:` followed by a fallback `Vision scene:` instead of getting no scene at all.

Start with `blue_1` and optionally `red_1`. Do not start all ten drone observers yet; Qwen3-VL image calls currently take around 20 seconds each, so per-drone VLM vision needs request staggering or a cheaper perception layer before it is practical.

`launch\review_latest_run.cmd` uses `gpt-oss:latest` by default for the post-run reviewer so `qwen3-vl:latest` stays reserved for vision. Override `SIM_RUN_REPORT_MODEL` only if you intentionally want another reviewer model.
By default, the reviewer waits until Ollama finishes (`SIM_RUN_REPORT_TIMEOUT_SEC=0`) instead of timing out and falling back. Set `SIM_RUN_REPORT_TIMEOUT_SEC` to a positive number if you want a hard cap.

`launch\vision.cmd` and `launch\vision_check.cmd` now run a small Ollama prep step first. By default it tries to unload stale `magicoder:latest` and warm `qwen3-vl:latest`; it does not unload `gpt-oss:latest`. Set `SIM_VISION_PREP_OLLAMA=0` to skip this, or change `SIM_VISION_UNLOAD_MODELS` if another stale model needs to be removed.

Before running the full observer, check the VLM/server path:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\vision_check.cmd
```

To include UnrealCV camera capture in the check:

```powershell
$env:SIM_VISION_CHECK_UNREALCV=1
.\launch\vision_check.cmd
```

To prove actual image-to-VLM output before a match:

```powershell
$env:SIM_VISION_CHECK_IMAGE_VLM=1
.\launch\vision_check.cmd
```

Expected success looks like:

```text
OK: UnrealCV cameras=...
OK: image VLM returned in ...s: {...}
```

8. Terminal 5 or 6: start chase.

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\start.cmd
```

For 5v5, `start.cmd` auto-starts red/blue team coordinators and support controllers in the background. In this mode all five chasers and all five targets move through team support. When a target is hit, it drops to `z=0` and stays down. When all five targets are down, the game stops.

The default 5v5 setup is tuned for demos: tag distance is `220` cm, and chasers are configured about `1.75x` faster than the target burst speed.

You can also start support manually:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\team_support.cmd
```

Stop chase:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\stop.cmd
```

Start a new round after all targets are tagged:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\new_round.cmd
```

Use `new_round.cmd` when the bridge, panel, and support windows are still open. Use `stop.cmd` only when you want to clean up and restart the bridge/brains from scratch.

5v5 requires these existing actor names in the Unreal scene:

```text
DroneA
DroneA1
DroneA2
DroneA3
DroneA4

DroneB
DroneB1
DroneB2
DroneB3
DroneB4
```

The launch folder owns the runtime commands. The older `scripts\DroneROS` folder is now for lower-level/source helper scripts only.
