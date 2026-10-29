"""Overlap of each raw source with the public model's training texts (ealvaradob/phishing-dataset texts.json).
Exact = same lowercase letters-only text; near = cosine >= 0.8 on word 1-2gram hashing vectors."""
import json, re, hashlib, sys
import numpy as np, pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize
D="dataset/"
hf=json.load(open(D+"external/hf_phishing_texts.json",encoding="utf-8"))
hf=pd.DataFrame(hf)
def key(s): return hashlib.md5(re.sub(r"[^a-z]+"," ",str(s).lower()).strip().encode()).hexdigest()
hv=HashingVectorizer(n_features=2**20,ngram_range=(1,2),alternate_sign=False,norm=None)
def vec(t): return normalize(hv.transform([str(x)[:3000] for x in t]))
Hk=set(hf.text.map(key)); HX=vec(hf.text).T.tocsr()
rows=[]
for f in ["CEAS_08","Enron","Ling","Nazario","Nigerian_Fraud","SpamAssasin"]:
    df=pd.read_csv(D+f+".csv",encoding_errors="replace",on_bad_lines="skip",low_memory=False)
    t=(df.subject.fillna("").astype(str)+" . "+df.body.fillna("").astype(str))
    df=df.assign(t=t).sample(min(len(df),3000),random_state=0)
    ex=df.t.map(key).isin(Hk)
    X=vec(df.t); m=np.concatenate([(X[i:i+1000]@HX).max(axis=1).toarray().ravel() for i in range(0,X.shape[0],1000)])
    for lab,g in df.assign(ex=ex,n8=m>=0.8,n9=m>=0.9).groupby("label"):
        rows.append(dict(source=f,label=int(lab),sampled=len(g),exact=int(g.ex.sum()),near_ge_0_8=int(g.n8.sum()),pct_near=round(100*g.n8.mean(),1)))
    print(rows[-1],flush=True)
out=pd.DataFrame(rows); out.to_csv(D+"processed_v2_overlap_hf.csv",index=False); print(out.to_string())
