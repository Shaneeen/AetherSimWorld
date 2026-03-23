prompt_agent.py
=================

What it does
------------
- Provides a small CLI that connects to a running SimWorld Unreal Engine instance (UnrealCV) and spawns a `Humanoid` agent.
- Accepts simple text prompts and maps them to simulator actions (step, rotate, stop, spawn queries).
- Offers two perception modes:
  - Asset-based "look" that queries UE object names and maps them to human-readable descriptions using the repository's `data/description_map.json` and `data/ue_assets.json`.
  - Vision-based captioning (BLIP via Hugging Face `transformers`) that captures the humanoid camera view and produces textual captions. Also includes a simple `explore` routine that rotates and captions multiple views.
- Optional Ollama integration: if you run a local Ollama server and set environment variables, the script can use an LLM to parse free-form commands into structured actions.

Requirements
------------
- A running Unreal Engine server with the UnrealCV plugin enabled and reachable (default: `localhost:9000`). Follow the SimWorld docs for UE server setup: https://simworld.readthedocs.io/en/latest/getting_started/installation.html
- Python 3.10+ and the SimWorld package installed (you already ran `pip install -e .`).
- Optional packages for vision captioning (required only if you use `caption` / `explore`):

  ```powershell
  pip install pillow numpy transformers torch
  ```

  - On systems with a GPU you may want a CUDA-enabled `torch`; see https://pytorch.org/get-started/locally/ for install instructions.

- Optional for Ollama parsing (if you want LLM parsing): install and run Ollama (see https://ollama.com/docs), pull a model and run the server with `ollama serve`.

Environment variables
---------------------
- `USE_OLLAMA=1` — enable Ollama LLM parsing (must also set `OLLAMA_MODEL`).
- `OLLAMA_MODEL=your-model-name` — model name to send to Ollama.
- `OLLAMA_API_URL` — override default Ollama HTTP URL (default: `http://localhost:11434/api/generate`).
- `VISION_MODEL` — optional Hugging Face caption model (default: `Salesforce/blip-image-captioning-base`).

How to run
----------
1. Start your UE server with UnrealCV (make sure it is reachable).
2. (Optional) Install vision packages if you plan to use `caption`/`explore`.
3. Run the script:

```powershell
python scripts\prompt_agent.py
```

If using Ollama (PowerShell):

```powershell
$env:USE_OLLAMA='1'
$env:OLLAMA_MODEL='your-model-name'
python scripts\prompt_agent.py
```

Example commands supported
--------------------------
- walk 2 steps
  - Moves the humanoid forward by a duration mapped from step count.
- turn left
- turn right 90
  - Rotate humanoid by 90 degrees (or specified angle).
- stop
  - Send humanoid stop command.
- where am i
  - Query the agent position and yaw. Uses the UE manager if available, falls back to direct UnrealCV queries if not.
- view / show view
  - Retrieve and display the camera view.
- look / scan
  - Asset-based environment query: lists nearby UE objects and maps them to descriptions (trees, convenience stores, etc.) using repository mapping files.
- caption / describe
  - Vision-based caption for the current view (requires `transformers`, `torch`, `pillow`, `numpy`).
- explore
  - Rotate the agent and caption multiple views, then summarize the captions.
- go to X Y
  - Crude go-to implementation: computes heading relative to current pose, rotates then walks towards the target (best-effort; use waypoint APIs for robust navigation).
- quit / exit
  - Exit the CLI.

Notes and next improvements
--------------------------
- `go to` is a simple turn+walk heuristic. For reliable navigation, integrate a path planner that uses waypoints (e.g., `communicator.p_set_waypoints`) and obstacle-aware motion.
- Vision captioning uses a heavy model by default; for faster/cheaper captions use a smaller BLIP variant or a lightweight on-device caption model.
- Asset-based `look` returns semantic labels from `data/description_map.json` and `data/ue_assets.json`. This is the most reliable way to get object-level labels because it uses UE metadata rather than image models.
- I can add a simulated/dry-run communicator mode so you can develop without the UE server, or integrate an object-detection model (YOLO/Detectron) on camera frames for bounding-box-based perception.

File location
-------------
See [scripts/prompt_agent.py](scripts/prompt_agent.py) for the full implementation and configuration details.
