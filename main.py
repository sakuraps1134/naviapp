import requests
import pandas as pd
import io
import re
import os
import csv
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

# --- 設定 ---
URLS = {
    "1": "https://raw.githubusercontent.com/sakuraps1134/naviapp/main/20260401_hei.csv",
    "2": "https://raw.githubusercontent.com/sakuraps1134/naviapp/main/20260401_doyo.csv",
    "3": "https://raw.githubusercontent.com/sakuraps1134/naviapp/main/20260401_nichi.csv"
}

API_URL = "https://jik.nishitetsu.jp/jikoku/naviapp/busnavi"
# GitHub Actionsの環境に合わせて並列数を調整（10〜20程度が安定します）
MAX_CONCURRENT_REQUESTS = 15

# 車番の検索範囲
BUS_RANGES = [
    (351, 352, 4), (371, 377, 3), (21, 26, 2), (27, 27, 3), (101, 107, 4),
    (201, 221, 4), (701, 704, 4), (2001, 2006, 4), (2010, 2010, 4), (2101, 2120, 4),
    (2130, 2133, 4), (2260, 2280, 4), (2301, 2301, 4), (2350, 2359, 4), (2401, 2434, 4),
    (2501, 2537, 4), (2601, 2616, 4), (2660, 2701, 4), (2710, 2814, 4), (2830, 2886, 4),
    (2902, 2983, 4), (1001, 1001, 4), (1004, 1112, 4), (1121, 1196, 4), (1237, 1308, 4),
    (1320, 1361, 4), (1440, 1467, 4), (1801, 1826, 4), (1901, 1912, 4), (1913, 1925, 4),
    (3801, 3802, 4), (3901, 3936, 4), (4011, 4026, 4), (4101, 4101, 4), (4201, 4202, 4),
    (4301, 4303, 4), (4401, 4403, 4), (4501, 4505, 4), (4601, 4618, 4), (3630, 3677, 4),
    (4701, 4708, 4), (4720, 4733, 4), (94, 94, 4), (4830, 4880, 4), (3, 4, 4),
    (4905, 4950, 4), (3016, 3069, 4), (3121, 3158, 4), (3201, 3299, 4), (3330, 3351, 4),
    (3420, 3444, 4), (1, 2, 4), (3701, 3710, 4), (5801, 5898, 4), (92, 93, 4),
    (9001, 9147, 4), (9150, 9150, 4), (9201, 9382, 4), (9400, 9537, 4), (9601, 9725, 4),
    (9801, 9960, 4), (5900, 6026, 4), (6050, 6050, 4), (6101, 6265, 4), (6501, 6502, 4),
    (5601, 5706, 4), (5711, 5781, 4), (6701, 6701, 4), (7801, 7802, 4), (7901, 7905, 4),
    (8001, 8001, 4), (8101, 8102, 4), (8201, 8202, 4), (8000, 8014, 4), (8050, 8050, 4),
    (8015, 8017, 4), (8401, 8411, 4), (8501, 8547, 4), (8601, 8606, 4), (7610, 7626, 4),
    (10, 11, 4), (7701, 7753, 4), (7777, 7777, 4), (7801, 7846, 4), (7905, 1947, 4),
    (8017, 8050, 4), (8103, 8140, 4), (8203, 8231, 4), (8301, 8320, 4), (8420, 8441, 4),
    (8550, 8559, 4), (8650, 8658, 4), (8750, 8754, 4), (8801, 8812, 4), (8901, 8902, 4), ("K1141", "K1269", 4), ("K2141", "K2300", 4), ("K9450", "K9450", 4)
]

def get_target_date():
    """日本時間(JST)で日付を取得し、深夜3時までは前日扱いとする"""
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    if now.hour < 3:
        now = now - timedelta(days=1)
    return now.strftime("%Y%m%d")

