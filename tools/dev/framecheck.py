#!/usr/bin/env python3
"""被動量測(不碰遊戲、不需 root):主執行緒被 split lock 罰睡的比例 + DXVK 送幀的間隔分布。
用法: framecheck.py [秒數=30]"""
import os,sys,time,subprocess
dur=float(sys.argv[1]) if len(sys.argv)>1 else 30
p=subprocess.check_output(['pgrep','-x','MapleStory.exe']).split()[0].decode()
sub=next(t for t in os.listdir(f'/proc/{p}/task') if open(f'/proc/{p}/task/{t}/comm').read().strip()=='dxvk-submit')
fio=os.open(f'/proc/{p}/task/{sub}/io',os.O_RDONLY); fwc=os.open(f'/proc/{p}/task/{p}/wchan',os.O_RDONLY)
fst=os.open(f'/proc/{p}/task/{p}/stat',os.O_RDONLY)
def cpulist(path):
    try: txt=open(path).read().strip()
    except OSError: return set()
    out=set()
    for r in txt.split(','):
        a,_,b=r.partition('-'); out.update(range(int(a),int(b or a)+1))
    return out
ecores=cpulist('/sys/devices/cpu_atom/cpus')  # 大小核 CPU 才有
def rd(f): os.lseek(f,0,0); return os.read(f,512)
mit=open('/proc/sys/kernel/split_lock_mitigate').read().strip()
onE=0; runN=0; sl=0.0; slN=0; inSl=None; ev=[]; lastw=None; t0=time.perf_counter(); end=t0+dur; prev=t0
while (now:=time.perf_counter())<end:
    w=rd(fio).split(b'\n')[3]
    if w!=lastw:
        if lastw is not None: ev.append(now)
        lastw=w
    st=rd(fst).rsplit(b')',1)[1].split()
    if st[0]==b'R': runN+=1; onE+=int(st[36]) in ecores
    asleep = rd(fwc)==b'msleep_interruptible'
    if asleep and inSl is None: inSl=now; slN+=1
    if not asleep and inSl is not None: sl+=now-inSl; inSl=None
    time.sleep(0.0002)
d=sorted((b-a)*1000 for a,b in zip(ev,ev[1:])); n=len(d)
q=lambda x: d[min(n-1,int(n*x))]
print(f'{time.strftime("%F %T")} split_lock_mitigate={mit} dur={dur:.0f}s')
print(f'  split-lock 罰睡: {slN/dur:.1f} 次/s, 佔主執行緒 {sl/dur*100:.0f}% 時間')
if ecores: print(f'  主執行緒執行中時在 E-core 的比例: {onE/max(runN,1)*100:.0f}%  (affinity {os.sched_getaffinity(int(p)).__len__()} 顆)')
print(f'  dxvk-submit 事件 {n/dur:.0f}/s, 間隔 ms p50 {q(.5):.1f} p90 {q(.9):.1f} p99 {q(.99):.1f} max {d[-1]:.1f}, >12ms 的 {sum(x>12 for x in d)/dur:.1f} 次/s')
