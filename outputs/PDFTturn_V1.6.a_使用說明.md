# PDF旋轉吧 / PDFTturn V1.6.a 使用說明

## 執行方式

- 一般執行：`python PDFTturn_V1.6.a_PDF旋轉吧.py`
- Windows 雙擊執行：`PDFTturn_V1.6.a_PDF旋轉吧.pyw`

## 套件需求

程式啟動時會檢查：

- PyMuPDF
- Pillow
- tkinterdnd2

PyMuPDF 與 Pillow 為核心套件。`tkinterdnd2` 用於拖曳 PDF；若未安裝，仍可用「開啟 PDF」或「加入 PDF」按鈕選取檔案。

## 功能分頁

- 頁面移轉：旋轉單頁、全部旋轉、重設、拖曳縮圖調整頁序，輸出 `原檔名_r.pdf`
- 壓縮檔案：調整品質並輸出 `原檔名_comp.pdf`
- 頁面合併：加入多個 PDF、調整順序，輸出 `PDF_mer_YYYYMMDDhhmmss.pdf`
- 頁面編輯：刪除頁面、插入其他 PDF 頁面，輸出 `原檔名_edit.pdf`

## 注意事項

- 壓縮功能會將頁面影像化以降低檔案大小，文字可選取性可能消失。
- 拖曳排序目前以「按住縮圖後放到目標縮圖」的方式調整。
- 已用 `python3 -m py_compile` 完成語法檢查。
