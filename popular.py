#!/usr/bin/env python3
"""Põe na fila as peças EN já preparadas em ~/w31/_ig_en_post_claude (só as sem alerta). Pode rodar de novo: não duplica."""
import json, os, re, shutil
B=os.path.expanduser('~/w31/_ig_en_post_claude'); AQUI=os.path.dirname(os.path.abspath(__file__))
PRIMEIRAS=[('G069','04_G069'),('N003','05_N003'),('G296','07_G296'),('G062','09_G062')]
arq=os.path.join(AQUI,'carrosseis.json')
fila=json.load(open(arq)) if os.path.exists(arq) else {'carrosseis':[]}
ja={c['id'] for c in fila['carrosseis']}
rel={}
rp=os.path.join(B,'all','_relatorio.json')
if os.path.exists(rp): rel={r['nome']:r['flags'] for r in json.load(open(rp))}
cand=[(i,os.path.join(B,d)) for i,d in PRIMEIRAS]
for nome in sorted(rel):
    if rel[nome]: continue
    cand.append(('EN'+re.sub(r'[^A-Za-z0-9]+','_',nome)[:40].strip('_'),os.path.join(B,'all',nome)))
novos=0
for cid,pasta in cand:
    P=os.path.join(pasta,'POSTAR')
    if cid in ja or not os.path.isfile(os.path.join(P,'10.jpg')): continue
    leg=open(os.path.join(P,'caption.txt'),encoding='utf-8').read().strip()
    slides=[]
    for n in range(1,11):
        dst=f'{cid}_{n:02d}.jpg'; shutil.copyfile(os.path.join(P,f'{n:02d}.jpg'),os.path.join(AQUI,'carrosseis',dst)); slides.append(dst)
    fila['carrosseis'].append({'id':cid,'titulo':leg.split('\n')[0].strip(),'slides':slides,'legenda':leg,'aprovado':True,'sem_oferta':True}); novos+=1
json.dump(fila,open(arq,'w'),ensure_ascii=False,indent=2)
print('na fila:',len(fila['carrosseis']),'| novos:',novos,'| a publicar:',sum(1 for c in fila['carrosseis'] if not c.get('publicado')))
