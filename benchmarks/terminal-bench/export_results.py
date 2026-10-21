"""Export a sanitized, post-hoc pool of two independent Terminal-Bench runs.

Both source runs must have full passing audits and the same tasks and arms.
Raw captures, sessions, account metadata, and provider IDs are never exported.
"""
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from pennybench.stats import compute_stats, paired_tasks

ROOT=Path(__file__).resolve().parents[2]
SLUG='pennyrouter-tb21-20261019-20261020'
TRIAL_FIELDS=('pair','position','task','rep','role','trial_id','arm','status','reward',
              'exception_type','agent_version','task_checksum','runner_wall_clock_s',
              'harbor_exit_code','harbor_hung')
PRIVATE=re.compile(r'/Users/[^/\s"\']+|/private/var/folders/[^\s"\']+|sk-ant-[^\s"\']+|Bearer [^\s"\']+|msg_[A-Za-z0-9_-]+')


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(PRIVATE.sub('<redacted>',json.dumps(value,indent=2))+'\n')


def sanitize_manifest(manifest):
    value=copy.deepcopy(manifest);value.pop('host_home',None)
    for arm in value['arms'].values():
        if arm.get('endpoint'):arm['endpoint']['base_url']='<local-proxy-endpoint>'
    return value


def export(runs,out):
    pooled=[];trials=[];eligible=[];sources=[];audits={};manifests=[]
    source_sets=[]
    for rep,run in enumerate(runs):
        m=json.loads((run/'run.json').read_text());a=json.loads((run/'audit.json').read_text())
        assert a['passed'] and not a.get('partial'),'A source full audit did not pass'
        metrics=json.loads((run/'metrics.json').read_text());assert len(metrics)==136
        assert {t['trial_id'] for t in metrics}=={t['trial_id'] for t in m['plan']}
        manifest_metrics=json.loads((run/'stats.json').read_text())
        source_slug='pennyrouter-tb21-'+('20261019' if rep==0 else '20261020')
        source_out=out/'source-runs'/source_slug;audits[source_slug]=a;manifests.append(m)
        write_json(source_out/'run.json',sanitize_manifest(m));write_json(source_out/'audit.json',a)
        write_json(source_out/'stats.json',manifest_metrics)
        clean_metrics=copy.deepcopy(metrics)
        for row in clean_metrics:
            if row.get('failure'):row['failure'].pop('provider_message_id',None)
        write_json(source_out/'metrics.json',clean_metrics)
        source_trials=[]
        for planned in m['plan']:
            rec=json.loads((run/'trials'/planned['trial_id']/'trial.json').read_text())
            selected={k:rec.get(k) for k in TRIAL_FIELDS};source_trials.append(selected)
            combined=copy.deepcopy(selected)
            combined.update(rep=rep,source_run=source_slug,source_experiment=m['experiment'],source_trial_id=rec['trial_id'],trial_id=source_slug+'/'+rec['trial_id'])
            trials.append(combined)
        write_json(source_out/'trials.json',source_trials)
        for row in clean_metrics:
            row.update(rep=rep,source_run=source_slug,source_experiment=m['experiment'],source_trial_id=row['trial_id'],trial_id=source_slug+'/'+row['trial_id'])
        pooled.extend(clean_metrics);eligible.append(set(paired_tasks(clean_metrics)[0]))
        source_sets.append({t['task'] for t in metrics})
        sources.append({'publication_name':source_slug,'experiment':m['experiment'],'created_at':m['created_at'],
                        'preregistered':m['preregistered'],'manifest_sha256':hashlib.sha256((run/'run.json').read_bytes()).hexdigest(),
                        'metrics_sha256':hashlib.sha256((run/'metrics.json').read_bytes()).hexdigest(),'audit_passed':True,'trials':136})
    assert source_sets[0]==source_sets[1] and len(source_sets[0])==68
    for key in ['arms','tasks','task_skills','cache_isolation']:
        assert manifests[0][key]==manifests[1][key],f'Source configuration differs: {key}'
    manifest={'experiment':SLUG,'stage':'full','k':2,'seed':20261020,'preregistered':False,
              'analysis_type':'post_hoc_pool_of_two_independent_k1_runs','endpoints':manifests[1]['endpoints'],
              'quality':manifests[1]['quality'],'sources':sources,'arms':sanitize_manifest(manifests[1])['arms'],
              'tasks':manifests[1]['tasks'],'task_skills':'without','cache_isolation':'trial',
              'reproduction_route':'Hosted default https://api.pennyrouter.com with your own linked account.',
              'measured_route':'Configured local PennyRouter endpoint; address redacted.'}
    stats=compute_stats(manifest,pooled,True)
    reason='Post-hoc pooling of two independent k=1 runs; not a preregistered k=2 experiment.'
    stats['not_a_claim_because']=[reason]
    tasks,dropped=paired_tasks(pooled);both=eligible[0]&eligible[1];one=eligible[0]^eligible[1]
    outcomes={}
    from collections import Counter
    for role in ['baseline','treatment']:
        rows=[t for t in pooled if t['role']==role]
        kept=[t for t in rows if t['task'] in eligible[t['rep']]]
        outcomes[role]={'attempts':len(rows),'successes':sum(t['metrics']['reward']==1 for t in rows),
          'eligible_repetitions':len(kept),'eligible_cost':sum(t['metrics']['cost'] for t in kept),
          'all_attempt_cost':sum(t['metrics']['cost'] for t in rows),
          'failure_categories':dict(Counter(t['failure']['category'] for t in rows if t.get('failure')))}
    outcomes['eligible_cost_change_pct']=(outcomes['treatment']['eligible_cost']/outcomes['baseline']['eligible_cost']-1)*100
    method={'analysis':reason,'runs':sources,'unit':'Task; each arm uses its median across eligible repetitions.',
      'eligibility':'Both arm statuses must be complete for a task-repetition.',
      'eligible_task_repetitions':sum(map(len,eligible)),'excluded_task_repetitions':len(dropped),
      'tasks_both_repetitions':len(both),'tasks_one_repetition':len(one),'tasks_neither_repetition':68-len(tasks),
      'bootstrap_seed':20261020,'actual_spending':'Sum across all eligible task-repetitions.',
      'table_sum':'Sum of per-task arm medians; each task contributes once.'}
    sensitivity=compute_stats(manifest,[t for t in pooled if t['task'] in both],True)
    sensitivity['not_a_claim_because']=[reason+' Sensitivity restricted to tasks with both eligible repetitions.']
    for name,value in [('run',manifest),('stats',stats),('metrics',pooled),('trials',trials),('outcomes',outcomes),('sources',method),('both-repetitions-only',sensitivity)]:
        write_json(out/f'{name}.json',value)
    write_json(out/'audit.json',{'passed':True,'scope':'Both source runs passed full evidence audits; no new pooled evidence audit is claimed.','sources':audits})
    print(f'Exported {len(pooled)} trials; {len(tasks)} tasks; {len(dropped)} excluded task-repetitions to {out}')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first_run',type=Path);parser.add_argument('second_run',type=Path)
    parser.add_argument('--out',type=Path,default=ROOT/'benchmarks/terminal-bench/results'/SLUG)
    args=parser.parse_args();export([args.first_run,args.second_run],args.out)
