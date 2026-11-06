"""Apply only the approved submission status label; no restart."""
from pathlib import Path
import hashlib,datetime,json
root=Path('/path/to/colosseum-unified-ui')
target=root/'i18n.js'
incoming=root.parent/'i18n-submitting-label.js'
before=target.read_bytes();after=incoming.read_bytes()
assert hashlib.sha256(before).hexdigest()=='4afaafcb031bfba4270b07f5b9b9aec9f4d44d70eedea40e97a54b38271d8008'
assert hashlib.sha256(after).hexdigest()=='373dccbc8b52227c501bf82816bfd9fc13f53a9e6ccb2ac606d4042d4c0e7075'
stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
backup=root.parent/'backups'/('unified-ui-submitting-label-'+stamp)
backup.mkdir(mode=0o700)
(backup/'i18n.js').write_bytes(before)
assert (backup/'i18n.js').read_bytes()==before
assert target.read_bytes()==before
staged=root/'i18n.js.submitting-label'
staged.write_bytes(after)
staged.replace(target)
assert target.read_bytes()==after
print(json.dumps({'backup':str(backup),'restart':False}))
