"""JupyterLab exam UI loaded by the notebook's small bootstrap cell."""
import ast
import contextlib
import datetime
import html
import io
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import tokenize
import warnings

import ipywidgets as W
from IPython.display import display, Javascript

CATEGORIES = {'python': 'Python 核心与算法', 'pandas': 'Pandas / NumPy 数据处理',
               'ml': '机器学习（Scikit-learn）', 'ops': '系统运维、并发与文件'}
SOURCE_NAME = '人工智能工程技术人员 (初级) 重点知识梳理.ipynb'
SAVE_NAME = '.python_fill_exam_progress_v2.json'

def normal(value):
    """Compare Python token sequences, preserving token boundaries and string contents."""
    value = value.strip()
    try:
        tokens = []
        for t in tokenize.generate_tokens(io.StringIO(value).readline):
            if t.type in (tokenize.ENDMARKER, tokenize.NEWLINE, tokenize.NL, tokenize.ENCODING):
                continue
            text = t.string
            if t.type == tokenize.STRING:
                text = repr(ast.literal_eval(text))
            tokens.append((t.type, text))
        return tokens
    except (SyntaxError, ValueError, tokenize.TokenError, IndentationError):
        return [('literal', value)]

def equivalent(value, expected):
    if not value.strip():
        return False
    if normal(value) == normal(expected):
        return True
    # Parentheses and quote styles may vary without changing a Python expression.
    try:
        return ast.dump(ast.parse(value.strip(), mode='eval')) == ast.dump(ast.parse(expected, mode='eval'))
    except (SyntaxError, ValueError, TypeError):
        return False

def compile_exam_code(code, filename):
    """Compile answer code without leaking Python's callability warnings to the UI."""
    with warnings.catch_warnings():
        warnings.simplefilter('error', SyntaxWarning)
        return compile(code, filename, 'exec')

def marks(question, answers):
    results=[]
    canonical=[b['answers'][0] for b in question['blanks']]
    for i,b in enumerate(question['blanks']):
        valid=any(equivalent(answers[i], a) for a in b['answers'])
        if valid:
            # An equivalent expression must also fit its surrounding source syntax,
            # e.g. nested quote styles in an f-string on the current Python version.
            candidate=list(canonical);candidate[i]=answers[i]
            try:compile_exam_code(filled_code(question,candidate),'<填空语法检查>')
            except (SyntaxError,ValueError,SyntaxWarning):valid=False
        results.append(valid)
    return results

def filled_code(question, answers):
    return re.sub(r'\{\{(\d+)\}\}', lambda m: answers[int(m[1])-1], question['masked'])

