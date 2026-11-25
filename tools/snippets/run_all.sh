cd code
export FL_RES=/root/flres                         # ghi kết quả trên ổ đĩa của WSL
sudo -E python3 run_experiments.py --group Q1         # 7 mức băng thông
sudo -E python3 run_experiments.py --group Q2 --pcap  # 14 cấu hình mất gói, độ trễ
sudo -E python3 run_experiments.py --group K          # 25 lần chạy N, nén, Edge/Cloud
python3 summarize.py            # data/q1_bw.csv, q2_*.csv, measured_*.csv
python3 pcap_overhead.py        # data/q3_overhead.csv
