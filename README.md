# Federated Learning trên nền tảng Mininet

Tự động hóa đo lường và đánh giá hiệu năng mạng. Bài tập lớn học phần Hệ thống và mạng máy tính (MI4060), Đại học Bách khoa Hà Nội.

## Thư mục

| Đường dẫn | Nội dung |
|---|---|
| `project_htmmt.tex`, `project_htmmt.pdf` | Báo cáo |
| `MoDau/`, `NoiDung/`, `KetThuc/`, `Images/` | Các phần và hình của báo cáo |
| `slide/` | Slide trình bày (Beamer) |
| `code/` | Topo Mininet, giao thức FLSync, server, client, mô hình MLP, script đo |
| `tools/` | Demo, kiểm tra môi trường, script kiểm chứng |
| `data/` | Số liệu tổng hợp dùng cho bảng và biểu đồ |
| `results/` | Log từng lần chạy và file pcap |

## Biên dịch

Báo cáo:

```bash
pdflatex project_htmmt && bibtex project_htmmt && pdflatex project_htmmt && pdflatex project_htmmt
```

Slide, chạy trong thư mục `slide/`:

```bash
lualatex -shell-escape slide_baocao && biber slide_baocao && lualatex -shell-escape slide_baocao
```

## Chạy thí nghiệm

Cần Linux có Mininet 2.3.0, Open vSwitch, Python 3.10 và numpy. Các lệnh chạy từ thư mục gốc.

```bash
sudo python3 tools/demo.py --web                                # demo, xem tại http://localhost:8765
cd code && sudo -E python3 run_experiments.py --group Q1         # Q1, Q2 hoặc K
python3 summarize.py                                             # ghi data/*.csv
```

## Nguồn

Mẫu báo cáo: GraduationThesisTemplate (ledangquangdangquang). Giao diện slide: HUST Beamer Theme (bản fork vanetta).
