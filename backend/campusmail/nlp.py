"""Conservative local analysis; every extraction references original text."""
from datetime import datetime, timedelta
from pathlib import Path
import re
from .models import CATEGORIES

MONTHS = {name:i for i,name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
MONTH_PATTERN = '|'.join(name + '|' + name[:3] for name in MONTHS)
DATE = re.compile(r'\b(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:'+MONTH_PATTERN+r')(?:\s+\d{4})?|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|tomorrow|today)\b', re.I)
RULES = {
 'assignments':r'\b(assignment|homework|project submission)\b',
 'examinations':r'\b(exam|examination|marks|result|viva|midsem)\b',
 'scholarships':r'\b(scholarship|fellowship|financial aid)\b',
 'placements':r'\b(placement|internship|recruitment|job opportunity)\b',
 'course_materials':r'\b(lecture notes|slides|syllabus|course material)\b',
 'workshops_events':r'\b(workshop|webinar|meeting|seminar|event|hackathon)\b',
 'administration':r'\b(fees|holiday|administration|circular|timetable|registration)\b'}


def sentences(text):
    return [m for m in re.finditer(r'[^.!?\n]+(?:[.!?]|$)', text) if m.group().strip()]


def analyze(text, subject='', reference_date=None, model_path=None):
    if not text.strip(): raise ValueError('Notice text is empty')
    if isinstance(reference_date,str):
        try: reference_date = datetime.fromisoformat(reference_date.replace('Z','+00:00'))
        except ValueError: reference_date = None
    category = next((k for k,v in RULES.items() if re.search(v,subject+' '+text,re.I)), 'nonacademic_other')
    method = 'local_rules'
    if model_path and Path(model_path).is_file():
        import joblib
        model = joblib.load(model_path)  # Only application-managed artifacts.
        category, method = str(model.predict([subject+' '+text])[0]), 'self_trained_pipeline'
    result = {'category':category,'classification_method':method,'dates':[], 'actions':[], 'resources':[], 'courses':[], 'needs_review':False}
    for match in DATE.finditer(text):
        raw = match.group(); normalized = None; reason = None
        try:
            if raw.lower() in ('today','tomorrow'):
                if reference_date is None: reason = 'Relative date needs the source date'
                else: normalized = (reference_date + timedelta(days=raw.lower()=='tomorrow')).date().isoformat()
            elif '/' in raw or '-' in raw:
                day,month,year = map(int,re.split(r'[/\-]',raw))
                if day<=12 and month<=12: reason = 'Ambiguous numeric date order'
                elif year<100: reason = 'Two-digit year needs review'
                else: normalized = datetime(year,month,day).date().isoformat()
            else:
                parts=raw.split(); day=int(re.sub(r'\D','',parts[0])); month=next(i for n,i in MONTHS.items() if n.lower().startswith(parts[1].lower()))
                if len(parts)==2: reason = 'Missing year'
                else: normalized=datetime(int(parts[2]),month,day).date().isoformat()
        except (ValueError,StopIteration): reason = 'Invalid or unsupported date'
        sentence = next((s for s in sentences(text) if s.start()<=match.start()<s.end()),None)
        prefix = text[sentence.start() if sentence else max(0,match.start()-100):match.start()].lower()
        cues=[]
        for role,pattern in [('registration_deadline',r'registration.{0,25}(?:close|deadline|last date)|register by'),('assignment_deadline',r'submit(?:ted)? by|submission.{0,20}(?:deadline|due)|due(?: on| by)?|last date'),('exam_date',r'exam(?:ination)?.{0,30}(?:on|held)'),('event_start',r'held on|conducted on|scheduled (?:on|for)|meet on|starts? on')]:
            cues.extend((m.end(),role) for m in re.finditer(pattern,prefix))
        role = max(cues)[1] if cues else 'unknown'
        result['dates'].append({'text':raw,'start':match.start(),'end':match.end(),'normalized':normalized,'precision':'date','role':role,'needs_review':bool(reason) or role=='unknown','reason':reason or ('Date role unclear' if role=='unknown' else None)})
    for sentence in sentences(text):
        raw=sentence.group(); lower=raw.lower()
        if re.search(r'\b(must|should|please|register|submit|apply|bring|upload|complete)\b',lower) and not re.search(r'\b(do not|must not|already|has closed|submitted|completed|no need)\b',lower):
            result['actions'].append({'text':raw,'start':sentence.start(),'end':sentence.end(),'status':'required' if re.search(r'\b(must|required|submit by)\b',lower) else 'optional_or_uncertain'})
    for m in re.finditer(r'https?://[^\s<>"\)]+',text):
        url=m.group().rstrip('.,;'); context=text[max(0,m.start()-70):m.start()].lower()
        role='meeting' if re.search(r'meet\.google|zoom\.',url) else 'submission' if 'submit' in context else 'registration' if 'register' in context else 'reference'
        result['resources'].append({'url':url,'role':role,'start':m.start(),'end':m.start()+len(url),'drive_link_only':'drive.google.com' in url or 'docs.google.com' in url})
    result['courses']=sorted(set(re.findall(r'\b[A-Z]{2,5}[- ]?\d{3}\b',subject+' '+text)))
    result['needs_review']=any(x['needs_review'] for x in result['dates'])
    return result
