#!/usr/bin/env python3
"""Mô hình giải tích thời gian một vòng đồng bộ FL qua TCP.

Sinh các file CSV trong thư mục data/ để vẽ biểu đồ "giá trị dự kiến"
trong báo cáo. Khi có số liệu đo thật, đặt file *_measured.csv cạnh
các file này và bật dòng \\addplot tương ứng trong Chuong5.tex.
"""
import csv
import math
import os

MSS = 1448                  # byte, Ethernet MTU 1500 - IP 20 - TCP 32 (có timestamps)
FRAME = 1514                # byte trên dây (L2 header 14 + 1500)
ETA = MSS / FRAME           # hiệu suất tải tin của một khung
IW = 10 * MSS               # cửa sổ khởi đầu 10 MSS (RFC 6928)
T_TRAIN = 1.0               # s, thời gian huấn luyện cục bộ mô phỏng (sleep)
MB = 10 ** 6

# Đường đi trong topo Mininet (độ trễ một chiều mỗi link, ms)
# Edge : h_i -(1ms)- s1 -(1ms)- agg                 -> RTT = 2*(1+1)    = 4 ms
# Cloud: h_i -(1ms)- s1 -(20ms)- s2 -(1ms)- cloud    -> RTT = 2*(1+20+1) = 44 ms
SITES = {
    "edge": {"rtt": 0.004, "bw": 100e6},
    "cloud": {"rtt": 0.044, "bw": 100e6},
    "cloud20": {"rtt": 0.044, "bw": 20e6},
}


def phase_time(n, size, rtt, bw):
    """Thời gian để n luồng TCP song song, mỗi luồng `size` byte, đi hết
    qua một link nghẽn chung băng thông `bw` (bit/s), RTT cơ sở `rtt`.

    Giả thiết: slow start bắt đầu từ IW (kết nối mới hoặc sau idle),
    tổng cửa sổ tăng gấp đôi mỗi RTT tới khi lấp đầy BDP, sau đó link
    chạy ở ETA*bw. Cộng thêm nửa RTT để byte cuối tới đích.
    """
    total = n * size
    bdp = bw * rtt / 8
    k_star = max(0, math.ceil(math.log2(bdp / (n * IW)))) if bdp > n * IW else 0
    sent_ss = n * IW * (2 ** k_star - 1)
    if sent_ss >= total:
        k = math.ceil(math.log2(size / IW + 1))
        return k * rtt + rtt / 2
    return k_star * rtt + (total - sent_ss) * 8 / (ETA * bw) + rtt / 2


def round_time(n, size, site):
    p = SITES[site]
    t_down = phase_time(n, size, p["rtt"], p["bw"])
    t_up = phase_time(n, size, p["rtt"], p["bw"])
    return t_down, t_up, t_down + T_TRAIN + t_up


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(out, exist_ok=True)
    rows = []
    for site in SITES:
        for size_mb in (10, 1):
            for n in range(1, 7):
                t_down, t_up, t_round = round_time(n, size_mb * MB, site)
                rows.append({
                    "site": site, "size_mb": size_mb, "n": n,
                    "t_down": round(t_down, 3), "t_up": round(t_up, 3),
                    "t_comm": round(t_down + t_up, 3),
                    "t_round": round(t_round, 3),
                })
    # Một file cho mỗi (site, size) để pgfplots đọc trực tiếp
    for site in SITES:
        for size_mb in (10, 1):
            name = os.path.join(out, f"model_{site}_{size_mb}MB.csv")
            with open(name, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(r for r in rows if r["site"] == site and r["size_mb"] == size_mb)
    for r in rows:
        print(r)


if __name__ == "__main__":
    main()
