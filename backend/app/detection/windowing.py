"""A small sliding-window helper shared by every rule that needs "N events
of interest within W seconds," rather than each rule re-deriving it.
"""

from datetime import datetime


def densest_window(sorted_timestamps: list[datetime], window_seconds: int) -> tuple[int, int, int]:
    """Given timestamps already sorted ascending, find the contiguous
    sub-range spanning the most events within any `window_seconds` window.
    Returns (count, start_index, end_index), both indices inclusive.
    Empty input returns (0, 0, -1).
    """
    if not sorted_timestamps:
        return 0, 0, -1

    best_count = 1
    best_start = 0
    best_end = 0
    left = 0
    for right in range(len(sorted_timestamps)):
        while (sorted_timestamps[right] - sorted_timestamps[left]).total_seconds() > window_seconds:
            left += 1
        count = right - left + 1
        if count > best_count:
            best_count = count
            best_start = left
            best_end = right
    return best_count, best_start, best_end
