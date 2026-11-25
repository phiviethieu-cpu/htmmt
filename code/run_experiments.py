#!/usr/bin/env python3
"""Chạy batch các kịch bản đo và gom log CSV vào results/.

  sudo python3 run_experiments.py --group K    # số nút N, nén 1/10, Edge/Cloud (đo mạng thuần)
  sudo python3 run_experiments.py --group Q1   # quét băng thông WAN 1-100 Mbps (FedAvg thật)
  sudo python3 run_experiments.py --group Q2   # mất gói 0-5 % và độ trễ WAN (FedAvg thật)
  sudo python3 run_experiments.py --group all --pcap
  FL_RES=/root/flres sudo -E python3 run_experiments.py ...   # đổi thư mục kết quả

Mỗi lần chạy: N client, R vòng; song song ping từ h1 tới server để đo RTT khi có tải.
"""
import argparse
import os
import shlex
import time

from mininet.log import setLogLevel

from topo import make_net

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.abspath(os.environ.get("FL_RES", os.path.join(HERE, "..", "results")))
# Đường dẫn có thể chứa dấu cách: luôn bọc bằng shlex.quote khi ghép vào lệnh shell
Q = shlex.quote
TRAIN = 1.0
MB = 10 ** 6

# Nhóm K (đo mạng thuần, payload giả): (tên, vị trí aggregator, BW WAN, byte xuống, byte lên)
SCENARIOS = [
    ("K1_edge_full", "agg", 100, 10 * MB, 10 * MB),
    ("K2_edge_comp", "agg", 100, 10 * MB, 1 * MB),
    ("K2_cloud_comp", "cloud", 100, 10 * MB, 1 * MB),
    ("K3_cloud_full", "cloud", 100, 10 * MB, 10 * MB),
    ("K3_cloud20_full", "cloud", 20, 10 * MB, 10 * MB),
]

# Nhóm Q1, Q2 (FedAvg thật, mô hình MLP 1,2 MB, N = 4, aggregator đặt tại cloud)
N_FL = 4
Q1_BW = [1, 2, 5, 10, 20, 50, 100]          # Mbps, delay 20 ms, không mất gói
Q2_LOSS = [0, 0.5, 1, 2, 3, 5]              # %, 100 Mbps, delay 20 ms
Q2_DELAY = [5, 20, 50, 100]                 # ms một chiều, kết hợp loss 0 % và 1 %
ROUNDS = {"K": 10, "Q1": 6, "Q2": 20}


def experiments(group):
    """Sinh danh sách (tag, tham số chạy) cho một nhóm."""
    out = []
    if group in ("K", "all"):
        for name, where, bw, down, up in SCENARIOS:
            for n in range(2, 7):
                out.append((f"{name}_n{n}", dict(where=where, bw=bw, delay=20, loss=0, n=n,
                                                 down=down, up=up, fedavg=False, rounds=ROUNDS["K"])))
    if group in ("Q1", "all"):
        for bw in Q1_BW:
            out.append((f"Q1_bw{bw}", dict(where="cloud", bw=bw, delay=20, loss=0, n=N_FL,
                                            fedavg=True, rounds=ROUNDS["Q1"])))
    if group in ("Q2", "all"):
        for p in Q2_LOSS:
            out.append((f"Q2_loss{p}", dict(where="cloud", bw=100, delay=20, loss=p, n=N_FL,
                                             fedavg=True, rounds=ROUNDS["Q2"])))
        for d in Q2_DELAY:
            for p in (0, 1):
                out.append((f"Q2_d{d}_l{p}", dict(where="cloud", bw=100, delay=d, loss=p, n=N_FL,
                                                   fedavg=True, rounds=ROUNDS["Q2"])))
    return out


def run_one(tag, where, bw, delay, loss, n, rounds, fedavg, pcap, down=0, up=0):
    net = make_net(n=6, bw_wan=bw, wan_delay=f"{delay}ms", loss=loss)
    net.start()
    # Tắt offload để tcpdump thấy từng đoạn cỡ MSS thay vì gói GSO 64 KB
    for node in net.hosts + net.switches:
        for intf in node.intfList():
            if intf.name != "lo":
                node.cmd(f"ethtool -K {intf.name} tso off gso off gro off")
    try:
        srv = net.get(where)
        ip = srv.IP()
        log = os.path.join(RES, f"{tag}.csv")
        if os.path.exists(log):
            os.remove(log)
        if pcap:
            # Chỉ lấy 96 byte đầu mỗi gói: đủ header, file pcap nhỏ.
            # Bắt ở hai phía của chặng WAN: giao diện server và giao diện LAN của gateway
            srv.cmd(f"tcpdump -i {srv.defaultIntf()} -s 96 -w {Q(RES)}/{tag}_srv.pcap tcp port 5000 &")
            if where == "cloud":
                net.get("r1").cmd(f"tcpdump -i r1-eth0 -s 96 -w {Q(RES)}/{tag}_r1.pcap tcp port 5000 &")
            time.sleep(1)
        net.get("h1").cmd(f"ping -i 0.2 {ip} > {Q(RES)}/{tag}_ping.txt &")
        env = "OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1"
        mode = "--fedavg" if fedavg else f"--size {down}"
        srv.cmd(f"cd {Q(HERE)} && {env} python3 fl_server.py --clients {n} --rounds {rounds} "
                f"{mode} --train {TRAIN} --out {Q(log)} > {Q(RES)}/{tag}_srv.txt 2>&1 &")
        time.sleep(1)
        for i in range(1, n + 1):
            mode = f"--fedavg --clients {n}" if fedavg else f"--size {up}"
            net.get(f"h{i}").cmd(f"cd {Q(HERE)} && {env} python3 fl_client.py --server {ip} --id {i} "
                                 f"{mode} --train {TRAIN} > {Q(RES)}/{tag}_h{i}.txt 2>&1 &")
        # Chờ server ghi đủ số vòng (dòng header + rounds dòng)
        t0 = time.time()
        while time.time() - t0 < 3600:
            if os.path.exists(log) and sum(1 for _ in open(log)) > rounds:
                break
            time.sleep(1)
        print(f"[run] {tag} done in {time.time() - t0:.0f} s", flush=True)
    finally:
        for h in net.hosts:
            h.cmd("pkill -f fl_client.py; pkill -f fl_server.py; pkill ping; pkill tcpdump")
        net.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="all", choices=["K", "Q1", "Q2", "all"])
    ap.add_argument("--only", default="", help="chỉ chạy các tag bắt đầu bằng chuỗi này")
    ap.add_argument("--pcap", action="store_true")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    setLogLevel("warning")
    for tag, kw in experiments(a.group):
        if a.only and not tag.startswith(a.only):
            continue
        run_one(tag, pcap=a.pcap, **kw)


if __name__ == "__main__":
    main()
