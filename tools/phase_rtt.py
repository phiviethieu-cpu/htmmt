"""Tách RTT (ping -i 0.2) theo pha của vòng FL. Log ping không có mốc thời gian, nhưng gói thứ k được gửi
ở ~0.2k s sau khi ping khởi động; căn lệch với log vòng (T_down, T_round) bằng cách chọn độ lệch off làm
RTT trong khoảng nghỉ (train) thấp nhất so với ngoài khoảng đó. Chỉ dùng khi tương phản rõ."""
import csv, glob, os, re, statistics as st, sys


def load(base):
    pings = {}
    for l in open(base + '_ping.txt', encoding='utf-8', errors='replace'):
        m = re.search(r'icmp_seq=(\d+) .*time=([\d.]+)', l)
        if m: pings[int(m.group(1))] = float(m.group(2))
    rows = list(csv.DictReader(open(base + '.csv')))
    return pings, rows


def spans(rows, off, gap):
    """(pha, đầu, cuối). Tải xuống: [t0, t0+T_down]; nghỉ chung: [t0+T_down, t0+T_first+1]... chỉ lấy phần chắc chắn."""
    t, out = off, []
    for r in rows:
        d, u, T = float(r['t_down']), float(r['t_up']), float(r['t_round'])
        skew = max(0.0, d + 1 + u - T)
        first = d - skew                        # ACK đầu tiên (xấp xỉ, bỏ qua T_agg)
        out.append(('down', t, t + first))       # chắc chắn chưa nút nào train xong
        out.append(('idle', t + d, t + first + 1))  # nút cuối đã tải xong, nút đầu chưa gửi (rỗng nếu skew>=1)
        out.append(('up', t + d + 1, t + T))     # mọi nút đã train xong -> chỉ còn upload
        t += T + gap
    return out


def classify(pings, sp, m=0.15):
    g = {'down': [], 'idle': [], 'up': []}
    for k, v in pings.items():
        x = 0.2 * k
        for name, a, b in sp:
            if a + m <= x <= b - m:
                g[name].append(v); break
    return g


for base in sys.argv[1:]:
    pings, rows = load(base)
    best = None
    for gap in (0.0, 0.01, 0.02, 0.03, 0.05):
        for i in range(14, 70):
            off = i * 0.05
            g = classify(pings, spans(rows, off, gap))
            if len(g['idle']) < 4 or len(g['down']) < 5 or len(g['up']) < 5: continue
            s = (st.median(g['down']) + st.median(g['up'])) / 2 - st.mean(g['idle'])
            if best is None or s > best[0]: best = (s, off, gap, g)
    n = os.path.basename(base)
    if not best:
        print(n, 'không tách được (khoảng nghỉ chung quá ngắn)'); continue
    s, off, gap, g = best
    q = lambda v: 'n=%3d trung vị %7.1f max %7.1f' % (len(v), st.median(v), max(v))
    allv = list(pings.values())
    print('%-18s off %.2f | xuống %s | nghỉ %s | lên %s | cả lần đo trung bình %.1f trung vị %.1f max %.1f'
          % (n, off, q(g['down']), q(g['idle']), q(g['up']), st.mean(allv), st.median(allv), max(allv)))
