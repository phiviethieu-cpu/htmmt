"""Chạy kiểm chứng: lặp lại Q2 (p=0, FedAvg thật, N=4, WAN 100 Mbps) với hai cách đặt hàng đợi netem:
  limit=200            (như báo cáo)
  limit=200+gói đang bay (hàng đợi nghẽn thực sự còn đủ 200 gói)
Kết quả ghi vào /root/qverify, không đụng vào dữ liệu cũ."""
import math, os, sys
CODE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'code')
sys.path.insert(0, CODE)
os.environ['FL_RES'] = '/root/qverify'
os.makedirs('/root/qverify', exist_ok=True)
import run_experiments as R
from mininet.log import setLogLevel
setLogLevel('critical')
orig = R.make_net
LIM = [200]


def patched(**kw):
    net = orig(**kw)
    start = net.start

    def st():
        start()
        if LIM[0] != 200:
            d = kw['wan_delay']
            r1, s2 = net.get('r1', 's2')
            for l in net.links:
                a, b = l.intf1, l.intf2
                if {a.node.name, b.node.name} == {'r1', 's2'}:
                    for i in (a, b):
                        out = i.node.cmd('tc qdisc change dev %s parent 5:1 handle 10: netem limit %d delay %s' % (i.name, LIM[0], d))
                        if out.strip(): print('tc:', out)
            print('   ', r1.cmd('tc qdisc show dev r1-eth1').strip().splitlines()[-1], flush=True)
    net.start = st
    return net


R.make_net = patched
for d in (20, 50, 100):
    for fixed in (False, True):
        LIM[0] = 200 + math.ceil(100e6 * d / 1000 / 8 / 1514) if fixed else 200
        tag = 'V_d%d_lim%d' % (d, LIM[0])
        R.run_one(tag, where='cloud', bw=100, delay=d, loss=0, n=4, rounds=20, fedavg=True, pcap=False)
        import csv
        rows = list(csv.DictReader(open('/root/qverify/%s.csv' % tag)))
        rs = rows[1:]
        av = lambda k: sum(float(r[k]) for r in rs) / len(rs)
        sd = (sum((float(r['t_round']) - av('t_round')) ** 2 for r in rs) / (len(rs) - 1)) ** .5
        hit = next((i for i, r in enumerate(rows) if float(r['acc']) >= .9), None)
        tta = sum(float(r['t_round']) for r in rows[:hit + 1]) if hit is not None else float('nan')
        print('%-16s vòng %d T_down %.3f T_up %.3f T_round %.3f sd %.3f | 90%% ở vòng %s TTA %.1f | acc cuối %s'
              % (tag, len(rows), av('t_down'), av('t_up'), av('t_round'), sd, hit + 1 if hit is not None else '-', tta, rows[-1]['acc']), flush=True)
