"""Run the actual UI label function against the synthetic camera map."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


UI = Path(__file__).resolve().parents[1]


def test_franka_labels_use_configuration_without_inventing_mount_positions():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the browser label check')
    page = (UI / 'eval_gui.html').read_text(encoding='utf-8')
    function = re.search(r'function cameraLabel\(.*?\n}', page, re.S).group()
    cameras = {'head_image': 'test-head', 'left_image': 'test-left', 'right_image': 'test-right'}
    script = 'let CFG=' + json.dumps({'robot': 'franka', 'camera_serials': cameras}) + ';\n' + function + '''
const assert = require('node:assert/strict');
assert.deepEqual(Object.keys(CFG.camera_serials).map(c => cameraLabel(c)), [
  'head_image · test-head', 'left_image · test-left', 'right_image · test-right']);
// Old recordings/references have no serial metadata: do not attach today's serial.
assert.equal(cameraLabel('head_image', false), 'head_image');
assert.equal(cameraLabel('unknown_sensor'), 'unknown_sensor');
CFG = {robot: 'franka'};
assert.equal(cameraLabel('head_image'), 'head_image');
CFG = {robot: 'yam'};
assert.equal(cameraLabel('head_image'), 'Top');
assert.equal(cameraLabel('left_image'), 'Left wrist');
'''
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True, encoding='utf-8')
