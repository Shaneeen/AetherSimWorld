import numpy as np


def center_depth_cm(comm, hum, crop_ratio: float = 0.2):
    try:
        depth = comm.get_camera_observation(hum.camera_id, 'depth', mode='direct')
    except Exception:
        return None
    if depth is None:
        return None
    arr = np.asarray(depth)
    if arr.ndim != 2:
        return None
    h, w = arr.shape
    y0 = int(h * (0.5 - crop_ratio / 2))
    y1 = int(h * (0.5 + crop_ratio / 2))
    x0 = int(w * (0.5 - crop_ratio / 2))
    x1 = int(w * (0.5 + crop_ratio / 2))
    crop = arr[y0:y1, x0:x1]
    finite = crop[np.isfinite(crop)]
    if finite.size == 0:
        return None
    return float(np.median(finite))


def depth_stats_cm(comm, hum, crop_ratio: float = 0.2):
    try:
        depth = comm.get_camera_observation(hum.camera_id, 'depth', mode='direct')
    except Exception:
        return None
    if depth is None:
        return None
    arr = np.asarray(depth)
    if arr.ndim != 2:
        return None
    h, w = arr.shape
    y0 = int(h * (0.5 - crop_ratio / 2))
    y1 = int(h * (0.5 + crop_ratio / 2))
    x0 = int(w * (0.5 - crop_ratio / 2))
    x1 = int(w * (0.5 + crop_ratio / 2))
    crop = arr[y0:y1, x0:x1]
    finite = crop[np.isfinite(crop)]
    if finite.size == 0:
        return None
    return {
        'min_depth_cm': float(np.min(finite)),
        'median_depth_cm': float(np.median(finite)),
        'mean_depth_cm': float(np.mean(finite)),
    }


def visible_mask_strength(comm, hum):
    try:
        mask = comm.get_camera_observation(hum.camera_id, 'object_mask', mode='direct')
    except Exception:
        return None
    arr = np.asarray(mask)
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    h, w, _ = arr.shape
    crop = arr[int(h * 0.35):int(h * 0.7), int(w * 0.35):int(w * 0.65), :3]
    if crop.size == 0:
        return None
    flat = crop.reshape(-1, 3)
    colors, counts = np.unique(flat, axis=0, return_counts=True)
    valid = [(tuple(int(v) for v in color), int(count)) for color, count in zip(colors, counts) if any(int(v) > 5 for v in color)]
    if not valid:
        return None
    return max(valid, key=lambda item: item[1])[1]
