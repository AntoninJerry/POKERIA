from dataclasses import dataclass

@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

@dataclass
class RelRect:
    rx: float
    ry: float
    rw: float
    rh: float

def rel_to_abs(parent: Rect, r: RelRect) -> Rect:
    return Rect(
        x=parent.x + int(r.rx * parent.w),
        y=parent.y + int(r.ry * parent.h),
        w=max(1, int(r.rw * parent.w)),
        h=max(1, int(r.rh * parent.h)),
    )

def abs_to_rel(parent: Rect, r: Rect) -> RelRect:
    pw = max(1, parent.w)
    ph = max(1, parent.h)
    return RelRect(
        rx=(r.x - parent.x) / pw,
        ry=(r.y - parent.y) / ph,
        rw=r.w / pw,
        rh=r.h / ph,
    )

def clamp_to_bounds(r: Rect, bounds: Rect) -> Rect:
    x = max(bounds.x, min(r.x, bounds.x + bounds.w - 1))
    y = max(bounds.y, min(r.y, bounds.y + bounds.h - 1))
    w = max(1, min(r.w, bounds.x + bounds.w - x))
    h = max(1, min(r.h, bounds.y + bounds.h - y))
    return Rect(x, y, w, h)
