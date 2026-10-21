"""Populate the actual SkillsBench HTML template with the published pooled results."""
import copy
import html
import json
import re
from pathlib import Path
from pennybench.stats import paired_tasks
from report_template import Node, parse, pct, pv, tone

ROOT=Path(__file__).resolve().parents[2]
SLUG='pennyrouter-tb21-20261019-20261020'
RESULTS=ROOT/'benchmarks/terminal-bench/results'/SLUG
HERE=ROOT/'output'/SLUG


def build():
    stats=json.loads((RESULTS/'stats.json').read_text())
    pooled=json.loads((RESULTS/'metrics.json').read_text())
    actual=json.loads((RESULTS/'outcomes.json').read_text())
    tasks,dropped=paired_tasks(pooled)
    eligible=[set(paired_tasks([row for row in pooled if row['rep']==i])[0]) for i in [0,1]]
    both=eligible[0]&eligible[1]
    HERE.mkdir(parents=True,exist_ok=True)
    source=(ROOT/'output/pennyrouter-skillsbench-20261019/index.html').read_text()
    page=parse(source);ends=stats['endpoints'];cost=ends['cost'];reward=ends['reward'];n=len(tasks)
    better,worse,equal=[reward[k] for k in ['treatment_better','treatment_worse','equal']]
    page.one('title').text('PennyBench - Terminal-Bench 2.1 / pooled analysis')
    for meta in page.all('meta'):
        if meta.attrs.get('name')=='description':meta.attrs['content']='Exploratory pooled analysis of two Terminal-Bench 2.1 runs: 68 tasks, 272 trials, task-level paired statistics.'
    page.one('.button').attrs['href']='../pdf/pennyrouter-tb21-20261019-20261020.pdf'
    for section in page.all('section'):
        section.one('.sectionline').all('span')[1].text('POOLED ANALYSIS')
    overview=page.one('#overview')
    overview.one('.eyebrow').text('Harbor harness / Terminal-Bench 2.1 task-provided verifiers')
    overview.one('h1').content('68 tasks. Two runs.<br>31% lower median cost.')
    overview.one('.lede').content('Exploratory pooling of two native Claude Code and PennyRouter runs, using the <strong>Harbor harness and Terminal-Bench task-provided verifiers</strong>. 272 trials; 63 tasks contribute to paired statistics.')
    overview.one('.big').content('31.1<small>%</small>')
    note=overview.one('.hero-note');note.one('strong').text(f'{pct(cost["ci95_median_pct"][0])} to {pct(cost["ci95_median_pct"][1])}')
    exponent=int(f'{cost["wilcoxon_p"]:.2e}'.split('e')[1]);mantissa=f'{cost["wilcoxon_p"]:.2e}'.split('e')[0]
    note.all('p')[1].content(f'Primary endpoint / {n} pooled tasks<br>Wilcoxon p = {mantissa} &times; 10<sup>{exponent}</sup>')
    for node,value in zip(overview.all('.number'),['51 / 63','12.1%','63 tasks']):node.text(value)
    overview.all('.tile')[1].one('p').text('Lower spending across 116 eligible repetitions')
    overview.all('.tile')[2].one('p').text('53 with two eligible reps; 10 with one')
    bars=overview.all('.barline');btotal=actual['baseline']['eligible_cost'];ttotal=actual['treatment']['eligible_cost']
    bars[0].one('.mono').text(f'${btotal:.3f}');bars[1].one('.mono').text(f'${ttotal:.3f}')
    bars[1].one('.bar').attrs['style']=f'width:{ttotal/btotal*100:.4f}%'
    blocks=overview.all('.block')
    blocks[0].one('.caption').text(f'${btotal-ttotal:.3f} less across 116 eligible task-repetitions per arm. Actual summed spend: -12.1%. Notional model-call USD, not a subscription bill.')
    blocks[1].all('.caption')[0].text(f'Penny scored higher on {better} tasks, lower on {worse}, and tied on {equal}. Mean task-level reward was {reward["mean_treatment"]:.3f} through Penny versus {reward["mean_baseline"]:.3f} natively.')
    blocks[1].all('.caption')[1].text('Both source runs passed their full evidence audits. This is a post-hoc pooled analysis, not a preregistered k=2 study. Original rewards and source files are unchanged.')
    for bar in page.all('.qualitybar'):
        bar.attrs['aria-label']=f'Penny pooled reward across 63 tasks: {better} higher, {equal} tied, {worse} lower'
        for span,count in zip(bar.all('span'),[better,equal,worse]):span.attrs['style']=f'width:{count/n*100:.4f}%'
    for legend in page.all('.legend'):
        bold=bool(legend.all('b'));labels=['Penny higher','Equal reward','Penny lower'] if bold else ['higher','tied','lower']
        for span,count,label in zip(legend.all('span'),[better,equal,worse],labels):span.content(f'<b>{count}</b>{label}' if bold else f'{count} {label}')
    efficiency=page.one('#efficiency')
    efficiency.one('.lede').text('Median task-level cost fell 31.1%. The sum of per-task medians fell 10.4%; actual spending across eligible repetitions fell 12.1%. These use different task weights.')
    efficiency.one('thead').all('th')[3].text('Sum of task medians')
    keys=['cost','total_tokens','output_tokens','fresh_input_tokens','cache_read_tokens','cache_write_tokens','turns','wall_clock']
    for row,key in zip(efficiency.one('tbody').all('tr'),keys):
        e=ends[key];lo,hi=e['ci95_median_pct'];values=[pct(e['median_pct']),f'[{lo:+.1f}, {hi:+.1f}]',pct(e['total_pct']),pv(e['wilcoxon_p'])]
        for td,value in zip(row.all('td'),values):td.text(value)
        row.all('td')[0].attrs['class']=tone(e['median_pct']);row.all('td')[2].attrs['class']=tone(e['total_pct'])
    blocks=efficiency.all('.block');tokens=ends['total_tokens'];cache=ends['cache_read_tokens'];output=ends['output_tokens']
    blocks[0].one('h3').content(f'{tokens["total_baseline"]/1e6:.2f}M &rarr; {tokens["total_treatment"]/1e6:.2f}M')
    blocks[0].one('p').content(f'Sums of per-task median token counts, native to Penny. Cache-read tokens: {cache["total_baseline"]/1e6:.2f}M &rarr; {cache["total_treatment"]/1e6:.2f}M. These are not totals across all attempts.')
    blocks[1].one('h3').content(f'{output["total_baseline"]:,.1f} &rarr; {output["total_treatment"]:,.1f}')
    blocks[1].one('p').text(f'Sums of per-task median output tokens, native to Penny: {pct(output["total_pct"])}. The median task-level change was {pct(output["median_pct"])}.')
    ps=blocks[2].all('p')
    ps[0].text('Within each task, take each arm\'s median across eligible repetitions, then compare Penny / native - 1. A repetition is eligible only when both arms completed. Tasks are the statistical unit; 272 trials are not treated as independent tasks.')
    ps[1].text(f'The median and 95% bootstrap interval describe task-level changes. P-values use paired Wilcoxon signed-rank on per-task log ratios; the cost Hodges-Lehmann estimate is {pct(cost["hodges_lehmann_pct"])}. Table sums add 63 per-task medians; the first-page cost bars sum spending over 116 eligible repetitions.')
    ps[2].text('Agent execution time uses Harbor\'s agent-execution span, excluding container build and installation. With both eligible repetitions required (53 tasks), median cost fell 30.2% and summed task cost fell 14.2%. Quality tests do not establish equivalence or non-inferiority.')
    audit=page.one('#audit');audit.one('.methodology-intro').one('h3').text('Harbor execution. Terminal-Bench verification.')
    audit.one('.methodology-intro').one('p').text('Two independent k=1 runs cover the same 68 tasks and arms. Their 272 finished trials are pooled here post-hoc. The full evidence audit passed in each source run. Original task rewards, graders, and source manifests are unchanged; this post-hoc analysis does not create a new preregistered experiment.')
    audit.one('.eyebrow').text('Task-level mean rewards / 63 pooled tasks')
    for node,value in zip(audit.one('.tiles').all('.number'),[reward['mean_baseline'],reward['mean_treatment']]):node.text(f'{value:.3f}')
    grid=audit.one('.grid2');left,right=[node for node in grid.children if isinstance(node,Node)]
    left.all('p')[-1].text(f'Sign test p = {reward["sign_test_p"]:.3f}. No significant difference detected. Values are mean task-level rewards after pooling, not all-attempt pass rates. No non-inferiority margin was declared.')
    scope=audit.one('.scopebox');scope.one('.number').text('68 = 53 + 10 + 5')
    scope.one('p').text('53 tasks have two eligible repetitions; 10 have one; 5 have neither. 116 task-repetitions are eligible, 20 excluded.')
    ps=right.all('.caption')
    ps[0].content('<strong>All-attempt outcomes:</strong> Native passed 103/136 attempts (75.7%); Penny passed 104/136 (76.5%). Errors remain scored failures. All 272 rewards are present.')
    ps[1].content('<strong>Pooling scope:</strong> 63 tasks contribute to paired statistics. Only eligible repetitions contribute to their per-task medians. Both-repetitions-only results are saved separately as a sensitivity check.')
    audit.one('.block').one('p').text('Both source runs passed all 11 evidence checks. These are source-run audits, not a new pooled audit or preregistration. No adoption marker was declared.')
    items=audit.all('.audit-item')
    items[0].one('p').text('Two full source runs: all 272 planned trials finished.')
    items[5].one('strong').text('Task skills');items[5].one('p').text('No task-local skills were installed in either arm.')
    items[-1].one('.mono').text('POOLED ANALYSIS')
    audit.one('.source').content('<strong>Setup:</strong> Terminal-Bench 2.1 / Sonnet 5.5, medium / Claude Code 2.1.302 / no task skills / two independent runs of 68 tasks / Pro plan / rates pinned 2026-10-15. Source seeds: 20261019 and 20261020. Selection: 68 of 89 tasks after 17 resource exclusions and 4 reference failures. The first run was registered; the second was not. This pooling was selected post-hoc. Recommended reproduction route: hosted https://api.pennyrouter.com with your own linked account.')
    order=list(dict.fromkeys(t['task'] for t in pooled if t['rep']==0));rows=[]
    for i,task in enumerate(order,1):
        count=sum(task in valid for valid in eligible);included=task in tasks
        if included:
            b,t=tasks[task]['baseline'],tasks[task]['treatment'];br,tr=b['reward'],t['reward'];change=(t['cost']/b['cost']-1)*100 if b['cost'] else None
            outcome='equal' if br==tr else 'better' if tr>br else 'worse';label=f'{count} eligible reps'
        else:
            br=tr=change=None;outcome='excluded';label='No eligible reps'
        rows.append(f'<tr data-outcome="{outcome}" data-task="{html.escape(task)}"><td class="idx">{i:02d}</td><th scope="row">{html.escape(task)}</th><td>{br if br is not None else "N/A"}</td><td>{tr if tr is not None else "N/A"}</td><td class="costchange {tone(change) if change is not None else "neutral"}">{pct(change) if change is not None else "N/A"}</td><td class="scope {"" if included else "excluded"}">{label}</td></tr>')
        # Display the same three-decimal format as the source template.
        if included:rows[-1]=rows[-1].replace(f'<td>{br}</td>',f'<td>{br:.3f}</td>',1).replace(f'<td>{tr}</td>',f'<td>{tr:.3f}</td>',1)
    main=page.one('main');templates=[page.one(f'#projects-{i}') for i in [1,2,3]]
    main.children=[node for node in main.children if not(isinstance(node,Node) and 'appendix' in node.attrs.get('class','').split())]
    for i,start in enumerate(range(0,68,20),1):
        node=copy.deepcopy(templates[0] if i==1 else templates[2] if start+20>=68 else templates[1])
        node.attrs['id']=f'projects-{i}';node.attrs['aria-labelledby']=f'projects-title-{i}';node.one('h2').attrs['id']=f'projects-title-{i}'
        node.one('h2').text('Every task. Every pooled reward.')
        node.one('.sectionline').one('span').text(f'{i+3:02d} / TASK REGISTER')
        node.one('.sectionline').all('span')[1].text('POOLED ANALYSIS')
        node.one('.caption').text(f'Tasks {start+1:02d}-{min(start+20,68):02d} of 68, in first-run order. Rewards and costs are per-arm medians over eligible repetitions. N/A means no eligible repetition, not a missing original reward.')
        node.one('tbody').content(''.join(rows[start:start+20]))
        if node.all('.filters'):node.one('input').attrs['placeholder']='Search all 68 tasks';node.one('#matchcount').text('68 tasks shown')
        if node.all('.source'):node.one('.source').content('<strong>Source record / pooled analysis</strong><br>Source experiment IDs: proxy-tb21-bounded; proxy-tb21-repeat-20261020<br>Supporting files: REPORT.md, stats.json, outcomes.json, metrics.json, trials.json, audit.json, run.json, sources.json, both-repetitions-only.json, source-runs/<br>Published data: benchmarks/terminal-bench/results/pennyrouter-tb21-20261019-20261020/. Original trials, rewards and source manifests are unchanged.')
        else:node.all('.caption')[-1].text('Each eligible repetition has both arms marked complete. Per-task values use the median across the one or two eligible repetitions. Tasks with no eligible repetitions are excluded from paired statistics; all 272 original attempt outcomes are retained in supporting data.')
        main.children.append(node)
    for i,footer in enumerate(page.all('footer'),1):
        spans=footer.all('span');spans[0].text('PENNYBENCH / TERMINAL-BENCH');spans[1].text('POOLED ANALYSIS');spans[2].text(f'{i:02d} / 07')
    page.one('script').children=[page.one('script').children[0].replace('of 60 tasks shown','of 68 tasks shown')]
    result=page.render();assert re.findall(r'<style>.*?</style>',result,re.S)==re.findall(r'<style>.*?</style>',source,re.S)
    (HERE/'index.html').write_text(result+'\n')
    print(HERE/"index.html")


if __name__=="__main__":build()
