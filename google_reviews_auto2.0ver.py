"""
get review 2.0.py

用途：
- 半自動收集 Google Maps 評論資料
- 使用 Selenium 開啟 Chrome
- 使用者手動點進評論分頁
- 程式自動滑動評論區、抓取瀏覽器載入的 listugcposts response
- 整理成 CSV

注意：
- 本程式僅供課堂練習與小規模測試。
- 請勿大量爬取、散布或公開上傳 Google Maps 評論資料。
- 放 GitHub 時，建議只放程式碼，不要放輸出的 CSV 或原始 response。
"""

import json
import time
import re
from pathlib import Path
from urllib.parse import quote

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# =========================
# 基本工具函式
# =========================

def safe_get(data, path, default=None):
    """
    安全取得巢狀 list 裡面的資料。
    例如 safe_get(x, [0, 1, 4, 5, 0])
    """
    try:
        for p in path:
            data = data[p]
        return data
    except Exception:
        return default


def parse_google_response(raw_text):
    """
    Google Maps response 前面通常會有 )]}'
    所以從第一個 [ 開始解析 JSON。
    """
    start = raw_text.find("[")
    if start == -1:
        return None

    try:
        return json.loads(raw_text[start:])
    except Exception:
        return None


def clean_bad_review_text(comment_text):
    """
    如果評論欄位誤抓到網址、business reply/delete URL，就改成 None。
    但不刪掉該筆評論，因為它可能是只有星等、沒有文字。
    """
    if comment_text is None:
        return None

    if not isinstance(comment_text, str):
        return comment_text

    text = comment_text.strip()

    if text == "":
        return None

    bad_patterns = [
        "http",
        "google.com",
        "business.google",
        "/local/business",
        "deletereply",
        "customers/reviews",
        "cb_client",
        "imagery/report",
    ]

    lower_text = text.lower()

    for p in bad_patterns:
        if p.lower() in lower_text:
            return None

    return text


def sanitize_filename(name):
    """
    避免輸出檔名包含 Windows 不允許的符號。
    """
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = name.replace(" ", "_")
    return name if name else "google_reviews"


# =========================
# Selenium driver
# =========================

def make_driver():
    """
    建立 Chrome driver，並開啟 Network log。
    """
    options = Options()
    options.add_argument("--lang=zh-TW")
    options.add_argument("--window-size=1400,1000")

    # 開啟 Network log，之後才能抓 listugcposts response
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    driver.execute_cdp_cmd("Network.enable", {})
    return driver


# =========================
# 解析評論 response
# =========================

def extract_reviews_from_data(data, store_name=None):
    """
    從 Google Maps listugcposts response 裡抽出評論資料。

    重點：
    - 保留只有星等、沒有文字的評論
    - 沒有文字時，「評論」欄位為 None
    - 不再使用「找最長字串」的備援方法，避免把網址誤抓成評論
    """
    rows = []

    raw_items = safe_get(data, [2], [])

    if not isinstance(raw_items, list):
        return rows

    for item in raw_items:
        comment_data = safe_get(item, [0])

        if comment_data is None:
            continue

        review_id = safe_get(item, [0, 0])

        reviewer_name = safe_get(comment_data, [1, 4, 5, 0])
        reviewer_id = safe_get(comment_data, [1, 4, 5, 3])
        reviewer_status = safe_get(comment_data, [1, 4, 5, 10, 0])
        relative_time = safe_get(comment_data, [1, 6])

        # 星等通常在這個位置
        rating = safe_get(comment_data, [2, 0, 0])

        # 評論文字通常在這個位置
        comment_text = safe_get(comment_data, [2, 15, 0, 0])
        comment_text = clean_bad_review_text(comment_text)

        rows.append({
            "店名": store_name,
            "review_id": str(review_id) if review_id is not None else None,
            "評論者": reviewer_name,
            "評論者id": str(reviewer_id) if reviewer_id is not None else None,
            "評論者狀態": reviewer_status,
            "留言時間": relative_time,
            "評論分數": rating,
            "評論": comment_text
        })

    return rows


def get_new_listugcposts_bodies(driver, seen_request_ids):
    """
    從 Chrome Network log 裡抓新的 listugcposts response body。
    """
    bodies = []

    logs = driver.get_log("performance")

    for entry in logs:
        try:
            message = json.loads(entry["message"])["message"]

            if message.get("method") != "Network.responseReceived":
                continue

            params = message.get("params", {})
            response = params.get("response", {})
            url = response.get("url", "")

            if "listugcposts" not in url:
                continue

            request_id = params.get("requestId")

            if request_id in seen_request_ids:
                continue

            seen_request_ids.add(request_id)

            try:
                body_info = driver.execute_cdp_cmd(
                    "Network.getResponseBody",
                    {"requestId": request_id}
                )

                body = body_info.get("body", "")
                bodies.append(body)

                print("抓到一個 listugcposts response，長度：", len(body))

            except Exception as e:
                print("抓 response body 失敗：", e)

        except Exception:
            pass

    return bodies


