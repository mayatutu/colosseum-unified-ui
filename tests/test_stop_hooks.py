import asyncio
import threading
from types import SimpleNamespace
import numpy as np
import pytest
from stop_hooks import install_action_hooks


@pytest.mark.parametrize('name', ['execute_robot_action', 'execute_g05_guarded_action'])
def test_franka_normal_and_g05_late_reply_never_executes(name):
    calls = []
    ev = SimpleNamespace(**{name: lambda *a, **k: calls.append(a)})
    stopped = threading.Event()
    obs = SimpleNamespace(joints=np.arange(7), gripper=np.array([.2]))
    robot = SimpleNamespace(joint_count=7)
    install_action_hooks(ev, stopped, lambda: obs)
    getattr(ev, name)(robot, np.ones(8), 0, True)
    assert len(calls) == 1
    stopped.set()
    held = getattr(ev, name)(robot, np.ones(8), 0, True)
    np.testing.assert_allclose(held, np.r_[obs.joints, obs.gripper])
    assert len(calls) == 1


def test_yam_stop_between_queue_and_executor_preserves_action_order():
    stopped = threading.Event()
    obs = SimpleNamespace(joints=np.arange(12), gripper=np.array([.1, .9]))
    calls = []
    async def action(robot, target, step, robot_call, enabled=True):
        return await robot_call(lambda: calls.append(target))
    async def executor(fn, *args, **kwargs):
        stopped.set()  # user Stop arrives while robot executor is waiting
        return fn(*args, **kwargs)
    ev = SimpleNamespace(execute_robot_action_async=action)
    install_action_hooks(ev, stopped, lambda: obs)
    value = asyncio.run(ev.execute_robot_action_async(SimpleNamespace(joint_count=12), np.ones(14), 3, executor))
    assert calls == []
    np.testing.assert_allclose(value, np.r_[np.arange(6), .1, np.arange(6, 12), .9])


def test_yam_without_stop_calls_original_action():
    async def action(robot, target, step, robot_call, enabled=True):
        return await robot_call(lambda: target)
    async def executor(fn, *args, **kwargs):
        return fn(*args, **kwargs)
    ev = SimpleNamespace(execute_robot_action_async=action)
    install_action_hooks(ev, threading.Event(), lambda: None)
    assert asyncio.run(ev.execute_robot_action_async(None, 'action', 1, executor)) == 'action'


def test_actual_yam_interpolation_stops_before_next_motor_command():
    import sys
    from test_worker_process import CLIENT
    sys.path.insert(0, str(CLIENT / 'src'))
    from colosseum_client.robots.yam import YAMRobot
    stopped = threading.Event()
    obs = SimpleNamespace(joints=np.arange(12), gripper=np.array([.1, .9]))
    sent = []
    robot = SimpleNamespace(joint_count=12, joint_step_mode='interpolate',
                            _interpolation=lambda action: [np.zeros(14), np.ones(14), np.full(14, 2)],
                            _send_action=lambda action: sent.append(action))
    robot.execute_async = lambda action, call: YAMRobot.execute_async(robot, action, call)
    async def action(robot, target, step, robot_call, enabled=True):
        return await robot.execute_async(target, robot_call)
    count = [0]
    async def executor(fn, *args, **kwargs):
        count[0] += 1
        if count[0] == 3:
            stopped.set()
        return fn(*args, **kwargs)
    ev = SimpleNamespace(execute_robot_action_async=action)
    install_action_hooks(ev, stopped, lambda: obs)
    asyncio.run(ev.execute_robot_action_async(robot, np.full(14, 2), 1, executor))
    assert len(sent) == 1