def fetch_bus_info(bus_no):
    """APIからバスの運行情報を取得"""
    params = {'bus_no': bus_no, 'lang': 'ja', 'site_cd': '0006', 'ver': '3'}
    try:
        # GitHub Actions環境を考慮しタイムアウトを少し長めに設定
        response = requests.get(API_URL, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            data['queried_bus_no'] = bus_no
            return data
    except Exception:
        pass
    return None

def load_master_data():
    """外部の運用マスターCSVを読み込む"""
    master = {}
    for yobi_cd, url in URLS.items():
        try:
            response = requests.get(url)
            response.raise_for_status()
            # 西鉄のCSVに合わせてCP932(Shift-JIS)でデコード
            csv_text = response.content.decode('cp932')
            df = pd.read_csv(io.StringIO(csv_text))
            for col in df.columns:
                clean_col = str(col).strip()
                # 運用番号 {xxxx-x} の抽出
                codes = df[col].dropna().apply(lambda x: re.findall(r'\{(.*?)\}', str(x)))
                for code_list in codes:
                    for code in code_list:
                        master[f"{yobi_cd}_{code}"] = clean_col
        except Exception as e:
            print(f"Error loading {url}: {e}")
    return master

def main():
    target_date = get_target_date()
    master_data = load_master_data()
    
    bus_numbers = []
    for start, end, digits in BUS_RANGES:
        # start や end が文字列（例: "K1141"）の場合の処理
        if isinstance(start, str) or isinstance(end, str):
            # 文字列から数字の部分（例: "1141"）だけを抜き出す
            start_num = int(re.sub(r'\D', '', str(start)))
            end_num = int(re.sub(r'\D', '', str(end)))
            # アルファベット部分（例: "K"）を取得
            prefix = re.match(r'^([a-zA-Z]*)', str(start)).group(1)
            
            for i in range(start_num, end_num + 1):
                # アルファベット + ゼロ埋めした数字 を組み合わせる
                bus_numbers.append(f"{prefix}{str(i).zfill(digits)}")
        else:
            # 通常の数値の場合（これまでの処理）
            for i in range(start, end + 1):
                bus_numbers.append(str(i).zfill(digits))

    new_results = []
    print(f"Fetching data for {len(bus_numbers)} buses (Target Date: {target_date})...")

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        futures = {executor.submit(fetch_bus_info, b_no): b_no for b_no in bus_numbers}
        
        for future in futures:
            data = future.result()
            if data and data.get("response") == "200":
                yobi_cd = data.get("yobi_cd")
                keito_cd = data.get("keito_cd")
                bin_no = data.get("bin_no")
                
                bus_no = data.get("bus_no")
                if not bus_no or str(bus_no).strip() == "":
                    bus_no = data.get("queried_bus_no")
                
                if yobi_cd and keito_cd and bin_no:
                    lookup_key = f"{yobi_cd}_{keito_cd}-{bin_no}"
                    if lookup_key in master_data:
                        new_results.append({
                            "date": target_date,
                            "unyo": master_data[lookup_key],
                            "bus_no": str(bus_no)
                        })

    # 今回の取得結果をDataFrame化
    new_df = pd.DataFrame(new_results).astype(str)

    # --- CSV保存 & マージ処理 ---
    file_path = f"{target_date}.csv"
    if os.path.exists(file_path):
        try:
            existing_df = pd.read_csv(file_path, dtype=str)
            combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=["date", "unyo", "bus_no"])
        except Exception:
            combined_df = new_df
    else:
        combined_df = new_df

    # CSV出力
    combined_df.to_csv(
        file_path, 
        index=False, 
        encoding='utf-8-sig', 
        quoting=csv.QUOTE_NONNUMERIC
    )

    # --- JSON保存処理 (Webアプリ用) ---
    # 常に最新状態を保持する 'latest.json' として出力
    json_file_path = "latest.json"
    combined_df.to_json(
        json_file_path,
        orient='records',
        force_ascii=False,
        indent=4
    )

    print(f"Update complete. CSV: {file_path}, JSON: {json_file_path}")

if __name__ == "__main__":
    main()