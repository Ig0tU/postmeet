"""Evidence-bound transcript extraction: chapters, agenda items and decisions."""
from __future__ import annotations
import html,re
from typing import List,Tuple
Cue=Tuple[float,str]
_LINE=re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d\d)\s*[-–]\s*(.+)$")
AGENDA=re.compile(r"\b(call(?:ing)? (?:this |the )?meeting to order|roll call|pledge of allegiance|approval of (?:the )?(?:minutes|agenda)|consent (?:agenda|calendar)|public (?:comment|participation|hearing)|superintendent'?s? report|(?:financial|treasurer'?s?|principal'?s?) report|old business|new business|executive session|closed session|adjourn(?:ment)?|(?:agenda )?item (?:number |no\.? |#)?\d+|next (?:agenda )?item|mov(?:e|ing) on to|turn(?:ing)? to item)\b",re.I)
MOTION=re.compile(r"\b(i move\b|i'?d like to move\b|move that\b|so moved\b|entertain a motion\b|do i have a motion\b|motion to\s+\w)",re.I)
SECOND=re.compile(r"\b(i second|second(?:ed)?(?: that| the motion)?)\b",re.I)
VOTE=re.compile(r"\b(all (?:those )?in favou?r|all opposed|any opposed|aye|nay|abstain|roll call vote|motion (?:carries|passes|fails|is approved|is denied)|unanimous(?:ly)?)\b",re.I)
CARRIED=re.compile(r"\b(motion (?:carries|passes|is approved)|approved unanimously|unanimously approved)\b",re.I)
FAILED=re.compile(r"\b(motion (?:fails|failed|is denied|does not carry))\b",re.I)
CANON=[(r"meeting to order","Call to Order","procedural"),(r"roll call$","Roll Call","procedural"),(r"pledge of allegiance","Pledge of Allegiance","procedural"),(r"approval of (?:the )?minutes","Approval of Minutes","action"),(r"approval of (?:the )?agenda","Approval of Agenda","action"),(r"consent (?:agenda|calendar)","Consent Agenda","action"),(r"public (?:comment|participation)","Public Comment","information"),(r"public hearing","Public Hearing","information"),(r"superintendent","Superintendent's Report","information"),(r"treasurer","Treasurer's Report","information"),(r"financial report","Financial Report","information"),(r"principal","Principal's Report","information"),(r"old business","Old Business","action"),(r"new business","New Business","action"),(r"(?:executive|closed) session","Executive Session","procedural"),(r"adjourn","Adjournment","procedural")]

def clean(line):
 s=html.unescape(html.unescape(line or "")); s=re.sub(r">>+"," ",s); s=re.sub(r"\[(?:music|applause|inaudible|laughter)[^\]]*\]"," ",s,flags=re.I); return re.sub(r"\s+"," ",s).strip()
def parse_transcript(text:str)->List[Cue]:
 out=[]
 for raw in text.splitlines():
  m=_LINE.match(raw)
  if not m: continue
  h,mi,se,body=m.groups(); out.append(((int(h)*3600 if h else 0)+int(mi)*60+int(se),clean(body)))
 return [(t,s) for t,s in out if s]
def stamp(sec):
 m,s=divmod(int(sec),60); h,m=divmod(m,60); return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
def slug(s): return re.sub(r"[^a-z0-9]+","-",s.lower()).strip("-")[:48] or "item"
def canon(line):
 for pat,label,kind in CANON:
  if re.search(pat,line,re.I): return label,kind
 m=re.search(r"item\s*(?:number|no\.?|#)?\s*(\d+)",line,re.I)
 return (f"Item {m.group(1)}","information") if m else (line[:88].strip().capitalize(),"information")
def extract(text:str)->List[dict]:
 cues=parse_transcript(text); hits=[]
 for i,(t,line) in enumerate(cues):
  if AGENDA.search(line):
   if hits and t-hits[-1][1]<60 and AGENDA.search(cues[hits[-1][0]][1]).group(0).lower()==AGENDA.search(line).group(0).lower(): continue
   hits.append((i,t))
 items=[]
 for n,(idx,t) in enumerate(hits):
  end=hits[n+1][0] if n+1<len(hits) else len(cues); body=[x[1] for x in cues[idx:end]]; label,kind=canon(cues[idx][1]); key=f"agenda-{len(items)+1:02d}-{slug(label)}"
  items.append({"record_type":"agenda","record_key":key,"title":label,"agenda_number":str(len(items)+1),"agenda_kind":kind,"description":" ".join(body)[:600],"outcome":"discussed","highlight":False,"start_time":stamp(t),"evidence_line":cues[idx][1],"confidence":0.75})
 for i,(t,line) in enumerate(cues):
  if not MOTION.search(line): continue
  target=None
  for a in items:
   if a.get("start_time") and _seconds(a["start_time"])<=t: target=a
  motion=" ".join(x[1] for x in cues[i:i+4]); window=" ".join(x[1] for x in cues[i:i+25]);
  if target is None:
   target={"record_type":"agenda","record_key":f"agenda-motion-{len(items)+1:02d}","title":f"Motion: {motion[:70]}","agenda_number":"","agenda_kind":"action","description":window[:600],"outcome":"moved","highlight":True,"start_time":stamp(t),"evidence_line":line,"confidence":0.5}; items.append(target)
  target["motion_text"]=motion.strip(); target["verbatim"]=True
  sec=next((x[1] for x in cues[i:i+25] if SECOND.search(x[1])),None); vote=" ".join(x[1] for x in cues[i:i+25] if VOTE.search(x[1]))
  if sec: target["second_text"]=sec
  if vote: target["vote_text"]=vote
  target["outcome"]="approved" if CARRIED.search(window) else "failed" if FAILED.search(window) else "voted" if vote else "moved"; target["highlight"]=target["outcome"] in {"approved","failed"}
 return items
def _seconds(ts):
 p=[int(x) for x in ts.split(":")]; return p[-1]+60*p[-2]+3600*p[-3] if len(p)==3 else p[0]*60+p[1]

def build_payload(meeting_key,title,transcript,**fields):
 items=extract(transcript); return {"meeting_key":meeting_key,"title":title,"meeting_status":fields.pop("meeting_status","complete"),"items":items or [{"record_key":"chapter-01","record_type":"chapter","title":"Meeting recording","start_time":"00:00","confidence":1}],"retention":fields.pop("retention",{"correlation_id":meeting_key,"stored_at":"","stages_complete":["extract"]}),**fields}
