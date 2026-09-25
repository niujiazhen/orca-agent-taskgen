"""Built-in v2 primitive and gesture catalog."""

from __future__ import annotations

import numpy as np

OPEN = np.asarray(
    [-0.15, 0.0, -0.73304, -0.58496, -0.50477, -0.4, 0.0, 0.0, 0.0,
     0.0, 0.0, 0.17, 0.0, 0.0, 0.52333, 0.0, 0.0], dtype=np.float64
)
PINCH = np.asarray(
    [-0.15, -0.1663850854, -0.0869970018, 0.1769704880, 0.0919940746,
     -1.0229435134, 1.4213437181, 0.1353799058, 0.0, 0.0, 0.0, 0.17,
     0.0, 0.0, 0.52333, 0.0, 0.0], dtype=np.float64
)
HALF_CLOSE = np.asarray(
    [-0.15, -0.08, -0.45, 0.15, 0.2, -0.25, 0.70, 0.75, 0.0,
     0.65, 0.75, 0.17, 0.65, 0.75, 0.52333, 0.65, 0.75], dtype=np.float64
)
FIST = np.asarray(
    [-0.15, -0.215, -0.465, 0.68, 0.795, -0.19, 1.07, 1.36, 0.0,
     1.35, 1.45, 0.17, 1.35, 1.45, 0.52333, 1.4, 1.45], dtype=np.float64
)
THREE_FINGER = np.asarray(
    [-0.15, -0.18, -0.10, 0.25, 0.20, -0.65, 1.25, 1.15, -0.15,
     1.20, 1.10, 0.17, 0.25, 0.25, 0.52333, 0.15, 0.20], dtype=np.float64
)

# Keep the ring and little fingers folded away from the support surface while
# the thumb, index, and middle fingers perform the grasp.
TABLETOP_THREE_FINGER = THREE_FINGER.copy()
TABLETOP_THREE_FINGER[11:] = FIST[11:]

GESTURE_SEQUENCES: dict[str, tuple[np.ndarray, ...]] = {
    "open_half_close_fist_open": (OPEN, HALF_CLOSE, FIST, OPEN),
    "thumb_index_pinch_release": (OPEN, PINCH, OPEN),
    "three_finger_grasp_release": (OPEN, THREE_FINGER, OPEN),
}

GRASP_POSES = {
    # The scripted feasibility controller closes three fingers around the
    # object.  The object is then moved only by MuJoCo contacts; there is no
    # simulator-state attachment or object teleportation.
    "box": TABLETOP_THREE_FINGER,
    "cylinder": TABLETOP_THREE_FINGER,
    "sphere": FIST,
}

GRASP_CENTER_OFFSETS = {
    "box": np.asarray([0.020, -0.005, 0.025], dtype=np.float64),
    "cylinder": np.asarray([0.0, -0.005, 0.030], dtype=np.float64),
    "sphere": np.asarray([0.0, -0.005, 0.030], dtype=np.float64),
}

# The open fingers start above the support surface and descend as they close.
# Shape-specific clearances preserve contact feasibility for each primitive.
PREGRASP_CLEARANCES = {
    "box": 0.060,
    "cylinder": 0.020,
    "sphere": 0.035,
}

GESTURE_PROVENANCE = {
    "repository": "https://github.com/back2-thebasic/orcahand-retarget-experiments",
    "configuration": "configs/last.yaml",
    "note": (
        "The scenarios and retargeting configuration inform these locally calibrated "
        "ORCA v1 targets; the source repository does not provide joint trajectories."
    ),
}
