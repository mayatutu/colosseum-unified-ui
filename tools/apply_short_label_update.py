"""Apply only the approved Chinese translation button label; no restart."""
from pathlib import Path
import hashlib,datetime,json
root=Path('/path/to/colosseum-unified-ui')
target=root/'i18n.js'
incoming=root.parent/'i18n-short-label.js'
before=target.read_bytes();after=incoming.read_bytes()
assert hashlib.sha256(before).hexdigest()=='d9b77632583243a9bee9e57fc32057029caa3e8ca1037ee592213c96dff7c72c'
assert hashlib.sha256(after).hexdigest()=='4afaafcb031bfba4270b07f5b9b9aec9f4d44d70eedea40e97a54b38271d8008'
stamp=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
backup=root.parent/'backups'/('unified-ui-short-label-'+stamp)
backup.mkdir(mode=0o700)
(backup/'i18n.js').write_bytes(before)
assert (backup/'i18n.js').read_bytes()==before
assert target.read_bytes()==before
staged=root/'i18n.js.short-label'
staged.write_bytes(after)
staged.replace(target)
assert target.read_bytes()==after
print(json.dumps({'backup':str(backup),'restart':False}))
