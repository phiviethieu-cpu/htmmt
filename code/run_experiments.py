#!/usr/bin/env python3
"""Chạy toàn bộ kịch bản đo và gom log vào results/.

  sudo python3 run_experiments.py            # tất cả kịch bản
  sudo python3 run_experiments.py --only K1  # một kịch bản
  sudo python3 run_experiments.py --pcap     # kèm tcpdump trên interface của server

Mỗi lần chạy: N client, ROUNDS vòng; song song ping từ h1 tới server để đo RTT khi có tải.
"""
import argparse
import os
import time

from mininet.log import setLogLevel

from topo import make_net

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
ROUNDS = 10
TRAIN = 1.0
MB = 10 ** 6

# (tên, vị trí aggregator, băng thông WAN Mbps, byte tải xuống, byte tải lên)
SCENARIOS = [
    ("K1_edge_full", "agg", 100, 10 * MB, 10 * MB),
    ("K2_edge_comp", "agg", 100, 10 * MB, 1 * MB),
    ("K2_cloud_comp", "cloud", 100, 10 * MB, 1 * MB),
    ("K3_cloud_full", "cloud", 100, 10 * MB, 10 * MB),
    ("K3_cloud20_full", "cloud", 20, 10 * MB, 10 * MB),
]


def run_one(name, where, bw_wan, size_down, size_up, n, pcap):
    net = make_net(n=6, bw_wan=bw_wan)
    net.start()
    # Tắt offload để tcpdump thấy từng đoạn cỡ MSS thay vì gói GSO 64 KB
    for node in net.hosts + net.switches:
        for intf in node.intfList():
            if intf.name != "lo":
                node.cmd(f"ethtool -K {intf.name} tso off gso off gro off")
    try:
        srv = net.get(where)
        ip = srv.IP()
        tag = f"{name}_n{n}"
        log = os.path.join(RES, f"{tag}.csv")
        if pcap:
            # Chỉ lấy 96 byte đầu mỗi gói: đủ header, file pcap nhỏ
            srv.cmd(f"tcpdump -i {srv.defaultIntf()} -s 96 -w {RES}/{tag}.pcap tcp port 5000 &")
            time.sleep(1)
        net.get("h1").cmd(f"ping -i 0.2 {ip} > {RES}/{tag}_ping.txt &")
        srv.cmd(f"cd {HERE} && python3 fl_server.py --clients {n} --rounds {ROUNDS} "
                f"--size {size_down} --train {TRAIN} --out {log} > {RES}/{tag}_srv.txt 2>&1 &")
        time.sleep(1)
        for i in range(1, n + 1):
            net.get(f"h{i}").cmd(f"cd {HERE} && python3 fl_client.py --server {ip} --id {i} "
                                 f"--size {size_up} --train {TRAIN} > /dev/null 2>&1 &")
        # Chờ server ghi đủ ROUNDS dòng
        deadline = time.time() + 600
        while time.time() < deadline:
            if os.path.exists(log) and sum(1 for _ in open(log)) > ROUNDS:
                break
            time.sleep(1)
        print(f"[run] {tag} done", flush=True)
    finally:
        for h in net.hosts:
            h.cmd("pkill -f fl_client.py; pkill -f fl_server.py; pkill ping; pkill tcpdump")
        net.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--pcap", action="store_true")
    a = ap.parse_args()
    os.makedirs(RES, exist_ok=True)
    setLogLevel("warning")
    for sc in SCENARIOS:
        if a.only and not sc[0].startswith(a.only):
            continue
        for n in range(2, 7):
            run_one(*sc, n=n, pcap=a.pcap)


if __name__ == "__main__":
    main()
