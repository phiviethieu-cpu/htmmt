#!/usr/bin/env python3
"""Topo Edge-Cloud cho thí nghiệm FL.

  Mạng biên 10.0.1.0/24                                   Mạng cloud 10.0.2.0/24
  h1..hN --(100M,1ms)-- s1 --(100M,1ms)-- agg (Edge Aggregator, 10.0.1.100)
                         |
                         +--(100M)-- r1 --(BW_WAN, DELAY, LOSS)-- s2 --(100M,1ms)-- cloud (10.0.2.200)
                              Edge Gateway: router + firewall iptables
                              r1-eth0 10.0.1.254, r1-eth1 10.0.2.254

Chạy thử tương tác:  sudo python3 topo.py --n 4 --bw-wan 10 --delay 50ms --loss 1
Chặng WAN là chặng biên-cloud: BW_WAN (Mbps), DELAY (một chiều) và LOSS (% mỗi chiều)
được netem/HTB áp lên cả hai đầu link r1-s2.
"""
import argparse

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import Node, OVSBridge
from mininet.topo import Topo

FL_PORT = 5000


class LinuxRouter(Node):
    """Host Linux bật chuyển tiếp IP, có firewall iptables kiểu stateful."""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")
        # Firewall: mặc định chặn mọi gói đi xuyên router
        self.cmd("iptables -P FORWARD DROP")
        self.cmd("iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")
        # Chỉ cho Edge Node mở kết nối FLSync tới Cloud Server, và cho ping để đo RTT
        self.cmd(f"iptables -A FORWARD -s 10.0.1.0/24 -d 10.0.2.200 -p tcp --dport {FL_PORT} "
                 "-m conntrack --ctstate NEW -j ACCEPT")
        self.cmd("iptables -A FORWARD -p icmp --icmp-type echo-request -j ACCEPT")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


class EdgeCloudTopo(Topo):
    def build(self, n=6, bw_wan=100, wan_delay="20ms", loss=0, queue=200):
        s1 = self.addSwitch("s1")   # Edge Switch
        s2 = self.addSwitch("s2")   # switch phía cloud
        r1 = self.addNode("r1", cls=LinuxRouter, ip="10.0.1.254/24")
        gw_edge, gw_cloud = "via 10.0.1.254", "via 10.0.2.254"
        for i in range(1, n + 1):
            h = self.addHost(f"h{i}", ip=f"10.0.1.{i}/24", defaultRoute=gw_edge)
            self.addLink(h, s1, bw=100, delay="1ms", max_queue_size=queue)
        agg = self.addHost("agg", ip="10.0.1.100/24", defaultRoute=gw_edge)
        cloud = self.addHost("cloud", ip="10.0.2.200/24", defaultRoute=gw_cloud)
        self.addLink(s1, agg, bw=100, delay="1ms", max_queue_size=queue)
        self.addLink(r1, s1, intfName1="r1-eth0", params1={"ip": "10.0.1.254/24"},
                     bw=100, max_queue_size=queue)
        self.addLink(r1, s2, intfName1="r1-eth1", params1={"ip": "10.0.2.254/24"},
                     bw=bw_wan, delay=wan_delay, loss=loss or None, max_queue_size=queue)
        self.addLink(s2, cloud, bw=100, delay="1ms", max_queue_size=queue)


def make_net(**kw):
    # OVSBridge: switch L2 học địa chỉ, không cần controller
    return Mininet(topo=EdgeCloudTopo(**kw), link=TCLink, switch=OVSBridge,
                   autoSetMacs=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--bw-wan", type=float, default=100)
    ap.add_argument("--delay", default="20ms", help="độ trễ một chiều chặng WAN")
    ap.add_argument("--loss", type=float, default=0, help="tỉ lệ mất gói chặng WAN, %%")
    a = ap.parse_args()
    setLogLevel("info")
    net = make_net(n=a.n, bw_wan=a.bw_wan, wan_delay=a.delay, loss=a.loss)
    net.start()
    CLI(net)
    net.stop()
