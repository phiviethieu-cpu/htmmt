"""Từ pcap phía server (K1 agg-eth0, K3 cloud-eth0): với mỗi vòng, mỗi client:
thời điểm nhận đủ GLOBAL, bắt đầu/kết thúc UPDATE, độ chồng pha, thông lượng từng luồng, RTT pha tải xuống."""
import struct, sys, collections, statistics as st
PORT = 5000


def packets(path):
    with open(path, 'rb') as f:
        g = f.read(24)
        e = '<' if g[:4] in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1') else '>'
        nano = g[:4] in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d')
        rec = struct.Struct(e + 'IIII')
        while (h := f.read(16)):
            s, us, incl, orig = rec.unpack(h)
            d = f.read(incl)
            if len(d) < 54 or d[12:14] != b'\x08\x00' or d[23] != 6:
                continue
            ihl = (d[14] & 15) * 4
            tot = struct.unpack('!H', d[16:18])[0]
            t = 14 + ihl
            sp, dp, seq, ack = struct.unpack('!HHII', d[t:t + 12])
            thl = (d[t + 12] >> 4) * 4
            yield s + us / (1e9 if nano else 1e6), d[29], d[33], sp, dp, seq, ack, d[t + 13], tot - ihl - thl


def main(path, tag):
    down = collections.defaultdict(list)  # client -> [(time, rel_end)]
    up = collections.defaultdict(list)
    isn_d, isn_u = {}, {}
    sent = collections.defaultdict(dict)  # client -> {end_seq: time} (gửi lần đầu)
    resent = collections.defaultdict(set)
    rtts = []
    acks = []
    for t, sip, dip, sp, dp, seq, ack, fl, pl in packets(path):
        if sp == PORT:
            c = dip
            if fl & 2: isn_d[c] = (seq + 1) & 0xffffffff
            if pl > 0 and c in isn_d:
                end = (seq + pl - isn_d[c]) & 0xffffffff
                down[c].append((t, end, pl))
                if end in sent[c] or end in resent[c]: resent[c].add(end)
                else: sent[c][end] = t
        elif dp == PORT:
            c = sip
            if fl & 2: isn_u[c] = (seq + 1) & 0xffffffff
            if c in isn_d and (fl & 16):
                a = (ack - isn_d[c]) & 0xffffffff
                if a in sent[c] and a not in resent[c]:
                    rtts.append((t, (t - sent[c].pop(a)) * 1000))
            if pl > 0 and c in isn_u:
                up[c].append((t, (seq + pl - isn_u[c]) & 0xffffffff, pl))
    S = 10_000_000
    nc = sorted(up)
    print('###', tag, 'client', nc)
    for r in range(1, 4):
        # byte tích luỹ: mỗi vòng down = 20+S (GLOBAL) + 20 (ACK); up = HELLO 20 trước vòng 1, mỗi vòng ACK 20 + UPDATE 20+S
        dlo = (r - 1) * (S + 40); dhi = dlo + 20 + S
        ulo = 20 + (r - 1) * (S + 40); uhi = ulo + 40 + S
        D0, D1, A, U0, U1 = {}, {}, {}, {}, {}
        for c in nc:
            D0[c] = min(t for t, e, p in down[c] if e > dlo)
            D1[c] = min(t for t, e, p in down[c] if e >= dhi)          # server đẩy xong byte cuối (xấp xỉ)
            A[c] = min(t for t, e, p in up[c] if e >= ulo + 20)        # ACK tầng ứng dụng tới server
            U0[c] = min(t for t, e, p in up[c] if e >= ulo + 40)       # header UPDATE tới
            U1[c] = min(t for t, e, p in up[c] if e >= uhi)
        t0 = min(D0.values())
        f = lambda d: ' '.join('%6.2f' % (d[c] - t0) for c in nc)
        print('vòng', r)
        print('  ACK (nhận đủ GLOBAL):', f(A), ' lệch %.2f s' % (max(A.values()) - min(A.values())))
        print('  UPDATE bắt đầu      :', f(U0))
        print('  UPDATE xong         :', f(U1))
        tdown = max(A.values()) - t0; tup = max(U1.values()) - min(A.values()) - 1
        tr = max(U1.values()) - t0
        pure = [U1[c] - U0[c] for c in nc]
        print('  T_down %.2f  T_up %.2f  T_round~ %.2f  | T_down+1+T_up %.2f | chồng pha (ACK cuối - UPDATE đầu) %.2f s'
              % (tdown, tup, tr, tdown + 1 + tup, max(A.values()) - min(U0.values())))
        print('  thời gian upload riêng từng nút:', ' '.join('%.2f' % x for x in pure),
              '| T_up - (U cuối - U đầu) = %.2f' % (tup - (max(U1.values()) - min(U0.values()))))
        lo, hi = t0, max(A.values())
        a_only = [x for t, x in rtts if lo <= t <= min(U0.values())]
        ov = [x for t, x in rtts if min(U0.values()) < t <= hi]
        q = lambda v: 'n=%d trung vị %.1f  p95 %.1f  max %.1f' % (len(v), st.median(v), sorted(v)[int(.95 * len(v))], max(v)) if len(v) > 20 else 'n=%d' % len(v)
        print('  RTT (ms) lúc chỉ tải xuống:', q(a_only))
        print('  RTT (ms) lúc chồng pha    :', q(ov))
    # Thông lượng từng luồng theo giây, chiều xuống và chiều lên
    allv = [(t, c, p, 'd') for c in down for t, e, p in down[c]] + [(t, c, p, 'u') for c in up for t, e, p in up[c]]
    b = min(x[0] for x in allv)
    bins = collections.defaultdict(lambda: collections.Counter())
    for t, c, p, k in allv:
        bins[(k, int(t - b))][c] += p
    vals, jain = [], []
    for (k, s), cnt in bins.items():
        tot = sum(cnt.values())
        if tot > 10.5e6:
            v = [cnt.get(c, 0) / 1e6 for c in nc]
            vals += v
            jain.append(sum(v) ** 2 / (len(v) * sum(x * x for x in v)))
    print('giây bão hoà: %d; phần mỗi luồng MB/s: min %.2f max %.2f trung bình %.2f; Jain trung bình %.2f (min %.2f max %.2f)'
          % (len(jain), min(vals), max(vals), sum(vals) / len(vals), sum(jain) / len(jain), min(jain), max(jain)))


for a in sys.argv[1:]:
    main(a, a.split('/')[-1])
