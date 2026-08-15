from .common import channel_projected_target


def apply(task, side, position, velocity, frame, fade):
    return channel_projected_target(task, side, position, velocity, frame, "support", fade)
