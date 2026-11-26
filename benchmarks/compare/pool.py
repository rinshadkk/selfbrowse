import json,collections,random,statistics as st,sys
import os
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'results')+'/'
SETS={'qwen3.8':['qwen3.8-baseline','qwen3.8-u5-rerun'],
      'sonnet5.5':['sonnet5.5-all','sonnet5.5-all-run2','sonnet5.5-u5','sonnet5.5-t6x10']}
TASKS=['T1-read-text','T2-search','T3-navigate','T4-cart','T5-login','T6-paginate','T7-live-hn','T8-live-wiki','U1-github','U2-pypi','U3-wikipedia','U4-books','U5-pydocs']
random.seed(1)
out={}
for m,dirs in SETS.items():
    d=collections.defaultdict(list)
    for x in dirs:
        for l in open(R+x+'/runs.jsonl'):
            r=json.loads(l)
            assert r['calls_without_usage']==0
            d[(r['task'],r['lib'])].append(r)
    out[m]=d
    print('\n##',m)
    def stat(lib,key): return {t:st.mean(r[key] for r in d[(t,lib)]) for t in TASKS}
    for lib in ('selfbrowse','browser-use'):
        n=sum(len(d[(t,lib)]) for t in TASKS); p=sum(r['success'] for t in TASKS for r in d[(t,lib)])
        tot=st.mean(stat(lib,'total_tokens').values()); inp=st.mean(stat(lib,'input_tokens').values()); o=st.mean(stat(lib,'out_tokens').values())
        fc=st.mean(stat(lib,'first_call_input').values()); w=st.mean(stat(lib,'wall_seconds').values()); c=st.mean(stat(lib,'model_calls').values())
        print(f"{lib:12} runs {n} pass {p}/{n} calls {c:.1f} in {inp:,.0f} out {o:,.0f} total {tot:,.0f} first {fc:,.0f} wall {w:.0f}")
    print('task            n(sb/bu)  pass sb  pass bu  sb tok   bu tok  ratio')
    for t in TASKS:
        s,b=d[(t,'selfbrowse')],d[(t,'browser-use')]
        sm,bm=st.mean(r['total_tokens'] for r in s),st.mean(r['total_tokens'] for r in b)
        print(f"{t:15} {len(s):>3}/{len(b):<3}  {sum(r['success'] for r in s):>3}/{len(s):<3}  {sum(r['success'] for r in b):>3}/{len(b):<3} {sm:>8,.0f} {bm:>8,.0f} {bm/sm:5.1f}")
    # bootstrap overall ratio and tasks-won
    def ratio(sample):
        sb=st.mean(st.mean(r['total_tokens'] for r in sample[(t,'selfbrowse')]) for t in TASKS)
        bu=st.mean(st.mean(r['total_tokens'] for r in sample[(t,'browser-use')]) for t in TASKS)
        return bu/sb
    base=ratio(d); bs=[]
    for _ in range(2000):
        smp={k:[random.choice(v) for _ in v] for k,v in d.items()}
        bs.append(ratio(smp))
    bs.sort(); print(f"overall ratio {base:.2f}  95% range {bs[50]:.2f}-{bs[1949]:.2f}")
    wins=sum(st.mean(r['total_tokens'] for r in d[(t,'selfbrowse')])<st.mean(r['total_tokens'] for r in d[(t,'browser-use')]) for t in TASKS)
    print('tasks where selfbrowse used fewer tokens:',wins,'/13')
    tws=sum(st.mean(r['wall_seconds'] for r in d[(t,'selfbrowse')])<st.mean(r['wall_seconds'] for r in d[(t,'browser-use')]) for t in TASKS)
    print('tasks where selfbrowse was faster:',tws,'/13')
