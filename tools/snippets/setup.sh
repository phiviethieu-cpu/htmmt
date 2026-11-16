sudo apt install mininet openvswitch-switch tcpdump wireshark ethtool iperf
# Kiểm tra nhanh: hai link, mỗi link 20 ms -> RTT khoảng 80 ms
sudo mn --link tc,bw=10,delay=20ms
mininet> h1 ping -c 5 h2
mininet> exit
# Kiểm tra topo của đề tài
cd code
sudo python3 topo.py --n 6
mininet> h1 ping -c 5 agg       # khoảng 4 ms
mininet> h1 ping -c 5 cloud     # khoảng 44 ms
mininet> iperf h1 agg           # khoảng 95 Mbps
# Chạy toàn bộ kịch bản, gom số liệu
sudo python3 run_experiments.py --pcap
python3 summarize.py
python3 model.py                # sinh lại số liệu mô hình nếu đổi tham số
