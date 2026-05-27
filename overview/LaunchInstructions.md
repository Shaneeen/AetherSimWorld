# Launch Instructions

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

7. Terminal 5: start chase.

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\start.cmd
```

For 5v5, `start.cmd` auto-starts red/blue team coordinators and support controllers in the background. You can also start support manually:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\team_support.cmd
```

Stop chase:

```powershell
cd C:\CodeSimWorld\AetherSimWorld
.\launch\stop.cmd
```

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