def execute_code(code, stdin='', timeout=30, setup=''):
    """Run in the kernel's Python environment, with a fresh temporary working folder."""
    try:
        compile_exam_code(code, '<本题补全代码>')
    except (SyntaxError, ValueError, SyntaxWarning) as e:
        return {'status': 'syntax', 'text': str(e), 'seconds': 0, 'returncode': None}
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='python-fill-exam-') as folder:
        filename = Path(folder)/'answer.py'
        filename.write_text((setup+'\n' if setup else '')+code, encoding='utf-8')
        # The file contains only the original example with the user's fills.
        # Output is spooled to files so a mistaken loop cannot fill notebook RAM.
        with open(Path(folder)/'stdout.capture','w+b') as stdout, open(Path(folder)/'stderr.capture','w+b') as stderr:
            proc = subprocess.Popen([sys.executable, '-u', str(filename)], cwd=folder,
                                    stdin=subprocess.PIPE,stdout=stdout,stderr=stderr)
            timed_out = False
            try:
                proc.communicate(input=stdin.encode('utf-8'),timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                proc.communicate()
            stdout.seek(0); stderr.seek(0)
            out = stdout.read(60001).decode('utf-8',errors='replace')
            err = stderr.read(20001).decode('utf-8',errors='replace')
            text = out[:60000]
            if len(out)>60000: text += '\n[标准输出已截断]'
            if err: text += '\n[标准错误 / 警告]\n'+err[:20000]
            if len(err)>20000: text += '\n[标准错误已截断]'
            if timed_out: text += f'\n[超过 {timeout} 秒，已停止本次运行]'
            return {'status': 'timeout' if timed_out else ('ok' if proc.returncode == 0 else 'error'),
                    'text':text or '（程序没有打印输出）', 'seconds':round(time.monotonic()-start,2),
                    'returncode':proc.returncode}

def kernel_id():
    try:
        from ipykernel.connect import get_connection_file
        return Path(get_connection_file()).stem.removeprefix('kernel-')
    except Exception:
        return ''

def learning_html(q, full=False):
    n=q['learning']
    task=n.get('task') or ('请补全代码，解决本题问题：'+n['overview'])
    text='<div class="exam-task"><b>题目要求：</b>'+h(task)
    if full:
        text+='<b>怎样核对输出</b><p>'+h(n['expected'])+'</p>'
        text+='<b>逐空讲解与易错点</b><ol>'+''.join('<li>空 '+str(i+1)+'：<code>'+h(b['answers'][0])+'</code> — '+h(b['why'])+'</li>' for i,b in enumerate(q['blanks']))+'</ol>'
        text+='<b>再想一步</b><p>'+h(n['transfer'])+'</p>'
        if q['note']:text+='<p style="color:#9a5b11">'+h(q['note'])+'</p>'
        text+='<p>复习建议：说明每个空的作用，再点“重做本题”独立填写；隔天进入错题本复测。</p>'
    return text+'</div>'

def code_comment_html(q):
    """A compact paragraph annotation kept outside executable code."""
    note=q.get('learning', {})
    comment=note.get('code_comment') or (
        '本段代码用于：'+note.get('overview','完成题目要求的处理流程')+'。'
        +'执行顺序：'+note.get('flow','先准备输入，再执行核心处理，最后核对输出。'))
    return ('<details><summary>代码段讲解</summary>'
            '<p style="margin:6px 0;line-height:1.7">'+h(comment)+'</p></details>')


def diagnosis_html(q, answers, result):
    outcomes=marks(q,answers)
    wrong=[str(i+1) for i,ok in enumerate(outcomes) if not ok]
    text='<h4>运行后学习反馈</h4><p>填空判分：'+str(sum(outcomes))+' / '+str(len(outcomes))+' 空正确。'
    text+=('需要复习：空 '+ '、'.join(wrong)+'。' if wrong else '所有填空符合本题要求。')+'</p>'
    if result['status']=='ok' and wrong:text+='<p>程序能运行，但这些填空不符合本题要求；对照下方输出预期，检查实际行为。</p>'
    if result['status']=='syntax':text+='<p>先检查缺少的括号、引号、冒号与缩进，再检查所填代码能否接入原语句。</p>'
    if result['status']=='error':text+='<p>先看报错末行的异常类型，再回到相关行核对对象类型、方法名、键与路径。</p>'
    if result['status']=='timeout':text+='<p>检查循环是否前进或结束，以及网络是否超时；不要仅凭超时认定算法答案错误。</p>'
    return text+learning_html(q,True)

def h(text):
    return html.escape(str(text),quote=True)

def error_hint(q,index,value):
    expected=q['blanks'][index]['answers'][0]
    if not value.strip(): return '此空尚未填写，先结合语句后的编号提示作答。'
    pairs={('idxmin','min'):'本题需要最小值所在行的标签，你填写的是最小数值。',
           ('idxmax','max'):'本题需要最大值所在行的标签，你填写的是最大数值。',
           ('move','copy'):'题目要求改变文件位置；复制后源文件仍存在，请核对操作目的。',
           ('bfill','ffill'):'填充方向相反：此处应使用后面的有效值。',
           ('ffill','bfill'):'填充方向相反：此处应使用前面的有效值。',
           ('loc','iloc'):'此处按标签选取，你填写的方式按整数位置选取。',
           ('fit','predict'):'这一步需要从训练数据学习参数，还没有进入预测步骤。'}
    if (expected,value.strip()) in pairs:return pairs[(expected,value.strip())]
    if value.strip().lower()==expected.lower():return '注意大小写，Python 名称区分大小写。'
    if expected.endswith('()') and value.strip()==expected[:-2]:return '这里需要执行调用，检查是否缺少调用括号。'
    if value.strip()==expected+'()':return '检查周围是否已有括号，或此处是否应读取属性。'
    return '填写内容尚不符合本空要求；核对对象、返回值类型，以及语句后对应空号的提示。'

class FillExam:
    """Study UI. Drafts, immutable submissions and review scheduling are separate."""
    def __init__(self, bank, save_path=None):
        self.bank=bank
        self.by_id={q['id']:q for q in bank}
        configured=os.environ.get('PYTHON_PRACTICAL_EXAM_PROGRESS','').strip()
        self.save_path=Path(save_path) if save_path else Path(configured) if configured else Path(globals().get('ROOT',Path.cwd()))/SAVE_NAME
        self.save_lock=threading.RLock()
        self.storage_warning=''
        self.write_blocked=False
        self.needs_backup=False
        self.data=self.empty_data()
        try:
            if self.save_path.exists():
                loaded=json.loads(self.save_path.read_text(encoding='utf-8'))
                if loaded.get('version') not in (2,3): raise ValueError('未知进度版本')
                for qid,r in loaded['practice'].items():
                    assert qid in self.by_id and len(r['answers'])==len(self.by_id[qid]['blanks'])
                    assert all(isinstance(a,str) for a in r['answers'])
                assert all(qid in self.by_id for qid in loaded['wrong'])
                ex=loaded.get('exam')
                if ex:
                    # The final coverage paper may contain fewer than ten
                    # questions (for example, the final partial batch of a
                    # full question-bank cycle). Older ten-question papers remain
                    # fully compatible.
                    assert 1 <= len(ex['ids']) <= 10
                    assert isinstance(ex['deadline'],(int,float))
                    for qid in ex['ids']:
                        assert qid in self.by_id and len(ex['answers'][qid])==len(self.by_id[qid]['blanks'])
                self.data.update(loaded)
                # Do not let the default empty_data() placeholders hide the
                # absence of these fields in an older V1.0 progress file;
                # the migration code needs that absence to seed the last
                # known daily batch correctly.
                if 'exam_coverage' not in loaded:self.data.pop('exam_coverage',None)
                if 'daily_coverage' not in loaded:self.data.pop('daily_coverage',None)
                if loaded['version']==2:
                    self.needs_backup=True
                    for qid,r in loaded['practice'].items():
                        if r.get('checked') or any(r['answers']):
                            self.data['legacy'].append(qid)
                            # Old checked drafts may already have exposed solutions.
                            r['revealed']=bool(r.get('checked'))
                            r['legacy_assistance_unknown']=True
                    if ex:
                        for qid in ex['ids']:
                            if ex.get('submitted') or any(ex['answers'][qid]):
                                if qid not in self.data['legacy']:self.data['legacy'].append(qid)
                                ex.setdefault('drafts',{}).setdefault(qid,{})['legacy_assistance_unknown']=True
                    for qid in loaded['wrong']:
                        self.data['reviews'][qid]={'state':'待复习','due':self.today(),'dates':[]}
                self.data['version']=3
                self._normalize_exam_coverage()
                daily=self.data.get('daily')
                if daily:
                    assert len(daily['ids'])==len(set(daily['ids']))
                    assert all(x in self.by_id for x in daily['ids'])
        except Exception as e:
            self.storage_warning='进度读取失败，已保护原文件；请从“更多”查看或备份原文件后处理。'+str(e)
            self.write_blocked=True
            self.data=self.empty_data()
        self.mode='exam' if self.exam_active() else 'today'
        daily=self.data.get('daily')
        self.index=daily.get('index',0) if daily and self.mode=='today' else 0
        self.category='all'
        self.practice_order=self.build_practice_order()
        self.review_ids=self.review_order()
        self.running=False
        self.results={}
        self.open_answers=set()
        self.open_more=False
        self.stopped=threading.Event()
        self.root=W.VBox(layout=W.Layout(width='100%'))
        self.root.add_class('exam-root')
        self.storage=W.HTML()
        self.timer=W.HTML()
        self.clear_area=W.VBox()
        # Keep the body container stable across renders. Replacing it on every
        # question change leaves detached widget models in the kernel/browser.
        self.body=W.VBox(layout=W.Layout(width='100%'))
        self.render()
        self.clock_thread=threading.Thread(target=self._clock,daemon=True)
        self.clock_thread.start()

    @staticmethod
    def empty_data():
        return {'version':3,'practice':{},'wrong':[],'exam':None,'history':[],
                'attempts':{},'reviews':{},'daily':None,'legacy':[],
                'exam_coverage':{'cycle':1,'covered_ids':[],'unseen_ids':[],
                                 'completed':False},
                'daily_coverage':{'cycle':1,'covered_ids':[],'unseen_ids':[],
                                  'completed':False,'next_is_first':True}}

    def today(self):
        return datetime.date.today().isoformat()

    def future_day(self,days):
        return (datetime.date.fromisoformat(self.today())+datetime.timedelta(days=days)).isoformat()

    def close(self):
        self.stopped.set()

    @staticmethod
    def _dispose_widgets(widgets, keep=()):
        """Close detached widget trees so repeated renders do not accumulate models."""
        keep_ids={id(w) for w in keep}
        seen=set()
        def dispose(widget):
            if id(widget) in keep_ids or id(widget) in seen:return
            seen.add(id(widget))
            for child in tuple(getattr(widget,'children',()) or ()):
                dispose(child)
            try:
                widget.close()
                # ipywidgets does not expose a public closed flag; retain a
                # lightweight marker for diagnostics and regression checks.
                setattr(widget,'_closed',True)
            except Exception:pass
        for widget in widgets:dispose(widget)

    def exam_active(self):
        return bool(self.data.get('exam') and not self.data['exam'].get('submitted'))

    def save(self):
        if self.write_blocked:
            self.storage.value='<span style="color:#b45309">'+h(self.storage_warning)+'</span>'
            return
        try:
            with self.save_lock:
                if self.needs_backup and self.save_path.exists():
                    backup=self.save_path.with_name(self.save_path.name+'.before-v3.bak')
                    if not backup.exists(): backup.write_bytes(self.save_path.read_bytes())
                    self.needs_backup=False
                temp=self.save_path.with_suffix('.tmp')
                temp.write_text(json.dumps(self.data,ensure_ascii=False),encoding='utf-8')
                temp.replace(self.save_path)
            self.storage.value='<span style="font-size:12px;color:#94a3b8">已保存</span>'
        except OSError as e:
            self.storage.value='<span style="color:#b45309">保存失败：'+h(e)+'</span>'

    def new_record(self,q):
        return {'answers':['']*len(q['blanks']),'checked':False,'revealed':False,
                'completion':False,'draft_id':os.urandom(8).hex(),'submissions':0}

    def record(self,q):
        if self.mode=='exam':
            ex=self.data['exam']
            r=ex.setdefault('drafts',{}).setdefault(q['id'],self.new_record(q))
            for key,value in self.new_record(q).items(): r.setdefault(key,value)
            r['answers']=ex['answers'][q['id']]
            r['checked']=ex['submitted']
            return r
        pool=self.data['daily']['records'] if self.mode=='today' and self.data.get('daily') else self.data['practice']
        r=pool.setdefault(q['id'],self.new_record(q))
        for key,value in self.new_record(q).items(): r.setdefault(key,value)
        return r

    def due_ids(self):
        # 统计只包含仍需复习、且会出现在“错题复习”中的题目。
        return [qid for qid,r in self.data['reviews'].items()
                if r.get('state')!='已掌握' and r.get('due','9999-12-31')<=self.today()]

    def review_order(self):
        return sorted(self.data.get('wrong',[]), key=lambda qid:self.data['reviews'].get(qid,{}).get('due',''))

    def priority(self,q):
        qid=q['id'];review=self.data['reviews'].get(qid)
        if review and review.get('state')!='已掌握' and review.get('due','9999-12-31')<=self.today(): return 0
        if not self.data['attempts'].get(qid) and qid not in self.data['legacy']: return 1
        if review and review['state']!='已掌握': return 2
        return 3

    def interleave(self,questions):
        remaining=list(questions);random.shuffle(remaining);out=[]
        while remaining:
            last=out[-1] if out else None
            different=[q for q in remaining if not last or q['category']!=last['category']]
            pool=different or remaining
            counts={c:sum(q['category']==c for q in remaining) for c in CATEGORIES}
            # Consume a dominant module early enough to avoid a long same-module tail.
            peak=max(counts.values())
            if peak >= (len(remaining)+1)//2:
                dominant=[q for q in pool if counts[q['category']]==peak]
                if dominant: pool=dominant
            fresh=[q for q in pool if not last or not set(q['topics'])&set(last['topics'])]
            if fresh: pool=fresh
            chosen=random.choice(pool);out.append(chosen);remaining.remove(chosen)
        return [q['id'] for q in out]

    def build_practice_order(self):
        return self.interleave(self.bank)

    def _normalized_exam_coverage(self, raw):
        """Return a repaired coverage state without changing persistent data."""
        all_ids=[q['id'] for q in self.bank]
        if not isinstance(raw,dict): raw={}
        try: cycle=max(1,int(raw.get('cycle',1)))
        except (TypeError,ValueError): cycle=1
        covered=[]
        for qid in raw.get('covered_ids',[]):
            if qid in self.by_id and qid not in covered: covered.append(qid)
        unseen=[qid for qid in raw.get('unseen_ids',[]) if qid in self.by_id and qid not in covered]
        # Missing/empty pool in a legacy file means no mock papers have been
        # consumed yet. Once a cycle has begun, derive the complement so a
        # hand-edited or partially written file cannot reintroduce duplicates.
        if not raw or ('covered_ids' not in raw and 'unseen_ids' not in raw):
            covered=[];unseen=list(all_ids)
        else:
            known=set(covered)|set(unseen)
            unseen.extend(qid for qid in all_ids if qid not in known)
        completed=bool(raw.get('completed',False)) and not unseen
        return {'cycle':cycle,'covered_ids':covered,'unseen_ids':unseen,
                'completed':completed}

    def _normalize_exam_coverage(self):
        """Migrate or repair the persistent cross-exam question pool.

        Coverage is deliberately separate from practice attempts: a question
        can be practiced many times without being consumed by the mock-exam
        cycle. Old V1.0 progress files did not have this field, so they start
        a fresh mock-exam coverage cycle without losing any study records.
        """
        self.data['exam_coverage']=self._normalized_exam_coverage(
            self.data.get('exam_coverage'))

    def _exam_coverage_state(self):
        self._normalize_exam_coverage()
        state=self.data['exam_coverage']
        # A completed cycle is reset only when the learner starts the next
                    # paper; this leaves the full-bank completion status visible on the setup
        # screen after the final paper is submitted.
        if not state['unseen_ids'] and state['covered_ids']:
            state['completed']=True
        return state

    def _exam_coverage_view(self):
        """Read coverage for the UI without materializing a new pool."""
        state=self._normalized_exam_coverage(self.data.get('exam_coverage'))
        if not state['unseen_ids'] and state['covered_ids']:
            state['completed']=True
        return state

    def _select_exam_ids(self, available, limit=10):
        """Select unseen questions while retaining an exam-like module mix.

        The first paper keeps the original 3/3/2/2 allocation. Later papers
        use the same proportions as a target, but redistribute a slot whenever
        a module has fewer remaining questions. Because selection is from the
        unseen pool only, the cycle always reaches complete coverage.
        """
        available=list(dict.fromkeys(available))
        if not available:return []
        take=min(limit,len(available))
        base={'python':3,'pandas':3,'ml':2,'ops':2}
        counts={cat:sum(self.by_id[qid]['category']==cat for qid in available)
                for cat in CATEGORIES}
        quotas={cat:min(base[cat],counts[cat]) for cat in CATEGORIES}
        remaining=take-sum(quotas.values())
        # Redistribute slots left by exhausted modules according to the
        # remaining pool, with a stable random tie-break for variety.
        while remaining>0:
            candidates=[cat for cat in CATEGORIES if quotas[cat]<counts[cat]]
            if not candidates:break
            random.shuffle(candidates)
            chosen=max(candidates,key=lambda cat:(counts[cat]-quotas[cat],random.random()))
            quotas[chosen]+=1;remaining-=1
        selected=[]
        for cat in CATEGORIES:
            pool=[qid for qid in available if self.by_id[qid]['category']==cat]
            random.shuffle(pool);selected.extend(pool[:quotas[cat]])
        return self.interleave([self.by_id[qid] for qid in selected])

    def _normalized_daily_coverage(self, raw):
        """Return the persistent 15-question daily coverage state."""
        all_ids=[q['id'] for q in self.bank]
        if not isinstance(raw,dict): raw={}
        try: cycle=max(1,int(raw.get('cycle',1)))
        except (TypeError,ValueError): cycle=1
        covered=[]
        for qid in raw.get('covered_ids',[]):
            if qid in self.by_id and qid not in covered: covered.append(qid)
        unseen=[qid for qid in raw.get('unseen_ids',[]) if qid in self.by_id and qid not in covered]
        # V1.0 files have no daily coverage pool. Count the last known daily
        # batch as already shown so the first new batch does not immediately
        # repeat it, while leaving all older practice records untouched.
        if not raw or ('covered_ids' not in raw and 'unseen_ids' not in raw):
            legacy_daily=self.data.get('daily') or {}
            covered=[qid for qid in legacy_daily.get('ids',[]) if qid in self.by_id]
            unseen=[qid for qid in all_ids if qid not in covered]
        else:
            known=set(covered)|set(unseen)
            unseen.extend(qid for qid in all_ids if qid not in known)
        completed=bool(raw.get('completed',False)) and not unseen
        first_default=True if (not raw or ('covered_ids' not in raw and 'unseen_ids' not in raw)) else not covered
        next_is_first=bool(raw.get('next_is_first',first_default))
        return {'cycle':cycle,'covered_ids':covered,'unseen_ids':unseen,
                'completed':completed,'next_is_first':next_is_first}

    def _normalize_daily_coverage(self):
        self.data['daily_coverage']=self._normalized_daily_coverage(
            self.data.get('daily_coverage'))

    def _daily_coverage_state(self):
        self._normalize_daily_coverage()
        state=self.data['daily_coverage']
        if not state['unseen_ids'] and state['covered_ids']:
            state['completed']=True
        return state

    def _daily_coverage_view(self):
        state=self._normalized_daily_coverage(self.data.get('daily_coverage'))
        if not state['unseen_ids'] and state['covered_ids']:
            state['completed']=True
        return state

    def archive_daily_drafts(self, daily):
        """Keep unfinished daily drafts available in专项练习 when a day rolls over."""
        for qid, old_record in (daily or {}).get('records', {}).items():
            q=self.by_id.get(qid)
            if not q or not any(old_record.get('answers', [])): continue
            record=self.data['practice'].setdefault(qid,self.new_record(q))
            # Never overwrite an existing专项草稿; it may contain a newer edit.
            if any(record.get('answers', [])): continue
            record['answers']=list(old_record.get('answers', []))
            record['checked']=bool(old_record.get('checked'))
            record['revealed']=bool(old_record.get('revealed'))
            record['completion']=bool(old_record.get('completion'))
            record['draft_id']=old_record.get('draft_id',record['draft_id'])
            record['submissions']=old_record.get('submissions',0)
            if old_record.get('last_signature'):
                record['last_signature']=old_record['last_signature']

    def start_daily(self):
        if self.running or self.exam_active(): return
        old=self.data.get('daily')
        if old and old.get('date')==self.today() and len(old['done'])<len(old['ids']):
            self.index=old.get('index',0);self.render();return
        if old and old.get('date')!=self.today():
            self.archive_daily_drafts(old)
        state=self._daily_coverage_state()
        if state['completed']:
            state['cycle']+=1;state['covered_ids']=[]
            state['unseen_ids']=[q['id'] for q in self.bank]
            state['completed']=False;state['next_is_first']=True
        # A batch consumes at most 15 unseen questions. Once fewer than 15
        # remain, keep all of them and supplement the batch with wrong-bank
        # questions so the learner still has a full daily study session.
        available=list(state['unseen_ids'])
        take=min(15,len(available))
        first_batch=bool(state.get('next_is_first',not state['covered_ids']))
        if first_batch:
            quotas={'python':5,'pandas':5,'ml':2,'ops':3}
            due=set(self.due_ids())
            ids=[]
            for cat,count in quotas.items():
                pool=[qid for qid in available if self.by_id[qid]['category']==cat]
                random.shuffle(pool);pool.sort(key=lambda qid: qid not in due)
                ids.extend(pool[:min(count,len(pool))])
            if len(ids)<take:
                rest=[qid for qid in available if qid not in ids]
                ids.extend(self._select_exam_ids(rest,take-len(ids)))
        else:
            # Preserve the earlier learning rule: questions already due for
            # spaced review are placed into later unseen batches first.
            due=[qid for qid in self.due_ids() if qid in available]
            ids=due[:take]
            if len(ids)<take:
                rest=[qid for qid in available if qid not in ids]
                ids.extend(self._select_exam_ids(rest,take-len(ids)))
        state['next_is_first']=False
        ids=self.interleave([self.by_id[qid] for qid in ids])
        state['unseen_ids']=[qid for qid in state['unseen_ids'] if qid not in ids]
        state['covered_ids'].extend(qid for qid in ids if qid not in state['covered_ids'])
        state['completed']=not state['unseen_ids']
        supplement_ids=[]
        if len(ids)<15:
            needed=15-len(ids)
            wrong_pool=[qid for qid in self.review_order() if qid not in ids]
            supplement_ids=wrong_pool[:needed]
            if len(supplement_ids)<needed:
                fallback=[qid for qid in state['covered_ids']
                          if qid not in ids and qid not in supplement_ids]
                random.shuffle(fallback);supplement_ids.extend(fallback[:needed-len(supplement_ids)])
            ids=self.interleave([self.by_id[qid] for qid in ids+supplement_ids])
        self.data['daily']={'date':self.today(),'ids':ids,'index':0,'done':[],
                            'records':{qid:self.new_record(self.by_id[qid]) for qid in ids},
                            'coverage_cycle':state['cycle'],'coverage_after':len(state['covered_ids']),
                            'supplement_ids':supplement_ids}
        self.index=0;self.save();self.render()

    def ids(self):
        if self.mode=='today': return (self.data.get('daily') or {}).get('ids',[])
        if self.mode=='exam': return (self.data.get('exam') or {}).get('ids',[])
        if self.mode=='wrong': return self.review_ids
        return [x for x in self.practice_order if self.category=='all' or self.by_id[x]['category']==self.category]

    def switch(self,change):
        if self.running or self.exam_active(): return
        self.mode=change['new'];self.index=0
        if self.mode=='today': self.index=(self.data.get('daily') or {}).get('index',0)
        if self.mode=='wrong': self.review_ids=self.review_order()
        self.render()

    def button(self,label,callback,primary=False,disabled=False):
        b=W.Button(description=label,button_style='primary' if primary else '',disabled=disabled,
                   layout=W.Layout(width='auto',min_width='86px',height='34px'))
        b.on_click(callback);return b

    def first_stats(self):
        first=[v[0] for qid,v in self.data['attempts'].items() if v and qid not in self.data['legacy']]
        return sum(sum(x['marks']) for x in first),sum(len(x['marks']) for x in first)

    def independent_stats(self):
        """Score the first submission made without answer reveal or Tab.

        This is a separate learning signal from the existing first-attempt
        score. Questions without such a submission are reported separately,
        so a high percentage cannot hide missing independent evidence.
        """
        independent=[]
        for qid,sequence in self.data['attempts'].items():
            if qid in self.data['legacy']:continue
            attempt=next((a for a in sequence
                          if not a.get('revealed') and not a.get('completion')
                          and not a.get('assistance_unknown')),None)
            if attempt:independent.append(attempt)
        return (sum(sum(x['marks']) for x in independent),
                sum(len(x['marks']) for x in independent),len(independent))

    def daily_stats(self):
        today=self.today()
        today_attempts=[a for sequence in self.data['attempts'].values()
                        for a in sequence if a.get('day')==today]
        today_wrong={qid for qid,sequence in self.data['attempts'].items()
                     if any(a.get('day')==today and not all(a.get('marks',[]))
                            for a in sequence)}
        daily=self.data.get('daily') or {}
        if daily.get('date')==today:
            done=len(daily.get('done',[]));total=len(daily.get('ids',[]))
        else:done=total=0
        state=self._daily_coverage_view()
        return {'attempts':len(today_attempts),'wrong':len(today_wrong),
                'done':done,'total':total,'covered':len(state['covered_ids'])}

    def seen(self,qid):
        return bool(self.data['attempts'].get(qid)) or qid in self.data['legacy']

    def stats_html(self):
        correct,total=self.first_stats()
        accuracy=f'{100*correct/total:.0f}%' if total else '暂无数据'
        independent_correct,independent_total,independent_questions=self.independent_stats()
        independent_accuracy=(f'{100*independent_correct/independent_total:.0f}%'
                              if independent_total else '暂无数据')
        daily=self.daily_stats();seen=sum(self.seen(q['id']) for q in self.bank)
        review_total=sum(r.get('state')!='已掌握' for r in self.data['reviews'].values())
        mastered=sum(r.get('state')=='已掌握' for r in self.data['reviews'].values())
        independent_note=(f'{independent_accuracy}（{independent_questions}/{len(self.bank)}题有记录）'
                          if independent_questions else '暂无独立记录')
        return ('<div class="exam-stats"><b>今日</b> '
                f'完成 {daily["done"]}/{daily["total"]} 题 · 提交 {daily["attempts"]} 次 · '
                f'错题 {daily["wrong"]} 题 · 到期复测 {len(self.due_ids())} 题 · '
                f'覆盖 {daily["covered"]}/{len(self.bank)}</div>'
                '<div class="exam-stats"><b>累计</b> '
                f'已练 {seen}/{len(self.bank)} 题 · 首次正确率 {accuracy} · '
                f'独立答题率 {independent_note} · 待复习/巩固 {review_total} 题 · '
                f'已掌握 {mastered} 题</div>')

    def high_error_html(self,q,threshold=5):
        """Explain recurring wrong blanks without exposing the answer."""
        sequence=self.data['attempts'].get(q['id'],[])
        total_errors=sum(len(a.get('marks',[]))-sum(a.get('marks',[])) for a in sequence)
        if total_errors<threshold:return ''
        blank_errors=[]
        for i,b in enumerate(q['blanks']):
            count=sum(1 for a in sequence
                      if i<len(a.get('marks',[])) and not a['marks'][i])
            if count:blank_errors.append((count,i,b))
        blank_errors.sort(key=lambda x:(-x[0],x[1]))
        focus='、'.join('空'+str(i+1) for _,i,_ in blank_errors[:4])
        intro=(f'本题累计有 {total_errors} 次填空错误，错误主要集中在 {focus}。'
               '建议先用自己的话说明这些空在整段程序中的作用，再重新填写；不要只记住关键词。')
        items=[]
        for count,i,b in blank_errors[:4]:
            hint=b.get('hint','结合语句后的提示判断其作用。')
            why=b.get('why','先确认输入、处理过程和返回值之间的关系。')
            hint=str(hint).rstrip('。；，, ');why=str(why).rstrip('。；，, ')
            items.append(f'<li><b>空 {i+1}</b>（累计错 {count} 次）：{h(hint)}。{h(why)}。</li>')
        return ('<details><summary>高频错误段落讲解</summary>'
                '<p style="margin:6px 0;line-height:1.7">'+h(intro)+'</p>'
                '<ul style="margin:4px 0 6px">'+''.join(items)+'</ul></details>')

    def toggle_more(self,_=None):
        self.open_more=not self.open_more
        if self.open_more:self.more.children=(self.coverage(),)+self.more.children[1:]
        self.more.layout.display='flex' if self.open_more else 'none'

    def ask_clear(self,_=None):
        if self.running or self.exam_active(): return
        self.clear_area.children=(W.HTML('<p>清空所有练习、复测、今日任务和模拟成绩？此操作无法撤销。</p>'),
            W.HBox([self.button('确认清空',lambda _:self.clear_records()),
                    self.button('取消',lambda _:setattr(self.clear_area,'children',()))]))

    def ask_new_practice(self,_=None):
        if self.running or self.exam_active(): return
        self.clear_area.children=(W.HTML('<p>开始新一轮专项练习？只清空专项练习草稿，保留历史提交、错题和复测记录。</p>'),
            W.HBox([self.button('确认新一轮',lambda _:self.reset_practice_drafts()),
                    self.button('取消',lambda _:setattr(self.clear_area,'children',()))]))

    def reset_practice_drafts(self):
        if self.running or self.exam_active(): return
        for qid,record in self.data['practice'].items():
            q=self.by_id.get(qid)
            if not q: continue
            fresh=self.new_record(q)
            record.clear();record.update(fresh)
        self.results.clear();self.open_answers.clear();self.index=0
        self.practice_order=self.build_practice_order();self.clear_area.children=()
        self.save();self.render()

    def clear_records(self):
        if self.running or self.exam_active(): return
        try:
            if self.save_path.exists(): self.save_path.unlink()
        except OSError as e:
            self.storage.value=h(e);return
        self.data=self.empty_data();self.write_blocked=False;self.needs_backup=False
        self.mode='today';self.index=0;self.category='all';self.review_ids=[]
        self.results.clear();self.open_answers.clear();self.clear_area.children=()
        self.practice_order=self.build_practice_order();self.render()
        self.storage.value='答题记录已清空。'

    def render(self):
        # Remove detached widget models before rebuilding the current question.
        # Keeping the persistent body/storage/timer/clear area avoids disrupting
        # state while releasing old buttons, text fields, and code rows.
        old_root_children=tuple(self.root.children)
        old_body_children=tuple(self.body.children)
        self.root.children=()
        self.body.children=()
        self._dispose_widgets(old_root_children,keep=(self.body,self.storage,self.timer,self.clear_area))
        self._dispose_widgets(old_body_children)
        active=self.exam_active()
        style=W.HTML('''<style>
.exam-root{max-width:1180px;margin:0 auto;color:#243449}
.exam-root .widget-hbox{gap:8px}
.exam-root h2{font-size:23px;margin:8px 0}.exam-root h3{font-size:18px;margin:10px 0}
.exam-stats{color:#64748b;font-size:13px;margin:10px 0}.exam-task{line-height:1.75;font-size:14px;margin:8px 0 12px}
.exam-line:focus-within{background:#eff6ff;border-radius:4px}
.exam-complete input:focus{outline:2px solid #60a5fa!important;outline-offset:1px}
.exam-root details{margin:8px 0;font-size:13px}.exam-root summary{cursor:pointer;color:#52657b}
.exam-root pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.6}
.exam-hint{color:#46825b;white-space:normal;font:13px/1.6 monospace;overflow-wrap:anywhere}
.exam-hint-inline{display:inline-block;margin-left:12px;max-width:620px;min-width:180px;vertical-align:middle}
.exam-comment{color:#4f8068;font:13px/30px ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;display:block;padding:1px 0}
.exam-code-row{max-width:100%;box-sizing:border-box;overflow:visible}
.exam-code-row .widget-html{min-width:0;max-width:100%;box-sizing:border-box}
.exam-feedback-meta{display:flex;flex-flow:row wrap;align-items:center;gap:6px 10px;font-size:13px;margin:6px 0}
</style>''')
        title=W.HTML('<h2>人工智能平台产品实现（初级）· 实操代码填空</h2>')
        more_button=self.button('更多 ⋯',self.toggle_more,disabled=active or self.running)
        header=W.HBox([title,more_button],layout=W.Layout(justify_content='space-between',align_items='center'))
        self.tabs=W.ToggleButtons(options=[('今日练习','today'),('专项练习','practice'),('模拟考试','exam'),('错题复习','wrong')],
                                  value=self.mode,disabled=active or self.running)
        self.tabs.observe(self.switch,names='value')
        clear=self.button('清空记录',self.ask_clear,disabled=active or self.running)
        new_round=self.button('开始新一轮专项练习',self.ask_new_practice,disabled=active or self.running)
        self.more=W.VBox([self.coverage(),new_round,clear,self.clear_area],layout=W.Layout(display='flex' if self.open_more else 'none'))
        self.stats=W.HTML(self.stats_html())
        heads=[style,header,self.tabs,self.timer]+([] if active else [self.stats])+[self.more]
        if self.storage_warning: heads.append(W.HTML(h(self.storage_warning)))
        self.root.children=tuple(heads+[self.body,self.storage])
        daily=self.data.get('daily')
        if self.mode=='today' and daily and daily.get('date')!=self.today():
            self.body.children=(W.HTML('<h3>新的一天</h3><p>上一组练习日期为 '+h(daily.get('date',''))+'，可以开始今天的新题组。未完成草稿会保留到专项练习。</p>'),
                                self.button('开始今日练习',lambda _:self.start_daily(),primary=True))
            self._update_timer();return
        if self.mode=='today' and not daily:
            state=self._daily_coverage_view()
            text=(f'<h3>今日练习</h3><p>每组 15 题；每轮首场为 Python 5、Pandas 5、机器学习 2、运维 3，后续场次只抽取未覆盖题目并按剩余题量动态调整。本轮已覆盖 '
                  f'{len(state["covered_ids"])}/{len(self.bank)} 题，剩余 {len(state["unseen_ids"])} 题。最后一组不足 15 题时，优先从错误题库补足。</p>')
            self.body.children=(W.HTML(text),
                                self.button('开始今日练习',lambda _:self.start_daily(),primary=True))
            self._update_timer();return
        if self.mode=='exam' and not self.data.get('exam'):
            self.setup_exam();self._update_timer();return
        ids=self.ids()
        if not ids:
            self.body.children=(W.HTML('<p>暂无待复习错题，可以先完成今日练习。</p>'),)
            self._update_timer();return
        self.index=max(0,min(self.index,len(ids)-1))
        q=self.by_id[ids[self.index]];r=self.record(q)
        self.current_q=q
        controls=[]
        if self.mode=='practice':
            category=W.Dropdown(options=[('全部模块','all')]+[(v,k) for k,v in CATEGORIES.items()],value=self.category,
                                layout=W.Layout(width='225px'),disabled=self.running)
            def change_category(c):
                if self.running:return
                self.category=c['new'];self.index=0;self.render()
            category.observe(change_category,names='value');controls.append(category)
        self.picker=W.Dropdown(options=[(f'{i+1:02d}  {self.by_id[x]["title"]}',i) for i,x in enumerate(ids)],value=self.index,
                               layout=W.Layout(width='min(480px,100%)'),disabled=self.running)
        def change_question(c):
            if self.running:return
            self.index=c['new'];self.persist_position();self.render()
        self.picker.observe(change_question,names='value');controls.append(self.picker)
        pieces=[W.HBox(controls,layout=W.Layout(flex_flow='row wrap'))]
        if self.mode=='today':
            daily=self.data['daily'];n=len(daily['done'])
            supplement=len(daily.get('supplement_ids',[]))
            batch_note=(f' · 本组含 {supplement} 题错题补充' if supplement else '')
            if n==len(ids):
                pieces.extend([W.HTML(f'<p>本组已完成 {n}/{len(ids)} 题{batch_note}；错题将按复测计划再次安排。</p>'),
                               self.button('开始下一组',lambda _:self.start_daily())])
            else: pieces.append(W.HTML(f'<small>本组已完成 {n}/{len(ids)} 题{batch_note} · 自动保存，可退出续练</small>'))
        if self.mode=='exam' and r['checked']:
            pieces.extend([self.exam_summary(),self.button('重新抽卷',lambda _:self.new_exam())])
        origin={'source':'题库练习','supplement':'补充练习'}.get(q['origin'],'')
        title=q['title'].replace('补充 · ','')
        pieces.append(W.HTML(f'<h3>第 {self.index+1} / {len(ids)} 题　'+h(title)+f'</h3><small style="color:#64748b">{h(origin)} · {len(q["blanks"])} 个空</small>'))
        pieces.append(W.HTML(learning_html(q)))
        if not active:
            pieces.append(W.HTML(code_comment_html(q)))
            focus_html=self.high_error_html(q)
            if focus_html:pieces.append(W.HTML(focus_html))
        if self.mode=='wrong':
            review=self.data['reviews'].get(q['id'],{})
            pieces.append(W.HTML('<small>'+h(review.get('state','待复习'))+' · 下次复测 '+h(review.get('due',self.today()))+'；点击“再试一次”开始新的独立填写。</small>'))
        completion=not active or self.data['exam'].get('completion',False)
        pieces.append(W.HTML('<div class="exam-context" data-kernel="'+h(kernel_id())+'" data-completion="'+str(completion).lower()+'" data-code="'+h(q['masked'])+'"></div>'))
        assistance=W.Checkbox(value=bool(r.get('completion')),layout=W.Layout(display='none'))
        assistance.add_class('exam-assistance')
        def mark_assistance(c):
            if c['new']:
                self.record(q)['completion']=True;self.save()
        assistance.observe(mark_assistance,names='value');pieces.append(assistance)
        self.fields=[];lines=[];answers=r['answers']
        # 今日练习和模拟考试保持原版紧凑代码；专项练习/错题复习才显示
        # 参考 Notebook 的逐条学习注释，避免正式练习时题目代码过长。
        show_learning_comments=self.mode not in ('today','exam')
        outcomes=marks(q,answers) if r['checked'] else []
        locked=(self.mode=='exam' and r['checked']) or self.running
        for line in q['lines']:
            # 学习性段落注释只存在于显示层，不进入 masked/original，因而不会改变填空判分。
            if line.get('comment'):
                if not show_learning_comments:
                    continue
                row=W.HTML('<span class="exam-comment">'+h(line['text'])+'</span>',
                           layout=W.Layout(width='100%',min_width='0'))
                row.add_class('exam-line');lines.append(row);continue
            nums=[int(n) for n in re.findall(r'\{\{(\d+)\}\}',line['text'])]
            # 没有填空的普通代码行只需一个 HTML 控件，减少嵌套 HBox/VBox，
            # 避免长题首次打开时向前端发送过多 widget 通信。
            if not nums:
                row=W.HTML(
                    '<span style="color:#94a3b8;font:12px monospace;width:27px;display:inline-block">'+str(line['line'])+'</span>'
                    '<span style="white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font:14px/30px ui-monospace,monospace">'+h(line['text'])+'</span>',
                    layout=W.Layout(width='100%',min_width='0'))
                row.add_class('exam-line');lines.append(row);continue
            parts=[W.HTML('<span style="color:#94a3b8;font:12px monospace;width:27px;display:inline-block">'+str(line['line'])+'</span>')]
            for chunk in re.split(r'(\{\{\d+\}\})',line['text']):
                match=re.fullmatch(r'\{\{(\d+)\}\}',chunk)
                if match:
                    i=int(match[1])-1
                    width=min(520,max(145,68+8*len(q['blanks'][i]['answers'][0])))
                    field=W.Text(value=answers[i],description=f'空{i+1}',placeholder='填写代码',disabled=locked,
                                 style={'description_width':'28px'},layout=W.Layout(width=f'{width}px',height='30px',margin='0 3px',flex='0 0 auto'))
                    field.add_class('exam-complete');field.add_class('exam-blank-'+str(i+1))
                    if outcomes:field.layout.border='1px solid '+('#16a34a' if outcomes[i] else '#dc2626')
                    def update(c,index=i,question=q):
                        if self.exam_active() and time.time()>=self.data['exam']['deadline']:
                            self.submit_exam(auto=True);return
                        rec=self.record(question);rec['answers'][index]=c['new'];rec['checked']=False
                        c['owner'].layout.border='1px solid #dbe3ef'
                        field_key=self.result_key(question)
                        self.results.pop(field_key,None)
                        self.feedback.children=()
                        self.save()
                    field.observe(update,names='value');self.fields.append((i,field));parts.append(field)
                elif chunk:
                    parts.append(W.HTML('<span style="white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;font:14px/30px ui-monospace,monospace">'+h(chunk)+'</span>',
                                        layout=W.Layout(min_width='0',max_width='100%',flex='0 1 auto')))
            code_line=W.HBox(parts,layout=W.Layout(flex_flow='row wrap',align_items='center',width='100%',max_width='100%',min_width='0'))
            code_line.add_class('exam-code-row')
            comment='# '+'；'.join('空 '+str(n)+'：'+q['blanks'][n-1]['hint'] for n in nums)
            # 将提示放在同一代码行的末尾，明确对应本行语句中的填空。
            parts.append(W.HTML('<span class="exam-hint exam-hint-inline">'+h(comment)+'</span>',
                                layout=W.Layout(min_width='180px',max_width='100%',flex='1 1 300px')))
            code_line=W.HBox(parts,layout=W.Layout(flex_flow='row wrap',align_items='center',width='100%',max_width='100%',min_width='0'))
            code_line.add_class('exam-code-row');code_line.add_class('exam-line');lines.append(code_line)
        # 题目代码和学习注释均完整展开，避免代码后半段被固定高度裁剪。
        # 页面只保留 Notebook 自身的整体滚动，不在题目代码区制造嵌套滚动条。
        full_display=True
        code=W.VBox(lines,layout=W.Layout(
            width='100%', overflow='visible' if full_display else 'hidden',
            border='1px solid #dbe3ef', padding='12px',
            max_height=None if full_display else ('760px' if len(lines)>28 else None)))
        instruction='输入前缀后按 Tab 请求原生内核候选；↑↓ 选择，Tab / Enter 确认。空白时 Tab 跳到下一空。' if completion else '本卷关闭补全；Tab 跳到下一空。'
        pieces.append(W.HTML('<span title="'+h(instruction)+'" style="font-size:12px;color:#64748b">ⓘ '+('Tab 补全' if completion else '独立模拟')+'</span>'))
        pieces.append(code)
        if q.get('stdin'):
            self.stdin=W.Textarea(value=r.get('stdin',q['stdin']),description='程序输入',layout=W.Layout(width='100%',height='64px'))
            self.stdin.observe(lambda c:(r.update(stdin=c['new']),self.save()),names='value');pieces.append(self.stdin)
        else:self.stdin=None
        self.check_button=self.button('检查答案',lambda _:self.check(q),primary=True,disabled=self.running)
        self.run_button=self.button('▶ 运行程序',lambda _:self.run(q),disabled=self.running)
        actions=[self.button('上一题',lambda _:self.navigate(-1),disabled=self.index==0 or self.running)]
        if not active: actions.append(self.check_button)
        actions.append(self.run_button)
        actions.append(self.button('下一题',lambda _:self.navigate(1),disabled=self.index==len(ids)-1 or self.running))
        if active:actions.append(self.button('交卷',lambda _:self.confirm_submit(),primary=True,disabled=self.running))
        self.actions=actions
        pieces.append(W.HBox(actions,layout=W.Layout(flex_flow='row wrap',margin='10px 0')))
        self.confirm_area=W.VBox();pieces.append(self.confirm_area)
        self.feedback=W.VBox();self.feedback.add_class('exam-feedback');pieces.append(self.feedback)
        self.runtime=W.HTML() # Compatibility: all visible output lives inside self.feedback.
        self.body.children=tuple(pieces)
        if not self.running and (r['checked'] or self.result_key(q) in self.results):self.show_feedback(q,marks(q,answers))
        self._update_timer()

    def result_key(self,q):
        return (self.mode,q['id'])

    def persist_position(self):
        if self.mode=='today' and self.data.get('daily'):
            self.data['daily']['index']=self.index;self.save()

    def navigate(self,delta):
        if self.running:return
        self.index=max(0,min(self.index+delta,len(self.ids())-1));self.persist_position();self.render()

    def reset_question(self,q):
        if self.running or self.mode=='exam':return
        if self.mode=='today':pool=self.data['daily']['records']
        else:pool=self.data['practice']
        pool[q['id']]=self.new_record(q)
        self.results.pop(self.result_key(q),None);self.open_answers.discard(self.result_key(q))
        self.save();self.render()

    def submit_attempt(self,q,r,mode=None):
        """Append once per changed answer set; no duplicate credit for check + run."""
        mode=mode or self.mode
        outcomes=marks(q,r['answers'])
        signature=json.dumps([r['answers'],r.get('revealed',False),r.get('completion',False)],ensure_ascii=False)
        if signature==r.get('last_signature'):
            r['checked']=True
            return outcomes
        r.setdefault('draft_id',os.urandom(8).hex())
        count=r.get('submissions',0)
        attempt={'at':time.time(),'day':self.today(),'answers':list(r['answers']),'marks':outcomes,
                 'revealed':bool(r.get('revealed')),'completion':bool(r.get('completion')),
                 'assistance_unknown':bool(r.get('legacy_assistance_unknown')),
                 'independent':not r.get('revealed') and not count and not r.get('legacy_assistance_unknown'),
                 'draft_id':r['draft_id'],'mode':mode}
        self.data['attempts'].setdefault(q['id'],[]).append(attempt)
        r['last_signature']=signature;r['submissions']=count+1
        review=self.data['reviews'].setdefault(q['id'],{'state':'待复习','due':self.today(),'dates':[]})
        if all(outcomes) and attempt['independent']:
            if self.today() not in review['dates']:review['dates'].append(self.today())
            review['state']='已掌握' if len(review['dates'])>=2 else '待巩固'
            review['due']=self.future_day(3 if review['state']=='已掌握' else 1)
        elif not all(outcomes):
            review.update(state='待复习',due=self.future_day(1),dates=[])
        elif not review['dates']:
            # Reading feedback after an independent success must not erase
            # already-earned review credit. Assisted corrections add no credit.
            review.update(state='待复习',due=self.future_day(1))
        if review['state']=='已掌握':
            if q['id'] in self.data['wrong']:self.data['wrong'].remove(q['id'])
        elif q['id'] not in self.data['wrong']:self.data['wrong'].append(q['id'])
        # 状态变化后立即刷新当前错题列表，避免已掌握题继续停留在页面中。
        self.review_ids=self.review_order()
        if mode=='today' and q['id'] not in self.data['daily']['done']:
            self.data['daily']['done'].append(q['id'])
        r['checked']=True
        return outcomes

    def check(self,q):
        if self.running or self.exam_active():return
        if self.mode=='exam': self.show_feedback(q,marks(q,self.record(q)['answers']));return
        r=self.record(q);self.submit_attempt(q,r);r['checked']=True
        self.save();self.render()

    def add_review(self,q):
        if self.exam_active():return
        # 手动加入复习不抹掉已有的独立正确日期，避免误操作清空学习进度。
        review=self.data['reviews'].setdefault(q['id'],{'state':'待复习','due':self.today(),'dates':[]})
        review['state']='待复习';review['due']=self.today();review.setdefault('dates',[])
        if q['id'] not in self.data['wrong']:self.data['wrong'].append(q['id'])
        self.review_ids=self.review_order()
        self.save();self.stats.value=self.stats_html()

    def reveal(self,q):
        if self.exam_active():return
        r=self.record(q);r['revealed']=True
        self.open_answers.add(self.result_key(q))
        if self.mode!='exam' and q['id'] not in self.data['reviews']:
            self.data['reviews'][q['id']]={'state':'待复习','due':self.future_day(1),'dates':[]}
            if q['id'] not in self.data['wrong']:self.data['wrong'].append(q['id'])
        self.save();self.show_feedback(q,marks(q,r['answers']))

    def show_feedback(self,q,outcomes):
        r=self.record(q);active=self.exam_active();result=self.results.get(self.result_key(q))
        text='<b>本题反馈</b>'
        meta=[]
        key_error='';run_warning='';wrong_html=''
        if not active:
            score=sum(outcomes);total=len(outcomes)
            score_color='#15803d' if score==total else '#b91c1c'
            meta.append(f'<span style="color:{score_color};font-weight:600">本次：{score} / {total} 空正确</span>')
        if result:
            if result['status']!='ok':
                tail=next((line for line in reversed(result['text'].splitlines()) if line.strip()),'')
                key_error='<p style="color:#b91c1c">关键错误：'+h(tail)+'</p>'
            labels={'ok':'程序正常结束','syntax':'语法检查未通过','error':'运行报错','timeout':'运行超时'}
            meta.append(labels[result['status']]+f' · {result["seconds"]} 秒')
            if result['status']=='ok' and not active and not all(outcomes):run_warning=' <p>程序能运行，但填空仍有错误，请核对题意。</p>'
        if not active:
            wrong=[f'<li>空 {i+1}：{h(error_hint(q,i,r["answers"][i]))}</li>' for i,ok in enumerate(outcomes) if not ok]
            if wrong:wrong_html='<ul>'+''.join(wrong)+'</ul>'
            if r.get('revealed'):meta.append('本轮已查看答案，单独记为辅助练习。')
            elif r.get('completion'):meta.append('本轮使用过 Tab 候选；补全使用单独记录。')
        if meta:
            text+='<div class="exam-feedback-meta">'+''.join('<span>'+item+'</span><span style="color:#94a3b8">·</span>' for item in meta[:-1])+'<span>'+meta[-1]+'</span></div>'
        text+=key_error+run_warning+wrong_html
        children=[W.HTML(text)]
        if result:
            # 使用 ipywidgets.Output 承载结果，让 JupyterLab 以原生输出区显示。
            # 结果默认可见，保留滚动区域以免长日志撑开整页。
            native_output=W.Output(layout=W.Layout(
                width='100%', max_height='420px', overflow='auto',
                border='1px solid #dbe3ef', padding='10px'))
            output_text=result['text'] or '（程序没有打印输出）'
            if not output_text.endswith('\n'):
                output_text+='\n'
            # 直接写入 Output.outputs，避免后台线程的 print 被 Jupyter
            # 追加到外层 Notebook 单元末尾；组件会留在当前反馈区原位。
            native_output.outputs=({
                'output_type':'stream', 'name':'stdout', 'text':output_text
            },)
            children.extend((W.HTML('<p style="margin:10px 0 4px"><b>运行输出（Jupyter 原生输出）</b></p>'), native_output))
        if not active:
            key=self.result_key(q)
            if key in self.open_answers:
                explanation='<ol>'+''.join('<li>空 '+str(i+1)+'：<code>'+h(b['answers'][0])+'</code> — '+h(b['why'])+'</li>' for i,b in enumerate(q['blanks']))+'</ol>'
                explanation+='<p>核对输出：'+h(q['learning']['expected'])+'</p><p>'+h(q['learning']['transfer'])+'</p>'
                if q.get('note'):explanation+='<p>'+h(q['note'])+'</p>'
                explanation+='<details><summary>完整参考程序</summary><pre>'+h(q['original'])+'</pre></details>'
                children.append(W.HTML(explanation))
                def hide(_):self.open_answers.discard(key);self.show_feedback(q,outcomes)
                children.append(self.button('收起解析',hide))
            else:children.append(self.button('查看解析与参考答案',lambda _:self.reveal(q)))
            if self.mode!='exam':
                children.append(W.HBox([self.button('再试一次',lambda _:self.reset_question(q)),self.button('加入复习',lambda _:self.add_review(q))],layout=W.Layout()))
        self.feedback.children=tuple(children)

    def run(self,q):
        if self.running:return
        r=self.record(q);answers=list(r['answers'])
        if any(not a.strip() for a in answers):
            self.feedback.children=(W.HTML('<p>请先填写全部空格，再运行程序。</p>'),);return
        mode=self.mode
        if mode!='exam': self.submit_attempt(q,r);self.save()
        stdin=self.stdin.value if self.stdin else ''
        self.running=True;self.render()
        self.feedback.children=(W.HTML('<p>正在运行… 最多 30 秒。</p>'),)
        def work():
            try:result=execute_code(filled_code(q,answers),stdin=stdin,setup=q.get('setup',''))
            except Exception as e:result={'status':'error','seconds':0,'text':str(e)}
            self.results[(mode,q['id'])]=result
            self.running=False;self.render()
        self.run_thread=threading.Thread(target=work,daemon=True);self.run_thread.start()

    def coverage(self):
        rows=[]
        for cat,label in CATEGORIES.items():
            qs=[q for q in self.bank if q['category']==cat]
            attempted=sum(self.seen(q['id']) for q in qs)
            mastered=sum(self.data['reviews'].get(q['id'],{}).get('state')=='已掌握' for q in qs)
            rows.append(f'<tr><td>{h(label)}</td><td>{attempted}/{len(qs)}</td><td>{mastered}</td></tr>')
        attempts=[a for seq in self.data['attempts'].values() for a in seq]
        assisted=sum(a['revealed'] for a in attempts);completed=sum(a['completion'] for a in attempts)
        text='<h4>学习统计</h4><table style="width:100%;text-align:left"><tr><th>模块</th><th>已练 / 总题数</th><th>已掌握</th></tr>'+''.join(rows)+'</table>'
        text+=f'<p>累计提交 {len(attempts)} 次 · 查看答案后提交 {assisted} 次 · 使用补全提交 {completed} 次。</p>'
        state=self._exam_coverage_view()
        covered=len(state['covered_ids']);total=len(self.bank)
        status='本轮已完成' if state['completed'] else '进行中'
        text+=f'<p>模拟考试题库覆盖：{covered} / {total} 题 · {status}（跨场次不重复）</p>'
        daily_state=self._daily_coverage_view()
        daily_status='本轮已完成' if daily_state['completed'] else '进行中'
        text+=f'<p>今日练习题库覆盖：{len(daily_state["covered_ids"])} / {total} 题 · {daily_status}（每组 15 题）</p>'
        text+='<p>首次正确率按每题首次提交的填空数计算；独立答题率只统计没有查看答案、没有使用 Tab 的首次提交，并标出已有独立记录的题数。复测掌握规则仍按独立提交记录判断，Tab 使用另记。</p>'
        text+=f'<p>旧题首次表现未记录：{len(self.data["legacy"])} 题；不纳入首次正确率。</p>'
        ranked=[]
        for q in self.bank:
            seq=self.data['attempts'].get(q['id'],[])
            errors=sum(len(a['marks'])-sum(a['marks']) for a in seq)
            if errors:ranked.append((errors,q,len(seq)))
        if ranked:
            text+='<details><summary>易错题与提交次数</summary>'+''.join('<p>'+h(q['title'])+f' · 累计错 {n} 空 / 提交 {count} 次</p>' for n,q,count in sorted(ranked,key=lambda x:-x[0])[:10])+'</details>'
        if self.data['history']:
            text+='<details><summary>模拟成绩</summary>'+''.join('<p>'+h(x['date'])+f' · {x["score"]} 分</p>' for x in reversed(self.data['history'][-10:]))+'</details>'
        text+='<details><summary>全部考点覆盖</summary>'+''.join('<p>'+h(q['title'])+'：'+h(' / '.join(q['topics']))+'</p>' for q in self.bank)+'</details>'
        return W.HTML(text)

    def setup_exam(self):
        state=self._exam_coverage_view()
        covered=len(state['covered_ids']);remaining=len(state['unseen_ids']);total=len(self.bank)
        if state['completed']:
            coverage_text=(f'上一轮已覆盖全部 {total} 题；点击开始后自动开启第 {state["cycle"]+1} 轮。')
        else:
            coverage_text=(f'本轮已覆盖 {covered}/{total} 题，剩余 {remaining} 题；跨场次优先抽取未出现题目。')
        text='<h3>模拟考试</h3><p>30 分钟 · 每场最多 10 题。每轮首场保持 Python 3 / 数据处理 3 / 机器学习 2 / 系统操作 2；后续按剩余题目动态配平。</p><p>'+coverage_text+' 最后一场不足 10 题时按剩余题数出题。保留原题提示，交卷后提供解析；关闭页面不暂停计时。</p>'
        self.exam_completion=W.Checkbox(value=False,description='允许原生 Tab 补全',indent=False)
        self.body.children=(W.HTML(text),self.exam_completion,self.button('开始模拟考试',lambda _:self.start_exam(),primary=True))

    def new_exam(self):
        if self.running:return
        self.data['exam']=None;self.index=0;self.mode='exam';self.save();self.render()

    def start_exam(self):
        if self.running or self.exam_active():return
        enabled=bool(getattr(self,'exam_completion',None) and self.exam_completion.value)
        state=self._exam_coverage_state()
        if state['completed']:
            state['cycle']+=1;state['covered_ids']=[]
            state['unseen_ids']=[q['id'] for q in self.bank];state['completed']=False
        ids=self._select_exam_ids(state['unseen_ids'],10)
        # Reserve selected questions immediately. If the browser closes while
        # the paper is active, reopening it resumes the same paper and cannot
        # allocate these IDs to another paper.
        state['unseen_ids']=[qid for qid in state['unseen_ids'] if qid not in ids]
        state['covered_ids'].extend(qid for qid in ids if qid not in state['covered_ids'])
        state['completed']=not state['unseen_ids']
        self.data['exam']={'ids':ids,'answers':{qid:['']*len(self.by_id[qid]['blanks']) for qid in ids},
                           'start':time.time(),'deadline':time.time()+1800,'submitted':False,'completion':enabled,
                           'coverage_cycle':state['cycle'],'coverage_after':len(state['covered_ids'])}
        self.mode='exam';self.index=0;self.save();self.render()

    def confirm_submit(self):
        ex=self.data['exam'];missing_details=[]
        missing=0
        for number,qid in enumerate(ex['ids'],1):
            blank_numbers=[str(i+1) for i,a in enumerate(ex['answers'][qid]) if not a.strip()]
            if blank_numbers:
                missing+=len(blank_numbers)
                missing_details.append('第'+str(number)+'题（空'+'、'.join(blank_numbers)+'）')
        if missing_details:
            detail='；'.join(missing_details)
            prompt=f'<p>还有 <b>{missing} 个空</b>未填写，涉及：{h(detail)}。现在交卷？</p>'
        else:
            prompt='<p>所有空均已填写。现在交卷？</p>'
        self.confirm_area.children=(W.HTML(prompt),
            W.HBox([self.button('确认交卷',lambda _:self.submit_exam()),self.button('继续作答',lambda _:setattr(self.confirm_area,'children',()))]))

    def submit_exam(self,auto=False):
        with self.save_lock:
            if not self.exam_active():return
            ex=self.data['exam'];ex['submitted']=True;ex['auto']=auto;ex['end']=time.time()
            for qid in ex['ids']:
                q=self.by_id[qid];r=ex.setdefault('drafts',{}).setdefault(qid,self.new_record(q));r['answers']=ex['answers'][qid]
                self.submit_attempt(q,r,mode='exam')
            correct,total=self.exam_score()
            self.data['history'].append({'date':datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),'score':round(100*correct/total,1),'correct':correct,'total':total,
                'unfilled':sum(not a.strip() for values in ex['answers'].values() for a in values),'seconds':round(ex['end']-ex['start'])})
            self.save();self.render()

    def exam_score(self,category=None):
        ex=self.data['exam'];correct=total=0
        for qid in ex['ids']:
            q=self.by_id[qid]
            if category and q['category']!=category:continue
            correct+=sum(marks(q,ex['answers'][qid]));total+=len(q['blanks'])
        return correct,total

    def exam_summary(self):
        correct,total=self.exam_score();ex=self.data['exam']
        missing=sum(not a.strip() for values in ex['answers'].values() for a in values)
        minutes=max(0,ex.get('end',time.time())-ex['start'])/60
        detail=' · '.join(CATEGORIES[c]+f' {self.exam_score(c)[0]}/{self.exam_score(c)[1]}' for c in CATEGORIES)
        state=self._exam_coverage_view()
        coverage=f' · 题库覆盖 {len(state["covered_ids"])}/{len(self.bank)}'
        failed=[]
        for number,qid in enumerate(ex['ids'],1):
            outcomes=marks(self.by_id[qid],ex['answers'][qid])
            wrong_blanks=[str(i+1) for i,ok in enumerate(outcomes) if not ok]
            if wrong_blanks:failed.append('第'+str(number)+'题（空'+'、'.join(wrong_blanks)+'）')
        if failed:
            failed_html='<p style="color:#b91c1c"><b>未全对题目：</b>'+h('；'.join(failed))+'</p>'
        else:
            failed_html='<p style="color:#15803d"><b>未全对题目：</b>无，全部题目填空正确。</p>'
        summary=f'<p><b>{100*correct/total:.1f} 分</b> · 未填 {missing} 空 · 用时 {minutes:.1f} 分钟'+(' · 到时自动交卷' if ex.get('auto') else '')+coverage+'</p><small>'+detail+'</small>'
        return W.HTML(summary+failed_html)

    def _update_timer(self):
        if self.exam_active():
            ex=self.data['exam'];remain=max(0,int(ex['deadline']-time.time()))
            done=sum(bool(a.strip()) for v in ex['answers'].values() for a in v);total=sum(len(v) for v in ex['answers'].values())
            self.timer.value=f'<b style="color:#2563eb">剩余 {remain//60:02d}:{remain%60:02d} · 已填 {done}/{total} 空</b>'
        else:self.timer.value=''

    def _clock(self):
        while not self.stopped.wait(1):
            if self.exam_active() and time.time()>=self.data['exam']['deadline']:self.submit_exam(auto=True)
            self._update_timer()

if __name__ == '__main__' and 'BANK' in globals():
    if '_fill_exam' in globals():
        _fill_exam.close()
        _fill_exam.root.close()
    _fill_exam=FillExam(BANK)
    display(_fill_exam.root)
    if 'AUTOCOMPLETE_JS' in globals():
        display(Javascript(AUTOCOMPLETE_JS))
    if 'KERNEL_GUARD_JS' in globals():
        display(Javascript(KERNEL_GUARD_JS))
