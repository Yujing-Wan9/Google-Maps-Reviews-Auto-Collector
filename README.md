# Google Maps Reviews Auto Collector 

這是一個用於課堂練習與資料蒐集測試的 Google Maps 評論半自動收集工具。

本工具使用 Selenium 開啟 Google Maps 頁面，讓使用者手動確認店家並點擊評論分頁，接著由程式自動滑動評論區，擷取瀏覽器載入的 `listugcposts` response，並整理成 CSV 表格。

> ⚠️ 本專案僅供課堂練習與技術學習用途，請勿用於大量爬取、商業用途或公開散布 Google Maps 評論資料。

---

## 專案功能

- 以店家或飯店名稱開啟 Google Maps 搜尋結果
- 使用者手動確認正確店家並點擊評論分頁
- 程式自動滑動評論區
- 自動擷取 Google Maps 動態載入的評論 response
- 將評論整理成 CSV
- 保留只有星等、沒有文字的評論
- 避免將網址誤判為評論內容
- 輸出欄位包含：
  - 店名
  - review_id
  - 評論者
  - 評論者id
  - 評論者狀態
  - 留言時間
  - 評論分數
  - 評論

---

## 專案結構

```text
.
├── google_reviews_auto2.0ver.py
├── requirements.txt
├── README.md
├── .gitignore
└── output/
