#!/usr/bin/env python3
"""Dựng topo như topo.py, tắt TSO/GSO/GRO như run_experiments.py, rồi mở Mininet CLI để kiểm tra môi trường.

  sudo python3 tools/sanity.py --bw-wan 100
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "code"))

from mininet.cli import CLI
from mininet.log import setLogLevel

from topo import make_net

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=6)
ap.add_argument("--bw-wan", type=float, default=100)
a = ap.parse_args()

# Lúc dựng mạng chỉ in lỗi nghiêm trọng (bỏ cảnh báo quantum của HTB), sau đó trả về mức output cho CLI
setLogLevel("critical")
net = make_net(n=a.n, bw_wan=a.bw_wan)
net.start()
for node in net.hosts + net.switches:
    for intf in node.intfList():
        if intf.name != "lo":
            node.cmd(f"ethtool -K {intf.name} tso off gso off gro off")
setLogLevel("output")
print(f"*** Topo Edge-Cloud: {a.n} Edge Node, WAN {a.bw_wan:g} Mbps, offload tắt")
CLI(net)
net.stop()
