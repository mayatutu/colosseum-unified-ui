import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
origin = root.parents[1] / 'Official/colosseum-client-main'
inventory = json.loads((origin / '.planning/colosseum-ui-offline-review/archive-inventory.json').read_text(encoding='utf-8'))
changed = [item['path'] for item in inventory['files']
           if hashlib.sha256((origin / item['path']).read_bytes()).hexdigest() != item['sha256']]
source = json.loads((root / 'upstream/source.json').read_text(encoding='utf-8'))
copied = {name: hashlib.sha256((root / 'upstream' / name).read_bytes()).hexdigest() == expected
          for name, expected in source['sha256'].items()}
franka = root.parent / 'client-reset-timing-20261027/candidate/src/colosseum_client/evaluation.py'
result = {'original_archive_files': len(inventory['files']), 'changed_original_files': changed,
          'upstream_copies': copied,
          'franka_evaluation_sha256': hashlib.sha256(franka.read_bytes()).hexdigest(),
          'yam_evaluation_sha256': hashlib.sha256((root / 'validation/yam-evaluation-source.py').read_bytes()).hexdigest(),
          'remote_writes': False, 'hardware_tested': False}
(root / 'validation/source-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
assert not changed and all(copied.values()), result
assert result['franka_evaluation_sha256'] == 'a0d598073811718f61ee1eb2d167641d3ea01b8157e3b17e118d5d5611a78edc'
assert result['yam_evaluation_sha256'] == '60078e9330d128288d966bd75f2d60311389cf33b0167800783ef3c8ab740a80'
print(json.dumps(result, indent=2))
