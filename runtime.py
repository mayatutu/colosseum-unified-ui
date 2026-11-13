"""Station adaptation of the original UI runtime; loaded only by Client Python."""
import base64
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

from bridge import Bridge
from candidate_host import CandidateHost
from nuc_maintenance import NucDockerHost
from stop_hooks import install_action_hooks
from store import Store, PendingEvaluation
from submission import install_api_hook, reconcile, mark_manifest
from evaluation_lock import evaluation_lock
from ui_diagnostics import model_name, tail, LogMirror
from task_annotations import difficulty, save_difficulty
import scene_reference
import error_recovery
import scene_settings
import feishu_reporting


class RoundStopped(BaseException):
    """Exit the A/B loop only after the current trial's cleanup has completed."""


class Runtime:
    def __init__(self, station):
        self.station = station
        sys.path.insert(0, str(station.file('client_root') / 'src'))
        os.chdir(station.file('client_root'))
        import upstream_core as c
        self.c = c
        self.lock = threading.RLock()
        self.maintenance_lock = threading.Lock()
        self.store = Store(station.file('database'))
        self.policy_log = LogMirror(station.file('database').with_name('policy.log'))
        for person in station.evaluator_options():
            self.store.add_person(person)
        c.CONFIG = station.load_client_config()
        if c.CONFIG.robot_type != station.robot:
            raise ValueError('Station and Client robot types disagree')
        c.CLIENT = station.file('client_root')
        c.ARGS = SimpleNamespace(config=station.file('robot_config'), llm_keys=station.file('database').with_name('llm-settings.json'))
        c.CLAUDE_ENV = {}
        c.rv.CONFIG = station.file('robot_config')
        c.rv.ROOT = (c.CLIENT / c.CONFIG.evaluation_dir).resolve()
        c.rv.CACHE = c.rv.ROOT.parent / 'eval_review_cache'
        self.root = c.rv.ROOT
        self.legacy = None
        nuc_url = station.data.get('nuc_maintenance_url')
        self.nuc = NucDockerHost(nuc_url) if station.robot == 'franka' and nuc_url else None
        maintenance = station.data.get('maintenance', {})
        self.candidate = CandidateHost(maintenance) if maintenance.get('mode') == 'candidate' else None
        if self.candidate and (maintenance.get('python') or maintenance.get('root')):
            raise ValueError('Candidate and legacy maintenance cannot be combined')
        if maintenance.get('python') and maintenance.get('root'):
            self.legacy = Bridge([maintenance['python'], '-u', str(Path(__file__).with_name('legacy_host.py')),
                                  '--root', maintenance['root'], '--robot', station.robot,
                                  '--url', maintenance.get('url', 'http://127.0.0.1:8080'),
                                  '--policy-url', c.CONFIG.policy_server_url],
                                 log_path=station.file('database').with_name('maintenance.log'))
        self.current_person = None
        self.current_feishu = None
        self.last_replied_prompt = None
        self.closed = threading.Event()
        self.round_stop = threading.Event()
        self.round_stop_pending = False
        self.round_stop_clean = False
        self.round_stop_thread = None
        self.last_frame = -1
        self.frame_data = None
        self._adapt()
        self._install_hooks()
        # Client log capture drives the original phase transitions; protocol stdout is kept separate.
        sys.stdout = sys.stderr = c.Tee(sys.stderr)

    def _adapt(self):
        c = self.c
        self.original_preview = c.rv.preview
        self.original_detail = c.eval_detail
        self.original_summary = c.eval_summary
        self.original_run_check = c.run_check
        self.original_check_cameras = c.check_cameras
        self.original_check_can = c.check_can
        self.original_check_arms = c.check_arms
        c.record_thread = self.record_thread
        c.rv.router = self.router
        c.rv.preview = self.video_path
        c.eval_summary = self.summary
        c.eval_detail = self.detail
        c.save_keys = self.save_keys
        c.check_keys = self.check_keys
        c.verify_key = self.verify_key
        c.check_can = self.check_can
        c.check_arms = self.check_arms
        c.check_cameras = self.check_cameras
        c.PREVIEW.loop = self.preview_loop
        c.SERVER = SimpleNamespace(start=lambda: self.maintain('start_policy') if self.candidate else self.policy('start_policy'),
                                   stop=lambda: self.maintain('stop_policy') if self.candidate else self.policy('stop_policy'),
                                   status=lambda: self.policy('status'),
                                   pids=lambda: set(self.legacy.call('pids')) if self.legacy else set(), busy=False)
        if self.station.robot == 'franka':
            c.check_gpu = lambda: self.policy('status', check='gpu')
            c.free_gpu = lambda: self.maintain('restart_policy')
        # Historical records remain visible; do not silently mark them superseded locally.
        c.record_evals.mark_superseded = lambda *a, **k: None
        install_api_hook(c.ev, self.store, self.root, self.on_assignment)

    def on_assignment(self, assignment):
        self.store.register(assignment['id'], self.station.robot, self.current_person)
        folder = self.root / assignment['id']
        folder.mkdir(parents=True, exist_ok=True)
        manifest = folder / 'manifest.json'
        if not manifest.exists():
            self.c.ev.save(manifest, {'assignment': assignment, 'outcomes': {}, 'uploaded': []})
        (folder / 'ui-origin.json').write_text(json.dumps({'version': 1, 'person': self.current_person,
            'robot': self.station.robot, 'scene_reference_required': self.station.robot == 'franka',
            **({'feishu': self.current_feishu} if self.current_feishu else {})}, ensure_ascii=False), encoding='utf-8')
        self.c.S.set_run(eval_id=assignment['id'])

    def _install_hooks(self):
        c, ev = self.c, self.c.ev
        read = ev.read_observation

        def observe(robot, step, phase):
            obs = read(robot, step, phase)
            c.S.last_obs = obs
            if c.TOP in obs.images:
                c.S.push_frame(obs.images[c.TOP])
            c.S.set_run(step=step)
            return obs
        ev.read_observation = observe
        install_action_hooks(ev, c.PROMPTS.finish_now, lambda: c.S.last_obs)
        trial = ev.run_trial

        async def run_trial(config, assignment, run, path, *args, **kwargs):
            with self.lock:
                if self.round_stop.is_set():
                    raise RoundStopped('Round stopped by the operator')
                c.PROMPTS.finish_now.clear()
                c.PROMPTS.stop_reason = None
            c.S.set_run(side=run['side'], step=0, max_steps=assignment['task'].get('max_steps', config.max_trial_steps),
                        eval_id=assignment['id'], instruction=assignment['task'].get('instruction', ''))
            try:
                result = await trial(config, assignment, run, path, *args, **kwargs)
                if self.round_stop.is_set():
                    raise RoundStopped('Round stopped by the operator')
                return result
            finally:
                if c.PROMPTS.stop_reason:
                    path.mkdir(parents=True, exist_ok=True)
                    (path / 'operator-stop.json').write_text(json.dumps({'reason': c.PROMPTS.stop_reason, 'step': c.S.run['step']}))
                if not self.round_stop.is_set():
                    c.S.set_run(phase='between', message='Policy ' + run['side'] + ' finished.')
        ev.run_trial = run_trial
        ev.sys, ev.select = c.PROMPTS_SYS, c.PROMPTS
        if self.station.robot == 'yam':
            from colosseum_client.robots import yam
            yam.YAMRobot._zero_recovery_choice = staticmethod(c.PROMPTS.recovery_choice)

    def startup(self):
        for row in self.store.pending(self.station.robot):
            try:
                document = self.c.rv.load(row['id'])
                if document.get('recording_error'):
                    self.c.S.set_run(phase='error', eval_id=row['id'], side=None, step=0,
                        instruction=document['assignment']['task']['instruction'], message=document['recording_error'])
            except (OSError, ValueError, KeyError):
                pass
        if self.legacy:
            try:
                self.policy('startup')
            except Exception as e:
                self.c.S.set_check('server', 'fail', str(e))
        else:
            self.policy('status')
        threading.Thread(target=self._poll, daemon=True).start()
        # Retry uncertain confirmations using GET only, never replay submissions at startup.
        threading.Thread(target=self.reconcile_pending, daemon=True).start()
        if getattr(self.station, 'data', {}).get('feishu_reporting_enabled') is True:
            threading.Thread(target=self.report_feishu_loop, daemon=True).start()

    def report_feishu_loop(self):
        while not self.closed.is_set():
            try:
                for row in self.store.confirmed():
                    folder = self.root / row['id']
                    if self.closed.is_set():
                        break
                    if not feishu_reporting.origin(folder) or feishu_reporting.status(folder)['status'] != 'queued':
                        continue
                    try:
                        with (folder / 'review-feishu.log').open('a', encoding='utf-8') as log:
                            result = subprocess.run([feishu_reporting.sender_python(self.station), '-B', '-u',
                                str(Path(__file__).with_name('feishu_reporting.py')), '--station', str(self.station.path),
                                '--folder', str(folder)], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
                        if result.returncode and feishu_reporting.status(folder)['status'] == 'queued':
                            raise RuntimeError('Feishu reporter could not start')
                    except (OSError, RuntimeError, ValueError):
                        feishu_reporting.write(folder, {'status': 'error', 'error': 'Feishu reporter could not start'})
            except Exception as exc:
                print('Feishu reporting: ' + str(exc))
            self.closed.wait(5)

    def _poll(self):
        while not self.closed.wait(5):
            if not self.legacy and self.maintenance_lock.acquire(blocking=False):
                try:
                    self.policy('status')
                finally:
                    self.maintenance_lock.release()
            if self.legacy and not self.maintenance_lock.locked():
                try:
                    self.policy('status')
                    self.capture_policy_log()
                except Exception as e:
                    self.c.S.set_check('server', 'fail', str(e))

    def reconcile_pending(self):
        api = self.c.ev.EvalAPI(self.c.CONFIG)
        try:
            for row in self.store.pending(self.station.robot):
                if not (self.root / row['id'] / 'manifest.json').exists():
                    try:
                        assignment = api.request('GET', '/assignments/' + row['id'])
                        self.c.ev.save(self.root / row['id'] / 'manifest.json',
                                       {'assignment': assignment, 'outcomes': {}, 'uploaded': []})
                    except Exception:
                        continue
                if row['intent'] or row['discard_reason']:
                    reconcile(api, self.store, self.root, row['id'])
        finally:
            api.close()

    def policy(self, method, check='server'):
        candidate = getattr(self, 'candidate', None)
        if candidate:
            try:
                value = candidate.call('gpu' if check == 'gpu' else method)
                if method in ('status', 'start_policy', 'restart_policy') and check == 'server' and value.get('ok'):
                    from colosseum_client.local_policy import capabilities
                    # systemd Type=simple can become active before the socket is listening.
                    for attempt in range(6 if method != 'status' else 1):
                        try:
                            result = asyncio.run(capabilities(self.c.CONFIG.policy_server_url))
                            break
                        except Exception:
                            if method == 'status' or attempt == 5:
                                raise
                            time.sleep(0.5)
                    value['ok'] = result.get('verification_only') is False
                    value['detail'] += '; endpoint connected' if value['ok'] else '; unexpected verification runtime'
            except Exception as exc:
                value = {'ok': False, 'detail': str(exc)}
            state = 'ok' if value.get('ok') else 'fail'
            if check == 'server' and value.get('active_state') == 'inactive':
                state = 'idle'
            self.c.S.set_check(check, state, value.get('detail', 'Candidate maintenance failed'))
            return value
        if not self.legacy:
            if check == 'server' and method in ('status', 'start_policy'):
                from colosseum_client.local_policy import capabilities
                try:
                    result = asyncio.run(capabilities(self.c.CONFIG.policy_server_url))
                    ok = result.get('verification_only') is False
                    detail = 'Policy endpoint connected' if ok else 'Expected real candidate Policy runtime'
                except Exception:
                    ok, detail = False, 'Policy endpoint unavailable; check candidate service and SSH tunnel'
                self.c.S.set_check('server', 'ok' if ok else 'fail', detail)
                return {'ok': ok, 'detail': detail}
            self.c.S.set_check(check, 'idle', 'Managed on Policy host; UI maintenance is not configured')
            return {'ok': False, 'detail': 'UI maintenance is not configured'}
        value = self.legacy.call(method)
        self.c.S.set_check(check, 'ok' if value.get('ok') else 'fail',
                           value.get('detail') or value.get('msg') or value.get('error') or method)
        return value

    def stop_recording(self):
        c = self.c
        if c.recording():
            c.PROMPTS.closing = True
            c.PROMPTS.finish_now.set()
            c.PROMPTS.reply(None)
            c.RECORDER['thread'].join(120)
            if c.recording():
                raise RuntimeError('Client is still cleaning up; maintenance has not been executed')

    def maintain(self, action):
        if getattr(self, 'candidate', None):
            with self.maintenance_lock, self.lock:
                if action not in ('start_policy', 'stop_policy', 'restart_policy', 'restart_docker'):
                    raise ValueError('Candidate maintenance only controls the candidate Policy unit')
                if self.c.recording() or self.round_stop_pending:
                    raise RuntimeError('End the evaluation before candidate maintenance')
                if action == 'restart_docker':
                    if not getattr(self, 'nuc', None):
                        raise ValueError('NUC Docker maintenance is not configured')
                    self.c.PREVIEW.stop()
                    result = self.nuc.restart()
                    self.c.S.set_check('can', 'idle' if result.get('ok') else 'fail',
                                       result.get('detail') or result.get('msg') or result.get('error')
                                       or 'NUC restart requested; check robot readiness before evaluation')
                    return result
                return self.policy(action)
        with self.maintenance_lock:
            if action not in ('restart_policy', 'restart_docker', 'restart_can'):
                raise ValueError('Unknown maintenance action')
            self.stop_recording()
            self.c.PREVIEW.stop()
            result = self.policy(action, check='can' if action == 'restart_can' else 'server')
            if action == 'restart_can' and result.get('ok'):
                self.check_can()
            return result

    def record_thread(self, form):
        c = self.c
        config = replace(self.station.load_client_config(), track='open', instruction=form.get('instruction', '').strip(),
                         scene=form.get('scene', '').strip() or c.CONFIG.scene,
                         evaluator=self.current_person, max_trial_steps=int(form.get('max_steps') or c.CONFIG.max_trial_steps))
        resume = form.get('resume') or None
        c.S.set_run(phase='starting', side=None, step=0, max_steps=config.max_trial_steps, eval_id=resume,
                    instruction=config.instruction, message='Asking the Router for two policies…')
        originals = {name: getattr(c.ev, name, None) for name in ('progress', 'input', 'print', 'prompt_task_difficulty')}
        export = c.record_evals.lx.export_trial
        try:
            eid = c.record_evals.record(config, resume=resume, ask=c.PROMPTS.ask)
            if eid:
                self.store.state(eid, 'review')
                mark_manifest(self.root, eid, recording_error=None)
                if self.station.robot == 'franka':
                    try:
                        scene_reference.cleanup(self.root / eid)
                    except (OSError, ValueError) as exc:
                        print('Initial scene cleanup: ' + str(exc))
                c.S.set_run(phase='done', eval_id=eid, message='Both runs recorded. Score them now.')
            else:
                c.S.set_run(phase='error', message='Nothing was recorded. See the log below.')
        except BaseException as e:
            eid = c.S.run.get('eval_id')
            if eid:
                self.store.state(eid, 'interrupted')
                try:
                    mark_manifest(self.root, eid, recording_error=type(e).__name__ + ': ' + str(e))
                except OSError as persist_error:
                    print('Could not persist evaluation error: ' + str(persist_error))
            self.round_stop_clean = isinstance(e, RoundStopped)
            c.S.set_run(phase='stopping' if self.round_stop_clean else 'error',
                        message='正在清理本轮数据…' if self.round_stop_clean else
                        'Cancelled.' if isinstance(e, KeyboardInterrupt) else str(e))
        finally:
            for name, value in originals.items():
                if value is None:
                    c.ev.__dict__.pop(name, None)
                else:
                    setattr(c.ev, name, value)
            c.record_evals.lx.export_trial = export
            c.HW.release()

    def start(self, body):
        with self.lock:
            if self.c.recording() or self.round_stop_pending:
                raise self.c.HTTPException(409, 'An evaluation is already running')
            for path in self.root.glob('*/manifest.json'):
                try:
                    recovery = json.loads(path.read_text(encoding='utf-8')).get('error_recovery')
                except (OSError, ValueError):
                    continue
                if recovery and not recovery.get('cleanup_complete'):
                    raise PendingEvaluation('Failed-round local cleanup is incomplete: ' + path.parent.name)
            resume = body.get('resume')
            if resume and self.c.rv.load(self.c.known(resume)).get('recording_error'):
                raise PendingEvaluation('Discard the failed round and start a new one')
            pending = self.store.pending(self.station.robot)
            if pending and pending[0]['id'] != resume:
                raise PendingEvaluation('Submit or discard the pending A/B evaluation first: ' + pending[0]['id'])
            row = self.store.get(resume) if resume else None
            self.current_feishu = feishu_reporting.origin(self.root / resume) if resume else feishu_reporting.selection(self.station, body)
            self.current_person = row['person'] if row else self.store.add_person(body.get('evaluator', ''))
            self.c.PROMPTS.closing = False
            self.round_stop.clear()
            self.round_stop_clean = False
            self.c.S.set_run(restarted_from=None)
            return self.c.start_eval({**body, 'evaluator': self.current_person})

    def finish(self, body):
        with self.lock:
            c = self.c
            if body.get('expected_eid') and body['expected_eid'] != c.S.run.get('eval_id'):
                raise c.HTTPException(409, 'The active evaluation changed; refresh the page')
            if self.station.robot != 'franka' or body.get('reason') != 'stopped':
                return c.finish_now(body)
            with c.S.lock:
                if c.S.run['phase'] != 'running' or not c.recording():
                    raise c.HTTPException(409, 'No policy is running')
                eid, recorder = c.S.run['eval_id'], c.RECORDER['thread']
                self.round_stop.set()
                self.round_stop_pending = True
                c.PROMPTS.stop_reason = 'stopped'
                c.PROMPTS.finish_now.set()
                c.S.run.update(phase='stopping', message='正在停止整轮，等待归位和资源释放后清理数据…')
                c.S.touch()

            def finish_round():
                recorder.join()  # Never delete captures while the recorder still owns them.
                with self.lock:
                    try:
                        if self.round_stop_clean:
                            self.act(eid, {'action': 'restart'})
                            c.S.set_run(restarted_from=eid)
                    except Exception as exc:
                        c.S.set_run(phase='error', eval_id=eid, message='本轮清理未完成：' + str(exc))
                    finally:
                        self.round_stop_pending = False
                        c.S.touch()
            self.round_stop_thread = threading.Thread(target=finish_round, daemon=True)
            self.round_stop_thread.start()
            return {'ok': True}

    def summary(self, path):
        value = self.original_summary(path)
        value['recording_error'] = json.loads(path.read_text(encoding='utf-8')).get('recording_error')
        row = self.store.get(value['id'])
        if row:
            value.update(person=row['person'], robot=row['robot'], managed=True,
                         confirmed_at=row['confirmed_at'], beijing_date=row['beijing_date'])
            if row['state'] in ('unknown', 'submitting', 'discarding', 'submitted', 'discarded'):
                value['state'] = row['state']
        else:
            value['managed'] = False
        return value

    def detail(self, eid):
        value = self.original_detail(eid)
        document = self.c.rv.load(eid)
        value['task_difficulty'] = document.get('task_difficulty')
        value['recording_error'] = document.get('recording_error')
        value['error_recovery'] = document.get('error_recovery')
        value['feishu'] = feishu_reporting.status(self.root / eid)
        for run in value['runs']:
            root = self.root / eid / run['id']
            run['model_name'] = model_name(root / 'policy.json')
            videos = self.exported_videos(root)
            run['cams'] = list(dict.fromkeys(run['cams'] + list(videos)))
            if videos:
                run['recorded'] = True
        return value

    def exported_videos(self, root):
        result = {}
        for cam in self.c.CAMS:
            for key in (cam, 'observation.images.' + cam):
                paths = sorted((root / 'lerobot' / 'videos' / key).glob('chunk-*/file-*.mp4'))
                if paths:
                    result[cam] = paths[0]
                    break
        return result

    def video_path(self, eid, run_id, cam):
        exported = self.exported_videos(self.root / eid / run_id).get(cam)
        return exported or self.original_preview(eid, run_id, cam)

    def router(self, eid, action, reason=''):
        c = self.c
        if any(c.rv.busy(x) for x in c.rv.JOBS):
            raise c.HTTPException(409, 'Another Router action is still running')
        if c.rv.load(eid).get('review') == 'superseded':
            raise ValueError('This evaluation was superseded in the original Client')
        log = (self.root / eid / 'review-router.log').open('a', encoding='utf-8')
        job = subprocess.Popen([str(self.station.file('client_python')), '-u', str(Path(__file__).with_name('client_job.py')),
                                '--station', str(self.station.path), '--id', eid, '--action', action],
                               cwd=self.c.CLIENT, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                               text=True, encoding='utf-8', env={**os.environ, 'PYTHONUTF8': '1'})
        job.stdin.write(json.dumps({'reason': reason}) + '\n')
        job.stdin.close()
        c.rv.JOBS[eid] = job

        def finish():
            code = job.wait()
            log.write('\n[exit ' + str(code) + ']\n')
            log.close()
            c.S.touch()
        threading.Thread(target=finish, daemon=True).start()
        return 'Submission started. Dataset upload follows the existing Client configuration.' if action == 'submit' else 'Discard started.'

    def act(self, eid, body):
        with self.lock:
            self.c.known(eid)
            if self.c.rv.busy(eid):
                raise self.c.HTTPException(409, 'Still talking to the Router; wait a moment')
            try:
                with evaluation_lock(self.root / eid, blocking=False):
                    return self._act_locked(eid, body)
            except (BlockingIOError, PermissionError):
                raise self.c.HTTPException(409, 'Still talking to the Router; wait a moment')

    def _act_locked(self, eid, body):
        if body.get('action') == 'restart':
            return self.restart_failed(eid)
        if body.get('action') == 'submit' and not str(body.get('feedback') or '').strip():
            raise self.c.HTTPException(400, 'Overall feedback is required before submitting')
        row = self.store.get(eid)
        if row and (row['intent'] or row['discard_reason']) and not row['confirmed_at']:
            api = self.c.ev.EvalAPI(self.c.CONFIG)
            try:
                state = reconcile(api, self.store, self.root, eid)
            finally:
                api.close()
            if state == 'unknown':
                return {'msg': 'Submission status is unknown; no result was changed. Retry status check.', 'state': state}
        d = self.c.rv.load(eid)
        if d.get('submitted') or d.get('discarded'):
            return {'msg': 'This evaluation is closed.', 'state': 'submitted' if d.get('submitted') else 'discarded'}
        if d.get('recording_error'):
            if body.get('action') == 'discard':
                return self.restart_failed(eid)
            raise self.c.HTTPException(409, 'Failed rounds must be discarded and restarted; no score is needed')
        if self.station.robot == 'franka' and body.get('action', 'save') in ('save', 'submit'):
            try:
                value = difficulty(body.get('task_difficulty', d.get('task_difficulty')),
                                   required=body.get('action') == 'submit')
                save_difficulty(self.root / eid, value)
            except ValueError as exc:
                raise self.c.HTTPException(400, str(exc))
        result = self.c.act_eval(eid, body)
        if body.get('action', 'save') == 'save':
            self.store.state(eid, 'scored' if 'result' in self.c.rv.load(eid) else 'review')
        return result

    def restart_failed(self, eid):
        c = self.c
        if c.recording() or any(c.rv.busy(x) for x in c.rv.JOBS):
            raise c.HTTPException(409, 'Recording or Router cleanup is still running')
        row, document = self.store.get(eid), c.rv.load(eid)
        if not row or row['robot'] != self.station.robot:
            raise c.HTTPException(409, 'This evaluation is not managed by this station')
        if row['confirmed_at'] or row['intent'] or document.get('submitted') or document.get('uploaded'):
            raise c.HTTPException(409, 'Submitted or uploaded data cannot be discarded here')
        recovery = document.get('error_recovery')
        failure = document.get('recording_error')
        if c.S.run.get('eval_id') == eid and c.S.run.get('phase') == 'error':
            failure = failure or c.S.run.get('message') or 'Evaluation failed'
        if not recovery and not failure:
            raise c.HTTPException(409, 'Only a failed evaluation can use discard and restart')
        if c.S.run.get('eval_id') not in (None, eid):
            raise c.HTTPException(409, 'The active evaluation changed; refresh the page')
        if not recovery:
            mark_manifest(self.root, eid, recording_error=failure,
                          error_recovery={'mode': 'local_restart', 'requested_at': time.time(), 'cleanup_complete': False})
        error_recovery.cleanup(self.root, eid, self.store)
        self.store.discard(eid)
        c.reset_run()
        c.S.set_run(instruction='', max_steps=c.CONFIG.max_trial_steps)
        # The next task is entered and started explicitly by the operator.
        # Cleanup must not request an assignment or launch a recording thread.
        return {'state': 'idle', 'cleanup_complete': True}

    def provider_urls(self):
        configured = dict(self.station.data.get('provider_urls', {}))
        policy_config = self.station.data.get('policy_config')
        if policy_config and Path(policy_config).exists():
            import yaml
            document = yaml.safe_load(Path(policy_config).read_text(encoding='utf-8'))
            for model in document.get('models', []):
                if model.get('model_type') != 'llm':
                    continue
                name = model.get('name', '').lower()
                provider = next((provider for prefix, provider in
                                 [('gpt-', 'openai'), ('claude-', 'anthropic'), ('grok-', 'xai')]
                                 if name.startswith(prefix)), None)
                if provider and model.get('url'):
                    configured.setdefault(provider, model['url'])

            def walk(value):
                if isinstance(value, dict):
                    provider = value.get('provider') or value.get('llm_provider')
                    url = value.get('base_url') or value.get('api_base') or value.get('api_base_url')
                    if provider and url:
                        configured.setdefault(str(provider), str(url))
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            walk(document)
        return configured

    def provider_auth(self, provider):
        policy = self.station.data.get('policy_config')
        if policy and Path(policy).exists():
            import yaml
            document = yaml.safe_load(Path(policy).read_text(encoding='utf-8'))
            prefix = {'anthropic': 'claude-', 'openai': 'gpt-', 'xai': 'grok-'}[provider]
            for model in document.get('models', []):
                if model.get('name', '').lower().startswith(prefix):
                    return model.get('backend_options', {}).get('api_auth', 'api_key' if provider == 'anthropic' else 'bearer')
        return 'api_key' if provider == 'anthropic' else 'bearer'

    def verify_key(self, provider, key):
        url = self.provider_urls().get(provider)
        if not url:
            return False, 'Configured; provider service URL is not available for verification'
        headers = {'Authorization': 'Bearer ' + key}
        if provider == 'anthropic' and self.provider_auth(provider) != 'bearer':
            headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
        if provider == 'anthropic':
            from urllib.parse import urlsplit
            if not urlsplit(url).path.strip('/'):
                url = url.rstrip('/') + '/v1'
            headers['anthropic-version'] = '2023-06-01'
        try:
            response = self.c.httpx.get(url.rstrip('/') + '/models', headers=headers, timeout=20, follow_redirects=False)
            return response.is_success, 'Verified' if response.is_success else 'Provider verification HTTP ' + str(response.status_code)
        except self.c.httpx.HTTPError:
            return False, 'Could not reach the configured provider'

    def check_keys(self):
        c = self.c
        c.CONFIG = self.station.load_client_config()
        c.KEYS = dict(getattr(c.CONFIG, 'llm_api_keys', {}))
        rows = []
        for provider in c.CONFIG.llm_providers:
            if self.station.robot == 'franka':
                ok, message, source = False, 'Configured on this Client; not verified with provider', 'Client configuration'
            else:
                ok, message = self.verify_key(provider, c.KEYS.get(provider, ''))
                source = 'Local configuration'
            rows.append({'provider': provider, 'label': provider, 'ok': ok, 'msg': message, 'source': source})
        c.S.keys = rows
        c.S.set_check('keys', 'ok' if rows and all(x['ok'] for x in rows) else 'idle',
                      'Verified' if rows and all(x['ok'] for x in rows) else 'Configured credentials; see each provider status')

    def save_keys(self, body):
        if self.station.robot == 'franka':
            from client_credentials import save_client_keys
            save_client_keys(self.station, body)
            self.c.CONFIG = self.station.load_client_config()
            return
        path = self.station.file('database').with_name('llm-settings.json')
        value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        keys = value.setdefault('llm_api_keys', {})
        for provider, key in body.items():
            if provider in self.c.PROVIDERS and isinstance(key, str) and key.strip():
                keys[provider] = key.strip()
        tmp = path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        tmp.replace(path)
        self.c.CONFIG = self.station.load_client_config()

    def check_can(self, reset=False):
        if self.station.robot == 'franka':
            if reset:
                return self.maintain('restart_docker')
            return self.check_arms()
        if reset:
            return self.maintain('restart_can')
        return self.original_check_can()

    def check_arms(self):
        if self.station.robot == 'yam':
            return self.original_check_arms()
        # Ping only. Never construct RobotEnv as a connectivity check.
        import zerorpc
        client = zerorpc.Client(timeout=4, heartbeat=None)
        try:
            client.connect(self.station.data.get('robot_rpc', 'tcp://robot-controller.example.invalid:4242'))
            pong = client._zerorpc_ping()
            ok = bool(pong)
            for key in ('can', 'arms'):
                self.c.S.set_check(key, 'ok' if ok else 'fail', 'Robot RPC responded' if ok else 'Robot RPC did not respond')
        finally:
            client.close()

    def camera_reader(self):
        c = self.c
        if c.CONFIG.test:
            raise ValueError('No physical camera is opened by this test configuration')
        if self.station.robot == 'franka':
            from droid.camera_utils.camera_readers.uvc_camera import UvcMultiCameraWrapper
            adapter = c.CONFIG.adapter_config
            if adapter.get('camera_backend') != 'uvc':
                raise ValueError('This Franka station expects the existing UVC camera backend')
            reader = UvcMultiCameraWrapper(adapter['camera_config'])

            def read():
                data, _ = reader.read_cameras()
                images = data['image']
                return {name: next(value[..., :3][..., ::-1].copy() for key, value in images.items()
                                   if serial in str(key) and 'left' in str(key)) for name, serial in c.CONFIG.cameras.items()}
            return read, reader.disable_cameras
        from colosseum_client.robots.yam import _RealSenseCamera
        cameras = {}
        try:
            for name, serial in c.CONFIG.cameras.items():
                cameras[name] = _RealSenseCamera(serial, 3000)
        except BaseException:
            for camera in cameras.values():
                camera.close()
            raise
        return lambda: {name: camera.read() for name, camera in cameras.items()}, lambda: [x.close() for x in cameras.values()]

    def check_cameras(self):
        c = self.c
        if self.station.robot == 'yam':
            return self.original_check_cameras()
        if not c.HW.acquire(blocking=False):
            return c.S.set_check('cameras', 'fail', 'Cameras are busy')
        close = None
        try:
            read, close = self.camera_reader()
            images = read()
            c.S.thumbs = {name: c.jpeg(rgb, 640) for name, rgb in images.items()}
            c.S.set_check('cameras', 'ok', str(len(images)) + ' UVC cameras')
        finally:
            if close:
                close()
            c.HW.release()

    def preview_loop(self):
        c, close = self.c, None
        try:
            read, close = self.camera_reader()
            while not c.PREVIEW.stop_event.is_set():
                images = read()
                if c.TOP in images:
                    c.S.push_frame(images[c.TOP])
                c.PREVIEW.stop_event.wait(1 / 15)
        except Exception as e:
            print('Camera preview: ' + str(e))
        finally:
            try:
                if close:
                    close()
            finally:
                c.HW.release()

    def snapshot(self):
        state = self.c.snapshot()
        state['recording'] = state['recording'] or self.round_stop_pending
        if state.get('prompt'):
            # Nanosecond identifiers exceed JavaScript's exact integer range.
            state['prompt'] = {**state['prompt'], 'id': str(state['prompt']['id'])}
        eid = state['run'].get('eval_id')
        state['scene_reference'] = None
        if eid and self.station.robot == 'franka':
            try:
                reference = scene_reference.describe(self.root / eid)
                if reference:
                    state['scene_reference'] = {'evaluation_id': eid, 'cameras': list(scene_reference.CAMERAS),
                                                'version': str(reference['captured_at_ns'])}
            except (OSError, ValueError):
                pass  # Confirmation validates again and reports an actionable error.
        state['models'] = {}
        if eid:
            try:
                assignment = self.c.rv.load(eid)['assignment']
                state['models'] = {r['side']: model_name(self.root / eid / r['id'] / 'policy.json')
                                   for r in assignment['runs']}
            except (OSError, ValueError, KeyError):
                pass
        state['pending'] = self.store.pending(self.station.robot)
        if self.c.S.frame is not None and self.c.S.frame_seq != self.last_frame:
            self.last_frame = self.c.S.frame_seq
            self.frame_data = base64.b64encode(self.c.jpeg(self.c.S.frame, 960, 75)).decode('ascii')
        state['frame'], state['frame_seq'] = self.frame_data, self.last_frame
        return state

    def reply(self, body):
        if self.station.robot != 'franka' or body.get('kind') == 'recovery':
            return self.c.reply(body)
        with self.lock:
            c = self.c
            with c.S.lock:
                prompt = dict(c.S.prompt or {})
                eid = c.S.run.get('eval_id')
            if (not prompt or str(prompt.get('id')) != str(body.get('id')) or prompt.get('kind') != body.get('kind')
                    or prompt['id'] == self.last_replied_prompt):
                raise c.HTTPException(409, 'This confirmation has expired. Refresh the page.')
            if prompt['kind'] == 'scene' and body.get('answer') is not None:
                if body.get('answer') != '':
                    raise c.HTTPException(400, 'Invalid scene confirmation')
                folder = self.root / c.known(eid)
                document = c.rv.load(eid)
                reference = scene_reference.describe(folder)
                if not reference:
                    first = document['assignment']['runs'][0]['side']
                    if prompt.get('side') == first:
                        close = None
                        try:
                            read, close = self.camera_reader()
                            scene_reference.capture(folder, read())
                        finally:
                            if close:
                                close()
                    else:
                        origin = folder / 'ui-origin.json'
                        if origin.exists() and json.loads(origin.read_text()).get('scene_reference_required'):
                            raise ValueError('The initial scene reference is missing; the trial has not started')
                else:
                    for camera in scene_reference.CAMERAS:
                        scene_reference.image_path(folder, camera)
            self.last_replied_prompt = prompt['id']
            return c.reply(body)

    def capture_policy_log(self):
        manager = getattr(self, 'candidate', None) or self.legacy
        value = manager.call('logs') if manager else {}
        self.policy_log.append_snapshot(value.get('policy_tail') or value.get('POLICY_BUF') or '')
        return value

    def technical_logs(self):
        error = ''
        try:
            self.capture_policy_log()
        except Exception as exc:
            error = str(exc)
        directory = self.station.file('database').parent
        return {'client': tail(directory / 'worker.log'), 'policy': tail(directory / 'policy.log'),
                'error': error}

    def dispatch(self, method, body):
        c = self.c
        if method == 'config':
            info = c.config_info()
            if self.station.robot == 'franka':
                info['scene'] = scene_settings.read_scene(self.station.file('robot_config'))
            return {**info, 'people': self.store.people(), 'station': self.station.robot,
                    'scene_persistence_enabled': self.station.robot == 'franka',
                    'feishu': feishu_reporting.options(self.station),
                    'task_difficulty_enabled': self.station.robot == 'franka',
                    'scene_reference_enabled': self.station.robot == 'franka',
                    'evaluator_options': self.station.evaluator_options(),
                    'feedback_generation_enabled': self.station.data.get('feedback_generation_enabled') is True,
                    'managed_providers': list(c.CONFIG.llm_providers), 'settings_mode': 'keys',
                    'camera_serials': dict(c.CONFIG.cameras),
                    'policy_managed': bool(getattr(self, 'candidate', None) or self.legacy),
                    'maintenance': (['restart_policy'] + (['restart_docker'] if getattr(self, 'nuc', None) else []) if getattr(self, 'candidate', None) else [] if not self.legacy else
                                    ['restart_policy', 'restart_docker'] if self.station.robot == 'franka' else ['restart_policy', 'restart_can'])}
        if method == 'save_scene':
            with self.lock:
                if self.station.robot != 'franka':
                    raise c.HTTPException(400, 'Scene saving is not enabled for this station')
                if c.recording():
                    raise c.HTTPException(409, 'End the current evaluation before saving the scene')
                value = scene_settings.save_scene(self.station.file('robot_config'), body.get('scene'), body.get('expected_scene'))
                c.CONFIG = replace(c.CONFIG, scene=value)
                return {'ok': True, 'scene': value}
        if method == 'snapshot':
            return self.snapshot()
        if method == 'start':
            return self.start(body)
        if method == 'check':
            name = body['name']
            actions = {'gpu': c.check_gpu, 'free_gpu': c.free_gpu, 'can': c.check_can,
                       'can_reset': lambda: c.check_can(reset=True), 'arms': c.check_arms,
                       'cameras': c.check_cameras, 'router': c.check_router, 'keys': c.check_keys,
                       'server': c.SERVER.start, 'server_stop': c.SERVER.stop}
            if name not in actions and name != 'all':
                raise c.HTTPException(404)
            if c.recording() and name not in ('gpu', 'router', 'keys'):
                raise c.HTTPException(409, 'An evaluation is running')
            def check_one(key):
                try:
                    actions[key]()
                except Exception as e:
                    c.S.set_check({'can_reset': 'can', 'server_stop': 'server', 'free_gpu': 'gpu'}.get(key, key), 'fail', str(e))
            def check():
                for key in ('gpu', 'can', 'arms', 'cameras', 'router', 'keys', 'server') if name == 'all' else (name,):
                    check_one(key)
            threading.Thread(target=check, daemon=True).start()
            return {'ok': True}
        if method == 'preview':
            return c.preview(body['action'])
        if method == 'reply':
            return self.reply(body)
        if method == 'scene_reference':
            path = scene_reference.image_path(self.root / c.known(body['id']), body['camera'])
            return str(path) if path else None
        if method == 'finish':
            return self.finish(body)
        if method == 'reset':
            if body.get('expected_eid') and c.S.run.get('eval_id') not in (None, body['expected_eid']):
                raise c.HTTPException(409, 'The active evaluation changed; refresh the page')
            return c.reset_run()
        if method == 'list':
            values = []
            for path in self.root.glob('*/manifest.json'):
                try:
                    values.append(self.summary(path))
                except (ValueError, KeyError, OSError):
                    continue
            values.sort(key=lambda x: x['time'], reverse=True)
            offset, limit = max(0, int(body.get('offset', 0))), max(1, int(body.get('limit', 60)))
            return {'items': values[offset:offset + limit], 'total': len(values), 'offset': offset, 'limit': limit}
        if method == 'detail':
            return self.detail(c.known(body['id']))
        if method == 'act':
            return self.act(body['id'], body['body'])
        if method == 'reconcile':
            self.reconcile_pending()
            return {'ok': True, 'pending': self.store.pending(self.station.robot)}
        if method == 'stats':
            reports = []
            for row in self.store.confirmed(body.get('date')):
                folder = self.root / row['id']
                if feishu_reporting.origin(folder):
                    reports.append({'id': row['id'], 'person': row['person'], 'date': row['beijing_date'],
                                    **{k: v for k, v in feishu_reporting.status(folder).items() if k in ('status', 'error')}})
            return {**self.store.stats(body.get('date')), 'feishu_reports': reports}
        if method == 'retry_feishu':
            eid = c.known(body['id'])
            row = self.store.get(eid)
            if not row or not row['confirmed_at'] or not feishu_reporting.origin(self.root / eid):
                raise c.HTTPException(400, 'Only confirmed evaluations with Feishu enabled can be reported')
            feishu_reporting.retry(self.root / eid, body.get('checked_missing') is True)
            return {'ok': True}
        if method == 'people':
            if body.get('name'):
                self.store.add_person(body['name'])
            return self.store.people()
        if method == 'keys':
            return c.set_keys(body)
        if method == 'maintenance':
            return self.maintain(body['action'])
        if method == 'logs':
            return self.technical_logs()
        if method == 'generate':
            return self.generate_feedback(body['id'], body['body'])
        if method == 'thumb':
            data = c.S.thumbs.get(body['cam'])
            return base64.b64encode(data).decode('ascii') if data else None
        if method == 'video':
            eid = c.known(body['id'])
            if body['cam'] not in c.CAMS or body['run'] not in {r['id'] for r in c.rv.load(eid)['assignment']['runs']}:
                raise c.HTTPException(404)
            value = self.video_path(eid, body['run'], body['cam'])
            return str(value) if value else None
        if method == 'shutdown':
            self.closed.set()
            self.stop_recording()
            c.PREVIEW.stop()
            if self.legacy:
                self.legacy.close()
            return {'ok': True}
        raise ValueError('Unknown worker operation')

    def generate_feedback(self, eid, body):
        c = self.c
        if self.station.data.get('feedback_generation_enabled') is not True:
            raise c.HTTPException(403, 'AI feedback generation is disabled in this station configuration')
        observation = str(body.get('feedback') or '').strip()
        if not observation:
            raise c.HTTPException(400, 'Write an overall comment first')
        a = c.rv.load(c.known(eid))['assignment']
        prompt = ('Rewrite the evaluator comment below as one concise overall evaluation in English. '
                  'Preserve its meaning; do not invent events, infer unseen video content, or change the scores '
                  'or preference. Use no headings and no more than 100 words.\n'
                  f"Task: {a.get('task', {}).get('instruction', '')}\n"
                  f"A score: {body.get('score_A', 'not given')}/100\n"
                  f"B score: {body.get('score_B', 'not given')}/100\n"
                  f"Preference: {body.get('preference') or 'not chosen'}\n"
                  f'Evaluator comment: {observation}')
        c.KEYS = dict(getattr(self.station.load_client_config(), 'llm_api_keys', {}))
        if not c.KEYS.get('anthropic'):
            return {'feedback': c.feedback_via_claude_code(prompt)}
        url = self.provider_urls().get('anthropic')
        if not url:
            raise ValueError('Configure the Anthropic service URL before generating feedback')
        from urllib.parse import urlsplit
        if not urlsplit(url).path.strip('/'):
            url = url.rstrip('/') + '/v1'
        headers = {'anthropic-version': '2023-06-01'}
        if self.provider_auth('anthropic') == 'bearer':
            headers['Authorization'] = 'Bearer ' + c.KEYS['anthropic']
        else:
            headers['x-api-key'] = c.KEYS['anthropic']
        try:
            response = c.httpx.post(url.rstrip('/') + '/messages', headers=headers,
                json={'model': self.station.data.get('feedback_model', 'claude-haiku-5-5'), 'max_tokens': 16000,
                      'output_config': {'effort': 'low'}, 'messages': [{'role': 'user', 'content': prompt}]},
                timeout=120, follow_redirects=False)
        except c.httpx.HTTPError:
            raise c.HTTPException(502, 'Could not reach the configured feedback provider')
        if not response.is_success:
            raise c.HTTPException(502, 'Feedback generation HTTP ' + str(response.status_code))
        result = response.json()
        text = ''.join(x.get('text', '') for x in result.get('content', []) if x.get('type') == 'text').strip()
        if not text or result.get('stop_reason') == 'refusal':
            raise c.HTTPException(502, 'No feedback was written; edit the observations and try again')
        return {'feedback': text}
