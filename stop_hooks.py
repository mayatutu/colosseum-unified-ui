"""Optional GUI hooks; original Client files and command-line defaults are untouched."""
import functools
import numpy as np


def measured_hold(robot, observation):
    # Return only: never send a new command after Stop. Existing trial cleanup homes the robot.
    if observation is None:
        return None
    if getattr(robot, 'joint_count', None) == 12:
        return np.r_[observation.joints[:6], observation.gripper[:1],
                     observation.joints[6:], observation.gripper[1:]].astype(np.float32)
    return np.r_[observation.joints, observation.gripper].astype(np.float32)


def install_action_hooks(ev, stopped, latest):
    originals = {}
    for name in ('execute_robot_action', 'execute_g05_guarded_action'):
        if not hasattr(ev, name):
            continue
        original = getattr(ev, name)
        originals[name] = original

        def make_sync(fn):
            @functools.wraps(fn)
            def guarded(robot, *args, **kwargs):
                if stopped.is_set():
                    return measured_hold(robot, latest())
                return fn(robot, *args, **kwargs)
            return guarded
        setattr(ev, name, make_sync(original))
    if hasattr(ev, 'execute_robot_action_async'):
        original = ev.execute_robot_action_async
        originals['execute_robot_action_async'] = original

        class ActionStopped(Exception):
            pass

        async def guarded_async(robot, action, step, robot_call, enabled=True):
            # Recheck on the robot executor thread too: a queued call can outlive an HTTP Stop.
            if stopped.is_set():
                return measured_hold(robot, latest())

            async def guarded_call(fn, *args, **kwargs):
                def invoke():
                    if stopped.is_set():
                        raise ActionStopped
                    return fn(*args, **kwargs)
                return await robot_call(invoke)
            try:
                return await original(robot, action, step, guarded_call, enabled)
            except ActionStopped:
                return measured_hold(robot, latest())
        ev.execute_robot_action_async = guarded_async
    return originals
