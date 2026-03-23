"""Camera-follow and simple obstacle checks for drones."""
import math

import numpy as np


FOLLOW_CAMERA_ID = 0
FOLLOW_CAMERA_BACK_OFFSET_CM = 260.0
FOLLOW_CAMERA_UP_OFFSET_CM = 140.0
FOLLOW_CAMERA_PITCH_DEG = -18.0
FOLLOW_CAMERA_FOV_DEG = 90.0
OBSTACLE_DEPTH_THRESHOLD_CM = 260.0
TREE_MASK_MIN_PIXELS = 120


def point_camera_at_drone(comm, drone, heading_deg: float = 0.0, camera_id: int = FOLLOW_CAMERA_ID):
    """Move a free camera behind and above the drone for a usable chase view."""
    heading_rad = math.radians(heading_deg)
    camera_x = drone.position.x - math.cos(heading_rad) * FOLLOW_CAMERA_BACK_OFFSET_CM
    camera_y = drone.position.y - math.sin(heading_rad) * FOLLOW_CAMERA_BACK_OFFSET_CM
    camera_z = drone.z + FOLLOW_CAMERA_UP_OFFSET_CM
    comm.unrealcv.set_camera_location(camera_id, (camera_x, camera_y, camera_z))
    comm.unrealcv.set_camera_rotation(camera_id, (FOLLOW_CAMERA_PITCH_DEG, heading_deg, 0.0))
    try:
        comm.unrealcv.set_camera_fov(camera_id, FOLLOW_CAMERA_FOV_DEG)
    except Exception:
        pass


def get_forward_depth_stats(comm, drone, heading_deg: float = 0.0, camera_id: int = FOLLOW_CAMERA_ID):
    """Return center-window depth statistics from the chase camera."""
    point_camera_at_drone(comm, drone, heading_deg=heading_deg, camera_id=camera_id)
    depth = comm.get_camera_observation(camera_id, 'depth', mode='direct')
    if depth is None:
        return None

    depth = np.asarray(depth)
    if depth.ndim != 2:
        return None

    h, w = depth.shape
    y0 = int(h * 0.35)
    y1 = int(h * 0.70)
    x0 = int(w * 0.35)
    x1 = int(w * 0.65)
    center = depth[y0:y1, x0:x1]
    if center.size == 0:
        return None

    finite = center[np.isfinite(center)]
    if finite.size == 0:
        return None

    return {
        'min_depth_cm': float(np.min(finite)),
        'mean_depth_cm': float(np.mean(finite)),
    }


def obstacle_ahead(comm, drone, heading_deg: float = 0.0, threshold_cm: float = OBSTACLE_DEPTH_THRESHOLD_CM):
    stats = get_forward_depth_stats(comm, drone, heading_deg=heading_deg)
    if not stats:
        return False, None
    return stats['min_depth_cm'] <= threshold_cm, stats


def get_forward_tree_mask_stats(comm, drone, heading_deg: float = 0.0, camera_id: int = FOLLOW_CAMERA_ID):
    """Return whether tree-like pixels occupy the center of the object mask."""
    point_camera_at_drone(comm, drone, heading_deg=heading_deg, camera_id=camera_id)
    mask = comm.get_camera_observation(camera_id, 'object_mask', mode='direct')
    if mask is None:
        return None

    mask = np.asarray(mask)
    if mask.ndim != 3 or mask.shape[2] < 3:
        return None

    h, w, _ = mask.shape
    y0 = int(h * 0.35)
    y1 = int(h * 0.70)
    x0 = int(w * 0.35)
    x1 = int(w * 0.65)
    center = mask[y0:y1, x0:x1, :3]
    if center.size == 0:
        return None

    # Trees use distinct flat colors in object masks. We do not know the exact
    # palette ahead of time, so treat any dominant non-background color in the
    # center crop as a candidate obstruction.
    flat = center.reshape(-1, 3)
    colors, counts = np.unique(flat, axis=0, return_counts=True)
    if len(colors) == 0:
        return None

    # Ignore near-black background-like colors.
    valid = []
    for color, count in zip(colors, counts):
        if int(color[0]) < 5 and int(color[1]) < 5 and int(color[2]) < 5:
            continue
        valid.append((color, int(count)))

    if not valid:
        return {
            'dominant_color': None,
            'dominant_pixels': 0,
            'blocked': False,
        }

    dominant_color, dominant_pixels = max(valid, key=lambda item: item[1])
    return {
        'dominant_color': tuple(int(v) for v in dominant_color),
        'dominant_pixels': dominant_pixels,
        'blocked': dominant_pixels >= TREE_MASK_MIN_PIXELS,
    }
