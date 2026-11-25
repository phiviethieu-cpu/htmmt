sudo apt install mininet openvswitch-switch tcpdump wireshark ethtool iperf python3-pip
sudo pip3 install numpy          # model.py: mạng nơ-ron MLP
# Kiểm tra nhanh: hai link, mỗi link 20 ms -> RTT khoảng 80 ms
sudo mn --link tc,bw=10,delay=20ms,loss=1
mininet> h1 ping -c 5 h2
mininet> exit
# Kiểm tra mô hình học máy (FedAvg cục bộ, không qua mạng)
cd code
python3 model.py                # đạt 90% ở vòng 14
# Kiểm tra topo của đề tài
sudo python3 topo.py --n 6 --bw-wan 10 --delay 20ms --loss 1
mininet> h1 ping -c 5 agg       # khoảng 4 ms
mininet> h1 ping -c 5 cloud     # khoảng 44 ms
mininet> iperf h1 agg           # khoảng 95 Mbps