# =========================
# 自動滑動評論區
# =========================

def scroll_reviews_area(driver, delay=1.5):
    """
    自動滑動 Google Maps 左側評論區。
    Google Maps 的可滑動區塊常常不是 window，而是某個 div。
    """
    driver.execute_script("""
    const scrollables = Array.from(document.querySelectorAll('div'))
      .filter(d => d.scrollHeight > d.clientHeight + 200);

    scrollables.sort((a, b) => b.scrollHeight - a.scrollHeight);

    if (scrollables.length > 0) {
        scrollables[0].scrollTop = scrollables[0].scrollHeight;
    } else {
        window.scrollTo(0, document.body.scrollHeight);
    }
    """)

    time.sleep(delay)


# =========================
# 主流程
# =========================

def collect_google_reviews(store_name, scroll_times=20):
    """
    半自動流程：
    1. 程式開 Google Maps
    2. 使用者手動確認店家、點評論分頁
    3. 程式自動滑動評論區
    4. 程式自動抓 listugcposts response
    5. 合併成 DataFrame
    """
    driver = make_driver()

    url = f"https://www.google.com/maps/search/?api=1&query={quote(store_name)}&hl=zh-TW"
    driver.get(url)

    print("\nChrome 已開啟 Google Maps。")
    print("請在跳出的 Chrome 裡操作：")
    print("1. 確認目前是正確店家或飯店")
    print("2. 點「評論」分頁")
    print("3. 等評論列表出現")
    print("4. 回到這個終端機按 Enter")
    input("\n完成後按 Enter：")

    seen_request_ids = set()
    all_rows = []

    # 先抓一次目前已經載入的 response
    bodies = get_new_listugcposts_bodies(driver, seen_request_ids)

    for body in bodies:
        data = parse_google_response(body)
        if data:
            rows = extract_reviews_from_data(data, store_name=store_name)
            all_rows.extend(rows)
            print("初始 response 解析出", len(rows), "筆評論")

    # 自動滑動 + 抓新的 response
    for round_idx in range(scroll_times):
        print(f"\n========== 第 {round_idx + 1} 輪滑動 ==========")

        scroll_reviews_area(driver, delay=1.5)

        bodies = get_new_listugcposts_bodies(driver, seen_request_ids)

        if not bodies:
            print("這一輪沒有新的 listugcposts response。")
        else:
            for body in bodies:
                data = parse_google_response(body)
                if data:
                    rows = extract_reviews_from_data(data, store_name=store_name)
                    all_rows.extend(rows)
                    print("這個 response 解析出", len(rows), "筆評論")

        print("目前累積評論數：", len(all_rows))

    driver.quit()

    df = pd.DataFrame(all_rows)

    if len(df) > 0:
        # 去重
        if "review_id" in df.columns:
            df = df.drop_duplicates(subset=["review_id"])
        else:
            df = df.drop_duplicates()

        # 不刪掉沒有文字的評論。
        # 只把誤抓到的網址清成 None。
        if "評論" in df.columns:
            url_mask = df["評論"].astype(str).str.contains(
                r"http|google\.com|business\.google|/local/business|deletereply|customers/reviews|cb_client|imagery/report",
                case=False,
                na=False,
                regex=True
            )
            df.loc[url_mask, "評論"] = None

        # 讓 Excel 不要把超長 ID 變成 1.08E+20
        for col in ["review_id", "評論者id"]:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: "'" + str(x) if pd.notna(x) and str(x) != "None" else None)

    return df


# =========================
# 程式入口
# =========================

if __name__ == "__main__":
    print("Google Maps 評論半自動收集工具 2.0")
    print("提醒：請只做課堂練習或小規模測試，不建議大量爬取。")

    store_name = input("\n請輸入店家或飯店名稱：").strip()

    if not store_name:
        store_name = "台北花園大酒店"

    scroll_times_input = input("請輸入要自動滑動幾次，預設 20 次：").strip()

    if scroll_times_input:
        try:
            scroll_times = int(scroll_times_input)
        except ValueError:
            print("輸入不是數字，改用預設 20 次。")
            scroll_times = 20
    else:
        scroll_times = 20

    df = collect_google_reviews(store_name, scroll_times=scroll_times)

    print("\n最後總共整理出", len(df), "筆評論")
    print(df.head())

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    safe_name = sanitize_filename(store_name)
    output_file = output_dir / f"{safe_name}_google_reviews.csv"

    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    print("\n已存成：", output_file)
