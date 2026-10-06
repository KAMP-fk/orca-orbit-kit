#!/usr/bin/env python3
"""Read-only context checks using isolated local Git repositories."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

CONTEXT=Path(__file__).resolve().parents[1] / 'agents/team/bin/context'


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='checkout-context-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.repo=self.root/'repository with spaces';self.repo.mkdir()
        self.git=shutil.which('git')
        self.env={key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null')
        self.g('init','-q')
        (self.repo/'tracked.txt').write_text('baseline\n')
        self.g('add','tracked.txt');self.g('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-qm','baseline')
        self.sha=self.g('rev-parse','HEAD').stdout.strip()

    def g(self,*args):
        return subprocess.run([self.git,'-C',str(self.repo),*args],env=self.env,text=True,capture_output=True,check=True)

    def context(self,*args,env=None):
        r=subprocess.run([str(CONTEXT),str(self.repo),'--json',*args],env=env or self.env,text=True,capture_output=True,timeout=20)
        return r,json.loads(r.stdout)

    def test_clean_full_sha_with_remote_unchecked(self):
        r,j=self.context();self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(j['headSha'],self.sha);self.assertFalse(j['dirty']);self.assertFalse(j['detached'])
        self.assertEqual(j['remoteFreshness'],'not-checked');self.assertEqual(j['authorization'],'not-evaluated')
        self.assertTrue(j['observedAt'].endswith('Z'))

    def test_changes_preserved_no_env_values_exposed(self):
        (self.repo/'tracked.txt').write_text('changed\n');(self.repo/'.env').write_text('TOKEN=fixture-private-value\n')
        index=self.repo/'.git/index';stamp=index.stat().st_mtime_ns
        r,j=self.context();self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(j['dirty']);self.assertIn('.env',r.stdout)
        self.assertNotIn('fixture-private-value',r.stdout+r.stderr);self.assertEqual((self.repo/'tracked.txt').read_text(),'changed\n')
        self.assertEqual(index.stat().st_mtime_ns,stamp)

    def test_contract_presence_without_content(self):
        (self.repo/'AGENTS.md').write_text('untrusted fixture: TOKEN=hidden-value\n')
        r,j=self.context();self.assertEqual(r.returncode,0,r.stderr)
        a=next(x for x in j['contractSources'] if x['path'].endswith('/AGENTS.md'))
        self.assertTrue(a['present']);self.assertFalse(a['contentRead']);self.assertNotIn('hidden-value',r.stdout)

    def test_detached_head_explicit(self):
        self.g('checkout','--detach','-q',self.sha);r,j=self.context();self.assertEqual(r.returncode,0,r.stderr)
        self.assertTrue(j['detached']);self.assertIsNone(j['branch']);self.assertEqual(j['headSha'],self.sha)

    def test_card_limit_observable_no_contents(self):
        card=self.root/'card.md';card.write_text('private note\n'*51)
        r,j=self.context('--card',str(card));self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(j['statusCard']['lineCount'],51);self.assertFalse(j['statusCard']['withinLimit']);self.assertNotIn('private note',r.stdout)

    def test_missing_card_is_not_presence(self):
        r,j=self.context('--card',str(self.root/'missing.md'));self.assertEqual(r.returncode,0,r.stderr);self.assertFalse(j['statusCard']['present'])

    def test_env_not_accepted_as_card(self):
        card=self.root/'.env';card.write_text('TOKEN=hidden\n')
        r,j=self.context('--card',str(card));self.assertEqual(r.returncode,1);self.assertEqual(j['status'],'error');self.assertNotIn('TOKEN=',r.stdout)

    def test_not_repository_is_error(self):
        empty=self.root/'empty';empty.mkdir()
        r=subprocess.run([str(CONTEXT),str(empty),'--json'],env=self.env,text=True,capture_output=True)
        self.assertEqual(r.returncode,1);j=json.loads(r.stdout);self.assertEqual(j['status'],'error');self.assertNotIn('headSha',j)

    def test_head_changed_during_observation_is_error(self):
        bindir=self.root/'bin';bindir.mkdir();wrapper=bindir/'git';counter=self.root/'count'
        wrapper.write_text('#!/usr/bin/python3\nimport os,sys,subprocess\nfrom pathlib import Path\na=sys.argv[1:]\np=Path(os.environ["COUNTER"])\nif a[-3:]==["rev-parse","--verify","HEAD"]:\n n=int(p.read_text()) if p.exists() else 0\n p.write_text(str(n+1))\n if n>0: print("b"*40);sys.exit(0)\nos.execv(os.environ["REAL_GIT"],[os.environ["REAL_GIT"]]+a)\n');wrapper.chmod(0o755)
        env=dict(self.env,PATH=str(bindir)+':'+self.env['PATH'],COUNTER=str(counter),REAL_GIT=self.git)
        r,j=self.context(env=env);self.assertEqual(r.returncode,1,r.stderr);self.assertEqual(j['status'],'error');self.assertNotIn('headSha',j)

    def test_symlink_invocation(self):
        link=self.root/'context-link';link.symlink_to(CONTEXT)
        r=subprocess.run([str(link),str(self.repo),'--json'],env=self.env,text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['headSha'],self.sha)

    def test_inherited_git_environment_cannot_redirect_checkout(self):
        other=self.root/'other';other.mkdir()
        subprocess.run([self.git,'-C',str(other),'init','-q'],env=self.env,check=True)
        (other/'other.txt').write_text('other repository\n')
        subprocess.run([self.git,'-C',str(other),'add','other.txt'],env=self.env,check=True)
        subprocess.run([self.git,'-C',str(other),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                        '-c','core.hooksPath=/dev/null','commit','--no-gpg-sign','-qm','other'],env=self.env,check=True)
        index=other/'.git/index';stamp=index.stat().st_mtime_ns
        polluted=dict(self.env,GIT_DIR=str(other/'.git'),GIT_WORK_TREE=str(other),
                      GIT_INDEX_FILE=str(index),GIT_COMMON_DIR=str(other/'.git'),
                      GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='core.worktree',GIT_CONFIG_VALUE_0=str(other))
        r,j=self.context(env=polluted)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(j['repositoryRoot'],str(self.repo.resolve()))
        self.assertEqual(j['headSha'],self.sha);self.assertFalse(j['dirty']);self.assertEqual(index.stat().st_mtime_ns,stamp)

    def test_fixture_with_polluted_parent_preserves_external_checkout(self):
        (self.repo/'tracked.txt').write_text('external uncommitted change\n')
        index=self.repo/'.git/index';stamp=index.stat().st_mtime_ns
        polluted=dict(self.env,GIT_DIR=str(self.repo/'.git'),GIT_WORK_TREE=str(self.repo),GIT_INDEX_FILE=str(index))
        r=subprocess.run([shutil.which('python3'),'-B',str(Path(__file__).resolve()),
                          'ContextTests.test_clean_full_sha_with_remote_unchecked'],
                         env=polluted,text=True,capture_output=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(self.g('rev-parse','HEAD').stdout.strip(),self.sha)
        self.assertEqual(index.stat().st_mtime_ns,stamp)
        self.assertEqual((self.repo/'tracked.txt').read_text(),'external uncommitted change\n')

    def test_subdirectory_resolves_to_containing_checkout(self):
        subdir=self.repo/'subdirectory';subdir.mkdir()
        r=subprocess.run([str(CONTEXT),str(subdir),'--json'],env=self.env,text=True,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['repositoryRoot'],str(self.repo.resolve()))

    def test_configured_worktree_outside_requested_path_is_error(self):
        other=self.root/'redirected';other.mkdir();self.g('config','core.worktree',str(other))
        r,j=self.context();self.assertEqual(r.returncode,1,r.stderr);self.assertEqual(j['status'],'error')
        self.assertNotIn('headSha',j)


if __name__=='__main__':unittest.main(verbosity=2)
