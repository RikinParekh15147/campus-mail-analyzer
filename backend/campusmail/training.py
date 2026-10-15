"""Offline research training. Never consumes operational student feedback."""
import hashlib
import json
from pathlib import Path


def load_rows(path):
    rows=[]
    for line in Path(path).open(encoding='utf-8'):
        d=json.loads(line);label=d.get('label',d.get('primary_category'))
        if label is None or str(label).lower() in ('null','unknown','none'):continue
        text=d.get('subject','')+' '+d.get('text','')
        if len(text.strip())<5:continue
        rows.append({'text':text,'label':str(label),'group':d.get('leakage_group_id') or d.get('duplicate_group_id') or d.get('thread_id') or hashlib.sha256(text.encode()).hexdigest()})
    return rows


def train_models(rows, output):
    import joblib
    import sklearn
    from sklearn.pipeline import make_pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.naive_bayes import MultinomialNB
    from sklearn.svm import LinearSVC
    from sklearn.dummy import DummyClassifier
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.metrics import accuracy_score,f1_score,confusion_matrix,classification_report
    if len(rows)<10 or len({r['label'] for r in rows})<2:raise ValueError('Need at least ten labeled examples in two classes')
    # Union source groups and exact normalized duplicates before splitting.
    parents={}
    def find(a):
        parents.setdefault(a,a)
        if parents[a]!=a:parents[a]=find(parents[a])
        return parents[a]
    texts={}
    for row in rows:
        group=str(row['group']); digest=hashlib.sha256(' '.join(row['text'].lower().split()).encode()).hexdigest()
        if digest in texts:parents[find(group)]=find(texts[digest])
        else:texts[digest]=group
    groups=[find(str(r['group'])) for r in rows]
    if len(set(groups))<3:raise ValueError('Insufficient independent groups')
    train,test=next(GroupShuffleSplit(n_splits=1,test_size=.25,random_state=42).split(rows,groups=groups))
    x=[r['text'] for r in rows];y=[r['label'] for r in rows];labels=sorted(set(y))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    report={'records':len(rows),'train_groups':sorted({groups[i] for i in train}),'test_groups':sorted({groups[i] for i in test}),'labels':labels,'models':{},'label_warning':'Source/weak labels; not an independently reviewed gold evaluation','sklearn_version':sklearn.__version__,'dataset_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()}
    pipelines={}
    for name,estimator in [('naive_bayes',MultinomialNB()),('linear_svm',LinearSVC()),('majority',DummyClassifier(strategy='most_frequent'))]:
        pipeline=make_pipeline(TfidfVectorizer(ngram_range=(1,2),sublinear_tf=True,max_features=30000),estimator)
        pipeline.fit([x[i] for i in train],[y[i] for i in train]);pred=pipeline.predict([x[i] for i in test])
        report['models'][name]={'accuracy':accuracy_score([y[i] for i in test],pred),'macro_f1':f1_score([y[i] for i in test],pred,labels=labels,average='macro',zero_division=0),'confusion_matrix':confusion_matrix([y[i] for i in test],pred,labels=labels).tolist(),'per_class':classification_report([y[i] for i in test],pred,labels=labels,output_dict=True,zero_division=0)}
        pipelines[name]=pipeline;joblib.dump(pipeline,output/(name+'.joblib'))
    # Predeclared deployment choice; held-out scores are reporting only, not tuning.
    joblib.dump(pipelines['linear_svm'],output/'classifier.joblib');report['selected']='linear_svm'
    (output/'metrics.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
